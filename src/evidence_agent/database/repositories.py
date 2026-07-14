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


def derive_task_status(task_id: str) -> str:
    """Derive task status from claims review state across all runs.

    Rules:
    - Any pending / needs_followup claim → review
    - All successful claims terminal → completed
    - All runs failed → failed
    - Some success, some failed → based on successful claims
    - 0 claims on success → completed
    """
    with get_connection(read_only=True) as conn:
        cursor = conn.execute(
            "SELECT run_id, status FROM processing_runs WHERE task_id = ?",
            (task_id,),
        )
        runs = [(r["run_id"], r["status"]) for r in cursor.fetchall()]

        if not runs:
            return "running"

        all_failed = all(status == "failed" for _, status in runs)
        if all_failed:
            return "failed"

        cursor = conn.execute(
            "SELECT c.record_review_status "
            "FROM source_claims c "
            "JOIN processing_runs r ON c.created_by_run_id = r.run_id "
            "WHERE r.task_id = ?",
            (task_id,),
        )
        statuses = [r["record_review_status"] for r in cursor.fetchall()]

        if not statuses:
            return "completed"

        pending_states = {"pending", "needs_followup"}
        terminal_states = {"approved", "approved_with_edits", "rejected"}

        any_pending = any(s in pending_states for s in statuses)
        all_terminal = all(s in terminal_states for s in statuses)

        if any_pending:
            return "review"
        if all_terminal:
            return "completed"

        return "review"


def refresh_task_status(task_id: str) -> str:
    """Derive and update task status. Returns the new status."""
    status = derive_task_status(task_id)
    update_task_status(task_id, status)
    return status
