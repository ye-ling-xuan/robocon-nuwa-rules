import pytest
from pydantic import ValidationError

from server.tools.calc_score import ScoreItem, calculate
from server.tools.check_protection import Tower, check
from server.tools.judge_foul import judge


@pytest.mark.parametrize("level,kind,expected", [("L1", "塔基", 10), ("L1", "中段", 20), ("L1", "塔顶", 40), ("L2", "塔基", 20), ("L2", "中段", 40), ("L2", "塔顶", 80)])
def test_score_table_is_parsed_from_rule(store, level, kind, expected):
    r = calculate(store, [ScoreItem(kind=kind)], level)
    assert r["total"] == expected
    assert r["citations"][0]["clause_id"] == "8.1.3"
    assert r["citations"][0]["page"] == 24


def test_score_transport_is_explicit_and_stone_has_no_transport_score(store):
    assert calculate(store, [ScoreItem(kind="塔顶", mode="transport", count=3)], "L1")["total"] == 15
    assert calculate(store, [ScoreItem(kind="五色石", mode="transport")], "L1")["total"] == 0
    assert calculate(store, [ScoreItem(kind="五色石")], "L2")["total"] == 250
    assert calculate(store, [ScoreItem(kind="塔顶", eligible=False)], "L2")["total"] == 0
    with pytest.raises(ValueError):
        calculate(store, [ScoreItem(kind="五色石")], "L1")
    with pytest.raises(ValueError):
        calculate(store, [ScoreItem(kind="五色石", count=2)], "L2")


@pytest.mark.parametrize("action,verdict", [
    ("TR 携带 4 个塔基会怎样？", "foul"),
    ("TR 携带四个塔基", "foul"),
    ("TR 携带十二个塔基", "foul"),
    ("TR 携带 4 个塔基是否犯规？", "foul"),
    ("BR 持有 3 个中段", "foul"),
    ("TR 拿着 2 个塔基和 2 个塔顶", "foul"),
    ("TR 拿着五色石和塔基", "foul"),
    ("TR 携带 3 个塔基", "no_overcarry_foul"),
    ("BR 携带 2 个塔顶", "no_overcarry_foul"),
    ("TR 没有携带 4 个塔基", "needs_clarification"),
    ("TR 拿4个塔基但之前放下两个", "needs_clarification"),
    ("TR 分两次拿 4 个塔基", "needs_clarification"),
    ("TR 和 BR 共持有 4 个塔基", "needs_clarification"),
    ("携带 4 个塔基", "needs_clarification"),
    ("今天食堂吃什么", "unspecified"),
])
def test_conservative_foul_judgment(store, action, verdict):
    r = judge(store, action)
    assert r["verdict"] == verdict
    if verdict == "foul":
        assert r["disposition"] == "强制重试"
        assert r["citations"][0]["clause_id"] == "6.5"
        assert r["citations"][0]["page"] == 23


def tower(identifier, zone="L1_private", **overrides):
    return Tower(id=identifier, **{**dict(zone=zone, standing=True, complete=True, in_build_site=True, top_matches_team=True), **overrides})


def test_protection_requires_simultaneous_full_towers_and_public_location(store):
    assert check(store, [tower("a"), tower("b", "L2")])["satisfied"] is True
    assert check(store, [tower("a"), tower("b")])["satisfied"] is False
    assert check(store, [tower("a", "L1_public")])["satisfied"] is False
    assert check(store, [tower("a"), tower("b", "L2", standing=False)])["satisfied"] is False
    assert check(store, [tower("a"), tower("b", "L2", top_matches_team=False)])["satisfied"] is False
    assert check(store, [tower("a"), tower("b", "L2", in_build_site=False)])["satisfied"] is False
    assert check(store, [tower("a"), tower("b", "L2", complete=False)])["satisfied"] is False


def test_protection_handles_unknown_and_permanent_satisfaction(store):
    assert check(store, [Tower(id="unknown")])["satisfied"] is None
    assert check(store, [])["satisfied"] is None
    assert check(store, [tower("a", standing=False)], previously_satisfied=True)["satisfied"] is True
    with pytest.raises(ValueError):
        check(store, [tower("a"), tower("a", "L2")])


def test_domain_schema_rejects_negative_fractional_counts_and_invalid_zones():
    for count in (-1, 1.5, True):
        with pytest.raises(ValidationError):
            ScoreItem(kind="塔顶", count=count)
    with pytest.raises(ValidationError):
        Tower(id="x", zone="somewhere")
