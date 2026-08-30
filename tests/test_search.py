"""Tests for qidlookup.core.search.SearchService."""

from __future__ import annotations

from qidlookup.core.search import SearchService

from conftest import SAMPLE_MAPPINGS, seed


def test_search_case_insensitive(repo):
    seed(repo, SAMPLE_MAPPINGS)
    lower = SearchService(repo).search("operation was performed")
    upper = SearchService(repo).search("OPERATION WAS PERFORMED")
    mixed = SearchService(repo).search("Operation Was Performed")
    assert len(lower) == len(upper) == len(mixed) == 2


def test_search_partial_matching(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = SearchService(repo).search("handle to an object")
    assert len(results) == 1
    assert results[0].qid == 5000843


def test_search_matches_description_and_category_too(repo):
    seed(repo, SAMPLE_MAPPINGS)
    by_category = SearchService(repo).search("process tracking")
    assert len(by_category) == 1
    assert by_category[0].qid == 5000001


def test_search_no_results(repo):
    seed(repo, SAMPLE_MAPPINGS)
    assert SearchService(repo).search("no such event anywhere") == []


def test_search_empty_term_returns_empty(repo):
    seed(repo, SAMPLE_MAPPINGS)
    assert SearchService(repo).search("   ") == []


def test_search_limit_is_respected(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = SearchService(repo).search("object", limit=1)
    assert len(results) == 1


def test_search_device_type_filter(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = SearchService(repo).search("operation was performed", device_type=15)
    assert len(results) == 1
    assert results[0].devicetypeid == 15


def test_search_category_filter(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = SearchService(repo).search("object", category="Object Access")
    assert len(results) == 1
    assert results[0].event_category == "Object Access"


def test_search_matches_low_level_category_text(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = SearchService(repo).search("process creation success")
    assert len(results) == 2
    assert all(m.low_level_category == "Process Creation Success" for m in results)


def test_search_matches_high_level_category_text(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = SearchService(repo).search("system")
    assert {m.qid for m in results} == {5000849}


def test_search_low_level_category_exact_filter(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = SearchService(repo).search(
        "object", low_level_category="Object Access Success"
    )
    assert len(results) == 1
    assert results[0].qid == 5000850


def test_search_high_level_category_exact_filter(repo):
    seed(repo, SAMPLE_MAPPINGS)
    results = SearchService(repo).search("object", high_level_category="System")
    assert len(results) == 2
    assert all(m.high_level_category == "System" for m in results)
