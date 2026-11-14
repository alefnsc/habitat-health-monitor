from hub.results import AssessmentResult, entry_for, escalate_to_for
from hub.store import StoredReading


def stored(**kw) -> StoredReading:
    d = dict(  # noqa: C408
        id=7, v=1, node="cabin-1", boot=2, seq=10, age_ms=0, ind="cabin_temp", val=22.0,
        unit="C", src="hobby", dev="BME280", q=("ok",), crew=None, code=None,
        measured_at="2026-11-14T12:00:00.000Z", received_at="2026-11-14T12:00:00.000Z",
        derived_from=None,
    )  # fmt: skip
    d.update(kw)
    return StoredReading(**d)


def res(rule_id, status, val=1.0):
    return AssessmentResult(
        id=0, reading_id=7, ind="cabin_temp", val=val, unit="C", status=status, rule_id=rule_id,
        source_kind="nasa_std", source_ref="ref", guidance_id=f"{rule_id}.{status}",
        escalate_to="cmo", measured_at="2026-11-14T12:00:00.000Z", crew=None,
    )  # fmt: skip


def test_entry_for_worst():
    e = entry_for(stored(), [res("A", "ok"), res("B", "watch", 5.0), res("C", "watch")])
    assert (e.status, e.rule_id, e.val) == ("watch", "B", 5.0)
    assert (e.src, e.dev, e.q, e.node, e.reading_id) == ("hobby", "BME280", ["ok"], "cabin-1", 7)


def test_entry_for_empty_or_flagged():
    for r, results in ((stored(), []), (stored(q=("settling",)), [res("A", "act")])):
        e = entry_for(r, results)
        assert e.status == "unknown" and e.escalate_to == "self" and e.val == 22.0
        assert e.rule_id is None and e.source_kind is None and e.guidance_id is None
        assert e.source_ref is None


def test_escalate_to_for():
    assert escalate_to_for("ok", "hr") == "self"
    assert escalate_to_for("unknown", "intake_kcal") == "self"
    assert escalate_to_for("watch", "hr") == "cmo"
    assert escalate_to_for("act", "hr") == "flight_surgeon"
    assert escalate_to_for("watch", "intake_sodium_mg") == "self"
    assert escalate_to_for("act", "intake_sodium_mg") == "cmo"
    assert escalate_to_for("act", "body_mass") == "flight_surgeon"
