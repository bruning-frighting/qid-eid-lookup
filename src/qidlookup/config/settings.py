"""Runtime configuration for qidlookup.

Resolves the active database path and other tunables from, in order of
precedence: explicit CLI argument > environment variable > default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENV_DATABASE_VAR = "QIDLOOKUP_DATABASE"

# Default database path is resolved relative to the package's project root
# (two levels above src/qidlookup/config), NOT the current working directory,
# so the tool behaves consistently regardless of where it's invoked from.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = _PROJECT_ROOT / "data" / "qid_eid.db"

DEFAULT_SEARCH_LIMIT = 100
DEFAULT_BATCH_SIZE = 5000


@dataclass(frozen=True)
class Settings:
    """Resolved application settings for a single CLI invocation."""

    database_path: Path
    verbose: bool = False
    no_color: bool = False

    @classmethod
    def resolve(
        cls,
        database: str | None = None,
        verbose: bool = False,
        no_color: bool = False,
    ) -> "Settings":
        """Resolve settings from CLI overrides, falling back to env/defaults."""
        if database:
            db_path = Path(database)
        else:
            env_value = os.environ.get(ENV_DATABASE_VAR)
            db_path = Path(env_value) if env_value else DEFAULT_DATABASE_PATH
        return cls(database_path=db_path, verbose=verbose, no_color=no_color)
