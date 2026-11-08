from copy import deepcopy
import json

import pytest

from scripts.validate_clauses import validate
from server.rules import RuleStore, UNSPECIFIED, normalize


def test_entire_shipped_dataset_matches_pdf():
    assert validate() == []


@pytest.mark.parametrize("query,ids", [
    ("TR拿着五色石还能拿塔基吗？", ["3.6.8", "4.4.2"]),
    ("L2 塔顶多少分？", ["8.1.3"]),
    ("TR携带4个塔基会怎样？", ["6.5"]),
    ("这个塔算不算满足保护法则？", ["3.6.1"]),
    ("同分怎么破平", ["9.2"]),
    ("看一下 3.6.8", ["3.6.8"]),
])
def test_real_questions_retrieve_authoritative_clauses(store, query, ids):
    results = store.search(query)
    assert [c["clause_id"] for c in results][:len(ids)] == ids


def test_main_carry_question_only_returns_two_direct_rules(store):
    assert len(store.search("TR拿着五色石还能拿塔基吗？")) == 2
    assert [c["page"] for c in store.search("TR拿着五色石还能拿塔基吗？")] == [17, 20]


def test_unknown_questions_and_nonexistent_clause_do_not_fabricate(store):
    for query in ("今天食堂吃什么？", "机器人可以隐身吗", "规则99.9.9"):
        assert store.search(query) == []
    assert store.validate_answer("随便编一个答案", []) == UNSPECIFIED
    with pytest.raises(ValueError):
        store.get("99.9.9")


@pytest.mark.parametrize("field,value", [("page", 99), ("page", True), ("quote", "虚构原文"), ("bbox", [1, 2, 3, 4]), ("rects", [])])
def test_rejects_modified_citation(store, field, value):
    citation = store.citation("3.6.8")
    citation[field] = value
    with pytest.raises(ValueError):
        store.canonicalize([citation])


def test_ids_only_are_canonicalized_and_cannot_mutate_store(store):
    result = store.canonicalize([{"clause_id": "3.6.8"}])
    assert result[0]["page"] == 17
    result[0]["rects"][0][0] = 0
    assert store.citation("3.6.8")["rects"][0][0] > 0


def test_answer_reference_must_match_returned_pages(store):
    citation = store.citation("3.6.8")
    with pytest.raises(ValueError):
        store.validate_answer("不能。[3.6.8 · P18]", [citation])
    with pytest.raises(ValueError):
        store.validate_answer("不能。[4.4.2 · P20]", [citation])


def test_quote_only_citation_is_supported():
    store = RuleStore()
    store.by_id["3.6.8"].pop("bbox")
    store.by_id["3.6.8"].pop("rects")
    c = store.citation("3.6.8")
    assert c["bbox"] is None and c["quote"]


def test_changed_pdf_rejected_at_startup(store, tmp_path):
    for filename in ("clauses.json", "page_map.json"):
        (tmp_path / filename).write_bytes((store.data_dir / filename).read_bytes())
    (tmp_path / "rules.pdf").write_bytes(b"wrong file")
    with pytest.raises(ValueError, match="PDF changed"):
        RuleStore(tmp_path)


def test_cross_page_clause_has_independent_physical_segments(store):
    c = store.citation("3.6.4")
    assert c["cross_page"]
    assert [s["page"] for s in c["segments"]] == [16, 17]
    assert all(s["quote"] and s["rects"] for s in c["segments"])
