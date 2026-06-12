"""Session history business logic."""

from data.kb_store import list_sessions, load_session, delete_session


def list_all() -> list[dict]:
    return list_sessions()


def get_detail(session_id: str) -> dict | None:
    return load_session(session_id)


def delete(session_id: str) -> bool:
    return delete_session(session_id)
