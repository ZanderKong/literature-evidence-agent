"""Research task CLI and database operations."""

from typing import Any

from evidence_agent.database.connection import get_connection
from evidence_agent.ids import generate_task_id, now_iso


def create_task(
    title: str,
    user_request: str,
    background: str | None = None,
    mode: str = "analyse_uploaded",
    depth: str = "task_focused",
) -> dict[str, Any]:
    """Create a new research task in the database."""
    valid_modes = {"analyse_uploaded", "source_complete_analysis", "evidence_query"}
    valid_depths = {"task_focused", "source_complete"}

    if mode not in valid_modes:
        raise ValueError(f"Invalid mode: {mode}. Must be one of {valid_modes}")
    if depth not in valid_depths:
        raise ValueError(
            f"Invalid depth: {depth}. Must be one of {valid_depths}"
        )

    task_id = generate_task_id()
    now = now_iso()

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO research_tasks (task_id, title, user_request, "
            "research_background, task_mode, analysis_depth, status, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'created', ?, ?)",
            (task_id, title, user_request, background, mode, depth, now, now),
        )

    return {
        "task_id": task_id,
        "title": title,
        "user_request": user_request,
        "task_mode": mode,
        "analysis_depth": depth,
        "status": "created",
        "created_at": now,
    }


def get_task(task_id: str) -> dict[str, Any] | None:
    """Get a task by ID."""
    with get_connection(read_only=True) as conn:
        cursor = conn.execute(
            "SELECT * FROM research_tasks WHERE task_id = ?", (task_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)


def list_tasks(status: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """List tasks, optionally filtered by status."""
    with get_connection(read_only=True) as conn:
        if status:
            cursor = conn.execute(
                "SELECT * FROM research_tasks WHERE status = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM research_tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return [dict(row) for row in cursor.fetchall()]


def update_task_status(task_id: str, status: str) -> None:
    """Update task status and updated_at timestamp."""
    valid_statuses = {"created", "running", "review", "completed", "failed"}
    if status not in valid_statuses:
        raise ValueError(
            f"Invalid task status: '{status}'. Must be one of {valid_statuses}"
        )
    with get_connection() as conn:
        conn.execute(
            "UPDATE research_tasks SET status = ?, updated_at = ? WHERE task_id = ?",
            (status, now_iso(), task_id),
        )
