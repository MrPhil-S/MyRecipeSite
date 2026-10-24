"""Rules for correcting a recently recorded cooking event."""
from datetime import timedelta


UNDO_WINDOW = timedelta(hours=24)


def can_undo_cooked(cooked_at, now):
    if cooked_at is None:
        return False
    age = now - cooked_at
    return timedelta(0) <= age < UNDO_WINDOW
