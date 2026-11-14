# linksim/tests/test_consent.py
from linksim.consent import filter_items, is_public, parse_crews
from linksim.engine import OutboxItem

T = "2026-11-14T15:00:00.000Z"


def item(i, kind, **payload):
    return OutboxItem(id=i, kind=kind, created_at=T, payload=payload)


def test_parse_crews():
    assert parse_crews(None) == frozenset()
    assert parse_crews("") == frozenset()
    assert parse_crews(" crew-a , ,crew-c ") == frozenset({"crew-a", "crew-c"})


def test_cabin_and_nasa_always_public():
    none = frozenset()
    assert is_public(item(1, "reading", node="cabin-1", ind="cabin_co2"), none, False)
    assert is_public(item(2, "reading", node="hub", ind="cabin_ppco2"), none, False)
    assert is_public(item(3, "reading", node="nasa", ind="space_weather"), none, False)
    assert is_public(item(4, "reading", node="nasa", ind="rad_dose_cum"), none, False)
    assert is_public(item(5, "alert", ind="cabin_ppco2", crew=None, rule_id="co2_1h"), none, False)


def test_body_needs_consent():
    a = frozenset({"crew-a"})
    hr_a = item(1, "reading", node="vitals-1", ind="hr", crew="crew-a")
    hr_b = item(2, "reading", node="vitals-1", ind="hr", crew="crew-b")
    hr_none = item(3, "reading", node="manual", ind="hr", crew=None)
    assert is_public(hr_a, a, False)
    assert not is_public(hr_b, a, False)
    assert not is_public(hr_none, a, False)
    assert not is_public(hr_a, frozenset(), False)


def test_intake_answers_and_body_alerts_need_consent():
    a = frozenset({"crew-a"})
    assert is_public(item(1, "reading", node="food", ind="intake_sodium_mg", crew="crew-a"), a, False)
    assert not is_public(item(2, "reading", node="food", ind="intake_sodium_mg", crew="crew-b"), a, False)
    assert is_public(item(3, "prompt_answer", crew="crew-a", prompt_id=1), a, False)
    assert not is_public(item(4, "prompt_answer", crew="crew-b", prompt_id=2), a, False)
    assert not is_public(item(5, "alert", ind="hr", crew="crew-b"), a, False)
    assert is_public(item(6, "alert", ind="hr", crew="crew-a"), a, False)


def test_synthetic_node_always_public():
    assert is_public(item(1, "reading", node="sim-1", ind="hr", crew="crew-b"), frozenset(), False)
    assert is_public(item(2, "rep", node="sim-1", session="s", rep=1), frozenset(), False)


def test_reps_need_flag():
    rep = item(1, "rep", node="camera", session="s1", rep=1)
    assert not is_public(rep, frozenset({"crew-a"}), False)
    assert is_public(rep, frozenset(), True)


def test_everything_else_dropped():
    none = frozenset()
    assert not is_public(item(1, "reading", node="exercise-1", ind="load_raw"), none, False)
    assert not is_public(item(2, "reading", node="vitals-1", ind="motion"), none, False)
    assert not is_public(item(3, "reading", node="x", ind="unknown"), none, False)


def test_filter_keeps_order():
    a = frozenset({"crew-a"})
    items = [
        item(1, "reading", node="cabin-1", ind="cabin_temp"),
        item(2, "reading", node="vitals-1", ind="hr", crew="crew-b"),
        item(3, "reading", node="vitals-1", ind="hr", crew="crew-a"),
    ]
    assert [i.id for i in filter_items(items, a)] == [1, 3]


def test_public_banner_names_crews_and_reps():
    from linksim.__main__ import public_banner

    assert public_banner(frozenset(), False) == "public crews: none; reps public: no"
    assert (
        public_banner(frozenset({"crew-b", "crew-a"}), True)
        == "public crews: crew-a,crew-b; reps public: yes"
    )
