import pytest

from hub.derive import derive_ppco2, ppco2_mmhg
from hub.ingest import Ingestor
from hub.store import Store
from hub.tests.helpers import msg


@pytest.fixture
def ing(tmp_path, clock):
    return Ingestor(Store(tmp_path / "d.db"), clock, deriver=derive_ppco2)


def p(seq, val=1000.0, age=0, **kw):
    return msg(ind="cabin_p", unit="hPa", val=val, dev="BME280", seq=seq, age_ms=age, **kw)


def co2(seq, val=4000, age=0, **kw):
    return msg(ind="cabin_co2", val=val, seq=seq, age_ms=age, **kw)


def derived(ing):
    return ing.store.readings("cabin_ppco2")


def test_formula():
    assert ppco2_mmhg(4000, 1000.0) == pytest.approx(3.000248, abs=1e-6)
    assert ppco2_mmhg(3990, 1000.0) == pytest.approx(2.992747, abs=1e-6)
    assert ppco2_mmhg(1000, 1013.25) == pytest.approx(0.760000, abs=1e-5)


def test_uses_recent_pressure(ing, clock):
    ing.ingest_reading(p(1), channel="mqtt")
    clock.advance(30)
    res = ing.ingest_reading(co2(2), channel="mqtt")
    (d,) = derived(ing)
    assert d.val == pytest.approx(3.000248, abs=1e-6)
    assert (d.unit, d.q) == ("mmHg", ("ok",))
    assert (d.node, d.boot, d.seq) == ("cabin-1", 2, 2)
    assert d.derived_from == res.stored.id


def test_pressure_after_co2_within_window(ing, clock):
    clock.advance(32)
    ing.ingest_reading(p(1), channel="mqtt")
    ing.ingest_reading(co2(2, age=2000), channel="mqtt")  # measured 12:00:30
    assert derived(ing)[0].val == pytest.approx(3.000248, abs=1e-6)


def test_assumed_pressure(ing, clock):
    ing.ingest_reading(p(1, age=90000), channel="mqtt")  # measured 90 s earlier
    ing.ingest_reading(co2(2), channel="mqtt")
    (d,) = derived(ing)
    assert d.val == pytest.approx(3.040001, abs=1e-5)
    assert d.q == ("assumed_pressure",)


def test_flagged_pressure_ignored(ing):
    ing.ingest_reading(p(1, q=["settling"]), channel="mqtt")
    ing.ingest_reading(co2(2), channel="mqtt")
    assert derived(ing)[0].q == ("assumed_pressure",)


def test_parent_flags_carried(ing):
    ing.ingest_reading(p(1), channel="mqtt")
    ing.ingest_reading(co2(2, q=["settling"]), channel="mqtt")
    assert derived(ing)[0].q == ("settling",)


def test_duplicate_parent(ing, clock):
    ing.ingest_reading(co2(2), channel="mqtt")
    clock.advance(5)
    ing.ingest_reading(co2(2), channel="mqtt")
    assert len(derived(ing)) == 1
