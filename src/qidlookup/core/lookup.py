"""QID <-> EID lookup service.

This is the business-logic layer: it knows nothing about SQL (that lives
in :mod:`qidlookup.database.repository`) and nothing about argument
parsing or terminal output (that lives in the CLI). It never assumes a
QID or EID maps to exactly one counterpart -- every lookup returns a
list, which may be empty (not found), contain one entry, or contain many
(e.g. the same QID mapped across several device types/categories).
"""

from __future__ import annotations

from collections.abc import Sequence

from qidlookup.core.models import Mapping
from qidlookup.database.repository import MappingRepository


class LookupService:
    """Looks up mappings by QID or EID, single or batch."""

    def __init__(self, repository: MappingRepository) -> None:
        self._repo = repository

    def lookup_qid(self, qid: int, device_type: int | None = None) -> list[Mapping]:
        """Return all mappings for a single QID (possibly empty)."""
        return self._repo.find_by_qid(qid, device_type=device_type)

    def lookup_eid(self, eid: str, device_type: int | None = None) -> list[Mapping]:
        """Return all mappings for a single EID (possibly empty)."""
        return self._repo.find_by_eid(eid, device_type=device_type)

    def lookup_by_category(
        self,
        low_level_category: str | None = None,
        high_level_category: str | None = None,
        device_type: int | None = None,
    ) -> list[Mapping]:
        """Return all mappings under a QRadar Low/High Level Category.

        At least one of ``low_level_category``/``high_level_category`` must
        be given. A single category commonly spans multiple QIDs and EIDs
        (e.g. "System > Process Creation Success" maps to several Sysmon/
        Windows/EDR QIDs, each with its own EID) -- all of them are
        returned, never collapsed to one answer.
        """
        return self._repo.find_by_category(
            low_level_category=low_level_category,
            high_level_category=high_level_category,
            device_type=device_type,
        )

    def lookup_qids(
        self, qids: Sequence[int], device_type: int | None = None
    ) -> dict[int, list[Mapping]]:
        """Look up multiple QIDs at once.

        Returns a dict preserving the input order, mapping each requested
        QID to its list of Mapping results (empty list if not found).
        Duplicate QIDs in the input are deduplicated in the result keys
        but every requested value is represented.
        """
        unique_qids = list(dict.fromkeys(qids))
        found = self._repo.find_by_qids(unique_qids, device_type=device_type)

        by_qid: dict[int, list[Mapping]] = {qid: [] for qid in unique_qids}
        for mapping in found:
            by_qid.setdefault(mapping.qid, []).append(mapping)
        return by_qid

    def lookup_eids(
        self, eids: Sequence[str], device_type: int | None = None
    ) -> dict[str, list[Mapping]]:
        """Look up multiple EIDs at once.

        Returns a dict preserving the input order, mapping each requested
        EID to its list of Mapping results (empty list if not found).
        """
        unique_eids = list(dict.fromkeys(eids))
        found = self._repo.find_by_eids(unique_eids, device_type=device_type)

        by_eid: dict[str, list[Mapping]] = {eid: [] for eid in unique_eids}
        for mapping in found:
            by_eid.setdefault(mapping.eid, []).append(mapping)
        return by_eid
