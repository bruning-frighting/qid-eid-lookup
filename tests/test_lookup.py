"""Tests for qidlookup.core.lookup.LookupService."""

from __future__ import annotations

from qidlookup.core.lookup import LookupService

from conftest import SAMPLE_MAPPINGS, seed


def test_lookup_qid_exists(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = LookupService(repo).lookup_qid(5000843)
    assert len(results) == 1
    assert results[0].eid == "4656"


def test_lookup_qid_not_found(repo):
    seed(repo, SAMPLE_MAPPINGS)
    assert LookupService(repo).lookup_qid(99999999) == []


def test_lookup_eid_exists(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = LookupService(repo).lookup_eid("4663")
    assert len(results) == 1
    assert results[0].qid == 5000850


def test_lookup_eid_not_found(repo):
    seed(repo, SAMPLE_MAPPINGS)
    assert LookupService(repo).lookup_eid("99999") == []


def test_lookup_qid_multiple_mappings(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = LookupService(repo).lookup_qid(5000849)
    assert len(results) == 2
    categories = {m.event_category for m in results}
    assert categories == {"Success Audit", "Object Access"}


def test_lookup_qids_batch_preserves_order_and_not_found(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = LookupService(repo).lookup_qids([5000843, 99999999, 5000850])

    assert list(results.keys()) == [5000843, 99999999, 5000850]
    assert len(results[5000843]) == 1
    assert results[99999999] == []
    assert len(results[5000850]) == 1


def test_lookup_eids_batch_preserves_order_and_not_found(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = LookupService(repo).lookup_eids(["4656", "00000", "4663"])

    assert list(results.keys()) == ["4656", "00000", "4663"]
    assert len(results["4656"]) == 1
    assert results["00000"] == []
    assert len(results["4663"]) == 1


def test_lookup_qids_does_not_lose_duplicate_mappings(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = LookupService(repo).lookup_qids([5000849])
    assert len(results[5000849]) == 2


def test_lookup_qid_with_device_type_filter(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = LookupService(repo).lookup_qid(5000849, device_type=12)
    assert len(results) == 1
    assert results[0].devicetypeid == 12


def test_lookup_by_category_low_level_only(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = LookupService(repo).lookup_by_category(
        low_level_category="Process Creation Success"
    )
    assert {m.qid for m in results} == {5000849}
    assert len(results) == 2  # two device-type rows for the same QID


def test_lookup_by_category_high_level_only(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = LookupService(repo).lookup_by_category(high_level_category="System")
    assert {m.qid for m in results} == {5000849}


def test_lookup_by_category_low_and_high_combined(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = LookupService(repo).lookup_by_category(
        low_level_category="Object Access Success", high_level_category="Access"
    )
    assert len(results) == 1
    assert results[0].qid == 5000850


def test_lookup_by_category_mismatched_low_and_high_returns_empty(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = LookupService(repo).lookup_by_category(
        low_level_category="Process Creation Success", high_level_category="Access"
    )
    assert results == []


def test_lookup_by_category_not_found(repo):
    seed(repo, SAMPLE_MAPPINGS)
    assert LookupService(repo).lookup_by_category(low_level_category="No Such Category") == []


def test_lookup_by_category_requires_at_least_one_filter(repo):
    seed(repo, SAMPLE_MAPPINGS)
    assert LookupService(repo).lookup_by_category() == []
