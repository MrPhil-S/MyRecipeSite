from functools import lru_cache
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import app_environment, database_url


class ReadOnlySession(Session):
    pass


@event.listens_for(ReadOnlySession, "before_flush")
def prevent_flush(session, flush_context, instances):
    raise RuntimeError("Read-only browsing sessions do not allow database writes.")


def guard_statement(conn, cursor, statement, parameters, context, executemany):
    # Application SQL is SELECT only. In particular, block DDL, DML and SET
    # statements that could override the server-side read-only setting.
    if not statement.lstrip().upper().startswith(("SELECT ", "SHOW ", "DESCRIBE ")):
        raise RuntimeError("Only read queries are allowed in browsing sessions.")


@lru_cache(maxsize=1)
def get_engine():
    engine = create_engine(
        database_url(), pool_pre_ping=True, pool_recycle=300,
        connect_args={"connect_timeout": 5, "read_timeout": 15, "write_timeout": 5},
    )

    @event.listens_for(engine, "connect")
    def read_only_connection(dbapi_connection, connection_record):
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")

    event.listen(engine, "before_cursor_execute", guard_statement)
    return engine


def get_session():
    factory = sessionmaker(bind=get_engine(), class_=ReadOnlySession, autoflush=False)
    with factory() as session:
        try:
            yield session
        finally:
            session.rollback()


def writes_enabled():
    variable = 'RECIPE_PROD_WRITES' if app_environment() == 'production' else 'RECIPE_DEV_WRITES'
    return os.environ.get(variable, '0') == '1'


@lru_cache(maxsize=1)
def get_write_engine():
    # A separate pool prevents a save from changing read-only browse sessions.
    if not writes_enabled():
        raise RuntimeError('Recipe saves are disabled.')
    engine = create_engine(database_url(), pool_pre_ping=True, pool_recycle=300,
        isolation_level='READ COMMITTED',
        connect_args={'connect_timeout': 5, 'read_timeout': 15, 'write_timeout': 15})

    @event.listens_for(engine, 'connect')
    def writable_connection(connection, record):
        with connection.cursor() as cursor:
            cursor.execute('SET SESSION TRANSACTION READ WRITE')

    return engine
