"""Read-only dev schema and recipe-card audit. Run: ``python -m tools.verify_dev``."""
import json

from sqlalchemy import UniqueConstraint, func, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError

from recipe_app_v2.config import app_environment
from recipe_app_v2.database import get_engine
from recipe_app_v2.models import Base, Recipe


def expected_local_recorded_dt_extra(table_name, column_name, column):
    """Recognize only the documented local migration's extra timestamp column."""
    return (
        table_name == 'recipe_cooked_date'
        and column_name == 'recorded_dt'
        and str(column['type']).strip().upper() in ('DATETIME', 'TIMESTAMP')
        and column['nullable'] is False
        and column['default'] is not None
        and str(column['default']).strip().upper() in (
            'CURRENT_TIMESTAMP', 'CURRENT_TIMESTAMP()'
        )
    )


def verify():
    if app_environment() != 'dev':
        raise RuntimeError('The dev audit requires the development environment before connecting.')
    engine = get_engine()
    differences = []
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT DATABASE()")) == "MyRecipes_DEV"
        assert conn.scalar(text("SELECT @@session.tx_read_only")) == 1
        inspector = inspect(conn)
        for table in Base.metadata.sorted_tables:
            actual = {col["name"]: col for col in inspector.get_columns(table.name)}
            expected = {col.name: col for col in table.columns}
            extras = set(actual) - set(expected)
            expected_extras = {
                name for name in extras
                if expected_local_recorded_dt_extra(table.name, name, actual[name])
            }
            if (set(actual) - expected_extras) != set(expected):
                differences.append(f"{table.name}: column names differ")
            for name in set(actual) & set(expected):
                model_col, db_col = expected[name], actual[name]
                actual_type = str(db_col["type"]).upper()
                expected_type = str(model_col.type).upper()
                if actual_type != expected_type and not (
                    expected_type == "BOOLEAN" and actual_type == "TINYINT"
                ) and not (expected_type == "INTEGER" and actual_type == "INTEGER"):
                    differences.append(f"{table.name}.{name}: {expected_type} vs {actual_type}")
                if model_col.nullable != db_col["nullable"]:
                    differences.append(f"{table.name}.{name}: nullability differs")
            primary = inspector.get_pk_constraint(table.name)["constrained_columns"]
            if set(primary) != {c.name for c in table.primary_key.columns}:
                differences.append(f"{table.name}: primary key differs")
            actual_fks = {
                (tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]),
                 fk.get("options", {}).get("ondelete"))
                for fk in inspector.get_foreign_keys(table.name)
            }
            expected_fks = {
                (tuple(c.name for c in fk.columns), fk.referred_table.name,
                 tuple(e.column.name for e in fk.elements), fk.ondelete)
                for fk in table.foreign_key_constraints
            }
            if actual_fks != expected_fks:
                differences.append(f"{table.name}: foreign keys differ")
            actual_unique = {tuple(c["column_names"]) for c in inspector.get_unique_constraints(table.name)}
            expected_unique = {tuple(c.name for c in constraint.columns)
                               for constraint in table.constraints if isinstance(constraint, UniqueConstraint)}
            if actual_unique != expected_unique:
                differences.append(f"{table.name}: unique constraints differ")
            for name, column in actual.items():
                if column["default"] is not None and not expected_local_recorded_dt_extra(table.name, name, column):
                    differences.append(f"{table.name}: unexpected server default on {name} requires review")
        count = conn.scalar(select(func.count()).select_from(Recipe))
        top_ids = list(conn.scalars(select(Recipe.recipe_id).order_by(Recipe.create_dt.desc(), Recipe.recipe_id.desc()).limit(24)))
        print(json.dumps({"database": "MyRecipes_DEV", "read_only": True,
                          "recipes": count, "mapped_tables": len(Base.metadata.tables),
                          "schema_differences": differences, "first_page_ids": top_ids}, indent=2))
    return differences


if __name__ == "__main__":
    try:
        issues = verify()
    except SQLAlchemyError as exc:
        print("Dev verification failed:", type(exc).__name__)
        raise SystemExit(1) from None
    raise SystemExit(bool(issues))
