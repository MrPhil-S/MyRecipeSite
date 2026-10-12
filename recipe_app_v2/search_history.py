"""Recent, distinct searches; persistence requires an explicit search action."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_write_engine, writes_enabled
from .models import Query_History


def recent_searches(session, query=''):
    term = func.trim(Query_History.query_text)
    ranked = select(
        term.label('query'), Query_History.query_dt.label('searched_at'),
        Query_History.query_history_id.label('id'),
        func.row_number().over(partition_by=func.lower(term), order_by=(
            Query_History.query_dt.desc(), Query_History.query_history_id.desc())).label('position')
    ).where(term != '')
    if query.strip():
        ranked = ranked.where(func.lower(term).contains(query.strip().lower(), autoescape=True))
    rows = ranked.subquery()
    return session.scalars(select(rows.c.query).where(rows.c.position == 1).order_by(
        rows.c.searched_at.desc(), rows.c.id.desc()).limit(10)).all()


def remember_search(query, result_count):
    query = query.strip()
    if not query:
        return None
    # Never truncate a query into a partial search to fit the legacy column.
    if len(query) > 100:
        return 'This search is too long to save in history.'
    if result_count <= 1:
        return None
    if not writes_enabled():
        return 'Search history saving is disabled.'
    with Session(get_write_engine(), autoflush=False) as session:
        # Preserve the legacy append-only history. The read query deduplicates
        # suggestions, and the new ID breaks ties for searches in the same second.
        session.add(Query_History(query_text=query))
        session.commit()
    return None
