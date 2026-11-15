from dataclasses import replace
from datetime import timedelta

import pytest

from hub.config import load_settings
from hub.prompts import PromptError, PromptService
from hub.signals.trigger import SignalTrigger
from hub.signals.types import Method, Signal, Value
from hub.tests.helpers import Rig, T


@pytest.fixture
def rig(tmp_path, clock):
    return Rig(tmp_path, clock)


@pytest.fixture
def prompts(rig, clock):
    return PromptService(rig.store, rig.ing, load_settings({}), clock)


@pytest.fixture
def trig(rig, prompts, clock):
    return SignalTrigger(rig.store, [], prompts, crews=["crew-a"], tz="UTC", clock=clock)


M0 = Method("own_baseline", "ref", None, 7, 7, "a", "b", None)


def sig(state, crew="crew-a", sid="rest_hr_baseline", replay=False):
    v = Value(66, 55, 60, "bpm") if state != "not_enough_data" else None
    return Signal(sid, "baseline", crew, state, "signals.baseline.above", v, M0, replay=replay,
                  can_trigger=True)  # fmt: skip


def events(rig):
    with rig.store.lock:
        return rig.store.conn.execute(
            "SELECT signal_id, crew, state, prompt_id FROM signal_events ORDER BY id"
        ).fetchall()


def test_steady_to_notable_opens_one_body_prompt(trig, rig, prompts):
    assert trig.step(sig("steady"), T) is None
    p = trig.step(sig("notable"), T + timedelta(minutes=5))
    assert p.kind == "signal_body" and p.asks == ["symptom", "mood"] and p.crew == "crew-a"
    assert p.trigger["signal_id"] == "rest_hr_baseline" and p.trigger["value"]["estimate"] == 66
    assert "series" not in p.trigger
    assert trig.step(sig("notable"), T + timedelta(minutes=10)) is None  # no change, no event
    assert [e[2] for e in events(rig)] == ["steady", "notable"]


def test_first_data_straight_to_notable_opens_nothing(trig, rig):
    assert trig.step(sig("not_enough_data"), T) is None
    assert trig.step(sig("notable"), T + timedelta(minutes=5)) is None
    assert [e[3] for e in events(rig)] == [None, None]


def test_open_prompt_and_cooldown_block_a_second_prompt(trig, prompts, clock):
    trig.step(sig("steady"), T)
    first = trig.step(sig("notable"), T)
    trig.step(sig("steady"), T + timedelta(hours=1))
    assert trig.step(sig("notable"), T + timedelta(hours=2)) is None  # still open
    prompts.answer(first.id, [], skipped=True)
    trig.step(sig("steady"), T + timedelta(hours=3))
    assert trig.step(sig("notable"), T + timedelta(hours=4)) is None  # 24 h cooldown
    trig.step(sig("steady"), T + timedelta(hours=25))
    assert trig.step(sig("notable"), T + timedelta(hours=26)) is not None


def test_cabin_signal_opens_cabin_prompt_with_2h_cooldown(trig, prompts):
    trig.step(sig("steady", crew=None, sid="cabin_rh_ttl"), T)
    p = trig.step(sig("notable", crew=None, sid="cabin_rh_ttl"), T)
    assert p.kind == "signal_cabin" and p.asks == ["symptom"] and p.crew is None
    prompts.answer(p.id, [], skipped=True)
    trig.step(sig("steady", crew=None, sid="cabin_rh_ttl"), T + timedelta(hours=1))
    assert trig.step(sig("notable", crew=None, sid="cabin_rh_ttl"), T + timedelta(hours=1)) is None
    trig.step(sig("steady", crew=None, sid="cabin_rh_ttl"), T + timedelta(hours=2, minutes=1))
    assert trig.step(sig("notable", crew=None, sid="cabin_rh_ttl"),
                     T + timedelta(hours=2, minutes=5)) is not None  # fmt: skip


def test_replay_signals_never_open_a_prompt(trig, rig):
    trig.step(sig("steady", replay=True), T)
    assert trig.step(sig("notable", replay=True), T) is None
    assert [e[2] for e in events(rig)] == ["steady", "notable"]


def test_never_an_alert(trig, rig):
    trig.step(sig("steady"), T)
    trig.step(sig("notable"), T)
    assert rig.alerts == [] and rig.store.count("outbox") == 0


def test_answer_payload_carries_no_signal_values(trig, rig, prompts):
    trig.step(sig("steady"), T)
    p = trig.step(sig("notable"), T)
    prompts.answer(p.id, [], skipped=True)
    [item] = rig.store.outbox_after(0, 10)
    assert item.kind == "prompt_answer" and item.payload["prompt_kind"] == "signal_body"
    assert item.payload["rule_id"] is None and "trigger" not in item.payload
    assert "66" not in str(item.payload)


def test_signal_kinds_cannot_be_opened_by_hand(prompts):
    with pytest.raises(PromptError):
        prompts.create("signal_body", "crew-a")
    with pytest.raises(PromptError):
        prompts.create("morning", "crew-a", trigger={"x": 1})


def test_tick_evaluates_trigger_signals_only(trig):
    assert trig.tick(T) == []  # an empty hub: everything is not_enough_data


def test_signals_feature_builds_the_trigger(settings, clock):
    from fastapi.testclient import TestClient

    from hub.api import create_app

    app = create_app(replace(settings, features=frozenset({"signals"})), clock=clock)
    with TestClient(app):
        assert app.state.runtime.signals_trigger is not None
