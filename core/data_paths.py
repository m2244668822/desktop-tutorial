#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path


def resolve_data_root(base_dir: str | Path) -> Path:
    """Resolve workspace data root across symlink/junction/plain-folder layouts."""
    workspace = Path(base_dir).expanduser().resolve()
    primary = workspace / "data"
    fallback = workspace / "data_hdd_storage"

    if primary.is_dir():
        return primary
    if fallback.is_dir():
        return fallback

    # If primary exists but is not a directory (for example a plain text file),
    # prefer fallback so callers can still recover gracefully.
    if primary.exists() and not primary.is_dir():
        return fallback

    return primary


def is_link_like(path: Path) -> bool:
    """Return True for symlink/junction-style paths."""
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction):
        try:
            return bool(is_junction())
        except Exception:
            return False
    return False


class ProjectPaths:
    """Centralized path management for the AI Agent system."""

    def __init__(self, root: str | Path | None = None):
        if root is None:
            # Try to resolve from environment or current file location
            env_root = os.environ.get("AGENT_WORKSPACE_ROOT")
            if env_root:
                self.root = Path(env_root).expanduser().resolve()
            else:
                # Default to the parent of the 'core' directory
                self.root = Path(__file__).resolve().parent.parent
        else:
            self.root = Path(root).expanduser().resolve()

        # Core directories
        self.data = resolve_data_root(self.root)
        self.config = self.root / "config"
        self.logs = self.root / "logs"
        self.templates = self.root / "templates"
        self.reports = self.root / "reports"
        self.tools = self.root / "tools"
        self.core = self.root / "core"
        self.uploads = self.root / "uploads"
        self.archive = self.root / "archive"

        # Legacy / Sub-project paths
        self.llama = self.root / "500" / "llama32-chat"
        self.llama_data = self.llama / "data"
        self.llama_logs = self.llama / "logs"
        self.llama_config = self.llama / "config"

        # Specific file paths (commonly used)
        self.env_main = self.llama / ".env"
        self.env_candidates = [
            self.root / ".env",
            self.llama / ".env",
            self.llama_config / ".env",
        ]
        
        self.catalog_json = self.data / "open_source_agent_catalog.json"
        self.knowledge_manifest = self.data / "knowledge_hub" / "manifest.json"
        self.memory_db = self.data / "knowledge_hub" / "memory_layers" / "memory.sqlite3"
        self.faiss_index = self.data / "knowledge_hub" / "memory_layers" / "long_term.faiss"

    def ensure_dirs(self):
        """Ensure critical directories exist."""
        for d in [self.config, self.logs, self.reports, self.uploads, self.archive]:
            d.mkdir(parents=True, exist_ok=True)
        (self.data / "knowledge_hub" / "notes").mkdir(parents=True, exist_ok=True)
        (self.logs / "workflow_runs").mkdir(parents=True, exist_ok=True)

    def __repr__(self):
        return f"ProjectPaths(root={self.root})"
