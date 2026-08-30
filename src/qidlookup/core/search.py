"""Free-text search over event name, description, and category."""

from __future__ import annotations

from qidlookup.config.settings import DEFAULT_SEARCH_LIMIT
from qidlookup.core.models import Mapping
from qidlookup.database.repository import MappingRepository


class SearchService:
    """Case-insensitive substring search across mapping text fields."""

    def __init__(self, repository: MappingRepository) -> None:
        self._repo = repository

    def search(
        self,
        term: str,
        device_type: int | None = None,
        category: str | None = None,
        low_level_category: str | None = None,
        high_level_category: str | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        offset: int = 0,
    ) -> list[Mapping]:
        """Search event_name, description, category, and LLC/HLC for ``term``.

        Results are paginated via ``limit``/``offset`` so a broad query
        against a multi-million-row database stays bounded.
        """
        if not term or not term.strip():
            return []
        return self._repo.search(
            term.strip(),
            device_type=device_type,
            category=category,
            low_level_category=low_level_category,
            high_level_category=high_level_category,
            limit=limit,
            offset=offset,
        )
