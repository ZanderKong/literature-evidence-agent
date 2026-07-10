"""Configuration management for the Literature Evidence Agent."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""

    def __init__(self) -> None:
        # Workspace
        self.workspace_path = Path(
            os.getenv("EVIDENCE_AGENT_WORKSPACE", "workspace")
        ).resolve()

        # Database
        db_rel = os.getenv("EVIDENCE_AGENT_DB_PATH", "external_evidence/evidence.sqlite")
        self.db_path = self.workspace_path / db_rel

        # LLM Provider
        self.llm_provider = os.getenv("EVIDENCE_AGENT_LLM_PROVIDER", "mock")
        self.llm_model = os.getenv("EVIDENCE_AGENT_LLM_MODEL", "")
        self.llm_api_key = os.getenv("EVIDENCE_AGENT_LLM_API_KEY", "")
        self.llm_api_base = os.getenv("EVIDENCE_AGENT_LLM_API_BASE", "")

        # Limits
        self.max_file_size = int(
            os.getenv("EVIDENCE_AGENT_MAX_FILE_SIZE", str(100 * 1024 * 1024))
        )

        # Derived paths
        self.sources_dir = self.workspace_path / "external_evidence" / "sources"
        self.review_dir = self.workspace_path / "external_evidence" / "review"
        self.exports_dir = self.workspace_path / "external_evidence" / "exports"
        self.logs_dir = self.workspace_path / "external_evidence" / "logs"
        self.backups_dir = self.workspace_path / "external_evidence" / "backups"

    def ensure_directories(self) -> None:
        """Create all required directories if they don't exist."""
        for d in [
            self.db_path.parent,
            self.sources_dir,
            self.review_dir,
            self.exports_dir,
            self.logs_dir,
            self.backups_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)


# Global config instance
config = Config()
