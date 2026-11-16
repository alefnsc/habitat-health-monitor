# Pluggable sensor modules and board configuration (D46) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A sensor, a pin move or a second board becomes an edit to one or two files in `registry/`. The hub, firmware headers, console lanes, Wokwi twins and tests follow from those files, and CI fails when any copy falls behind. The plan ends with the spec's worked example: an SCD41 and a BME280 on the UNO, so the hub judges ppCO2 against NASA-STD-3001.

**Architecture:** the four rollout steps of the spec (§13), one part each, each part its own PR:
- **Part A (Tasks 1–6): registry and hub tables.**
  - `registry/` JSON files and the `hub/registry/` loader and validator, with safety rules S1–S6.
  - `hub/contract.py` builds every table from them. No behaviour change, proven by a snapshot taken first.
- **Part B (Tasks 7–16): generation.**
  - `python -m tools.registry check | gen | builds` writes `board_config.h` and `board_parts.h` per sketch, the `ReadingFormat` tables, `wokwi_twin.h`, the hub chip's bands, the README board table, the per-board safety rows and `console/src/generated/registry.ts`.
  - CI fails on a stale file and gates the UNO's RAM.
- **Part C (Tasks 17–22): hub and console behaviour.**
  - Hub: `unexpected_output` on hardware channels, commands routed by board, `GET /api/registry`, and a stale-build warning.
  - Console: lanes from registry hints, one series per node, and nodes grouped by board.
- **Part D (Tasks 23–29): the worked example.**
  - `HabitatParts` drivers for the SCD41 and the BME280, with host tests.
  - Placements on `uno-1`, Wokwi chips, and the operator's bench bring-up.

**Tech Stack:** Python 3.12 (standard library only), pytest, ruff; Arduino C++ (arduino:avr 1.8.8, esp8266 3.1.2, arduino-cli 1.5.1) and c++17 host tests; TypeScript, Vite and vitest for the console; Wokwi custom chips in C.

**Spec:** `docs/decisions/2026-11-15-sensor-modules-design.md` (D46), approved by the team owner on 2026-11-15, in the same PR (alefnsc/habitat-health-monitor#38).

**How sure each part is:**
- **Part A was run once on a scratch copy of `main` at `239924d`:** 1,098 passed, 2 skipped, `ruff check .` clean. Its code blocks are those exact files.
- **Parts B–D have not been run.** They give the tests in full or as exact tables, plus the interfaces and the generated formats. Re-run writing-plans for a part before starting it if `main` has moved.

## Global Constraints

- **When.** Start only after judging. The submitted build must not change.
- **Where.** One worktree per part, never the main checkout `~/Applications/space-apps-2026-11-13/habitat-health-monitor` (the live hub runs from it). For Part A:
  ```bash
  git -C ~/Applications/space-apps-2026-11-13/habitat-health-monitor fetch origin
  git -C ~/Applications/space-apps-2026-11-13/habitat-health-monitor worktree add ~/Applications/space-apps-2026-11-13/wt-d46-registry -b feat/d46-registry-step1 origin/main
  ```
  - Each later part branches from `main` once the previous part is merged.
  - If `origin/main` has moved past `239924d`, read `git log 239924d..origin/main -- hub/contract.py hub/ingest.py hub/assess.py hub/derive.py hub/__main__.py` before Task 5. The Part A diffs are against `239924d`.
- **Environment.** Give each worktree its own venv, so `hub` resolves to the worktree:
  ```bash
  python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev,analysis]'
  ```
- **Gates.** `.venv/bin/python -m pytest -q -m 'not broker' --ignore=hub/tests/test_mqtt_broker.py` and `.venv/bin/ruff check .`. Judge on the exit code, never on piped output.
  - The broker test is ignored because it connects to whatever listens on 127.0.0.1:1883, which may be the bench broker.
  - New Python files must also pass `.venv/bin/ruff format --check`. Nine existing files already fail it; leave them alone.
  - From Part B on, also: `python -m tools.registry check`, the firmware host tests and compiles of `.github/workflows/ci.yml`, and `npm --prefix console run build && (cd console && npx vitest run)`.
- **No behaviour change in Part A.**
  - `hub/tests/fixtures/contract_snapshot.json` is written once, in Task 1, from the unchanged code. Never regenerate it to make a test pass.
  - The contract-v1 wire format and `REASON_CODES` never change in this plan. `unexpected_output` is an ingest reason, like `topic_node_mismatch`.
- **Hardware.** Agents never flash a board, never connect to the bench broker, and never start a second `python -m hub` on the bench machine: it would take the live hub's MQTT client id, `habitat-hub`. Tasks 9 (bench check), 28 (Wokwi paste) and 29 are the operator's.
- **Text.** No company name anywhere. Keep "Educational prototype, not a medical device." Registry error lines read `<folder>/<file>: <field>: <text>`, and the tests match those texts exactly.
- **Git.** Commit after each task. Push or open a PR only when the operator says so. Never merge.

---

## Part A — Rollout step 1: registry and hub tables (Tasks 1–6)

### Part A file map

| File | Task | Responsibility |
|---|---|---|
| `hub/tests/test_registry_migration.py`, `hub/tests/fixtures/contract_snapshot.json` | 1 | snapshot of today's tables and replay outcomes; the no-change gate |
| `registry/indicators.json`, `registry/core.json`, `registry/parts/*.json` (16), `registry/boards/*.json` (4) | 2 | the data: today's bench, the archived vitals node, and the core names |
| `hub/registry/schema.py` | 2 | `RegistryError`, `Errors`, key and type checks |
| `hub/registry/model.py` | 2 | frozen records, `output_inds`, `periods_ms` |
| `hub/registry/mcu.py` | 2 | pin, rail and power tables for `atmega328p`, `esp8266`, `host`; cell voltages |
| `hub/registry/parse.py` | 2 | one file into records; local checks |
| `hub/registry/loader.py`, `hub/registry/__init__.py` | 2 | read the folder, parse, check, hash; `load`, `load_default`, `default_dir` |
| `hub/registry/validate.py` | 2 (stub), 3 | rules across files: references, nodes, producers, pins, I2C, rates |
| `hub/registry/safety.py` | 2 (stub), 4 | S1–S6 |
| `hub/tests/registry_helpers.py`, `hub/tests/test_registry.py` | 2 | copy-and-change helpers; the real registry loads; local rules |
| `hub/tests/test_registry_rules.py` | 3 | one failing case per rule across files |
| `hub/tests/test_registry_safety.py` | 4 | one failing case per safety rule |
| `hub/contract.py`, `hub/ingest.py`, `hub/assess.py`, `hub/derive.py`, `hub/tests/test_registry_contract.py` | 5 | tables from the registry |
| `hub/__main__.py`, `hub/tests/test_registry_start.py`, `.env.example`, `registry/README.md` | 6 | refuse to start on a bad registry; log the hash; document |

---

### Task 1: Snapshot today's contract tables and replay parsing

**Files:**
- Create: `hub/tests/test_registry_migration.py`
- Create (generated once): `hub/tests/fixtures/contract_snapshot.json`

**Interfaces:**
- Produces: `build_snapshot() -> dict` and `replay_digest() -> dict` in `hub.tests.test_registry_migration`. Task 5 must keep both tests green without touching the fixture.

This is a characterization test. It passes on unchanged code by construction, and its job is to stay green through Task 5.

- [ ] **Step 1: Write the test module**

```python
"""D46 migration gate: the registry rebuilds today's contract tables exactly.

The snapshot in fixtures/contract_snapshot.json was written from the hard-coded tables before the
registry existed. Never regenerate it to make this test pass: a difference is a behaviour change.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from hub import assess, contract, ingest
from hub.contract import ContractError, parse_reading, parse_rep, reading_to_dict, rep_to_dict

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = Path(__file__).parent / "fixtures" / "contract_snapshot.json"
REPLAY_FILES = [
    *sorted((ROOT / "data" / "replay").glob("*.jsonl")),
    ROOT / "data" / "contract" / "camera-reps.v1.jsonl",
]
TABLES = (
    "INDICATORS", "DERIVED", "CABIN_INDS", "BODY_INDS", "INTAKE_ORDER", "INTAKE_INDS",
    "INTAKE_UNITS", "INTAKE_CEILINGS", "BODY_MASS_RANGE", "NODES", "SOURCES", "DEVICES", "FLAGS",
    "CREWS", "SYMPTOM_CODES", "REP_SOURCES", "EXERCISES", "REASON_CODES",
)  # fmt: skip


def _canon(x: object) -> object:
    """JSON-able form that keeps dict and tuple order and sorts sets."""
    if isinstance(x, dict):
        return [[k, _canon(v)] for k, v in x.items()]
    if isinstance(x, set | frozenset):
        return sorted(x)
    if isinstance(x, tuple | list):
        return [_canon(v) for v in x]
    return x


def _outcome(line: str) -> list:
    obj = json.loads(line)
    if "kind" in obj:
        kind, msg = obj["kind"], obj.get("msg")
    else:  # data/contract holds bare messages
        kind, msg = ("rep" if obj.get("type") == "rep" else "reading"), obj
    try:
        if kind == "reading":
            return ["ok", reading_to_dict(parse_reading(msg))]
        if kind == "rep":
            return ["ok", rep_to_dict(parse_rep(msg))]
    except ContractError as e:
        return ["reject", e.reason]
    return [kind]


def replay_digest() -> dict:
    out = {}
    for path in REPLAY_FILES:
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        outcomes = [_outcome(ln) for ln in lines]
        blob = json.dumps(outcomes, sort_keys=True, separators=(",", ":")).encode()
        out[path.relative_to(ROOT).as_posix()] = {
            "lines": len(lines),
            "ok": sum(o[0] == "ok" for o in outcomes),
            "reject": sum(o[0] == "reject" for o in outcomes),
            "sha256": hashlib.sha256(blob).hexdigest(),
        }
    return out


def build_snapshot() -> dict:
    tables = {name: _canon(getattr(contract, name)) for name in TABLES}
    tables["ingest.CREW_SCOPED"] = _canon(ingest.CREW_SCOPED)
    tables["ingest.QUIET_INDS"] = _canon(ingest.QUIET_INDS)
    tables["assess.CREW_SCOPED"] = _canon(assess.CREW_SCOPED)
    tables["assess.UNGATED_INDS"] = _canon(assess.UNGATED_INDS)
    return {"tables": tables, "replay": replay_digest()}


def test_tables_match_the_snapshot():
    want = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["tables"]
    got = build_snapshot()["tables"]
    assert got.keys() == want.keys()
    for name in want:
        assert got[name] == want[name], name


def test_replay_files_parse_as_before():
    want = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["replay"]
    assert replay_digest() == want
```

- [ ] **Step 2: Write the snapshot from the unchanged code**

Run (nothing else has changed in the worktree yet):
```bash
.venv/bin/python - <<'EOF'
import json
from hub.tests.test_registry_migration import SNAPSHOT, build_snapshot
s = build_snapshot()
SNAPSHOT.write_text(json.dumps(s, indent=1, sort_keys=True) + "\n")
print({k: (v["lines"], v["ok"], v["reject"]) for k, v in s["replay"].items()})
EOF
```
Expected output (on `239924d`): `{'data/replay/exercise-day.jsonl': (8, 8, 0), 'data/replay/food-crew-days.jsonl': (363, 363, 0), 'data/replay/food-flags.jsonl': (363, 363, 0), 'data/replay/l0-synthetic.jsonl': (5040, 5040, 0), 'data/replay/ring-synthetic-nights.jsonl': (2, 0, 0), 'data/contract/camera-reps.v1.jsonl': (8, 8, 0)}`. The ring file's two lines are neither readings nor reps, so they count in neither column.

- [ ] **Step 3: Run it**

Run: `.venv/bin/python -m pytest -q hub/tests/test_registry_migration.py`
Expected: `2 passed`.

- [ ] **Step 4: Commit**

```bash
git add hub/tests/test_registry_migration.py hub/tests/fixtures/contract_snapshot.json
git commit -m "test(registry): snapshot today's contract tables and replay parsing (D46 step 1)"
```

---

### Task 2: Registry files, loader and local checks

**Files:**
- Create: `registry/indicators.json`, `registry/core.json`
- Create: `registry/parts/` with `DHT11.json`, `DHT22.json`, `HX711.json`, `servo.json`, `buzzer-passive.json`, `NTC.json`, `KY039.json`, `KY017.json`, `MAX30102.json`, `MLX90614.json`, `MPU6050.json`, `DS18B20.json`, `BH1750.json`, `MH-Z19.json`, `SCD41.json`, `BME280.json`
- Create: `registry/boards/` with `uno-1.json`, `tilt-1.json`, `hub.json`, `vitals-1.json`
- Create: `hub/registry/__init__.py`, `schema.py`, `model.py`, `mcu.py`, `parse.py`, `loader.py`, plus stubs `validate.py` and `safety.py`
- Test: `hub/tests/registry_helpers.py`, `hub/tests/test_registry.py`

**Interfaces:**
- Produces:
  - `hub.registry.load(root: Path) -> Registry` (raises `RegistryError`), `load_default() -> Registry` (cached, reads `default_dir()`), and `default_dir() -> Path` (`HUB_REGISTRY_DIR` or `<repo>/registry`);
  - `RegistryError.errors: list[str]`;
  - `Registry` fields `root, label, hash, indicators, core, parts, boards`, `file(rel)`, `indicators_by_id`, `board_nodes`;
  - records `Indicator`, `Core`, `Part`, `Output`, `Param`, `PinSpec`, `Board`, `Pack`, `Placement`, and `output_inds(pl, part)`, `periods_ms(pl, part)`;
  - `Errors.add(path, field, msg)`, `schema.num(x)`;
  - `mcu.MCUS`, `mcu.CELL_V`, and `Mcu.misfit(label, kind)`;
  - `validate.check_all(reg, errs)` and `safety.check_safety(reg, errs)`, which are stubs here.
- Consumes: nothing from earlier tasks.

Decisions made for this plan, within the spec. Tell the operator if any is unwelcome:
- **`driver: "none"`.** It marks a part with no firmware yet. Task 3 refuses an enabled placement of such a part, so `SCD41.json` and `BME280.json` exist now and stay unplaceable until step 4.
- **No ESP32 table yet.** `mcu.py` has no ESP32 table, because no board file uses one. Step 2 adds it with the twin checks.
- **Node id rule.** The pattern `^[a-z]+-[0-9]+$` and the 15-character limit apply to board nodes only. The core producers keep their names (`manual`, `camera`, `nasa`, `food`).

- [ ] **Step 1: Write the test helpers and the tests**

`hub/tests/registry_helpers.py`:

```python
"""Helpers for the registry tests: copy the real registry/, change one thing, read the errors."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from hub.registry import RegistryError, load

ROOT = Path(__file__).resolve().parents[2]
Mutation = Callable[[dict], None]
Edit = Callable[[Path], None]


def copy_registry(tmp_path: Path) -> Path:
    dst = tmp_path / "registry"
    shutil.copytree(ROOT / "registry", dst)
    return dst


def _walk(obj: dict, dotted: str) -> tuple[dict | list, str | int]:
    keys: list[str | int] = [int(k) if k.isdigit() else k for k in dotted.split(".")]
    for key in keys[:-1]:
        obj = obj[key]  # type: ignore[index]
    return obj, keys[-1]


def setp(dotted: str, value: object) -> Mutation:
    """Set the value at a dotted path, e.g. setp("placements.0.pins.data", "D0")."""

    def run(obj: dict) -> None:
        parent, key = _walk(obj, dotted)
        parent[key] = value  # type: ignore[index]

    return run


def delp(dotted: str) -> Mutation:
    def run(obj: dict) -> None:
        parent, key = _walk(obj, dotted)
        del parent[key]  # type: ignore[arg-type]

    return run


def addp(dotted: str, value: object) -> Mutation:
    """Append to the list at a dotted path."""

    def run(obj: dict) -> None:
        parent, key = _walk(obj, dotted)
        parent[key].append(value)  # type: ignore[index]

    return run


def E(rel: str, *mutations: Mutation) -> Edit:
    """Change one file of the copied registry."""

    def run(root: Path) -> None:
        path = root / rel
        obj = json.loads(path.read_text(encoding="utf-8"))
        for m in mutations:
            m(obj)
        path.write_text(json.dumps(obj, indent=1), encoding="utf-8")

    return run


def COPY(src: str, dst: str, *mutations: Mutation) -> Edit:
    """Add a file made from another one, e.g. a second board."""

    def run(root: Path) -> None:
        shutil.copy(root / src, root / dst)
        E(dst, *mutations)(root)

    return run


def WRITE(rel: str, text: str) -> Edit:
    def run(root: Path) -> None:
        (root / rel).write_text(text, encoding="utf-8")

    return run


def errors_after(root: Path, edits: list[Edit]) -> list[str]:
    for edit in edits:
        edit(root)
    with pytest.raises(RegistryError) as e:
        load(root)
    return e.value.errors


def loads_after(root: Path, edits: list[Edit]) -> None:
    for edit in edits:
        edit(root)
    load(root)
```

`hub/tests/test_registry.py`:

```python
"""D46 registry: the real files load, and each local file rule fails on its own (D46 §4, §5.1)."""

from __future__ import annotations

import pytest

from hub.registry import load
from hub.tests.registry_helpers import (
    WRITE,
    E,
    addp,
    copy_registry,
    delp,
    errors_after,
    loads_after,
    setp,
)


def test_real_registry_loads(tmp_path):
    reg = load(copy_registry(tmp_path))
    assert [b.id for b in reg.boards] == ["hub", "tilt-1", "uno-1", "vitals-1"]
    assert len(reg.indicators) == 32 and len(reg.parts) == 16
    assert len(reg.hash) == 64 and reg.hash == load(copy_registry(tmp_path / "again")).hash


def test_hash_changes_with_content(tmp_path):
    root = copy_registry(tmp_path)
    before = load(root).hash
    E("parts/DHT11.json", setp("note", "changed"))(root)
    assert load(root).hash != before


def test_note_is_allowed_anywhere(tmp_path):
    loads_after(
        copy_registry(tmp_path),
        [E("boards/uno-1.json", setp("placements.0.note", "x"), setp("power.note", "y"))],
    )


def test_missing_folder(tmp_path):
    with pytest.raises(Exception, match="no registry folder"):
        load(tmp_path / "nowhere")


CASES = [
    ("unknown key", [E("parts/DHT11.json", setp("pinz", []))], "parts/DHT11.json: pinz: unknown key"),
    ("missing key", [E("indicators.json", delp("indicators.0.unit"))],
     "indicators.json: indicators[0].unit: missing"),
    ("wrong type", [E("indicators.json", setp("indicators.0.decimals", "1"))],
     "indicators[0].decimals: expected an integer"),
    ("schema version", [E("core.json", setp("schema", 2))], "core.json: schema: only schema 1"),
    ("unexpected file", [WRITE("extra.json", "{}")], "extra.json: unexpected file"),
    ("bad json", [WRITE("parts/BAD.json", "{")], "parts/BAD.json: not valid JSON"),
    ("lane window", [E("indicators.json", setp("indicators.0.lane.window", "mean_7d"))],
     "is not a lane window"),
    ("scope", [E("indicators.json", setp("indicators.0.scope", "space"))], "'space' is not one of"),
    ("repeated code", [E("indicators.json", addp("indicators.9.codes", "none"))],
     "none is listed twice"),
    ("core repeat", [E("core.json", addp("crews", "crew-a"))], "core.json: crews: crew-a is listed twice"),
    ("part id vs file", [E("parts/DHT11.json", setp("id", "DHT12"))],
     "id: DHT12 does not match the file name DHT11.json"),
    ("part kind", [E("parts/DHT11.json", setp("kind", "probe"))], "kind: 'probe' is not one of"),
    ("driver name", [E("parts/DHT11.json", setp("driver", "dht 11"))], "is not inline, none or"),
    ("macro", [E("parts/DHT11.json", setp("macro", "dht"))], "is not an UPPER_SNAKE macro prefix"),
    ("pin kind", [E("parts/DHT11.json", setp("pins.0.kind", "onewire"))], "'onewire' is not one of"),
    ("sensor without outputs", [E("parts/DHT11.json", setp("outputs", []))],
     "a sensor has at least one output"),
    ("sensor without src", [E("parts/DHT11.json", delp("src"))], "a sensor names its source class"),
    ("sensor without period", [E("parts/DHT11.json", delp("period_ms"))],
     "a sensor gives its period limits"),
    ("actuator with outputs",
     [E("parts/servo.json", setp("outputs", [{"ind": "tilt", "range": [0, 1], "flags": []}]))],
     "an actuator has no outputs"),
    ("period order", [E("parts/DHT11.json", setp("period_ms.default", 500))],
     "expected 0 < min <= default <= max"),
    ("range order", [E("parts/DHT11.json", setp("outputs.0.range", [50, 0]))],
     "expected [low, high] numbers with low <= high"),
    ("param order", [E("parts/KY017.json", setp("params.debounce_ms.default", 5))],
     "expected min <= default <= max"),
    ("i2c block without i2c pins", [E("parts/DHT11.json", setp("i2c", {"addr": "0x40", "max_hz": 1}))],
     "only an I2C part does"),
    ("i2c pins without block", [E("parts/MPU6050.json", delp("i2c"))],
     "an I2C part gives i2c.addr and i2c.max_hz"),
    ("i2c address format", [E("parts/MPU6050.json", setp("i2c.addr", "68"))],
     "is not a 7-bit address"),
    ("rail", [E("parts/DHT11.json", setp("rails", ["12V"]))], "rails: '12V' is not one of"),
    ("hazard", [E("parts/KY017.json", setp("hazards", ["lead"]))], "hazards: 'lead' is not one of"),
    ("wokwi part and chip", [E("parts/DHT11.json", setp("wokwi.chip", "dht"))],
     "give exactly one of part or chip"),
    ("wokwi label", [E("parts/DHT11.json", setp("wokwi.label", "DHT11 stand-in"))],
     "wokwi.label: must say it is simulated"),
    ("board id vs file", [E("boards/tilt-1.json", setp("board", "tilt-2"))],
     "board: tilt-2 does not match the file name tilt-1.json"),
    ("mcu", [E("boards/tilt-1.json", setp("mcu", "rp2040"))], "mcu: 'rp2040' is not one of"),
    ("host with a link", [E("boards/hub.json", setp("link", {"transport": "mqtt"}))],
     "a host board has no link"),
    ("mcu without a link", [E("boards/tilt-1.json", setp("link", None))],
     "a board with a microcontroller has a link"),
    ("serial without baud", [E("boards/uno-1.json", delp("link.baud"))],
     "a serial link gives its baud rate"),
    ("mqtt with baud", [E("boards/tilt-1.json", setp("link.baud", 9600))],
     "an MQTT link has no baud rate"),
    ("power source", [E("boards/uno-1.json", setp("power.source", "solar"))],
     "power.source: 'solar' is not one of"),
    ("node pattern", [E("boards/tilt-1.json", setp("nodes", ["Tilt_1"]))], "is not a node id"),
    ("node too long", [E("boards/tilt-1.json", setp("nodes", ["cabin-1234567890"]))],
     "is not a node id"),
    ("ack node", [E("boards/uno-1.json", setp("ack_node", "cabin-2"))],
     "ack_node: cabin-2 is not one of this board's nodes"),
    ("placement period", [E("boards/uno-1.json", setp("placements.0.period_ms", 0))],
     "expected milliseconds above 0"),
    ("placement enclosure", [E("boards/tilt-1.json", setp("placements.0.enclosure", "box"))],
     "'box' is not one of"),
    ("placement macro", [E("boards/uno-1.json", setp("placements.0.as", "dht-b"))],
     "is not an UPPER_SNAKE macro prefix"),
]  # fmt: skip


@pytest.mark.parametrize(("edits", "expect"), [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_rule(tmp_path, edits, expect):
    errs = errors_after(copy_registry(tmp_path), edits)
    assert any(expect in line for line in errs), errs
```

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/bin/python -m pytest -q hub/tests/test_registry.py`
Expected: collection error `ModuleNotFoundError: No module named 'hub.registry'`.

- [ ] **Step 3: Write the registry data files**

`registry/indicators.json`, in today's `INDICATORS` order with `cabin_ppco2` after `cabin_co2`. Lane hints copy `LANES` in `console/src/model/lanes.ts`, and decimals copy `kDecimals` in `ReadingFormat.cpp`:

```json
{
  "schema": 1,
  "note": "Every indicator of contract v1 (D46 §4.2). Order is the order of hub.contract.INDICATORS.",
  "indicators": [
    { "id": "hr", "unit": "bpm", "scope": "body", "label": "Heart rate", "decimals": 0,
      "lane": { "label": "Heart rate", "window": "instant", "order": 50, "optional": false } },
    { "id": "spo2", "unit": "%", "scope": "body", "label": "SpO2", "decimals": 0,
      "lane": { "label": "SpO2", "window": "instant", "order": 60, "optional": false } },
    { "id": "skin_temp", "unit": "C", "scope": "body", "label": "Skin temperature", "decimals": 2 },
    { "id": "body_temp", "unit": "C", "scope": "body", "label": "Body temperature", "decimals": 1 },
    { "id": "bp_sys", "unit": "mmHg", "scope": "body", "label": "Blood pressure, systolic", "decimals": 0 },
    { "id": "bp_dia", "unit": "mmHg", "scope": "body", "label": "Blood pressure, diastolic", "decimals": 0 },
    { "id": "glucose", "unit": "mg/dL", "scope": "body", "label": "Glucose", "decimals": 0 },
    { "id": "sleep_h", "unit": "h", "scope": "body", "label": "Sleep", "decimals": 1,
      "lane": { "label": "Sleep", "window": "instant", "order": 70, "optional": false } },
    { "id": "mood", "unit": "1-5", "scope": "body", "label": "Mood", "decimals": 0 },
    { "id": "symptom", "unit": "code", "scope": "body", "label": "Symptom", "decimals": 0,
      "codes": ["headache", "fatigue", "nausea", "poor_sleep", "none"] },
    { "id": "cabin_temp", "unit": "C", "scope": "cabin", "label": "Cabin temperature", "decimals": 1,
      "lane": { "label": "Cabin temperature", "window": "instant", "order": 10, "optional": false } },
    { "id": "cabin_rh", "unit": "%", "scope": "cabin", "label": "Cabin humidity", "decimals": 1,
      "lane": { "label": "Cabin humidity", "window": "instant", "order": 20, "optional": false } },
    { "id": "cabin_p", "unit": "hPa", "scope": "cabin", "label": "Cabin pressure", "decimals": 1,
      "lane": { "label": "Cabin pressure", "window": "instant", "order": 30, "optional": true } },
    { "id": "cabin_co2", "unit": "ppm", "scope": "cabin", "label": "Cabin CO2", "decimals": 0 },
    { "id": "cabin_ppco2", "unit": "mmHg", "scope": "cabin", "label": "Cabin CO2 (partial pressure)",
      "decimals": 2, "derived": { "from": "cabin_co2", "fn": "ppco2" },
      "lane": { "label": "Cabin CO2 (partial pressure)", "window": "mean_1h", "order": 40, "optional": true } },
    { "id": "cabin_lux", "unit": "lx", "scope": "cabin", "label": "Cabin light", "decimals": 0 },
    { "id": "motion", "unit": "g", "scope": "exercise", "label": "Motion", "decimals": 3, "assess": false },
    { "id": "load_raw", "unit": "N", "scope": "exercise", "label": "Load (raw)", "decimals": 1,
      "quiet": true, "assess": false },
    { "id": "tilt", "unit": "state", "scope": "exercise", "label": "Tilt switch", "decimals": 0, "assess": false },
    { "id": "space_weather", "unit": "level", "scope": "environment", "label": "Space weather", "decimals": 0 },
    { "id": "rad_dose_cum", "unit": "mSv", "scope": "environment", "label": "Radiation dose, cumulative",
      "decimals": 3 },
    { "id": "intake_kcal", "unit": "kcal", "scope": "intake", "label": "Energy intake",
      "reject_outside": [0, 10000] },
    { "id": "intake_protein_g", "unit": "g", "scope": "intake", "label": "Protein intake",
      "reject_outside": [0, 500] },
    { "id": "intake_carb_g", "unit": "g", "scope": "intake", "label": "Carbohydrate intake",
      "reject_outside": [0, 1000] },
    { "id": "intake_fat_g", "unit": "g", "scope": "intake", "label": "Fat intake", "reject_outside": [0, 500] },
    { "id": "intake_water_ml", "unit": "mL", "scope": "intake", "label": "Water intake",
      "reject_outside": [0, 10000] },
    { "id": "intake_sodium_mg", "unit": "mg", "scope": "intake", "label": "Sodium intake",
      "reject_outside": [0, 30000] },
    { "id": "intake_potassium_mg", "unit": "mg", "scope": "intake", "label": "Potassium intake",
      "reject_outside": [0, 30000] },
    { "id": "intake_calcium_mg", "unit": "mg", "scope": "intake", "label": "Calcium intake",
      "reject_outside": [0, 20000] },
    { "id": "intake_iron_mg", "unit": "mg", "scope": "intake", "label": "Iron intake",
      "reject_outside": [0, 1000] },
    { "id": "intake_vitd_ug", "unit": "ug", "scope": "intake", "label": "Vitamin D intake",
      "reject_outside": [0, 5000] },
    { "id": "body_mass", "unit": "kg", "scope": "body", "label": "Body mass", "decimals": 1,
      "reject_outside": [20, 300] }
  ]
}
```

`registry/core.json`:

```json
{
  "schema": 1,
  "note": "Contract-v1 names that no board owns (D46 §4.1). Board nodes and sensor devices come from boards/ and parts/.",
  "sources": ["certified", "hobby", "self", "nasa", "replay"],
  "flags": ["ok", "motion", "no_contact", "settling", "leads_off", "out_of_range", "assumed_pressure", "stale"],
  "crews": ["crew-a", "crew-b", "crew-c"],
  "rep_sources": ["camera", "load_cell"],
  "exercises": ["curl", "overhead_press", "row"],
  "commands": ["servo", "alarm", "cal", "tare"],
  "devices": ["H10", "manual", "camera", "DONKI", "OSDR", "catalog", "RING"],
  "nodes": ["strap-1", "manual", "camera", "sim-1", "nasa", "food", "ring-1"]
}
```

`registry/parts/DHT11.json`:

```json
{
  "schema": 1, "id": "DHT11", "kind": "sensor", "src": "hobby", "driver": "inline", "macro": "DHT",
  "pins": [{ "role": "data", "kind": "digital" }],
  "supply_v": [3.3, 5.5], "rails": ["5V", "3V3"], "io_v": [3.3, 5.5], "contact": "none",
  "outputs": [
    { "ind": "cabin_temp", "range": [0, 50], "flags": ["out_of_range", "no_contact"] },
    { "ind": "cabin_rh", "range": [20, 90], "flags": ["out_of_range", "no_contact"] }
  ],
  "period_ms": { "min": 1000, "default": 5000 },
  "params": { "fails_for_no_contact": { "min": 1, "max": 10, "default": 3 } },
  "wokwi": { "part": "wokwi-dht22", "label": "DHT11 stand-in (simulated)", "pins": { "data": "SDA" },
             "twin_defines": { "DHT_TYPE": "DHT22" } },
  "note": "Ranges are the DHT11 datasheet's (D40 §4); no_contact after 3 failed reads, as nodes/cabin_pi."
}
```

`registry/parts/DHT22.json`:

```json
{
  "schema": 1, "id": "DHT22", "kind": "sensor", "src": "hobby", "driver": "none", "macro": "DHT22",
  "pins": [{ "role": "data", "kind": "digital" }],
  "supply_v": [3.3, 6.0], "rails": ["5V", "3V3"], "io_v": [3.3, 6.0], "contact": "none",
  "outputs": [
    { "ind": "cabin_temp", "range": [-40, 80], "flags": ["out_of_range", "no_contact"] },
    { "ind": "cabin_rh", "range": [0, 100], "flags": ["out_of_range", "no_contact"] }
  ],
  "period_ms": { "min": 2000, "default": 5000 }
}
```

`registry/parts/HX711.json`:

```json
{
  "schema": 1, "id": "HX711", "kind": "sensor", "src": "hobby", "driver": "inline", "macro": "HX711",
  "pins": [{ "role": "dout", "kind": "digital" }, { "role": "sck", "kind": "digital" }],
  "supply_v": [2.6, 5.5], "rails": ["5V", "3V3"], "io_v": [2.6, 5.5], "contact": "none",
  "outputs": [{ "ind": "load_raw", "range": [-500, 500], "flags": ["settling", "out_of_range"] }],
  "commands": ["cal", "tare"],
  "period_ms": { "min": 12.5, "default": 12.5 },
  "wiring_notes": ["Tie the HX711 RATE pin to DVDD for 80 SPS.", "Keep the HX711 board enclosed or taped (checklist rule 9)."],
  "note": "80 SPS. Range: a 50 kg cell is about 490 N (CELL_CAPACITY_KG in the sketch)."
}
```

`registry/parts/servo.json`:

```json
{
  "schema": 1, "id": "servo", "kind": "actuator", "driver": "inline", "macro": "SERVO",
  "pins": [{ "role": "signal", "kind": "pwm" }],
  "supply_v": [4.8, 6.0], "rails": ["5V"], "io_v": [3.3, 5.5], "contact": "none",
  "commands": ["servo"]
}
```

`registry/parts/buzzer-passive.json`:

```json
{
  "schema": 1, "id": "buzzer-passive", "kind": "actuator", "driver": "inline", "macro": "BUZZER",
  "pins": [{ "role": "signal", "kind": "digital" }],
  "io_v": [3.3, 5.5], "contact": "none",
  "commands": ["alarm"],
  "wokwi": { "part": "wokwi-buzzer", "pins": { "signal": "2" }, "twin_defines": { "BUZZER_PASSIVE": "1" } },
  "note": "A passive piezo between the pin and GND, played with tone() (D40 §4). It takes no supply rail."
}
```

`registry/parts/NTC.json`:

```json
{
  "schema": 1, "id": "NTC", "kind": "sensor", "src": "hobby", "driver": "inline", "macro": "NTC",
  "pins": [{ "role": "out", "kind": "analog" }],
  "supply_v": [3.3, 5.5], "rails": ["5V", "3V3"], "io_v": [3.3, 5.5], "contact": "body",
  "outputs": [{ "ind": "skin_temp", "range": [-20, 80], "flags": ["out_of_range", "settling", "no_contact"] }],
  "period_ms": { "min": 5000, "default": 5000 },
  "note": "10 k NTC skin probe under a series resistor. The sketch flags out_of_range near the ADC rails; the range is informative."
}
```

`registry/parts/KY039.json`:

```json
{
  "schema": 1, "id": "KY039", "kind": "sensor", "src": "hobby", "driver": "inline", "macro": "KY039",
  "pins": [{ "role": "out", "kind": "analog" }],
  "supply_v": [3.3, 5.5], "rails": ["5V", "3V3"], "io_v": [3.3, 5.5], "contact": "body",
  "outputs": [{ "ind": "hr", "range": [30, 220], "flags": ["no_contact", "settling"] }],
  "period_ms": { "min": 5000, "default": 5000 },
  "note": "Finger pulse module; an estimate, not a measurement of heart rate."
}
```

`registry/parts/KY017.json`:

```json
{
  "schema": 1, "id": "KY017", "kind": "sensor", "src": "hobby", "driver": "inline", "macro": "TILT",
  "pins": [{ "role": "signal", "kind": "digital" }],
  "supply_v": [3.3, 5.5], "rails": ["3V3", "5V"], "io_v": [3.3, 5.5], "contact": "none",
  "hazards": ["mercury"], "handling": "adults_only",
  "outputs": [{ "ind": "tilt", "range": [0, 1], "flags": [] }],
  "period_ms": { "min": 1000, "default": 10000 },
  "params": {
    "debounce_ms": { "min": 50, "max": 1000, "default": 200 },
    "heartbeat_ms": { "min": 1000, "max": 60000, "default": 10000 },
    "active_low": { "min": 0, "max": 1, "default": 1 }
  },
  "wiring_notes": ["The capsule holds mercury: sealed pod, never opened, adult team members only (checklist rule 12)."],
  "wokwi": { "part": "wokwi-slide-switch", "label": "KY-017 stand-in (simulated)", "pins": { "signal": "2" } },
  "note": "One reading on every debounced change plus a heartbeat; period_ms is the heartbeat (D39)."
}
```

`registry/parts/MAX30102.json`:

```json
{
  "schema": 1, "id": "MAX30102", "kind": "sensor", "src": "hobby", "driver": "inline", "macro": "MAX30102",
  "pins": [{ "role": "sda", "kind": "i2c-sda" }, { "role": "scl", "kind": "i2c-scl" }],
  "i2c": { "addr": "0x57", "max_hz": 400000 },
  "supply_v": [3.0, 3.6], "rails": ["3V3"], "io_v": [1.8, 3.6], "contact": "body",
  "outputs": [
    { "ind": "hr", "range": [30, 220], "flags": ["no_contact", "settling", "motion"], "needs": { "motion": "motion" } },
    { "ind": "spo2", "range": [70, 100], "flags": ["no_contact", "settling", "motion"], "needs": { "motion": "motion" } }
  ],
  "period_ms": { "min": 1000, "default": 1000 },
  "wiring_notes": ["Many MAX30102 boards pull SDA and SCL up to 1.8 V: move the jumper to 3.3 V."],
  "wokwi": { "chip": "max30102", "label": "MAX30102 pulse sensor (simulated)" },
  "note": "Breakout on the 3.3 V rail, as in D37 (archived). supply_v is the team window for the breakout."
}
```

`registry/parts/MLX90614.json`:

```json
{
  "schema": 1, "id": "MLX90614", "kind": "sensor", "src": "hobby", "driver": "inline", "macro": "MLX90614",
  "pins": [{ "role": "sda", "kind": "i2c-sda" }, { "role": "scl", "kind": "i2c-scl" }],
  "i2c": { "addr": "0x5A", "max_hz": 100000 },
  "supply_v": [2.6, 3.6], "rails": ["3V3"], "io_v": [2.6, 3.6], "contact": "body",
  "outputs": [{ "ind": "skin_temp", "range": [-70, 380], "flags": ["no_contact", "settling"] }],
  "period_ms": { "min": 2000, "default": 2000 },
  "wokwi": { "chip": "mlx90614", "label": "MLX90614 GY-906 (simulated)" },
  "note": "Non-contact object temperature, worn on the body. 100 kHz is the SMBus limit."
}
```

`registry/parts/MPU6050.json`:

```json
{
  "schema": 1, "id": "MPU6050", "kind": "sensor", "src": "hobby", "driver": "inline", "macro": "MPU6050",
  "pins": [{ "role": "sda", "kind": "i2c-sda" }, { "role": "scl", "kind": "i2c-scl" }],
  "i2c": { "addr": "0x68", "max_hz": 400000 },
  "supply_v": [2.375, 3.46], "rails": ["3V3"], "io_v": [1.71, 3.46], "contact": "body",
  "outputs": [{ "ind": "motion", "range": [0, 16], "flags": [] }],
  "period_ms": { "min": 1000, "default": 1000 },
  "wokwi": { "part": "wokwi-mpu6050", "label": "MPU6050 (simulated)" }
}
```

`registry/parts/DS18B20.json`:

```json
{
  "schema": 1, "id": "DS18B20", "kind": "sensor", "src": "hobby", "driver": "none", "macro": "DS18B20",
  "pins": [{ "role": "data", "kind": "digital" }],
  "supply_v": [3.0, 5.5], "rails": ["5V", "3V3"], "io_v": [3.0, 5.5], "contact": "body",
  "outputs": [{ "ind": "skin_temp", "range": [-55, 125], "flags": ["no_contact", "settling"] }],
  "period_ms": { "min": 750, "default": 5000 },
  "note": "Skin probe of the validation protocol (docs/drafts/s5-validation-protocol.md); not on any board."
}
```

`registry/parts/BH1750.json`:

```json
{
  "schema": 1, "id": "BH1750", "kind": "sensor", "src": "hobby", "driver": "none", "macro": "BH1750",
  "pins": [{ "role": "sda", "kind": "i2c-sda" }, { "role": "scl", "kind": "i2c-scl" }],
  "i2c": { "addr": "0x23", "max_hz": 400000 },
  "supply_v": [2.4, 3.6], "rails": ["3V3"], "io_v": [2.4, 3.6], "contact": "none",
  "outputs": [{ "ind": "cabin_lux", "range": [1, 65535], "flags": ["out_of_range", "no_contact"] }],
  "period_ms": { "min": 1000, "default": 5000 }
}
```

`registry/parts/MH-Z19.json`:

```json
{
  "schema": 1, "id": "MH-Z19", "kind": "sensor", "src": "hobby", "driver": "none", "macro": "MHZ19",
  "pins": [{ "role": "tx", "kind": "digital" }, { "role": "rx", "kind": "digital" }],
  "supply_v": [4.5, 5.5], "rails": ["5V"], "io_v": [3.3, 3.3], "contact": "none",
  "outputs": [{ "ind": "cabin_co2", "range": [0, 5000], "flags": ["settling", "out_of_range", "no_contact"] }],
  "period_ms": { "min": 5000, "default": 5000 },
  "note": "UART at 3.3 V levels: on the 5 V UNO it needs a level shifter (S6)."
}
```

`registry/parts/SCD41.json`:

```json
{
  "schema": 1, "id": "SCD41", "kind": "sensor", "src": "hobby", "driver": "none", "macro": "SCD41",
  "pins": [{ "role": "sda", "kind": "i2c-sda" }, { "role": "scl", "kind": "i2c-scl" }],
  "i2c": { "addr": "0x62", "max_hz": 400000 },
  "supply_v": [2.4, 5.5], "rails": ["5V", "3V3"], "io_v": [2.4, 5.5], "contact": "none",
  "outputs": [
    { "ind": "cabin_co2", "range": [0, 5000], "flags": ["settling", "out_of_range", "no_contact"] },
    { "ind": "cabin_temp", "range": [-10, 60], "flags": ["no_contact"] },
    { "ind": "cabin_rh", "range": [0, 100], "flags": ["no_contact"] }
  ],
  "period_ms": { "min": 5000, "default": 5000 },
  "params": {
    "settle_s": { "min": 0, "max": 600, "default": 60 },
    "fails_for_no_contact": { "min": 1, "max": 10, "default": 3 }
  },
  "note": "Flags as nodes/cabin_pi. driver becomes \"SCD41\" when HabitatParts has it (D46 rollout step 4)."
}
```

`registry/parts/BME280.json`:

```json
{
  "schema": 1, "id": "BME280", "kind": "sensor", "src": "hobby", "driver": "none", "macro": "BME280",
  "pins": [{ "role": "sda", "kind": "i2c-sda" }, { "role": "scl", "kind": "i2c-scl" }],
  "i2c": { "addr": "0x76", "max_hz": 400000 },
  "supply_v": [1.71, 3.6], "rails": ["3V3"], "io_v": [1.2, 3.6], "contact": "none",
  "outputs": [
    { "ind": "cabin_p", "range": [300, 1100], "flags": ["settling", "no_contact"] },
    { "ind": "cabin_temp", "range": [-40, 85], "flags": ["no_contact"] },
    { "ind": "cabin_rh", "range": [0, 100], "flags": ["no_contact"] }
  ],
  "period_ms": { "min": 1000, "default": 30000 },
  "wiring_notes": ["A bare BME280 module is 3.3 V only: on the 5 V UNO use a breakout with a regulator and a level shifter."],
  "note": "driver becomes \"BME280\" when HabitatParts has it (D46 rollout step 4)."
}
```

`registry/boards/uno-1.json`:

```json
{
  "schema": 1, "board": "uno-1", "status": "active", "mcu": "atmega328p", "fqbn": "arduino:avr:uno",
  "sketch": "firmware/exercise-uno", "twins": ["firmware/wokwi/uno-rig", "firmware/wokwi/full-bench"],
  "link": { "transport": "serial", "baud": 250000 },
  "power": { "source": "usb-host" },
  "nodes": ["exercise-1", "cabin-1"], "ack_node": "exercise-1",
  "placements": [
    { "part": "DHT11", "node": "cabin-1", "pins": { "data": "D2" }, "period_ms": 5000, "supply": "5V" },
    { "part": "buzzer-passive", "node": "exercise-1", "pins": { "signal": "D8" } },
    { "part": "HX711", "node": "exercise-1", "pins": { "dout": "D3", "sck": "D4" }, "supply": "5V", "enabled": false },
    { "part": "servo", "node": "exercise-1", "pins": { "signal": "D6" }, "supply": "5V", "enabled": false },
    { "part": "NTC", "node": "exercise-1", "pins": { "out": "A0" }, "supply": "5V", "enabled": false },
    { "part": "KY039", "node": "exercise-1", "pins": { "out": "A1" }, "supply": "5V", "enabled": false }
  ],
  "note": "The UNO I/O board of D40. Disabled placements keep their pins and are compiled out."
}
```

`registry/boards/tilt-1.json`:

```json
{
  "schema": 1, "board": "tilt-1", "status": "active", "mcu": "esp8266", "fqbn": "esp8266:esp8266:nodemcuv2",
  "sketch": "firmware/tilt-esp8266", "twins": ["firmware/wokwi/tilt-esp32"],
  "link": { "transport": "mqtt" },
  "power": { "source": "pack", "pack": { "cells": 4, "chemistry": "nimh", "size": "AA", "pin": "VIN" } },
  "nodes": ["tilt-1"],
  "placements": [
    { "part": "KY017", "node": "tilt-1", "pins": { "signal": "D5" }, "supply": "3V3", "enclosure": "sealed",
      "params": { "debounce_ms": 200, "heartbeat_ms": 10000, "active_low": 1 } }
  ],
  "note": "The tilt pod of D39 on the D40 cell pack. The pack comes out before USB goes in to flash."
}
```

`registry/boards/hub.json`:

```json
{
  "schema": 1, "board": "hub", "status": "active", "mcu": "host",
  "link": null, "power": { "source": "mains" }, "nodes": [], "placements": [],
  "note": "The Raspberry Pi 3 (or a laptop) running the hub. Nothing goes on its 40-pin header (D40)."
}
```

`registry/boards/vitals-1.json`:

```json
{
  "schema": 1, "board": "vitals-1", "status": "archived", "mcu": "esp8266", "fqbn": "esp8266:esp8266:nodemcuv2",
  "sketch": "firmware/vitals-esp32", "twins": ["firmware/wokwi/vitals-esp32"],
  "link": { "transport": "mqtt" },
  "power": { "source": "usb-bank" },
  "nodes": ["vitals-1"],
  "placements": [
    { "part": "MAX30102", "node": "vitals-1", "pins": { "sda": "D2", "scl": "D1" }, "supply": "3V3",
      "period_ms": { "hr": 1000, "spo2": 4000 } },
    { "part": "MLX90614", "node": "vitals-1", "pins": { "sda": "D2", "scl": "D1" }, "supply": "3V3" },
    { "part": "MPU6050", "node": "vitals-1", "pins": { "sda": "D2", "scl": "D1" }, "supply": "3V3" }
  ],
  "note": "The D37 vitals node, archived by D40: validated and compiled, not on the bench."
}
```

- [ ] **Step 4: Write the package**

`hub/registry/schema.py`:

```python
"""Key and type checks for registry files (D46 §5.1). Unknown keys are refused; `note` is allowed."""

from __future__ import annotations

from typing import Any

# field -> (kind, required)
Spec = dict[str, tuple[str, bool]]

KIND_TEXT = {
    "str": "a non-empty string",
    "int": "an integer",
    "num": "a number",
    "bool": "true or false",
    "range": "[low, high] numbers with low <= high",
    "strs": "a list of non-empty strings",
    "list": "a list",
    "dict": "an object",
    "num|dict": "a number or an object",
    "dict|null": "an object or null",
}


class RegistryError(ValueError):
    """The registry is invalid. `errors` holds one line per problem: `<file>: <field>: <text>`."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


class Errors:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def add(self, path: str, field: str, msg: str) -> None:
        self.lines.append(f"{path}: {field}: {msg}" if field else f"{path}: {msg}")

    def raise_if_any(self) -> None:
        if self.lines:
            raise RegistryError(list(self.lines))


def is_num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def num(x: float) -> str:
    """A number for a message: 50.0 -> '50', 4.5 -> '4.5'."""
    return f"{x:g}"


def one_of(values: frozenset[str] | dict) -> str:
    return ", ".join(sorted(values))


def kind_ok(kind: str, x: Any) -> bool:
    if kind == "str":
        return isinstance(x, str) and x != ""
    if kind == "int":
        return isinstance(x, int) and not isinstance(x, bool)
    if kind == "num":
        return is_num(x)
    if kind == "bool":
        return isinstance(x, bool)
    if kind == "range":
        return isinstance(x, list) and len(x) == 2 and all(is_num(v) for v in x) and x[0] <= x[1]
    if kind == "strs":
        return isinstance(x, list) and all(isinstance(v, str) and v != "" for v in x)
    if kind == "list":
        return isinstance(x, list)
    if kind == "dict":
        return isinstance(x, dict)
    if kind == "num|dict":
        return is_num(x) or isinstance(x, dict)
    if kind == "dict|null":
        return x is None or isinstance(x, dict)
    raise ValueError(f"unknown kind {kind}")


def check(obj: Any, spec: Spec, errs: Errors, path: str, prefix: str = "") -> bool:
    """Report unknown keys, missing keys and wrong types. True when `obj` can be read further."""
    if not isinstance(obj, dict):
        errs.add(path, prefix.rstrip("."), "expected an object")
        return False
    ok = True
    for key in obj:
        if key not in spec and key != "note":
            errs.add(path, prefix + key, "unknown key")
            ok = False
    for key, (kind, required) in spec.items():
        if key not in obj:
            if required:
                errs.add(path, prefix + key, "missing")
                ok = False
        elif not kind_ok(kind, obj[key]):
            errs.add(path, prefix + key, f"expected {KIND_TEXT[kind]}")
            ok = False
    return ok
```

`hub/registry/model.py`:

```python
"""Frozen records for the module registry (D46 §4). Built by hub.registry.parse."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path


@dataclass(frozen=True)
class Lane:
    label: str
    window: str
    order: int
    optional: bool


@dataclass(frozen=True)
class Indicator:
    id: str
    unit: str
    scope: str
    label: str
    decimals: int = 1
    reject_outside: tuple[float, float] | None = None
    quiet: bool = False
    assess: bool = True
    derived_from: str | None = None
    derived_fn: str | None = None
    lane: Lane | None = None
    codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Core:
    sources: tuple[str, ...]
    flags: tuple[str, ...]
    crews: tuple[str, ...]
    rep_sources: tuple[str, ...]
    exercises: tuple[str, ...]
    commands: tuple[str, ...]
    devices: tuple[str, ...]
    nodes: tuple[str, ...]


@dataclass(frozen=True)
class PinSpec:
    role: str
    kind: str  # digital | analog | pwm | i2c-sda | i2c-scl


@dataclass(frozen=True)
class Output:
    ind: str
    range: tuple[float, float]
    flags: tuple[str, ...]
    needs: dict[str, str]  # flag -> the indicator that flag depends on


@dataclass(frozen=True)
class Param:
    min: float
    max: float
    default: float


@dataclass(frozen=True)
class Part:
    path: str
    id: str
    kind: str  # sensor | actuator
    src: str | None
    driver: str  # inline | none | a HabitatParts header name
    macro: str
    pins: tuple[PinSpec, ...]
    i2c_addr: int | None
    i2c_max_hz: int | None
    supply_v: tuple[float, float] | None
    rails: tuple[str, ...]
    io_v: tuple[float, float] | None
    contact: str
    hazards: tuple[str, ...]
    handling: str | None
    outputs: tuple[Output, ...]
    commands: tuple[str, ...]
    period_min_ms: float | None
    period_max_ms: float | None
    period_default_ms: float | None
    params: dict[str, Param]
    wiring_notes: tuple[str, ...]


@dataclass(frozen=True)
class Pack:
    cells: int
    chemistry: str
    size: str
    pin: str


@dataclass(frozen=True)
class Placement:
    part: str
    node: str
    pins: dict[str, str]  # role -> board pin label
    period_ms: float | dict[str, float] | None
    params: dict[str, float]
    supply: str | None
    outputs: tuple[str, ...] | None  # None: every output of the part
    enabled: bool
    enclosure: str | None
    level_shifted: bool
    macro_as: str | None


@dataclass(frozen=True)
class Board:
    path: str
    id: str
    status: str  # active | archived
    mcu: str
    fqbn: str | None
    sketch: str | None
    twins: tuple[str, ...]
    transport: str | None  # serial | mqtt | None for a host
    baud: int | None
    power_source: str
    pack: Pack | None
    nodes: tuple[str, ...]
    ack_node: str | None
    default: bool
    placements: tuple[Placement, ...]


@dataclass(frozen=True)
class Registry:
    root: Path
    label: str  # the folder name, used in messages
    hash: str  # SHA-256 of the canonical JSON of every file, sorted by path
    indicators: tuple[Indicator, ...]
    core: Core
    parts: dict[str, Part]
    boards: tuple[Board, ...]

    def file(self, rel: str) -> str:
        return f"{self.label}/{rel}"

    @cached_property
    def indicators_by_id(self) -> dict[str, Indicator]:
        return {i.id: i for i in self.indicators}

    @property
    def board_nodes(self) -> tuple[str, ...]:
        return tuple(n for b in self.boards for n in b.nodes)


def output_inds(pl: Placement, part: Part) -> tuple[str, ...]:
    """The indicators this placement sends: its `outputs`, or every output of the part."""
    if pl.outputs is not None:
        return pl.outputs
    return tuple(o.ind for o in part.outputs)


def periods_ms(pl: Placement, part: Part) -> dict[str, float]:
    """Sample period per output: the placement's number, its per-output map, or the part's default."""
    inds = output_inds(pl, part)
    if isinstance(pl.period_ms, int | float):
        return dict.fromkeys(inds, float(pl.period_ms))
    per = pl.period_ms or {}
    default = part.period_default_ms or 0.0
    return {i: float(per.get(i, default)) for i in inds}
```

`hub/registry/mcu.py`:

```python
"""Board facts the validator needs, one table per MCU kind (D46 §4.5).

Sources: firmware/README.md, the sketch headers and D40 §6. The ESP32 table is added with the Wokwi
twin checks (rollout step 2), because no board file uses an ESP32 yet.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Mcu:
    pins: dict[str, int]  # board pin label -> GPIO number
    digital: frozenset[str]
    analog: frozenset[str]
    pwm: frozenset[str]
    reserved: dict[str, str]  # label -> why it is not free
    sda: str | None
    scl: str | None
    logic_v: float | None
    rails: frozenset[str]  # supply rails a part may hang on
    # power-in pin -> (low, high, low is exclusive)
    pack_windows: dict[str, tuple[float, float, bool]]
    wifi: bool

    def misfit(self, label: str, kind: str) -> str | None:
        """Why `label` cannot serve a pin of `kind`, or None when it can."""
        if kind == "digital" and label not in self.digital:
            return "is not a digital pin"
        if kind == "analog" and label not in self.analog:
            return "is not an analog pin"
        if kind == "pwm" and label not in self.pwm:
            return "is not a PWM pin"
        if kind == "i2c-sda" and label != self.sda:
            return f"is not the I2C SDA pin ({self.sda})"
        if kind == "i2c-scl" and label != self.scl:
            return f"is not the I2C SCL pin ({self.scl})"
        return None


_UNO_D = {f"D{n}": n for n in range(14)}
_UNO_A = {f"A{n}": 14 + n for n in range(6)}

ATMEGA328P = Mcu(
    pins={**_UNO_D, **_UNO_A},
    digital=frozenset(_UNO_D) | frozenset(_UNO_A),
    analog=frozenset(_UNO_A),
    pwm=frozenset({"D3", "D5", "D6", "D9", "D10", "D11"}),
    reserved={"D0": "USB serial", "D1": "USB serial"},
    sda="A4",
    scl="A5",
    logic_v=5.0,
    rails=frozenset({"5V", "3V3"}),
    pack_windows={},  # USB power only, as on the bench
    wifi=False,
)

_NODEMCU = {
    "D0": 16,
    "D1": 5,
    "D2": 4,
    "D3": 0,
    "D4": 2,
    "D5": 14,
    "D6": 12,
    "D7": 13,
    "D8": 15,
    "RX": 3,
    "TX": 1,
    "A0": 17,
}

ESP8266 = Mcu(
    pins=_NODEMCU,
    digital=frozenset(_NODEMCU) - {"A0"},
    analog=frozenset({"A0"}),
    pwm=frozenset(_NODEMCU) - {"A0", "D0"},
    reserved={
        "D3": "boot pin",
        "D4": "boot pin",
        "D8": "boot pin",
        "RX": "USB serial",
        "TX": "USB serial",
    },
    sda="D2",
    scl="D1",
    logic_v=3.3,
    rails=frozenset({"3V3"}),
    pack_windows={"VIN": (4.5, 6.0, True), "3V3": (2.7, 3.6, False)},  # 6.0 V is a team limit
    wifi=True,
)

HOST = Mcu(
    pins={},
    digital=frozenset(),
    analog=frozenset(),
    pwm=frozenset(),
    reserved={},
    sda=None,
    scl=None,
    logic_v=None,
    rails=frozenset(),
    pack_windows={},
    wifi=False,
)

MCUS: dict[str, Mcu] = {"atmega328p": ATMEGA328P, "esp8266": ESP8266, "host": HOST}

# Voltage per cell: Ni-MH 1.2-1.4 V and alkaline 1.5-1.6 V fresh (D40 §6); a lithium coin 3.0-3.2 V.
CELL_V: dict[str, tuple[float, float]] = {
    "nimh": (1.2, 1.4),
    "alkaline": (1.5, 1.6),
    "lithium": (3.0, 3.2),
}
```

`hub/registry/parse.py`:

```python
"""Parse one registry file into model records. Local checks only; rules across files are in
hub.registry.validate and hub.registry.safety (D46 §4, §5.1)."""

from __future__ import annotations

import re
from typing import Any

from hub.registry.mcu import CELL_V, MCUS
from hub.registry.model import (
    Board,
    Core,
    Indicator,
    Lane,
    Output,
    Pack,
    Param,
    Part,
    PinSpec,
    Placement,
)
from hub.registry.schema import Errors, Spec, check, is_num, one_of

SCOPES = frozenset({"cabin", "body", "intake", "exercise", "environment", "other"})
LANE_WINDOWS = frozenset({"instant", "mean_1h"})  # what console/src/model/lanes.ts draws
PIN_KINDS = frozenset({"digital", "analog", "pwm", "i2c-sda", "i2c-scl"})
PART_KINDS = frozenset({"sensor", "actuator"})
CONTACTS = frozenset({"none", "body"})
HAZARDS = frozenset({"mercury"})
HANDLING = frozenset({"adults_only"})
ENCLOSURES = frozenset({"sealed"})
STATUSES = frozenset({"active", "archived"})
TRANSPORTS = frozenset({"serial", "mqtt"})
POWER_SOURCES = frozenset({"usb-host", "usb-bank", "pack", "mains"})
PACK_SIZES = frozenset({"AA", "AAA", "CR2032"})
RAILS = frozenset({"5V", "3V3"})

IND_RE = re.compile(r"^[a-z][a-z0-9_]*$")
MACRO_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
DRIVER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
NODE_RE = re.compile(r"^[a-z]+-[0-9]+$")
ADDR_RE = re.compile(r"^0x[0-9A-Fa-f]{2}$")
NODE_MAX = 15  # HabitatNode keeps the node id in 16 bytes

INDICATORS_FILE: Spec = {"schema": ("int", True), "indicators": ("list", True)}
INDICATOR: Spec = {
    "id": ("str", True),
    "unit": ("str", True),
    "scope": ("str", True),
    "label": ("str", True),
    "decimals": ("int", False),
    "reject_outside": ("range", False),
    "quiet": ("bool", False),
    "assess": ("bool", False),
    "derived": ("dict", False),
    "lane": ("dict", False),
    "codes": ("strs", False),
}
DERIVED: Spec = {"from": ("str", True), "fn": ("str", True)}
LANE: Spec = {
    "label": ("str", True),
    "window": ("str", True),
    "order": ("int", True),
    "optional": ("bool", True),
}
CORE: Spec = {
    "schema": ("int", True),
    "sources": ("strs", True),
    "flags": ("strs", True),
    "crews": ("strs", True),
    "rep_sources": ("strs", True),
    "exercises": ("strs", True),
    "commands": ("strs", True),
    "devices": ("strs", True),
    "nodes": ("strs", True),
}
PART: Spec = {
    "schema": ("int", True),
    "id": ("str", True),
    "kind": ("str", True),
    "src": ("str", False),
    "driver": ("str", True),
    "macro": ("str", True),
    "pins": ("list", True),
    "i2c": ("dict", False),
    "supply_v": ("range", False),
    "rails": ("strs", False),
    "io_v": ("range", False),
    "contact": ("str", False),
    "hazards": ("strs", False),
    "handling": ("str", False),
    "outputs": ("list", False),
    "commands": ("strs", False),
    "period_ms": ("dict", False),
    "params": ("dict", False),
    "wiring_notes": ("strs", False),
    "wokwi": ("dict", False),
}
PIN: Spec = {"role": ("str", True), "kind": ("str", True)}
I2C: Spec = {"addr": ("str", True), "max_hz": ("int", True)}
OUTPUT: Spec = {
    "ind": ("str", True),
    "range": ("range", True),
    "flags": ("strs", True),
    "needs": ("dict", False),
}
PERIOD: Spec = {"min": ("num", True), "max": ("num", False), "default": ("num", True)}
PARAM: Spec = {"min": ("num", True), "max": ("num", True), "default": ("num", True)}
WOKWI: Spec = {
    "part": ("str", False),
    "chip": ("str", False),
    "label": ("str", False),
    "pins": ("dict", False),
    "twin_defines": ("dict", False),
}
BOARD: Spec = {
    "schema": ("int", True),
    "board": ("str", True),
    "status": ("str", True),
    "mcu": ("str", True),
    "fqbn": ("str", False),
    "sketch": ("str", False),
    "twins": ("strs", False),
    "link": ("dict|null", True),
    "power": ("dict", True),
    "nodes": ("strs", True),
    "ack_node": ("str", False),
    "default": ("bool", False),
    "placements": ("list", True),
}
LINK: Spec = {"transport": ("str", True), "baud": ("int", False)}
POWER: Spec = {"source": ("str", True), "pack": ("dict", False)}
PACK: Spec = {
    "cells": ("int", True),
    "chemistry": ("str", True),
    "size": ("str", True),
    "pin": ("str", True),
}
PLACEMENT: Spec = {
    "part": ("str", True),
    "node": ("str", True),
    "pins": ("dict", True),
    "period_ms": ("num|dict", False),
    "params": ("dict", False),
    "supply": ("str", False),
    "outputs": ("strs", False),
    "enabled": ("bool", False),
    "enclosure": ("str", False),
    "level_shifted": ("bool", False),
    "as": ("str", False),
}


def _schema_ok(obj: dict, path: str, errs: Errors) -> bool:
    if obj["schema"] != 1:
        errs.add(path, "schema", "only schema 1 is supported")
        return False
    return True


def _enum(value: str, allowed: frozenset[str], path: str, field: str, errs: Errors) -> bool:
    if value in allowed:
        return True
    errs.add(path, field, f"{value!r} is not one of {one_of(allowed)}")
    return False


def _no_repeats(values: list[str], path: str, field: str, errs: Errors) -> None:
    seen: set[str] = set()
    for v in values:
        if v in seen:
            errs.add(path, field, f"{v} is listed twice")
        seen.add(v)


# indicators.json and core.json


def parse_indicators(obj: Any, path: str, errs: Errors) -> tuple[Indicator, ...]:
    if not check(obj, INDICATORS_FILE, errs, path) or not _schema_ok(obj, path, errs):
        return ()
    out: list[Indicator] = []
    for n, raw in enumerate(obj["indicators"]):
        f = f"indicators[{n}]"
        if not check(raw, INDICATOR, errs, path, f + "."):
            continue
        n0 = len(errs.lines)
        if not IND_RE.match(raw["id"]):
            errs.add(path, f + ".id", f"{raw['id']!r} is not a lower_snake id")
        _enum(raw["scope"], SCOPES, path, f + ".scope", errs)
        lane = None
        if "lane" in raw and check(raw["lane"], LANE, errs, path, f + ".lane."):
            ln = raw["lane"]
            if ln["window"] not in LANE_WINDOWS:
                errs.add(
                    path,
                    f + ".lane.window",
                    f"{ln['window']!r} is not a lane window ({one_of(LANE_WINDOWS)})",
                )
            lane = Lane(ln["label"], ln["window"], ln["order"], ln["optional"])
        derived = raw.get("derived")
        if derived is not None:
            check(derived, DERIVED, errs, path, f + ".derived.")
        codes = raw.get("codes", [])
        _no_repeats(codes, path, f + ".codes", errs)
        if len(errs.lines) > n0:
            continue
        rng = raw.get("reject_outside")
        out.append(
            Indicator(
                id=raw["id"],
                unit=raw["unit"],
                scope=raw["scope"],
                label=raw["label"],
                decimals=raw.get("decimals", 1),
                reject_outside=(float(rng[0]), float(rng[1])) if rng else None,
                quiet=raw.get("quiet", False),
                assess=raw.get("assess", True),
                derived_from=derived["from"] if derived else None,
                derived_fn=derived["fn"] if derived else None,
                lane=lane,
                codes=tuple(codes),
            )
        )
    return tuple(out)


def parse_core(obj: Any, path: str, errs: Errors) -> Core | None:
    if not check(obj, CORE, errs, path) or not _schema_ok(obj, path, errs):
        return None
    names = (
        "sources",
        "flags",
        "crews",
        "rep_sources",
        "exercises",
        "commands",
        "devices",
        "nodes",
    )
    for name in names:
        _no_repeats(obj[name], path, name, errs)
    return Core(**{name: tuple(obj[name]) for name in names})


# parts/<id>.json


def _addr(text: str, path: str, errs: Errors) -> int | None:
    value = int(text, 16) if ADDR_RE.match(text) else -1
    if not 0x08 <= value <= 0x77:
        errs.add(path, "i2c.addr", f'{text!r} is not a 7-bit address like "0x68"')
        return None
    return value


def _pin_specs(raw: list, path: str, errs: Errors) -> tuple[PinSpec, ...]:
    pins: list[PinSpec] = []
    for n, p in enumerate(raw):
        f = f"pins[{n}]"
        if check(p, PIN, errs, path, f + ".") and _enum(
            p["kind"], PIN_KINDS, path, f + ".kind", errs
        ):
            pins.append(PinSpec(p["role"], p["kind"]))
    _no_repeats([p.role for p in pins], path, "pins", errs)
    return tuple(pins)


def _outputs(raw: list, path: str, errs: Errors) -> tuple[Output, ...]:
    outs: list[Output] = []
    for n, o in enumerate(raw):
        f = f"outputs[{n}]"
        if not check(o, OUTPUT, errs, path, f + "."):
            continue
        needs = o.get("needs", {})
        if not all(isinstance(v, str) and v for v in needs.values()):
            errs.add(path, f + ".needs", "expected flag -> indicator names")
            continue
        outs.append(
            Output(
                o["ind"],
                (float(o["range"][0]), float(o["range"][1])),
                tuple(o["flags"]),
                dict(needs),
            )
        )
    _no_repeats([o.ind for o in outs], path, "outputs", errs)
    return tuple(outs)


def _params(raw: dict, path: str, errs: Errors) -> dict[str, Param]:
    params: dict[str, Param] = {}
    for name, p in raw.items():
        f = f"params.{name}"
        if not check(p, PARAM, errs, path, f + "."):
            continue
        if not p["min"] <= p["default"] <= p["max"]:
            errs.add(path, f, "expected min <= default <= max")
            continue
        params[name] = Param(float(p["min"]), float(p["max"]), float(p["default"]))
    return params


def parse_part(obj: Any, path: str, stem: str, errs: Errors) -> Part | None:
    if not check(obj, PART, errs, path) or not _schema_ok(obj, path, errs):
        return None
    n0 = len(errs.lines)
    pid, kind, driver = obj["id"], obj["kind"], obj["driver"]
    if pid != stem:
        errs.add(path, "id", f"{pid} does not match the file name {stem}.json")
    _enum(kind, PART_KINDS, path, "kind", errs)
    if driver not in ("inline", "none") and not DRIVER_RE.match(driver):
        errs.add(path, "driver", f"{driver!r} is not inline, none or a HabitatParts header name")
    if not MACRO_RE.match(obj["macro"]):
        errs.add(path, "macro", f"{obj['macro']!r} is not an UPPER_SNAKE macro prefix")
    pins = _pin_specs(obj["pins"], path, errs)
    i2c_addr = i2c_hz = None
    if "i2c" in obj and check(obj["i2c"], I2C, errs, path, "i2c."):
        i2c_addr, i2c_hz = _addr(obj["i2c"]["addr"], path, errs), obj["i2c"]["max_hz"]
    if any(p.kind.startswith("i2c-") for p in pins) != ("i2c" in obj):
        errs.add(
            path, "i2c", "an I2C part gives i2c.addr and i2c.max_hz, and only an I2C part does"
        )
    for rail in obj.get("rails", []):
        _enum(rail, RAILS, path, "rails", errs)
    contact = obj.get("contact", "none")
    _enum(contact, CONTACTS, path, "contact", errs)
    for hazard in obj.get("hazards", []):
        _enum(hazard, HAZARDS, path, "hazards", errs)
    if "handling" in obj:
        _enum(obj["handling"], HANDLING, path, "handling", errs)
    outputs = _outputs(obj.get("outputs", []), path, errs)
    if kind == "sensor":
        if not obj.get("outputs"):
            errs.add(path, "outputs", "a sensor has at least one output")
        if "src" not in obj:
            errs.add(path, "src", "a sensor names its source class")
        if "period_ms" not in obj:
            errs.add(path, "period_ms", "a sensor gives its period limits")
    else:
        if obj.get("outputs"):
            errs.add(path, "outputs", "an actuator has no outputs")
        if "period_ms" in obj:
            errs.add(path, "period_ms", "an actuator has no period")
    p_min = p_max = p_default = None
    if "period_ms" in obj and check(obj["period_ms"], PERIOD, errs, path, "period_ms."):
        pr = obj["period_ms"]
        p_min, p_max, p_default = pr["min"], pr.get("max"), pr["default"]
        if not (0 < p_min <= p_default and (p_max is None or p_default <= p_max)):
            errs.add(path, "period_ms", "expected 0 < min <= default <= max")
    params = _params(obj.get("params", {}), path, errs)
    wokwi = obj.get("wokwi")
    if wokwi is not None and check(wokwi, WOKWI, errs, path, "wokwi."):
        if ("part" in wokwi) == ("chip" in wokwi):
            errs.add(path, "wokwi", "give exactly one of part or chip")
        label = wokwi.get("label")
        if label is not None and "simulated" not in label.lower():
            errs.add(path, "wokwi.label", "must say it is simulated")
    if len(errs.lines) > n0:
        return None
    supply, io = obj.get("supply_v"), obj.get("io_v")
    return Part(
        path=path,
        id=pid,
        kind=kind,
        src=obj.get("src"),
        driver=driver,
        macro=obj["macro"],
        pins=pins,
        i2c_addr=i2c_addr,
        i2c_max_hz=i2c_hz,
        supply_v=(float(supply[0]), float(supply[1])) if supply else None,
        rails=tuple(obj.get("rails", ())),
        io_v=(float(io[0]), float(io[1])) if io else None,
        contact=contact,
        hazards=tuple(obj.get("hazards", ())),
        handling=obj.get("handling"),
        outputs=outputs,
        commands=tuple(obj.get("commands", ())),
        period_min_ms=p_min,
        period_max_ms=p_max,
        period_default_ms=p_default,
        params=params,
        wiring_notes=tuple(obj.get("wiring_notes", ())),
    )


# boards/<board>.json


def _placement(raw: Any, path: str, f: str, errs: Errors) -> Placement | None:
    if not check(raw, PLACEMENT, errs, path, f + "."):
        return None
    n0 = len(errs.lines)
    if not all(isinstance(v, str) and v for v in raw["pins"].values()):
        errs.add(path, f + ".pins", "expected role -> pin label")
    period = raw.get("period_ms")
    if isinstance(period, dict):
        if not all(is_num(v) and v > 0 for v in period.values()):
            errs.add(path, f + ".period_ms", "expected indicator -> milliseconds above 0")
    elif period is not None and period <= 0:
        errs.add(path, f + ".period_ms", "expected milliseconds above 0")
    params = raw.get("params", {})
    if not all(is_num(v) for v in params.values()):
        errs.add(path, f + ".params", "expected name -> number")
    if "enclosure" in raw:
        _enum(raw["enclosure"], ENCLOSURES, path, f + ".enclosure", errs)
    if "as" in raw and not MACRO_RE.match(raw["as"]):
        errs.add(path, f + ".as", f"{raw['as']!r} is not an UPPER_SNAKE macro prefix")
    if len(errs.lines) > n0:
        return None
    return Placement(
        part=raw["part"],
        node=raw["node"],
        pins=dict(raw["pins"]),
        period_ms=dict(period) if isinstance(period, dict) else period,
        params={k: float(v) for k, v in params.items()},
        supply=raw.get("supply"),
        outputs=tuple(raw["outputs"]) if "outputs" in raw else None,
        enabled=raw.get("enabled", True),
        enclosure=raw.get("enclosure"),
        level_shifted=raw.get("level_shifted", False),
        macro_as=raw.get("as"),
    )


def _link(obj: dict, path: str, errs: Errors) -> tuple[str | None, int | None]:
    link = obj["link"]
    if obj["mcu"] == "host":
        if link is not None:
            errs.add(path, "link", "a host board has no link")
        return None, None
    if link is None:
        errs.add(path, "link", "a board with a microcontroller has a link")
        return None, None
    if not check(link, LINK, errs, path, "link.") or not _enum(
        link["transport"], TRANSPORTS, path, "link.transport", errs
    ):
        return None, None
    transport, baud = link["transport"], link.get("baud")
    if transport == "serial" and (baud is None or baud <= 0):
        errs.add(path, "link.baud", "a serial link gives its baud rate")
    if transport == "mqtt" and baud is not None:
        errs.add(path, "link.baud", "an MQTT link has no baud rate")
    return transport, baud


def _power(obj: dict, path: str, errs: Errors) -> tuple[str | None, Pack | None]:
    power = obj["power"]
    if not check(power, POWER, errs, path, "power."):
        return None, None
    _enum(power["source"], POWER_SOURCES, path, "power.source", errs)
    pack = None
    if "pack" in power and check(power["pack"], PACK, errs, path, "power.pack."):
        pk = power["pack"]
        if pk["cells"] < 1:
            errs.add(path, "power.pack.cells", "at least one cell")
        _enum(pk["chemistry"], frozenset(CELL_V), path, "power.pack.chemistry", errs)
        _enum(pk["size"], PACK_SIZES, path, "power.pack.size", errs)
        pack = Pack(pk["cells"], pk["chemistry"], pk["size"], pk["pin"])
    return power["source"], pack


def parse_board(obj: Any, path: str, stem: str, errs: Errors) -> Board | None:
    if not check(obj, BOARD, errs, path) or not _schema_ok(obj, path, errs):
        return None
    n0 = len(errs.lines)
    if obj["board"] != stem:
        errs.add(path, "board", f"{obj['board']} does not match the file name {stem}.json")
    _enum(obj["status"], STATUSES, path, "status", errs)
    if not _enum(obj["mcu"], frozenset(MCUS), path, "mcu", errs):
        return None
    transport, baud = _link(obj, path, errs)
    source, pack = _power(obj, path, errs)
    nodes = obj["nodes"]
    for node in nodes:
        if not NODE_RE.match(node) or len(node) > NODE_MAX:
            errs.add(
                path,
                "nodes",
                f"{node!r} is not a node id (lower-case word, dash, number; "
                f"at most {NODE_MAX} characters)",
            )
    _no_repeats(nodes, path, "nodes", errs)
    ack = obj.get("ack_node")
    if ack is not None and ack not in nodes:
        errs.add(path, "ack_node", f"{ack} is not one of this board's nodes")
    placements = [
        _placement(raw, path, f"placements[{n}]", errs) for n, raw in enumerate(obj["placements"])
    ]
    if len(errs.lines) > n0:
        return None
    return Board(
        path=path,
        id=obj["board"],
        status=obj["status"],
        mcu=obj["mcu"],
        fqbn=obj.get("fqbn"),
        sketch=obj.get("sketch"),
        twins=tuple(obj.get("twins", ())),
        transport=transport,
        baud=baud,
        power_source=source or "",
        pack=pack,
        nodes=tuple(nodes),
        ack_node=ack,
        default=obj.get("default", False),
        placements=tuple(p for p in placements if p is not None),
    )
```

`hub/registry/loader.py` (named `loader`, not `load`, so the package's `load` function does not shadow the module):

```python
"""Read registry/ from disk, parse every file, check across files, hash (D46 §5, §6.1)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from hub.registry.model import Board, Part, Registry
from hub.registry.parse import parse_board, parse_core, parse_indicators, parse_part
from hub.registry.safety import check_safety
from hub.registry.schema import Errors, RegistryError
from hub.registry.validate import check_all

TOP_FILES = ("indicators.json", "core.json")


def load(root: Path) -> Registry:
    """The validated registry in `root`. Raises RegistryError with one line per problem."""
    root = Path(root)
    if not root.is_dir():
        raise RegistryError([f"{root}: no registry folder"])
    label = root.name
    errs = Errors()
    files = _read(root, label, errs)
    errs.raise_if_any()

    def where(rel: str) -> str:
        return f"{label}/{rel}"

    indicators = parse_indicators(files["indicators.json"], where("indicators.json"), errs)
    core = parse_core(files["core.json"], where("core.json"), errs)
    parts: dict[str, Part] = {}
    boards: list[Board] = []
    for rel in sorted(files):
        if rel.startswith("parts/"):
            part = parse_part(files[rel], where(rel), Path(rel).stem, errs)
            if part is not None:
                parts[part.id] = part
        elif rel.startswith("boards/"):
            board = parse_board(files[rel], where(rel), Path(rel).stem, errs)
            if board is not None:
                boards.append(board)
    errs.raise_if_any()
    assert core is not None
    reg = Registry(
        root=root,
        label=label,
        hash=_hash(files),
        indicators=indicators,
        core=core,
        parts=parts,
        boards=tuple(boards),
    )
    check_all(reg, errs)
    check_safety(reg, errs)
    errs.raise_if_any()
    return reg


def _read(root: Path, label: str, errs: Errors) -> dict[str, object]:
    for name in TOP_FILES:
        if not (root / name).is_file():
            errs.add(f"{label}/{name}", "", "missing")
    files: dict[str, object] = {}
    for path in sorted(root.rglob("*.json")):
        rel = path.relative_to(root).as_posix()
        in_folder = rel.count("/") == 1 and rel.startswith(("parts/", "boards/"))
        if rel not in TOP_FILES and not in_folder:
            errs.add(
                f"{label}/{rel}",
                "",
                "unexpected file: registry/ holds indicators.json, "
                "core.json, parts/*.json and boards/*.json",
            )
            continue
        try:
            files[rel] = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            errs.add(f"{label}/{rel}", "", f"not valid JSON ({e})")
    return files


def _hash(files: dict[str, object]) -> str:
    h = hashlib.sha256()
    for rel in sorted(files):
        canon = json.dumps(files[rel], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        h.update(f"{rel}\n{canon}\n".encode())
    return h.hexdigest()
```

`hub/registry/__init__.py`:

```python
"""Module registry (D46): the one source for indicators, devices, nodes, parts and boards.

`load(root)` reads and validates a registry folder; `load_default()` reads the repository's
`registry/` (or `HUB_REGISTRY_DIR`) once per process. Any problem raises RegistryError.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path

from hub.registry.loader import load
from hub.registry.model import Board, Core, Indicator, Part, Placement, Registry
from hub.registry.schema import RegistryError

__all__ = [
    "Board",
    "Core",
    "Indicator",
    "Part",
    "Placement",
    "Registry",
    "RegistryError",
    "default_dir",
    "load",
    "load_default",
]


def default_dir() -> Path:
    env = os.environ.get("HUB_REGISTRY_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[2] / "registry"


@functools.cache
def load_default() -> Registry:
    return load(default_dir())
```

`hub/registry/validate.py` (stub, replaced in Task 3):

```python
"""Rules across files (D46 §5.1-§5.3). Stub: Task 3 of the step-1 plan replaces this file."""

from __future__ import annotations

from hub.registry.model import Registry
from hub.registry.schema import Errors


def check_all(reg: Registry, errs: Errors) -> None:
    return None
```

`hub/registry/safety.py` (stub, replaced in Task 4):

```python
"""Safety rules S1-S6 (D46 §5.4). Stub: Task 4 of the step-1 plan replaces this file."""

from __future__ import annotations

from hub.registry.model import Registry
from hub.registry.schema import Errors


def check_safety(reg: Registry, errs: Errors) -> None:
    return None
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest -q hub/tests/test_registry.py`
Expected: `46 passed`. `hub.contract` does not use the registry yet, so nothing else changes.

- [ ] **Step 6: Lint and format the new files**

Run: `.venv/bin/ruff check hub/registry hub/tests/registry_helpers.py hub/tests/test_registry.py && .venv/bin/ruff format --check hub/registry hub/tests/registry_helpers.py hub/tests/test_registry.py`
Expected: `All checks passed!`, and every file reported as already formatted.

- [ ] **Step 7: Commit**

```bash
git add registry hub/registry hub/tests/registry_helpers.py hub/tests/test_registry.py
git commit -m "feat(registry): registry files, loader and local checks (D46 step 1)"
```

---

### Task 3: Rules across files

**Files:**
- Replace: `hub/registry/validate.py` (the Task 2 stub)
- Test: `hub/tests/test_registry_rules.py`

**Interfaces:**
- Consumes: `Registry`, `Board`, `Part`, `Placement`, `output_inds`, `periods_ms` (`model`); `Errors`, `num` (`schema`); `MCUS`, `Mcu.misfit` (`mcu`).
- Produces: `check_all(reg, errs)`, plus the constants `LINE_BYTES = 140` and `MQTT_MAX_PER_NODE = 10.0`.

- [ ] **Step 1: Write the tests**

```python
"""D46 registry: rules across files (references, nodes, producers, pins, buses, rates), one failing
case each (D46 §5.1-§5.3)."""

from __future__ import annotations

import pytest

from hub.tests.registry_helpers import (
    COPY,
    E,
    addp,
    copy_registry,
    delp,
    errors_after,
    loads_after,
    setp,
)

SECOND_DHT = {"part": "DHT11", "node": "cabin-1", "pins": {"data": "D7"}, "supply": "5V"}
SCD41_ON_UNO = {"part": "SCD41", "node": "cabin-1", "pins": {"sda": "A4", "scl": "A5"},
                "outputs": ["cabin_co2"], "supply": "5V"}  # fmt: skip

CASES = [
    ("duplicate indicator",
     [E("indicators.json", addp("indicators", {"id": "hr", "unit": "bpm", "scope": "body",
                                               "label": "x"}))],
     "hr is listed twice"),
    ("derived from unknown", [E("indicators.json", setp("indicators.14.derived.from", "cabin_o2"))],
     "cabin_o2 is not an indicator"),
    ("output indicator", [E("parts/DHT11.json", setp("outputs.0.ind", "cabin_tmp"))],
     "outputs[0].ind: cabin_tmp is not an indicator"),
    ("output derived", [E("parts/DHT11.json", setp("outputs.0.ind", "cabin_ppco2"))],
     "cabin_ppco2 is derived by the hub"),
    ("output flag", [E("parts/DHT11.json", setp("outputs.0.flags", ["wet"]))],
     "wet is not a flag in core.json"),
    ("ok is not raised", [E("parts/DHT11.json", setp("outputs.0.flags", ["ok"]))],
     "ok is not a node-raised flag"),
    ("needs a flag", [E("parts/MAX30102.json", setp("outputs.0.needs", {"stale": "motion"}))],
     "needs stale, which is not one of this output's flags"),
    ("command", [E("parts/servo.json", setp("commands", ["spin"]))],
     "spin is not a command in core.json"),
    ("source", [E("parts/DHT11.json", setp("src", "lab"))], "lab is not a source in core.json"),
    ("sensor id vs core device", [E("core.json", addp("devices", "DHT11"))],
     "DHT11 is also a core.json device"),
    ("derived from derived",
     [E("indicators.json", addp("indicators", {"id": "cabin_x", "unit": "x", "scope": "cabin",
                                               "label": "x",
                                               "derived": {"from": "cabin_ppco2", "fn": "x"}}))],
     "cabin_ppco2 is itself derived"),
    ("node on two boards",
     [COPY("boards/tilt-1.json", "boards/tilt-2.json", setp("board", "tilt-2"),
           setp("default", True))],
     "tilt-1 is already a node of"),
    ("core node on a board", [E("core.json", addp("nodes", "tilt-1"))],
     "tilt-1 is a core.json node and a board node"),
    ("unknown part", [E("boards/uno-1.json", setp("placements.0.part", "DHT99"))],
     "DHT99 has no file in parts/"),
    ("node not on board", [E("boards/uno-1.json", setp("placements.0.node", "tilt-1"))],
     "placements[0].node: tilt-1 is not one of this board's nodes"),
    ("pin roles", [E("boards/uno-1.json", setp("placements.0.pins", {"dat": "D2"}))],
     "expected the roles data, got dat"),
    ("outputs subset", [E("boards/uno-1.json", setp("placements.0.outputs", ["cabin_p"]))],
     "cabin_p is not an output of DHT11"),
    ("unknown param", [E("boards/tilt-1.json", setp("placements.0.params.speed", 3))],
     "KY017 has no param speed"),
    ("param limits", [E("boards/tilt-1.json", setp("placements.0.params.debounce_ms", 5))],
     "5 is outside KY017's limits [50, 1000]"),
    ("period too short", [E("boards/uno-1.json", setp("placements.0.period_ms", 500))],
     "is below DHT11's minimum period of 1000 ms"),
    ("period map key",
     [E("boards/vitals-1.json", setp("placements.0.period_ms", {"hr": 1000, "pulse": 10}))],
     "period_ms.pulse: pulse is not an output of this placement"),
    ("actuator period", [E("boards/uno-1.json", setp("placements.1.period_ms", 100))],
     "buzzer-passive is an actuator: it has no period"),
    ("macro twice", [E("boards/uno-1.json", addp("placements", SECOND_DHT))],
     "macro prefix DHT is already used by placements[0]"),
    ("one producer per node and indicator",
     [E("boards/uno-1.json", addp("placements", {**SECOND_DHT, "as": "DHT_B"}))],
     "cabin-1 already gets cabin_temp from"),
    ("no driver yet", [E("boards/uno-1.json", addp("placements", SCD41_ON_UNO))],
     "SCD41 has no firmware driver yet"),
    ("flag needs a producer", [E("boards/vitals-1.json", setp("placements.2.enabled", False))],
     "MAX30102 raises motion on hr only with a motion output on this board"),
    ("second serial board",
     [COPY("boards/uno-1.json", "boards/uno-2.json", setp("board", "uno-2"),
           setp("nodes", ["cabin-2"]), delp("ack_node"), setp("placements", []),
           setp("default", True))],
     "uno-2 is a second active serial board"),
    ("not a pin", [E("boards/uno-1.json", setp("placements.0.pins.data", "D20"))],
     "D20 is not a pin on atmega328p"),
    ("reserved pin", [E("boards/uno-1.json", setp("placements.0.pins.data", "D0"))],
     "placements[0].pins.data: D0 is reserved (USB serial)"),
    ("boot pin", [E("boards/tilt-1.json", setp("placements.0.pins.signal", "D3"))],
     "D3 is reserved (boot pin)"),
    ("analog pin", [E("boards/uno-1.json", setp("placements.4.pins.out", "D7"))],
     "D7 is not an analog pin"),
    ("pwm pin", [E("boards/uno-1.json", setp("placements.3.pins.signal", "D7"))],
     "D7 is not a PWM pin"),
    ("shared pin", [E("boards/uno-1.json", setp("placements.5.pins.out", "A0"))],
     "A0 is also used by placements[4]"),
    ("a disabled part keeps its pins", [E("boards/uno-1.json", setp("placements.0.pins.data", "D3"))],
     "D3 is also used by placements[0]"),
    ("i2c pin", [E("boards/vitals-1.json", setp("placements.0.pins.sda", "D5"))],
     "D5 is not the I2C SDA pin (D2)"),
    ("i2c address clash", [E("parts/MPU6050.json", setp("i2c.addr", "0x57"))],
     "I2C address 0x57 is also used by placements[0]"),
    ("serial budget",
     [E("boards/uno-1.json", setp("link.baud", 9600), setp("placements.2.enabled", True))],
     "needs more than half of 9600 baud"),
    ("mqtt budget",
     [E("parts/MAX30102.json", setp("period_ms.min", 10)),
      E("boards/vitals-1.json", setp("placements.0.period_ms", {"hr": 50, "spo2": 4000}))],
     "vitals-1 sends 21.8 messages/s, more than 10"),
    ("shared sketch needs a default",
     [COPY("boards/tilt-1.json", "boards/cabin-2.json", setp("board", "cabin-2"),
           setp("nodes", ["cabin-2"]), setp("placements", []))],
     "firmware/tilt-esp8266 runs on 2 boards"),
]  # fmt: skip


@pytest.mark.parametrize(("edits", "expect"), [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_rule(tmp_path, edits, expect):
    errs = errors_after(copy_registry(tmp_path), edits)
    assert any(expect in line for line in errs), errs


def test_shared_sketch_with_one_default_loads(tmp_path):
    loads_after(
        copy_registry(tmp_path),
        [
            COPY("boards/tilt-1.json", "boards/cabin-2.json", setp("board", "cabin-2"),
                 setp("nodes", ["cabin-2"]), setp("placements", []), setp("default", True)),
        ],
    )  # fmt: skip


def test_vitals_bus_shares_its_i2c_pins(tmp_path):
    """Three I2C parts on D2/D1 with three addresses is the archived vitals node as designed."""
    loads_after(copy_registry(tmp_path), [])
```

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/bin/python -m pytest -q hub/tests/test_registry_rules.py`
Expected: the parametrized cases fail with `Failed: DID NOT RAISE <class 'hub.registry.schema.RegistryError'>`; the two loading tests pass.

- [ ] **Step 3: Replace the stub**

```python
"""Rules across files: references, nodes, producers, pins, buses and rates (D46 §5.1-§5.3)."""

from __future__ import annotations

from hub.registry.mcu import MCUS, Mcu
from hub.registry.model import Board, Part, Placement, Registry, output_inds, periods_ms
from hub.registry.schema import Errors, num

LINE_BYTES = 140  # a contract-v1 line on the serial link, with margin
MQTT_MAX_PER_NODE = 10.0  # team value: the 32-slot ring then holds at least 3 s of a reconnect


def check_all(reg: Registry, errs: Errors) -> None:
    _indicators(reg, errs)
    for part in reg.parts.values():
        _part(reg, part, errs)
    _nodes(reg, errs)
    for board in reg.boards:
        _board(reg, board, errs)
    _producers(reg, errs)
    _serial_boards(reg, errs)
    _shared_sketches(reg, errs)


def _indicators(reg: Registry, errs: Errors) -> None:
    path = reg.file("indicators.json")
    seen: set[str] = set()
    by_id = reg.indicators_by_id
    for n, ind in enumerate(reg.indicators):
        f = f"indicators[{n}]"
        if ind.id in seen:
            errs.add(path, f + ".id", f"{ind.id} is listed twice")
        seen.add(ind.id)
        if ind.derived_from is not None:
            src = by_id.get(ind.derived_from)
            if src is None:
                errs.add(path, f + ".derived.from", f"{ind.derived_from} is not an indicator")
            elif src.derived_from is not None:
                errs.add(path, f + ".derived.from", f"{ind.derived_from} is itself derived")


def _part(reg: Registry, part: Part, errs: Errors) -> None:
    inds = reg.indicators_by_id
    for n, out in enumerate(part.outputs):
        f = f"outputs[{n}]"
        ind = inds.get(out.ind)
        if ind is None:
            errs.add(part.path, f + ".ind", f"{out.ind} is not an indicator")
        elif ind.derived_from is not None:
            errs.add(part.path, f + ".ind", f"{out.ind} is derived by the hub, not sent by a part")
        for flag in out.flags:
            if flag == "ok":
                errs.add(part.path, f + ".flags", "ok is not a node-raised flag")
            elif flag not in reg.core.flags:
                errs.add(part.path, f + ".flags", f"{flag} is not a flag in core.json")
        for flag, needed in out.needs.items():
            if flag not in out.flags:
                errs.add(
                    part.path,
                    f + ".needs",
                    f"needs {flag}, which is not one of this output's flags",
                )
            if needed not in inds:
                errs.add(part.path, f + ".needs", f"{needed} is not an indicator")
    for cmd in part.commands:
        if cmd not in reg.core.commands:
            errs.add(part.path, "commands", f"{cmd} is not a command in core.json")
    if part.src is not None and part.src not in reg.core.sources:
        errs.add(part.path, "src", f"{part.src} is not a source in core.json")
    if part.kind == "sensor" and part.id in reg.core.devices:
        errs.add(part.path, "id", f"{part.id} is also a core.json device")


def _nodes(reg: Registry, errs: Errors) -> None:
    owner: dict[str, str] = {}
    core_nodes = set(reg.core.nodes)
    for board in reg.boards:
        for node in board.nodes:
            if node in core_nodes:
                errs.add(board.path, "nodes", f"{node} is a core.json node and a board node")
            elif node in owner:
                errs.add(board.path, "nodes", f"{node} is already a node of {owner[node]}")
            else:
                owner[node] = board.path


def _board(reg: Registry, board: Board, errs: Errors) -> None:
    mcu = MCUS[board.mcu]
    macros: dict[str, int] = {}
    users: dict[str, list[tuple[int, str]]] = {}
    addrs: dict[int, int] = {}
    for n, pl in enumerate(board.placements):
        f = f"placements[{n}]"
        part = reg.parts.get(pl.part)
        if part is None:
            errs.add(board.path, f + ".part", f"{pl.part} has no file in parts/")
            continue
        if pl.node not in board.nodes:
            errs.add(board.path, f + ".node", f"{pl.node} is not one of this board's nodes")
        roles = sorted(p.role for p in part.pins)
        if sorted(pl.pins) != roles:
            got = ", ".join(sorted(pl.pins)) or "none"
            errs.add(board.path, f + ".pins", f"expected the roles {', '.join(roles)}, got {got}")
        _outputs_and_periods(board, f, pl, part, errs)
        _params(board, f, pl, part, errs)
        macro = pl.macro_as or part.macro
        if macro in macros:
            errs.add(
                board.path,
                f + ".as",
                f'macro prefix {macro} is already used by placements[{macros[macro]}]; set "as"',
            )
        else:
            macros[macro] = n
        if pl.enabled and part.driver == "none":
            errs.add(board.path, f + ".enabled", f"{part.id} has no firmware driver yet")
        _pins(board, mcu, n, pl, part, users, errs)
        if part.i2c_addr is not None:
            if part.i2c_addr in addrs:
                errs.add(
                    board.path,
                    f + ".part",
                    f"I2C address 0x{part.i2c_addr:02X} is also used by "
                    f"placements[{addrs[part.i2c_addr]}]",
                )
            else:
                addrs[part.i2c_addr] = n
    _needs(reg, board, errs)
    _rates(reg, board, errs)


def _outputs_and_periods(board: Board, f: str, pl: Placement, part: Part, errs: Errors) -> None:
    own = {o.ind for o in part.outputs}
    for ind in pl.outputs or ():
        if ind not in own:
            errs.add(board.path, f + ".outputs", f"{ind} is not an output of {part.id}")
    if part.kind == "actuator":
        if pl.period_ms is not None:
            errs.add(board.path, f + ".period_ms", f"{part.id} is an actuator: it has no period")
        return
    inds = set(output_inds(pl, part))
    if isinstance(pl.period_ms, dict):
        for ind in pl.period_ms:
            if ind not in inds:
                errs.add(
                    board.path, f"{f}.period_ms.{ind}", f"{ind} is not an output of this placement"
                )
    for ind, ms in periods_ms(pl, part).items():
        if part.period_min_ms is not None and ms < part.period_min_ms:
            errs.add(
                board.path,
                f + ".period_ms",
                f"{num(ms)} ms for {ind} is below {part.id}'s minimum period of "
                f"{num(part.period_min_ms)} ms",
            )
        if part.period_max_ms is not None and ms > part.period_max_ms:
            errs.add(
                board.path,
                f + ".period_ms",
                f"{num(ms)} ms for {ind} is above {part.id}'s maximum period of "
                f"{num(part.period_max_ms)} ms",
            )


def _params(board: Board, f: str, pl: Placement, part: Part, errs: Errors) -> None:
    for name, val in pl.params.items():
        spec = part.params.get(name)
        if spec is None:
            errs.add(board.path, f"{f}.params.{name}", f"{part.id} has no param {name}")
        elif not spec.min <= val <= spec.max:
            errs.add(
                board.path,
                f"{f}.params.{name}",
                f"{num(val)} is outside {part.id}'s limits [{num(spec.min)}, {num(spec.max)}]",
            )


def _pins(
    board: Board,
    mcu: Mcu,
    n: int,
    pl: Placement,
    part: Part,
    users: dict[str, list[tuple[int, str]]],
    errs: Errors,
) -> None:
    kinds = {p.role: p.kind for p in part.pins}
    for role, label in pl.pins.items():
        kind = kinds.get(role)
        if kind is None:
            continue  # the role mismatch is already reported
        f = f"placements[{n}].pins.{role}"
        if label not in mcu.pins:
            errs.add(board.path, f, f"{label} is not a pin on {board.mcu}")
            continue
        why = mcu.reserved.get(label)
        if why is not None:
            errs.add(board.path, f, f"{label} is reserved ({why})")
            continue
        misfit = mcu.misfit(label, kind)
        if misfit is not None:
            errs.add(board.path, f, f"{label} {misfit}")
            continue
        for m, other in users.get(label, []):
            if not (kind == other and kind.startswith("i2c-")):  # only an I2C bus is shared
                errs.add(board.path, f, f"{label} is also used by placements[{m}]")
                break
        users.setdefault(label, []).append((n, kind))


def _needs(reg: Registry, board: Board, errs: Errors) -> None:
    have: set[str] = set()
    for pl in board.placements:
        part = reg.parts.get(pl.part)
        if part is not None and pl.enabled:
            have.update(output_inds(pl, part))
    for n, pl in enumerate(board.placements):
        part = reg.parts.get(pl.part)
        if part is None or not pl.enabled:
            continue
        mine = set(output_inds(pl, part))
        for out in part.outputs:
            if out.ind not in mine:
                continue
            for flag, needed in out.needs.items():
                if needed not in have:
                    errs.add(
                        board.path,
                        f"placements[{n}]",
                        f"{part.id} raises {flag} on {out.ind} only with a {needed} "
                        "output on this board",
                    )


def _rates(reg: Registry, board: Board, errs: Errors) -> None:
    if board.transport is None:
        return
    per_node: dict[str, float] = {}
    for pl in board.placements:
        part = reg.parts.get(pl.part)
        if part is None or not pl.enabled or part.kind != "sensor":
            continue
        for ms in periods_ms(pl, part).values():
            per_node[pl.node] = per_node.get(pl.node, 0.0) + 1000.0 / ms
    if board.transport == "serial" and board.baud:
        total = sum(per_node.values())
        limit = 0.5 * board.baud / (LINE_BYTES * 10)
        if total > limit:
            errs.add(
                board.path,
                "link.baud",
                f"{total:.1f} lines/s needs more than half of {board.baud} baud "
                f"(at most {limit:.1f} lines/s of {LINE_BYTES} bytes)",
            )
    elif board.transport == "mqtt":
        for node, rate in per_node.items():
            if rate > MQTT_MAX_PER_NODE:
                errs.add(
                    board.path,
                    "placements",
                    f"{node} sends {rate:.1f} messages/s, more than "
                    f"{num(MQTT_MAX_PER_NODE)} (team value)",
                )


def _producers(reg: Registry, errs: Errors) -> None:
    seen: dict[tuple[str, str], str] = {}
    for board in reg.boards:
        for n, pl in enumerate(board.placements):
            part = reg.parts.get(pl.part)
            if part is None or not pl.enabled:
                continue
            for ind in output_inds(pl, part):
                key = (pl.node, ind)
                if key in seen:
                    errs.add(
                        board.path,
                        f"placements[{n}]",
                        f"{pl.node} already gets {ind} from {seen[key]}: one producer per "
                        "node and indicator",
                    )
                else:
                    seen[key] = f"{board.path} placements[{n}]"


def _serial_boards(reg: Registry, errs: Errors) -> None:
    first: str | None = None
    for board in reg.boards:
        if board.status != "active" or board.transport != "serial":
            continue
        if first is None:
            first = board.id
        else:
            errs.add(
                board.path,
                "link",
                f"{board.id} is a second active serial board; RigLink reads one port "
                f"({first} is the first)",
            )


def _shared_sketches(reg: Registry, errs: Errors) -> None:
    by_sketch: dict[str, list[Board]] = {}
    for board in reg.boards:
        if board.sketch:
            by_sketch.setdefault(board.sketch, []).append(board)
    for sketch, boards in by_sketch.items():
        if len(boards) > 1 and sum(b.default for b in boards) != 1:
            for board in boards:
                errs.add(
                    board.path,
                    "default",
                    f'{sketch} runs on {len(boards)} boards: mark exactly one with "default": true',
                )
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest -q hub/tests/test_registry.py hub/tests/test_registry_rules.py`
Expected: `87 passed`.

- [ ] **Step 5: Lint, format and commit**

```bash
.venv/bin/ruff check hub/registry hub/tests/test_registry_rules.py && .venv/bin/ruff format --check hub/registry/validate.py hub/tests/test_registry_rules.py
git add hub/registry/validate.py hub/tests/test_registry_rules.py
git commit -m "feat(registry): references, nodes, producers, pins, I2C and rate rules (D46 step 1)"
```

---

### Task 4: Safety rules S1–S6

**Files:**
- Replace: `hub/registry/safety.py` (the Task 2 stub)
- Test: `hub/tests/test_registry_safety.py`

**Interfaces:**
- Consumes: `Registry`, `Board`, `Part`, `Placement` (`model`); `Errors`, `num` (`schema`); `MCUS`, `CELL_V`, `Mcu` (`mcu`).
- Produces: `check_safety(reg, errs)`. Every message starts with its rule number (`S1:` to `S6:`).

What the rules mean on today's files:
- **S4 applies to enabled placements only.** `NTC` and `KY039` are `contact: "body"` parts on the USB-powered UNO, disabled since D40. Enabling either now fails S4, which is checklist rule 3 ("the Pi and the exercise rig's USB host never touch a person's sensors").
- **S3 and S6 apply to every placement,** enabled or not.

- [ ] **Step 1: Write the tests**

```python
"""D46 registry: safety rules S1-S6 are hard failures, one case each (D46 §5.4)."""

from __future__ import annotations

import pytest

from hub.tests.registry_helpers import E, addp, copy_registry, delp, errors_after, loads_after, setp

DHT_ON_HUB = {"part": "DHT11", "node": "cabin-1", "pins": {"data": "D2"}, "supply": "5V"}
VIN_PACK = {"cells": 4, "chemistry": "nimh", "size": "AA", "pin": "VIN"}

CASES = [
    ("S1 nothing on the Pi header", [E("boards/hub.json", addp("placements", DHT_ON_HUB))],
     "S1: nothing goes on the Pi header"),
    ("S2 two Ni-MH on VIN", [E("boards/tilt-1.json", setp("power.pack.cells", 2))],
     "S2: 2 x nimh gives 2.4-2.8 V, outside VIN's (4.5, 6] V"),
    ("S2 three alkaline on 3V3",
     [E("boards/tilt-1.json", setp("power.pack", {"cells": 3, "chemistry": "alkaline",
                                                  "size": "AA", "pin": "3V3"}))],
     "S2: 3 x alkaline gives 4.5-4.8 V, outside 3V3's [2.7, 3.6] V"),
    ("S2 two Ni-MH on 3V3",
     [E("boards/tilt-1.json", setp("power.pack", {**VIN_PACK, "cells": 2, "pin": "3V3"}))],
     "S2: 2 x nimh gives 2.4-2.8 V, outside 3V3's"),
    ("S2 coin cell",
     [E("boards/tilt-1.json", setp("power.pack", {"cells": 1, "chemistry": "lithium",
                                                  "size": "CR2032", "pin": "3V3"}))],
     "S2: a CR2032 coin cell cannot supply Wi-Fi bursts"),
    ("S2 pack missing", [E("boards/tilt-1.json", delp("power.pack"))],
     "S2: a pack-powered board describes its pack"),
    ("S2 two sources", [E("boards/uno-1.json", setp("power.pack", VIN_PACK))],
     "S2: one power source per board, not usb-host and a pack"),
    ("S2 no pack window",
     [E("boards/uno-1.json", setp("power", {"source": "pack", "pack": VIN_PACK}))],
     "S2: atmega328p takes no cell pack on VIN"),
    ("S3 mercury handling", [E("parts/KY017.json", delp("handling"))],
     'S3: KY017 holds mercury: set "handling": "adults_only"'),
    ("S3 mercury enclosure", [E("boards/tilt-1.json", delp("placements.0.enclosure"))],
     'S3: KY017 holds mercury: its placement needs "enclosure": "sealed"'),
    ("S4 body part on a computer's USB", [E("boards/vitals-1.json", setp("power.source", "usb-host"))],
     "S4: MAX30102 touches a person"),
    ("S4 body part on a serial link",
     [E("boards/vitals-1.json", setp("link", {"transport": "serial", "baud": 250000}))],
     "S4: MAX30102 touches a person"),
    ("S4 finger pulse module on the UNO", [E("boards/uno-1.json", setp("placements.5.enabled", True))],
     "S4: KY039 touches a person"),
    ("S5 rail the part refuses", [E("boards/tilt-1.json", setp("placements.0.supply", "VIN"))],
     "S5: KY017 may be powered from 3V3, 5V, not VIN"),
    ("S5 rail the board lacks", [E("boards/tilt-1.json", setp("placements.0.supply", "5V"))],
     "S5: esp8266 has no 5V rail"),
    ("S5 rail missing", [E("boards/uno-1.json", delp("placements.0.supply"))],
     "S5: DHT11 needs a supply rail"),
    ("S5 no rail for a pin-driven part", [E("boards/uno-1.json", setp("placements.1.supply", "5V"))],
     "S5: buzzer-passive takes no supply rail"),
    ("S6 logic level", [E("parts/DHT11.json", setp("io_v", [1.8, 3.6]))],
     "S6: atmega328p logic is 5 V, outside DHT11's 1.8-3.6 V"),
]  # fmt: skip


@pytest.mark.parametrize(("edits", "expect"), [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_rule(tmp_path, edits, expect):
    errs = errors_after(copy_registry(tmp_path), edits)
    assert any(expect in line for line in errs), errs


def test_s6_level_shifted_breakout_passes(tmp_path):
    loads_after(
        copy_registry(tmp_path),
        [
            E("parts/DHT11.json", setp("io_v", [1.8, 3.6])),
            E("boards/uno-1.json", setp("placements.0.level_shifted", True)),
        ],
    )


def test_bench_packs_pass(tmp_path):
    """The two D40 packs: 4 x Ni-MH on VIN (chosen) and 2 x alkaline on 3V3."""
    root = copy_registry(tmp_path)
    loads_after(root, [])
    alkaline = {"cells": 2, "chemistry": "alkaline", "size": "AAA", "pin": "3V3"}
    loads_after(root, [E("boards/tilt-1.json", setp("power.pack", alkaline))])
```

- [ ] **Step 2: Run them and see them fail**

Run: `.venv/bin/python -m pytest -q hub/tests/test_registry_safety.py`
Expected: the 18 parametrized cases fail with `DID NOT RAISE`; `test_s6_level_shifted_breakout_passes` and `test_bench_packs_pass` pass.

- [ ] **Step 3: Replace the stub**

```python
"""Safety rules S1-S6 as hard failures (D46 §5.4). Each message starts with its rule number."""

from __future__ import annotations

from hub.registry.mcu import CELL_V, MCUS, Mcu
from hub.registry.model import Board, Part, Placement, Registry
from hub.registry.schema import Errors, num

BATTERY = frozenset({"usb-bank", "pack"})


def check_safety(reg: Registry, errs: Errors) -> None:
    for part in reg.parts.values():
        if "mercury" in part.hazards and part.handling != "adults_only":
            errs.add(
                part.path, "handling", f'S3: {part.id} holds mercury: set "handling": "adults_only"'
            )
    for board in reg.boards:
        mcu = MCUS[board.mcu]
        if board.mcu == "host" and board.placements:
            errs.add(
                board.path,
                "placements",
                "S1: nothing goes on the Pi header: a host board has no placements",
            )
        _power(board, mcu, errs)
        for n, pl in enumerate(board.placements):
            part = reg.parts.get(pl.part)
            if part is not None:
                _placement(board, mcu, f"placements[{n}]", pl, part, errs)


def _power(board: Board, mcu: Mcu, errs: Errors) -> None:
    pack = board.pack
    if board.power_source == "pack" and pack is None:
        errs.add(board.path, "power.pack", "S2: a pack-powered board describes its pack")
        return
    if board.power_source != "pack" and pack is not None:
        errs.add(
            board.path,
            "power.pack",
            f"S2: one power source per board, not {board.power_source} and a pack",
        )
        return
    if pack is None:
        return
    window = mcu.pack_windows.get(pack.pin)
    if window is None:
        errs.add(board.path, "power.pack.pin", f"S2: {board.mcu} takes no cell pack on {pack.pin}")
        return
    cell_lo, cell_hi = CELL_V[pack.chemistry]
    lo, hi = pack.cells * cell_lo, pack.cells * cell_hi
    w_lo, w_hi, lo_open = window
    too_low = lo <= w_lo if lo_open else lo < w_lo
    if too_low or hi > w_hi:
        bracket = "(" if lo_open else "["
        errs.add(
            board.path,
            "power.pack",
            f"S2: {pack.cells} x {pack.chemistry} gives {lo:.1f}-{hi:.1f} V, outside "
            f"{pack.pin}'s {bracket}{num(w_lo)}, {num(w_hi)}] V",
        )
    if pack.size == "CR2032" and mcu.wifi:
        errs.add(board.path, "power.pack.size", "S2: a CR2032 coin cell cannot supply Wi-Fi bursts")


def _placement(board: Board, mcu: Mcu, f: str, pl: Placement, part: Part, errs: Errors) -> None:
    if "mercury" in part.hazards and pl.enclosure != "sealed":
        errs.add(
            board.path,
            f + ".enclosure",
            f'S3: {part.id} holds mercury: its placement needs "enclosure": "sealed"',
        )
    if (
        part.contact == "body"
        and pl.enabled
        and (board.power_source not in BATTERY or board.transport != "mqtt")
    ):
        errs.add(
            board.path,
            f,
            f"S4: {part.id} touches a person: only on a board powered by usb-bank or pack "
            f"over MQTT, not {board.power_source} over {board.transport or 'no link'}",
        )
    _rail(board, mcu, f, pl, part, errs)
    if (
        part.io_v is not None
        and mcu.logic_v is not None
        and not pl.level_shifted
        and not part.io_v[0] <= mcu.logic_v <= part.io_v[1]
    ):
        errs.add(
            board.path,
            f,
            f"S6: {board.mcu} logic is {num(mcu.logic_v)} V, outside {part.id}'s "
            f"{num(part.io_v[0])}-{num(part.io_v[1])} V: use a level-shifted breakout and "
            'set "level_shifted": true',
        )


def _rail(board: Board, mcu: Mcu, f: str, pl: Placement, part: Part, errs: Errors) -> None:
    if not part.rails:
        if pl.supply is not None:
            errs.add(board.path, f + ".supply", f"S5: {part.id} takes no supply rail")
        return
    if pl.supply is None:
        errs.add(
            board.path,
            f + ".supply",
            f"S5: {part.id} needs a supply rail ({', '.join(part.rails)})",
        )
    elif pl.supply not in part.rails:
        errs.add(
            board.path,
            f + ".supply",
            f"S5: {part.id} may be powered from {', '.join(part.rails)}, not {pl.supply}",
        )
    elif pl.supply not in mcu.rails:
        errs.add(board.path, f + ".supply", f"S5: {board.mcu} has no {pl.supply} rail")
```

- [ ] **Step 4: Run the registry tests**

Run: `.venv/bin/python -m pytest -q hub/tests/test_registry.py hub/tests/test_registry_rules.py hub/tests/test_registry_safety.py`
Expected: `107 passed`.

- [ ] **Step 5: Lint, format and commit**

```bash
.venv/bin/ruff check hub/registry hub/tests/test_registry_safety.py && .venv/bin/ruff format --check hub/registry/safety.py hub/tests/test_registry_safety.py
git add hub/registry/safety.py hub/tests/test_registry_safety.py
git commit -m "feat(registry): safety rules S1-S6 as hard failures (D46 step 1)"
```

---

### Task 5: Build the contract tables from the registry

**Files:**
- Modify: `hub/contract.py` (the tables at lines 10–102 of `239924d`, and `parse_reading`)
- Modify: `hub/ingest.py` (imports, `CREW_SCOPED`, `QUIET_INDS`, derive trigger)
- Modify: `hub/assess.py` (imports, `CREW_SCOPED`, `UNGATED_INDS`)
- Modify: `hub/derive.py` (add `DERIVERS`)
- Test: `hub/tests/test_registry_contract.py`; the gate is `hub/tests/test_registry_migration.py` from Task 1

**Interfaces:**
- Consumes: `load_default()` and `Registry` from Task 2.
- Produces:
  - in `hub.contract`, every name that exists today, plus `REGISTRY`, `DERIVE_FROM`, `CREW_SCOPED`, `QUIET_INDS`, `UNGATED_INDS`, `REJECT_OUTSIDE` and `CODED`;
  - in `hub.derive`, `DERIVERS: dict[str, Callable]`;
  - `hub.ingest.CREW_SCOPED` and `QUIET_INDS`, `hub.assess.CREW_SCOPED` and `UNGATED_INDS`, which stay importable. `hub/buckets.py` imports `CREW_SCOPED` from `hub.assess`.

- [ ] **Step 1: Write the test**

```python
"""D46: hub.contract, hub.ingest and hub.assess read their tables from registry/."""

from __future__ import annotations

import pytest

from hub import assess, contract, ingest
from hub.contract import ContractError, parse_reading
from hub.derive import DERIVERS
from hub.registry import load_default

MASS = {
    "v": 1, "node": "manual", "boot": 0, "seq": 1, "age_ms": 0, "ind": "body_mass", "val": 70.0,
    "unit": "kg", "src": "self", "dev": "manual", "q": ["ok"],
}  # fmt: skip


def test_contract_is_built_from_the_default_registry():
    assert contract.REGISTRY is load_default()
    assert contract.NODES >= set(contract.REGISTRY.board_nodes)


def test_ingest_and_assess_use_the_contract_sets():
    assert ingest.CREW_SCOPED is contract.CREW_SCOPED
    assert ingest.QUIET_INDS is contract.QUIET_INDS
    assert assess.CREW_SCOPED is contract.CREW_SCOPED
    assert assess.UNGATED_INDS is contract.UNGATED_INDS


def test_the_derive_trigger_is_the_derived_source():
    assert contract.DERIVE_FROM == {"cabin_co2"}


def test_every_derived_indicator_has_a_function():
    fns = [i.derived_fn for i in contract.REGISTRY.indicators if i.derived_fn]
    assert fns and all(fn in DERIVERS for fn in fns)


def test_reject_outside_edges_are_inclusive():
    for val in (20, 300):
        parse_reading({**MASS, "val": val})
    for val in (19.99, 300.01):
        with pytest.raises(ContractError, match="bad_value:val"):
            parse_reading({**MASS, "val": val})
```

- [ ] **Step 2: Run it and see it fail**

Run: `.venv/bin/python -m pytest -q hub/tests/test_registry_contract.py`
Expected: collection error `ImportError: cannot import name 'DERIVERS' from 'hub.derive'`.

- [ ] **Step 3: Change `hub/contract.py`**

Replace everything from `INDICATORS: dict[str, str] = {` down to, but not including, `REASON_CODES: tuple[str, ...] = (` with the registry block, and change two checks in `parse_reading`. The whole diff:

```diff
diff --git a/hub/contract.py b/hub/contract.py
index adc96bb..a452c06 100644
--- a/hub/contract.py
+++ b/hub/contract.py
@@ -7,99 +7,45 @@ import math
 from dataclasses import dataclass
 from typing import Any
 
-INDICATORS: dict[str, str] = {
-    "hr": "bpm",
-    "spo2": "%",
-    "skin_temp": "C",
-    "body_temp": "C",
-    "bp_sys": "mmHg",
-    "bp_dia": "mmHg",
-    "glucose": "mg/dL",
-    "sleep_h": "h",
-    "mood": "1-5",
-    "symptom": "code",
-    "cabin_temp": "C",
-    "cabin_rh": "%",
-    "cabin_p": "hPa",
-    "cabin_co2": "ppm",
-    "cabin_lux": "lx",
-    "motion": "g",
-    "load_raw": "N",
-    "tilt": "state",
-    "space_weather": "level",
-    "rad_dose_cum": "mSv",
-    "intake_kcal": "kcal",
-    "intake_protein_g": "g",
-    "intake_carb_g": "g",
-    "intake_fat_g": "g",
-    "intake_water_ml": "mL",
-    "intake_sodium_mg": "mg",
-    "intake_potassium_mg": "mg",
-    "intake_calcium_mg": "mg",
-    "intake_iron_mg": "mg",
-    "intake_vitd_ug": "ug",
-    "body_mass": "kg",
-}
-DERIVED: dict[str, str] = {"cabin_ppco2": "mmHg"}
+from hub.registry import load_default
 
-CABIN_INDS: frozenset[str] = frozenset(
-    {"cabin_temp", "cabin_rh", "cabin_p", "cabin_co2", "cabin_ppco2", "cabin_lux"}
-)
-BODY_INDS: frozenset[str] = frozenset(
-    {
-        "hr", "spo2", "skin_temp", "body_temp", "bp_sys", "bp_dia",
-        "glucose", "sleep_h", "mood", "symptom", "body_mass",
-    }
-)  # fmt: skip
-INTAKE_ORDER: tuple[str, ...] = (
-    "intake_kcal",
-    "intake_protein_g",
-    "intake_carb_g",
-    "intake_fat_g",
-    "intake_water_ml",
-    "intake_sodium_mg",
-    "intake_potassium_mg",
-    "intake_calcium_mg",
-    "intake_iron_mg",
-    "intake_vitd_ug",
-)
+# Every table below is built from registry/ (D46 §6.2): indicators.json, core.json, parts/, boards/.
+REGISTRY = load_default()
+_INDS = REGISTRY.indicators
+
+INDICATORS: dict[str, str] = {i.id: i.unit for i in _INDS if i.derived_from is None}
+DERIVED: dict[str, str] = {i.id: i.unit for i in _INDS if i.derived_from is not None}
+DERIVE_FROM: frozenset[str] = frozenset(i.derived_from for i in _INDS if i.derived_from is not None)
+
+CABIN_INDS: frozenset[str] = frozenset(i.id for i in _INDS if i.scope == "cabin")
+BODY_INDS: frozenset[str] = frozenset(i.id for i in _INDS if i.scope == "body")
+INTAKE_ORDER: tuple[str, ...] = tuple(i.id for i in _INDS if i.scope == "intake")
 INTAKE_INDS: frozenset[str] = frozenset(INTAKE_ORDER)
 INTAKE_UNITS: dict[str, str] = {i: INDICATORS[i] for i in INTAKE_ORDER}
+CREW_SCOPED: frozenset[str] = BODY_INDS | INTAKE_INDS
+QUIET_INDS: frozenset[str] = frozenset(i.id for i in _INDS if i.quiet)
+UNGATED_INDS: frozenset[str] = frozenset(i.id for i in _INDS if not i.assess)
+
+REJECT_OUTSIDE: dict[str, tuple[float, float]] = {
+    i.id: i.reject_outside for i in _INDS if i.reject_outside is not None
+}
 INTAKE_CEILINGS: dict[str, float] = {
-    "intake_kcal": 10000,
-    "intake_protein_g": 500,
-    "intake_carb_g": 1000,
-    "intake_fat_g": 500,
-    "intake_water_ml": 10000,
-    "intake_sodium_mg": 30000,
-    "intake_potassium_mg": 30000,
-    "intake_calcium_mg": 20000,
-    "intake_iron_mg": 1000,
-    "intake_vitd_ug": 5000,
+    i: REJECT_OUTSIDE[i][1] for i in INTAKE_ORDER if i in REJECT_OUTSIDE
 }
-BODY_MASS_RANGE: tuple[float, float] = (20.0, 300.0)
+BODY_MASS_RANGE: tuple[float, float] = REJECT_OUTSIDE.get("body_mass", (-math.inf, math.inf))
+CODED: dict[str, frozenset[str]] = {i.id: frozenset(i.codes) for i in _INDS if i.codes}
+SYMPTOM_CODES: frozenset[str] = CODED.get("symptom", frozenset())
 
-NODES: frozenset[str] = frozenset(
-    {"vitals-1", "cabin-1", "exercise-1", "strap-1", "manual", "camera", "sim-1", "nasa", "food",
-     "tilt-1", "ring-1"}
-)
-SOURCES: frozenset[str] = frozenset({"certified", "hobby", "self", "nasa", "replay"})
+NODES: frozenset[str] = frozenset(REGISTRY.board_nodes) | frozenset(REGISTRY.core.nodes)
+SOURCES: frozenset[str] = frozenset(REGISTRY.core.sources)
 DEVICES: frozenset[str] = frozenset(
-    {
-        "MAX30102", "DS18B20", "MLX90614", "SCD41", "BME280", "DHT22", "DHT11", "BH1750",
-        "HX711", "H10", "manual", "camera", "MPU6050", "MH-Z19", "DONKI", "OSDR", "catalog",
-        "NTC", "KY039", "KY017", "RING",
-    }
-)  # fmt: skip
-FLAGS: frozenset[str] = frozenset(
-    {"ok", "motion", "no_contact", "settling", "leads_off", "out_of_range",
-     "assumed_pressure", "stale"}
-)  # fmt: skip
-CREWS: frozenset[str] = frozenset({"crew-a", "crew-b", "crew-c"})
-SYMPTOM_CODES: frozenset[str] = frozenset({"headache", "fatigue", "nausea", "poor_sleep", "none"})
-REP_SOURCES: frozenset[str] = frozenset({"camera", "load_cell"})
+    p.id for p in REGISTRY.parts.values() if p.kind == "sensor"
+) | frozenset(REGISTRY.core.devices)
+FLAGS: frozenset[str] = frozenset(REGISTRY.core.flags)
+CREWS: frozenset[str] = frozenset(REGISTRY.core.crews)
+REP_SOURCES: frozenset[str] = frozenset(REGISTRY.core.rep_sources)
 # Exercises the astronaut picks on the camera page: wrist-tracked vertical lifts only.
-EXERCISES: frozenset[str] = frozenset({"curl", "overhead_press", "row"})
+EXERCISES: frozenset[str] = frozenset(REGISTRY.core.exercises)
 
 REASON_CODES: tuple[str, ...] = (
     "bad_json",
@@ -235,7 +181,7 @@ def parse_reading(raw: bytes | str | dict, *, max_bytes: int | None = None) -> R
     msg = _decode(raw, max_bytes)
     _check_fields(msg, _READING_FIELDS)
     ind = msg["ind"]
-    if ind == "symptom" and msg.get("code") is None:
+    if ind in CODED and msg.get("code") is None:
         raise ContractError("missing_field:code")
     if "code" in msg and msg["code"] is not None and not isinstance(msg["code"], str):
         raise ContractError("bad_type:code")
@@ -275,13 +221,12 @@ def parse_reading(raw: bytes | str | dict, *, max_bytes: int | None = None) -> R
     if msg["age_ms"] < 0:
         raise ContractError("bad_value:age_ms")
     code: str | None = None
-    if ind == "symptom":
+    if ind in CODED:
         code = msg["code"]
-        if code not in SYMPTOM_CODES:
+        if code not in CODED[ind]:
             raise ContractError("bad_value:code")
-    if ind in INTAKE_CEILINGS and not 0 <= val <= INTAKE_CEILINGS[ind]:
-        raise ContractError("bad_value:val")
-    if ind == "body_mass" and not BODY_MASS_RANGE[0] <= val <= BODY_MASS_RANGE[1]:
+    rng = REJECT_OUTSIDE.get(ind)
+    if rng is not None and not rng[0] <= val <= rng[1]:
         raise ContractError("bad_value:val")
     return Reading(
         v=1,
```

- [ ] **Step 4: Change `hub/ingest.py`, `hub/assess.py` and `hub/derive.py`**

```diff
diff --git a/hub/ingest.py b/hub/ingest.py
index 1919028..526b57b 100644
--- a/hub/ingest.py
+++ b/hub/ingest.py
@@ -9,8 +9,9 @@ from datetime import datetime
 from typing import TYPE_CHECKING
 
 from hub.contract import (
-    BODY_INDS,
-    INTAKE_INDS,
+    CREW_SCOPED,
+    DERIVE_FROM,
+    QUIET_INDS,
     ContractError,
     Reading,
     parse_reading,
@@ -25,9 +26,8 @@ if TYPE_CHECKING:
 
 log = logging.getLogger("hub.ingest")
 
-CREW_SCOPED = BODY_INDS | INTAKE_INDS
-# Streams that are stored but never assessed, outboxed or pushed one by one.
-QUIET_INDS = frozenset({"load_raw"})
+# CREW_SCOPED (body and intake indicators) and QUIET_INDS (stored but never assessed, outboxed or
+# pushed one by one) come from registry/indicators.json through hub.contract (D46 §6.2).
 # Channels fed by hardware nodes, whose (node, boot, seq) key can repeat when a boot counter does
 # (tilt-1, bench 2026-11-15). A repeated key with a different sample is stored under a `clash`
 # number there; software producers (http, prompt, internal) keep exact idempotency.
@@ -148,7 +148,7 @@ class Ingestor:
             )  # fmt: skip
         rows = [stored]
         derived: list[StoredReading] = []
-        if self.deriver is not None and stored.ind == "cabin_co2":
+        if self.deriver is not None and stored.ind in DERIVE_FROM:
             d = self.deriver(self.store, stored)
             if d is not None:
                 derived.append(d)
```

```diff
diff --git a/hub/assess.py b/hub/assess.py
index 9a5d9ec..8c15d17 100644
--- a/hub/assess.py
+++ b/hub/assess.py
@@ -9,7 +9,7 @@ from datetime import UTC, datetime, timedelta
 from pathlib import Path
 from zoneinfo import ZoneInfo
 
-from hub.contract import BODY_INDS, DERIVED, INDICATORS, INTAKE_INDS
+from hub.contract import CREW_SCOPED, DERIVED, INDICATORS, UNGATED_INDS
 from hub.results import Alert, AssessmentResult, entry_for, escalate_to_for
 from hub.store import Store, StoredReading
 from hub.thresholds import Rule, band_status, rules_for
@@ -17,8 +17,8 @@ from hub.timeutil import parse_iso, to_iso
 
 log = logging.getLogger("hub.assess")
 
-CREW_SCOPED = BODY_INDS | INTAKE_INDS
-UNGATED_INDS = frozenset({"motion", "load_raw", "tilt"})
+# CREW_SCOPED and UNGATED_INDS (never judged against a rule) come from registry/indicators.json
+# through hub.contract; hub.buckets imports CREW_SCOPED from this module.
 ESCALATIONS = frozenset({"self", "cmo", "flight_surgeon"})
 _COVERAGE_S = {"mean_1h": 2700, "mean_7d": 86400, "sum_24h_floor": 72000}
 _WINDOW_S = {"mean_1h": 3600, "mean_7d": 7 * 86400, "dose_24h": 86400, "sum_24h_floor": 86400}
```

```diff
diff --git a/hub/derive.py b/hub/derive.py
index 791fc01..441a47d 100644
--- a/hub/derive.py
+++ b/hub/derive.py
@@ -2,6 +2,7 @@
 
 from __future__ import annotations
 
+from collections.abc import Callable
 from datetime import timedelta
 
 from hub.contract import Reading
@@ -42,3 +43,9 @@ def derive_ppco2(store: Store, co2: StoredReading) -> StoredReading | None:
     )  # fmt: skip
     row, new = store.insert_reading(derived, parse_iso(co2.received_at), derived_from=co2.id)
     return row if new else None
+
+
+# registry/indicators.json names the function of each derived indicator ("derived": {"fn": ...}).
+DERIVERS: dict[str, Callable[[Store, StoredReading], StoredReading | None]] = {
+    "ppco2": derive_ppco2,
+}
```

- [ ] **Step 5: Run the new test and the gate**

Run: `.venv/bin/python -m pytest -q hub/tests/test_registry_contract.py hub/tests/test_registry_migration.py hub/tests/test_contract.py`
Expected: all pass. If `test_tables_match_the_snapshot` fails, it names the table that differs: fix the registry file or the builder, never the fixture.

- [ ] **Step 6: Run the full gates**

Run: `.venv/bin/python -m pytest -q -m 'not broker' --ignore=hub/tests/test_mqtt_broker.py && .venv/bin/ruff check .`
Expected: exit code 0. On `239924d` plus Tasks 1–5 that was `1096 passed, 2 skipped` (982 before this plan, 114 new so far).

- [ ] **Step 7: Commit**

```bash
git add hub/contract.py hub/ingest.py hub/assess.py hub/derive.py hub/tests/test_registry_contract.py
git commit -m "refactor(contract): build every contract table from registry/ (D46 step 1, no behaviour change)"
```

---

### Task 6: Refuse to start on a bad registry, log its hash, document

**Files:**
- Modify: `hub/__main__.py`
- Modify: `.env.example`
- Create: `registry/README.md`
- Test: `hub/tests/test_registry_start.py`

**Interfaces:**
- Consumes: `load`, `default_dir`, `RegistryError` (Task 2); `copy_registry`, `E`, `setp` (Task 2 helpers).
- Produces: `hub.__main__.check_registry(log) -> bool`. `main()` returns 2, before creating any folder, when the registry is invalid.

- [ ] **Step 1: Write the test**

```python
"""D46 §6.1: the hub refuses to start on an invalid registry and logs the hash of a valid one."""

from __future__ import annotations

import logging

from hub.__main__ import check_registry, main
from hub.tests.registry_helpers import E, copy_registry, setp


def test_hub_refuses_to_start_on_an_invalid_registry(tmp_path, monkeypatch, caplog):
    root = copy_registry(tmp_path)
    E("boards/uno-1.json", setp("placements.0.pins.data", "D0"))(root)
    monkeypatch.setenv("HUB_REGISTRY_DIR", str(root))
    monkeypatch.chdir(tmp_path)
    assert main([]) == 2
    assert "D0 is reserved (USB serial)" in caplog.text
    assert "not starting: 1 problem(s)" in caplog.text
    assert not (tmp_path / "var").exists()  # refused before anything was created


def test_a_valid_registry_logs_its_hash(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("HUB_REGISTRY_DIR", str(copy_registry(tmp_path)))
    caplog.set_level(logging.INFO)
    assert check_registry(logging.getLogger("hub"))
    assert "hash=" in caplog.text
```

- [ ] **Step 2: Run it and see it fail**

Run: `.venv/bin/python -m pytest -q hub/tests/test_registry_start.py`
Expected: collection error `ImportError: cannot import name 'check_registry' from 'hub.__main__'`.

- [ ] **Step 3: Change `hub/__main__.py` and `.env.example`**

```diff
diff --git a/hub/__main__.py b/hub/__main__.py
index 7911a24..5c702e0 100644
--- a/hub/__main__.py
+++ b/hub/__main__.py
@@ -8,6 +8,21 @@ import os
 from pathlib import Path
 
 from hub.config import load_settings
+from hub.registry import RegistryError, default_dir, load
+
+
+def check_registry(log: logging.Logger) -> bool:
+    """D46 §6.1: never start on an invalid registry; log its hash when it is valid."""
+    root = default_dir()
+    try:
+        reg = load(root)
+    except RegistryError as e:
+        for line in e.errors:
+            log.error("registry: %s", line)
+        log.error("not starting: %d problem(s) in %s", len(e.errors), root)
+        return False
+    log.info("registry %s hash=%s", root, reg.hash[:8])
+    return True
 
 
 def main(argv: list[str] | None = None) -> int:
@@ -16,12 +31,14 @@ def main(argv: list[str] | None = None) -> int:
     ap.add_argument("--port", type=int, default=None)
     args = ap.parse_args(argv)
     logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
+    log = logging.getLogger("hub")
+    if not check_registry(log):
+        return 2
     settings = load_settings(os.environ)
     Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
     Path("var").mkdir(exist_ok=True)
     host = args.host or settings.http_host
     port = args.port or settings.http_port
-    log = logging.getLogger("hub")
     log.info(
         "starting hub on %s:%s db=%s mqtt=%s:%s features=%s crews=%s",
         host, port, settings.db_path, settings.mqtt_host, settings.mqtt_port,
```

```diff
diff --git a/.env.example b/.env.example
index 0e0f758..e453235 100644
--- a/.env.example
+++ b/.env.example
@@ -7,6 +7,7 @@ HUB_MQTT_PASS=
 HUB_SERIAL_PORT=
 HUB_SERIAL_BAUD=250000
 HUB_THRESHOLDS=data/thresholds.json
+# HUB_REGISTRY_DIR=registry  # module registry (D46); default: the repository's registry/ folder
 HUB_GUIDANCE=data/guidance.json
 HUB_FOOD_CATALOG=data/food/catalog.json
 HUB_FOOD_THRESHOLDS=data/food/thresholds_food.json
```

- [ ] **Step 4: Write `registry/README.md`**

````markdown
# Module registry (D46)

Educational prototype, not a medical device. This folder is the one source for the habitat's indicators, devices,
nodes, sensor parts and boards (`docs/decisions/2026-11-15-sensor-modules-design.md`). `hub/contract.py` builds its
tables from it, and the hub refuses to start when any file here is invalid.

| File | One per | Says |
|---|---|---|
| `indicators.json` | contract | every indicator: unit, scope, label, decimals, `reject_outside`, `quiet`, `assess`, `derived`, `lane` |
| `core.json` | contract | sources, flags, crews, rep sources, exercises, commands, and the devices and nodes no board owns |
| `parts/<id>.json` | part type | what a sensor or actuator measures or drives: pins by role, outputs, ranges, flags, supply, hazards |
| `boards/<board>.json` | physical board | MCU, link, power, node ids, and each part's placement: pins, period, params, rail |

## Check the registry

```
.venv/bin/python -c "from hub.registry import load_default; print(load_default().hash[:8])"
.venv/bin/python -m pytest -q hub/tests/test_registry.py hub/tests/test_registry_rules.py \
  hub/tests/test_registry_safety.py hub/tests/test_registry_migration.py
```

The first command prints the registry hash, or one line per problem as `<file>: <field>: <text>`.

## Common changes

- **A known part on another pin:** edit the placement's `pins` in `boards/<board>.json`.
- **A second board of a kind** (say `cabin-2` on a NodeMCU): add `boards/cabin-2.json`. When two boards run the same
  sketch, mark one `"default": true`.
- **A new part type:** add `parts/<id>.json` with `"driver": "none"`. It can be placed only with `"enabled": false`
  until its firmware driver exists (D46 rollout step 4).
- **A new indicator:** add it to `indicators.json`, and add rules with their sources to `data/thresholds.json` if it
  is to be judged.

## Safety rules the check enforces (D46 §5.4)

- **S1** nothing on the Pi header: the `host` board has no placements.
- **S2** one power source per board, and the D40 pack rules: never 2 cells on VIN, never 3 or more on 3V3, no
  CR2032 on a Wi-Fi board.
- **S3** a part holding mercury has `"handling": "adults_only"`, and its placement `"enclosure": "sealed"`.
- **S4** a part that touches a person runs only on a `usb-bank` or `pack` board over MQTT.
- **S5** each placement's supply rail is one its part allows and its board has.
- **S6** the board's logic level suits the part, or the placement says `"level_shifted": true`.

Rules software cannot see stay on the checklist in `docs/safety-checklist.md`: the pack comes out before USB goes in
to flash, never mix cell charge levels, and the mercury cleanup steps.
````

- [ ] **Step 5: Run the full gates**

Run: `.venv/bin/python -m pytest -q -m 'not broker' --ignore=hub/tests/test_mqtt_broker.py && .venv/bin/ruff check . && .venv/bin/ruff format --check hub/registry hub/tests/registry_helpers.py hub/tests/test_registry*.py hub/__main__.py`
Expected: exit code 0 (on `239924d` plus this plan: `1098 passed, 2 skipped`).

- [ ] **Step 6: Check the start-up check on the real registry**

Run: `.venv/bin/python -c "import logging, sys; logging.basicConfig(level=20); from hub.__main__ import check_registry; sys.exit(0 if check_registry(logging.getLogger('hub')) else 1)"`
Expected: `INFO:hub:registry <worktree>/registry hash=<8 hex>` and exit code 0.

Do not start a second hub with `python -m hub` on the bench machine. It connects to the broker with the same client id as the live hub, `habitat-hub`, and the broker would disconnect the live one.

- [ ] **Step 7: Commit**

```bash
git add hub/__main__.py hub/tests/test_registry_start.py .env.example registry/README.md
git commit -m "feat(hub): refuse to start on an invalid registry and log its hash (D46 step 1)"
```

---

## Part B — Rollout step 2: generation (Tasks 7–16)

Starts from Part A merged. Unlike Part A, the code of Parts B–D has not been run in advance. Each task gives:
- the tests in full, or as exact input → expected tables;
- the interfaces;
- the generated formats, byte for byte where other code depends on them.

At the start of each part, re-read the files it names. If `main` has moved, re-run writing-plans for that part before coding. Generated files carry a first line `// Generated by tools.registry from registry/ (D46): do not edit.` (`#` comments where the language needs them). `REGISTRY_HASH` is the first 8 hex digits of `Registry.hash`; it was `a559bb56` on the Part A registry.

### Task 7: `tools/registry` command and the generator frame

**Files:**
- Create: `tools/registry/__init__.py` (empty), `tools/registry/__main__.py`, `tools/registry/gen.py`
- Test: `hub/tests/test_registry_gen.py`

**Interfaces:**
- Produces:
  - `gen.WRITERS: list[Callable[[Registry, Path], dict[str, str]]]`: each writer returns repo-relative path → full file text;
  - `gen.render_all(reg, repo) -> dict[str, str]`, which merges the writers and raises `ValueError` if two writers claim one path;
  - `gen.stale(files, repo) -> list[str]` (paths whose text differs on disk, sorted) and `gen.write(files, repo) -> list[str]` (paths written);
  - `gen.splice(text, begin, end, body) -> str`: replaces the lines strictly between the marker lines `begin` and `end`. It raises `ValueError(f"markers {begin!r}/{end!r} not found")` when a marker is missing or out of order;
  - CLI `python -m tools.registry check | gen [--check] | builds`. Exit code 0 when clean, 1 with one line per problem (`builds` comes in Task 15).
- Consumes: `hub.registry.load_default`, `RegistryError`.

- [ ] **Step 1: Write the failing tests**

```python
"""D46 step 2: generated files are current, and the generator frame behaves."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from hub.registry import load, load_default
from hub.tests.registry_helpers import E, copy_registry, setp
from tools.registry.gen import render_all, splice, stale

ROOT = Path(__file__).resolve().parents[2]


def test_generated_files_are_current():
    assert stale(render_all(load_default(), ROOT), ROOT) == []


def test_a_registry_change_makes_files_stale(tmp_path):
    root = copy_registry(tmp_path)
    E("parts/DHT11.json", setp("note", "changed"))(root)
    assert stale(render_all(load(root), ROOT), ROOT)  # the hash changed, so every header did


def test_splice_replaces_only_between_markers():
    text = "a\n// registry:begin\nold\n// registry:end\nz\n"
    assert splice(text, "// registry:begin", "// registry:end", "new\n") == (
        "a\n// registry:begin\nnew\n// registry:end\nz\n"
    )
    with pytest.raises(ValueError, match="not found"):
        splice("a\n", "// registry:begin", "// registry:end", "x\n")


def test_cli_gen_check_is_clean():
    run = subprocess.run([sys.executable, "-m", "tools.registry", "gen", "--check"], cwd=ROOT,
                         capture_output=True, text=True)  # fmt: skip
    assert run.returncode == 0, run.stdout + run.stderr
```

- [ ] **Step 2: Run them and see them fail** (`ModuleNotFoundError: No module named 'tools.registry'`)
- [ ] **Step 3: Implement**
  - `gen.py` holds the frame above with `WRITERS = []`, so `render_all` returns `{}` and the tests pass with no writers.
  - `__main__.py` parses `argv[1]`:
    - `check` runs `load_default()` (printing `RegistryError.errors`), then `stale(...)`; Task 12 adds the twin checks here;
    - `gen` writes and prints the changed paths;
    - `gen --check` prints the stale paths as `<path>: stale, run python -m tools.registry gen` and exits 1.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q hub/tests/test_registry_gen.py`. Expected: 4 passed.
- [ ] **Step 5: Commit** `feat(registry): tools.registry check/gen frame (D46 step 2)`

### Task 8: Generated `ReadingFormat` tables

**Files:**
- Modify: `firmware/libraries/HabitatNode/src/ReadingFormat.h` (put `// registry:begin` / `// registry:end` around the `Ind` and `Dev` enums) and `ReadingFormat.cpp` (around `kIndNames`, `kIndUnits`, `kDevNames`, `kDecimals`)
- Modify: `tools/registry/gen.py` (writer `reading_format`)
- Modify: `hub/tests/test_contract.py` (`test_ring_node_and_device`: drop the two `ReadingFormat` substring asserts, lines 297–299), `hub/tests/test_firmware_tilt.py` (drop the `ReadingFormat` substring checks, lines 30–32)
- Test: `hub/tests/test_registry_gen.py` (new cases)

**Interfaces:**
- Produces:
  - `Ind`: every indicator that at least one part file outputs, in `indicators.json` order, named `IND_` + `id.upper()`, then `IND_COUNT`. On the Part A registry that is `IND_HR, IND_SPO2, IND_SKIN_TEMP, IND_CABIN_TEMP, IND_CABIN_RH, IND_CABIN_P, IND_CABIN_CO2, IND_CABIN_LUX, IND_MOTION, IND_LOAD_RAW, IND_TILT, IND_COUNT`;
  - `Dev`: every sensor part sorted by id, named `DEV_` + the id upper-cased with each non-alphanumeric character turned into `_` (`MH-Z19` → `DEV_MH_Z19`), then `DEV_COUNT`. That gives `DEV_BH1750, DEV_BME280, DEV_DHT11, DEV_DHT22, DEV_DS18B20, DEV_HX711, DEV_KY017, DEV_KY039, DEV_MAX30102, DEV_MH_Z19, DEV_MLX90614, DEV_MPU6050, DEV_NTC, DEV_SCD41, DEV_COUNT`;
  - `kIndNames`, `kIndUnits` and `kDecimals` follow `Ind`; `kDevNames` follows `Dev`;
  - `body_temp`, `bp_*`, `glucose`, `sleep_h`, `mood` and `symptom` leave the firmware tables. `RING`, `H10`, `manual` and `camera` are core devices and leave them too: no firmware sends them;
  - helpers `gen.firmware_inds(reg) -> list[str]` and `gen.enum_name(dev) -> str`.
- Consumes: `gen.splice`, `Registry`.

- [ ] **Step 1: Add the tests**

```python
from tools.registry.gen import enum_name, firmware_inds

FW = ROOT / "firmware" / "libraries" / "HabitatNode" / "src"


def test_enum_names():
    assert enum_name("MH-Z19") == "DEV_MH_Z19" and enum_name("DHT11") == "DEV_DHT11"


def test_firmware_tables_list_every_part_output():
    reg = load_default()
    h, cpp = (FW / "ReadingFormat.h").read_text(), (FW / "ReadingFormat.cpp").read_text()
    assert firmware_inds(reg)[:3] == ["hr", "spo2", "skin_temp"] and "mood" not in firmware_inds(reg)
    for ind in firmware_inds(reg):
        assert f"IND_{ind.upper()}" in h and f'"{ind}"' in cpp
    for part in reg.parts.values():
        if part.kind == "sensor":
            assert enum_name(part.id) in h and f'"{part.id}"' in cpp
    assert "DEV_RING" not in h
```

- [ ] **Step 2: Run them** (`ImportError: cannot import name 'enum_name'`)
- [ ] **Step 3: Add the markers once, write the writer, run** `.venv/bin/python -m tools.registry gen`
- [ ] **Step 4: Gates**
  - Every library host test: the CI loop of `.github/workflows/ci.yml` ("HabitatNode library host tests"), run locally with `ARDUINOJSON_SRC` pointing at the installed ArduinoJson `src`.
  - `firmware/tilt-esp8266/test/run_host_tests.sh` and `firmware/vitals-esp32/test/run_host_tests.sh`.
  - `arduino-cli compile --fqbn esp8266:esp8266:nodemcuv2 --library firmware/libraries/HabitatNode firmware/tilt-esp8266`, with a copy of `secrets.example.h` as `secrets.h`.
  - `test_format.cpp` uses only `IND_TILT, IND_SPO2, IND_SKIN_TEMP, IND_MOTION, IND_HR, IND_CABIN_TEMP, IND_CABIN_CO2` and `DEV_NTC, DEV_MPU6050, DEV_MLX90614, DEV_MAX30102, DEV_KY039, DEV_KY017, DEV_DHT22`, which all stay.
  - Then the pytest gate.
- [ ] **Step 5: Commit** `feat(registry): generate the HabitatNode Ind/Dev tables (D46 step 2)`

### Task 9: `board_config.h` and the one-time sketch change

**Files:**
- Modify: `hub/registry/parse.py`: a new optional part field, `"defines": ("dict", False)`, with string values, stored as `Part.defines: dict[str, str]`. These are macros the board's build needs.
- Modify: `hub/registry/model.py`: add `defines: dict[str, str]` to `Part`.
- Modify: `registry/parts/DHT11.json` (`"defines": {"DHT_TYPE": "DHT11"}`) and `registry/parts/buzzer-passive.json` (`"defines": {"BUZZER_PASSIVE": "1"}`).
- Modify: `tools/registry/gen.py`: writer `board_config`.
- Create (generated): `firmware/exercise-uno/board_config.h`, `firmware/tilt-esp8266/board_config.h`, `firmware/vitals-esp32/board_config.h`.
- Modify: `firmware/exercise-uno/exercise-uno.ino` and `firmware/tilt-esp8266/tilt-esp8266.ino` (below).
- Modify: `firmware/wokwi/{uno-rig,full-bench,tilt-esp32,vitals-esp32}/sync.sh` and `check_sync.sh` (copy and check `board_config.h` beside `sketch.ino`); `firmware/wokwi/uno-rig/build.sh` (copy it into the build folder); `firmware/wokwi/full-bench/README.md` (add it to the paste table).
- Test: `hub/tests/test_registry_gen.py` (new cases), `hub/tests/test_firmware_full_bench.py::test_copies_equal_their_sources` (still passes once `sync.sh` has run).

**Interfaces:**
- Produces, for each placement with macro prefix `P` (`as`, or the part's `macro`):
  - `ENABLE_P` 1 or 0;
  - `PIN_P` when the part has one pin role, else `PIN_P_<ROLE>` (`PIN_HX711_DOUT`), with the GPIO number and a `// <label>` comment;
  - `P_NODE "<node>"`;
  - `P_PERIOD_MS` when all outputs share one period, else `P_<IND>_PERIOD_MS`. Actuators get none;
  - one `P_<PARAM>` per part param (the placement's value or the part's default), as an integer when whole;
  - the part's `defines` verbatim.
- Board-level macros: `BOARD_ID`, `REGISTRY_HASH`, `ACK_NODE` (when set), `LINK_BAUD` (serial), and `I2C_HZ` (the lowest `max_hz` of the enabled I2C parts, when there is one).
- Every macro is wrapped in `#ifndef`/`#endif`. The header comment lists the board's power line, each part's `wiring_notes` and its hazards.
- When more than one board runs a sketch, each board's block sits under `#if defined(BOARD_<ID>)` (id upper-cased, `-` → `_`), and the `default` board goes in the final `#else`.

Expected `firmware/exercise-uno/board_config.h` on the Part A registry plus this task's `defines`. The test compares these lines, and the hash line depends on the registry:

```c
// Generated by tools.registry from registry/ (D46): do not edit. Change registry/ and run
//   .venv/bin/python -m tools.registry gen
// Educational prototype, not a medical device.
//
// Board uno-1: atmega328p, serial 250000 baud, power usb-host.
// Wiring notes (checked by a person, docs/safety-checklist.md):
//   - HX711: Tie the HX711 RATE pin to DVDD for 80 SPS.
//   - HX711: Keep the HX711 board enclosed or taped (checklist rule 9).
#pragma once
#ifndef BOARD_ID
#define BOARD_ID "uno-1"
#endif
#ifndef REGISTRY_HASH
#define REGISTRY_HASH "<8 hex>"
#endif
#ifndef ACK_NODE
#define ACK_NODE "exercise-1"
#endif
#ifndef LINK_BAUD
#define LINK_BAUD 250000
#endif
// placements[0] DHT11 on cabin-1
#ifndef ENABLE_DHT
#define ENABLE_DHT 1
#endif
#ifndef PIN_DHT
#define PIN_DHT 2  // D2
#endif
#ifndef DHT_NODE
#define DHT_NODE "cabin-1"
#endif
#ifndef DHT_PERIOD_MS
#define DHT_PERIOD_MS 5000
#endif
#ifndef DHT_FAILS_FOR_NO_CONTACT
#define DHT_FAILS_FOR_NO_CONTACT 3
#endif
#ifndef DHT_TYPE
#define DHT_TYPE DHT11
#endif
// placements[1] buzzer-passive on exercise-1: ENABLE_BUZZER 1, PIN_BUZZER 8 // D8, BUZZER_NODE, BUZZER_PASSIVE 1
// placements[2] HX711 (disabled): ENABLE_HX711 0, PIN_HX711_DOUT 3, PIN_HX711_SCK 4, HX711_NODE, HX711_PERIOD_MS 12.5
// placements[3] servo (disabled): ENABLE_SERVO 0, PIN_SERVO 6, SERVO_NODE
// placements[4] NTC (disabled): ENABLE_NTC 0, PIN_NTC 14 // A0, NTC_NODE, NTC_PERIOD_MS 5000
// placements[5] KY039 (disabled): ENABLE_KY039 0, PIN_KY039 15 // A1, KY039_NODE, KY039_PERIOD_MS 5000
```

The last five comment lines stand for the same `#ifndef` triplets as the DHT block. They are written out in full in the real file.

Sketch change, `exercise-uno.ino`:
- After the `wokwi_twin.h` block, add `#if __has_include("board_config.h")` / `#include "board_config.h"` / `#endif`.
- Turn the two `static const uint8_t PIN_...` lines into `#ifndef` defaults with today's values, under the generated names. Rename the uses: `PIN_HX_DOUT` → `PIN_HX711_DOUT`, `PIN_HX_SCK` → `PIN_HX711_SCK`, `PIN_PULSE` → `PIN_KY039`.
- Readings use the node macros (`DHT_NODE`, `HX711_NODE`, `NTC_NODE`, `KY039_NODE`, with defaults `"cabin-1"` and `"exercise-1"`); acks use `ACK_NODE`.
- The fixed `5000` periods become `DHT_PERIOD_MS`, `NTC_PERIOD_MS` and `KY039_PERIOD_MS`.
- In the PURE block, `FailCount::fail()` returns `n >= DHT_FAILS_FOR_NO_CONTACT`, with `#ifndef DHT_FAILS_FOR_NO_CONTACT` / `#define DHT_FAILS_FOR_NO_CONTACT 3` inside the block so the host test still builds.
- After the `# channels` line, the banner prints `# registry=` + `REGISTRY_HASH` (sketch default `"none"`).

Sketch change, `tilt-esp8266.ino`:
- Include `board_config.h` the same way, before `TILT_ACTIVE_LOW`.
- `PIN_TILT` becomes an `#ifndef` default of 14.
- In the PURE block, `kDebounceMs` and `kHeartbeatMs` take `TILT_DEBOUNCE_MS` and `TILT_HEARTBEAT_MS`, with `#ifndef` defaults 200 and 10000.
- `node.begin(TILT_NODE)`, with default `"tilt-1"`.
- `fmtTiltLine` keeps its literal `"tilt-1"`: it is the serial-only twin format, and its host test pins it.
- Print `# registry=` after the banner in both modes.

`vitals-esp32`: header only, no sketch change.

- [ ] **Step 1: Add the tests**

```python
def test_uno_board_config():
    text = (ROOT / "firmware/exercise-uno/board_config.h").read_text()
    for line in ('#define BOARD_ID "uno-1"', "#define PIN_DHT 2  // D2", '#define DHT_NODE "cabin-1"',
                 "#define ENABLE_HX711 0", "#define PIN_HX711_DOUT 3  // D3", "#define DHT_TYPE DHT11",
                 "#define LINK_BAUD 250000", '#define ACK_NODE "exercise-1"'):
        assert line in text, line
    assert f'#define REGISTRY_HASH "{load_default().hash[:8]}"' in text


def test_tilt_board_config_uses_gpio_numbers():
    text = (ROOT / "firmware/tilt-esp8266/board_config.h").read_text()
    assert "#define PIN_TILT 14  // D5" in text and "#define TILT_DEBOUNCE_MS 200" in text
    assert "pack comes out before USB goes in" in text  # the power line for a pack board


def test_every_macro_is_guarded():
    for sketch in ("exercise-uno", "tilt-esp8266", "vitals-esp32"):
        lines = (ROOT / f"firmware/{sketch}/board_config.h").read_text().splitlines()
        for n, line in enumerate(lines):
            if line.startswith("#define "):
                assert lines[n - 1] == f"#ifndef {line.split()[1]}", (sketch, line)
```

For the power line, the writer prints `// Power: 4 x nimh AA on VIN. The pack comes out before USB goes in to flash.` for a pack board, and `// Power: usb-host.` otherwise.
- [ ] **Step 2: Run them** (they fail: `FileNotFoundError` for `board_config.h`)
- [ ] **Step 3: Implement the writer, run `gen`, make the sketch changes, run every `sync.sh`**
- [ ] **Step 4: Gates**
  - `firmware/exercise-uno/test/run_host_tests.sh` and `firmware/tilt-esp8266/test/run_host_tests.sh`;
  - `arduino-cli compile --fqbn arduino:avr:uno firmware/exercise-uno`, and again with `--build-property "build.extra_flags=-DENABLE_HX711=1 -DENABLE_SERVO=1 -DENABLE_NTC=1 -DENABLE_KY039=1"`;
  - `firmware/wokwi/uno-rig/build.sh`, the tilt compile, every `check_sync.sh`, and pytest.
- [ ] **Step 5: Bench check (operator only)**
  - The operator reflashes the UNO and the NodeMCU, the NodeMCU with its pack out.
  - The serial lines must match the old ones byte for byte, apart from the new `# registry=` banner line.
  - The hub's `GET /api/status` still shows `cabin-1` and `tilt-1` online.
- [ ] **Step 6: Commit** `feat(firmware): pins, channels and rates from generated board_config.h (D46 step 2)`

### Task 10: `board_parts.h` glue and the `partEmit` hook

**Files:**
- Modify: `tools/registry/gen.py` (writer `board_parts`)
- Create (generated): `firmware/{exercise-uno,tilt-esp8266,vitals-esp32}/board_parts.h`
- Modify: `exercise-uno.ino` and `tilt-esp8266.ino` (include it, call it, define the hook); the `sync.sh`/`check_sync.sh` copies as in Task 9
- Test: `hub/tests/test_registry_gen.py`

**Interfaces:**
- Produces, in `board_parts.h`:
  - `struct PartOut { const char* node; const char* ind; const char* unit; const char* dev; uint8_t ind_idx; uint8_t dev_idx; };` (the indexes are the `ReadingFormat` enums, or 255 on the AVR, which has no `ReadingFormat`);
  - `static inline void partsBegin()` and `static inline void partsPoll(uint32_t now)`. They call each enabled library part (no `driver: "inline"` and no `driver: "none"`). On the Part A registry there are none, so both bodies are empty;
  - an `#include "<Driver>.h"` per library part.
- The sketch defines `static void partEmit(const PartOut& o, float val, uint8_t q)` before including `board_parts.h`:
  - on the UNO, `emitReading(o.node, o.ind, val, o.unit, o.dev, q)`;
  - on the ESP, `node.queue(o.ind_idx, val, o.dev_idx, q)`.
  Mark it `[[maybe_unused]]` while no library part exists.

- [ ] **Step 1: Test:** `board_parts.h` of each sketch contains `static inline void partsBegin() {}` and `static inline void partsPoll(uint32_t now) { (void)now; }` on the Part A registry, and the `PartOut` struct.
- [ ] **Step 2: Run it** (fails: no file) **Step 3: implement, `gen`, sketch edits, `sync.sh`.**
- [ ] **Step 4: Gates:** as in Task 9, Step 4. **Step 5: Commit** `feat(firmware): board_parts.h glue for library parts (D46 step 2)`

### Task 11: Generated `wokwi_twin.h`

**Files:**
- Modify: `tools/registry/gen.py` (writer `twin_headers`)
- Modify (generated): `firmware/wokwi/uno-rig/wokwi_twin.h`. `firmware/wokwi/full-bench/wokwi_twin.h` stays a `sync.sh` copy.
- Test: `hub/tests/test_registry_gen.py`

**Interfaces:**
- Produces: for each board, in its first twin folder, the `twin_defines` of its enabled placements, in placement order, one `#define NAME VALUE  // <part>: Wokwi stand-in` each.
- A board with no `twin_defines` gets no file. Today that is `tilt-1` and `vitals-1`.

- [ ] **Step 1: Test:** `uno-rig/wokwi_twin.h` contains `#define DHT_TYPE DHT22` and `#define BUZZER_PASSIVE 1`. Neither `firmware/wokwi/tilt-esp32/wokwi_twin.h` nor `firmware/wokwi/vitals-esp32/wokwi_twin.h` exists.
- [ ] **Step 2–4:** fail, implement, `gen`, `sync.sh`, then `firmware/wokwi/uno-rig/build.sh` and every `check_sync.sh`.
- [ ] **Step 5: Commit** `feat(wokwi): generate the twin stand-in header (D46 step 2)`

### Task 12: ESP32 table and the Wokwi diagram checks

**Files:**
- Modify: `hub/registry/mcu.py`: add `ESP32` (DevKit v1). Pins `D<gpio>` → gpio for 0–39; reserved GPIO 0, 2, 5, 12, 15 (strapping), 6–11 (flash), 1 and 3 (USB serial); SDA `D21`, SCL `D22`; logic 3.3 V; rails `3V3`; pack windows as the ESP8266; Wi-Fi on. Add it to `MCUS` under `esp32`.
- Modify: `registry/parts/{MAX30102,MLX90614,MPU6050}.json`: add `"pins": {"sda": "SDA", "scl": "SCL"}` to `wokwi`.
- Create: `tools/registry/twins.py`
- Modify: `tools/registry/__main__.py` (`check` runs the twin checks)
- Test: `hub/tests/test_registry_twins.py`

**Interfaces:**
- Produces: `twins.check_twins(reg, repo) -> list[str]`, one message per problem.
- Rules for each board and each folder in `twins`:
  1. Read `<folder>/diagram.json`. The board's twin MCU part is the first part whose type is `wokwi-arduino-uno` (for `atmega328p`) or `wokwi-esp32-devkit-v1` (for `esp8266`/`esp32`).
  2. For each enabled placement whose part has a `wokwi` block, a part of type `wokwi.part` or `chip-<wokwi.chip>` exists.
  3. Each of its `wokwi.pins` roles is connected, in either order of the connection pair, to the twin pin. For an I2C role that is the twin MCU's SDA/SCL (`A4`/`A5`, or `D21`/`D22`). Otherwise it is the same GPIO number: `str(gpio)` on the UNO for D-pins and `A<n>` for analog pins, `D<gpio>` on the DevKit.
  4. With a `label`, some `wokwi-text` part's `text` contains it.
  5. No disabled placement's pins are connected on the twin MCU.
- Messages read `<folder>/diagram.json: <part>: <text>`.

- [ ] **Step 1: Write the tests**

```python
"""D46 §9: every twin draws and wires its board's enabled placements."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from hub.registry import load_default
from tools.registry.twins import check_twins

ROOT = Path(__file__).resolve().parents[2]


def test_the_real_twins_match_the_registry():
    assert check_twins(load_default(), ROOT) == []


def _copy_twin(tmp_path, name):
    shutil.copytree(ROOT / "firmware" / "wokwi" / name, tmp_path / "firmware" / "wokwi" / name)
    return tmp_path / "firmware" / "wokwi" / name / "diagram.json"


def test_a_rewired_dht_is_reported(tmp_path):
    for name in ("uno-rig", "full-bench", "tilt-esp32", "vitals-esp32"):
        _copy_twin(tmp_path, name)
    path = tmp_path / "firmware/wokwi/uno-rig/diagram.json"
    d = json.loads(path.read_text())
    d["connections"] = [c for c in d["connections"] if "dht:SDA" not in c[:2]]
    path.write_text(json.dumps(d))
    errs = check_twins(load_default(), tmp_path)
    assert any("uno-rig/diagram.json: DHT11" in e and "uno:2" in e for e in errs), errs
```

Add one case per rule in the same way:
- a missing part (DHT22 removed): "is not drawn";
- a label edited without "DHT11 stand-in (simulated)": "label";
- an I2C wire moved on the vitals twin (`max:SDA` to `esp:D19`): "max:SDA";
- a disabled placement wired (an extra connection `uno:3` ↔ `dht:NC`): "HX711 is disabled".
- [ ] **Step 2–4:** fail, implement, then pytest and `python -m tools.registry check`.
- [ ] **Step 5: Commit** `feat(registry): ESP32 table and Wokwi twin checks (D46 step 2)`

### Task 13: The hub chip's band table, generated

**Files:**
- Modify: `firmware/wokwi/full-bench/rpi3-hub.chip.c`: put `// registry:begin bands` / `// registry:end bands` around the eight `#define TEMP_*`/`RH_*` lines.
- Modify: `tools/registry/gen.py`: writer `hub_chip_bands`, with the mapping `CHIP_BANDS = (("cabin_health_box_temp", "TEMP_HEALTH"), ("cabin_performance_temp", "TEMP_PERF"), ("cabin_health_box_rh", "RH_HEALTH"), ("cabin_performance_rh", "RH_PERF"))`. For each pair it emits `#define <P>_MIN <ok.min>` and `#define <P>_MAX <ok.max>`, read from `data/thresholds.json`.
- Test: `hub/tests/test_firmware_full_bench.py::test_hub_chip_bands_match_the_thresholds_file` stays as the check. Add a `gen --check` freshness case.

The chip judges temperature and humidity only. A new `instant` cabin rule needs chip code as well, which is outside D46.

- [ ] **Steps:** add the markers; write the writer; `gen`; `firmware/wokwi/full-bench/test/run_chip_tests.sh`; pytest; commit `feat(wokwi): hub chip bands from thresholds.json (D46 step 2)`.

### Task 14: README board table and the per-board safety checks

**Files:**
- Modify: `firmware/README.md`: put `<!-- registry:begin boards -->` / `<!-- registry:end boards -->` under "## Which hardware runs what".
- Modify: `docs/safety-checklist.md`: add a section "## Per-board checks (generated from registry/)" with `<!-- registry:begin -->` / `<!-- registry:end -->`, before "## Per-session sign-off".
- Modify: `tools/registry/gen.py` (writers `readme_boards`, `safety_rows`)
- Test: `hub/tests/test_registry_gen.py`

**Interfaces:**
- Produces:
  - the board table `| Board | Status | MCU | Link | Power | Nodes | Parts (pin) |`, one row per board in file order. Parts read like `DHT11 (D2), buzzer-passive (D8), HX711 (D3, D4; off)`;
  - safety rows `| <board> | <check> | [ ] |`, one per item:
    - each enabled part's `wiring_notes`;
    - for a pack board, "the pack comes out before USB goes in to flash" and "never mix cell types or charge levels in one pack";
    - for a mercury part, "sealed pod, adult team members only; cleanup steps in rule 12";
    - for a `contact: "body"` part, "only the power bank is connected while worn".

- [ ] **Step 1: Test:**
  - every enabled placement's `wiring_notes` text appears between the markers of `docs/safety-checklist.md`;
  - the `tilt-1` row has the pack sentence;
  - the hand-written rules above the section are unchanged (compare the text before the section with `git show HEAD:docs/safety-checklist.md` up to the same heading).
- [ ] **Steps 2–5:** fail, implement, `gen`, gates, commit `docs(registry): generated board table and per-board safety checks (D46 step 2)`.

### Task 15: `builds`, CI and the RAM gate

**Files:**
- Modify: `tools/registry/__main__.py` (`builds`); Create: `tools/registry/ramgate.py`
- Modify: `.github/workflows/ci.yml`:
  - the python job gains `python -m tools.registry check`;
  - the firmware job replaces its two compile steps with a loop over `python -m tools.registry builds`, piping each compile through `ramgate.py`, after copying `secrets.example.h` to `secrets.h` for `tilt-esp8266`;
  - the firmware job runs every library host test (`firmware/libraries/*/test/test_*.cpp`).
- Test: `hub/tests/test_registry_builds.py`

**Interfaces:**
- Produces:
  - `builds` prints one line per build, as `<limit-percent> <command>`. The command is `arduino-cli compile --fqbn <fqbn> --libraries firmware/libraries <sketch>`, plus `--build-property "build.extra_flags=-DBOARD_<ID>"` when several boards share the sketch. Limit 75 for a board's real configuration, active or archived. Then one "every placement enabled" build per board with limit 90, adding `-DENABLE_<P>=1` for each disabled placement whose driver is not `none`;
  - `ramgate.parse_avr(text) -> int | None`: the percent from `Global variables use (\d+) bytes \((\d+)%\)`;
  - `ramgate.main()`: reads stdin, passes the text through, and exits 1 when the AVR percent is above the limit in `argv[1]`. ESP output is passed through without a gate. Its RAM line will be gated once its format has been captured from a CI run.
- Measured on 2026-11-15: the UNO at the D40 defaults is 961 B (46%), with every flag on 1,272 B (62%).

- [ ] **Step 1: Tests:**
  - `builds` lists 4 lines on the Part A registry: the real uno-1, tilt-1 and vitals-1, plus one all-enabled uno-1. uno-1 is the only board with disabled placements, so it is the only one that gets an all-enabled build;
  - the uno-1 all-enabled line carries `-DENABLE_HX711=1 -DENABLE_SERVO=1 -DENABLE_NTC=1 -DENABLE_KY039=1`;
  - `parse_avr("Global variables use 961 bytes (46%) of dynamic memory")` is 46;
  - `ramgate` exits 1 at limit 40 and 0 at limit 75 on that line.
- [ ] **Steps 2–5:** fail, implement, then run the CI firmware steps locally where the cores are installed, then commit `ci(registry): compile every board from the registry, with a RAM gate (D46 step 2)`.

### Task 16: `registry.ts` for the console

**Files:**
- Modify: `tools/registry/gen.py` (writer `console_registry`)
- Create (generated): `console/src/generated/registry.ts`
- Modify: `console/src/contract.ts`: drop the hand-written `INTAKE_INDS` array and `Ind` union, and re-export them, `export { INTAKE_INDS } from "./generated/registry"; export type { Ind, IntakeInd } from "./generated/registry";`
- Test: `console/tests/registry.test.ts`

**Interfaces:**
- Produces, in `registry.ts`:
  - `REGISTRY_HASH`;
  - `IND_IDS` (every indicator, file order, `as const`) and `type Ind`;
  - `INTAKE_INDS` and `type IntakeInd`;
  - `LANE_WINDOWS = ["instant", "mean_1h"] as const` and `type LaneWindow`;
  - `interface IndicatorInfo { id: Ind; unit: string; scope: string; label: string; lane: { label: string; window: LaneWindow; order: number; optional: boolean } | null }` and `INDICATORS: Record<Ind, IndicatorInfo>`;
  - `BOARDS: { id: string; status: string; transport: string | null; nodes: string[] }[]`.

- [ ] **Step 1: Test**

```ts
import { describe, expect, it } from "vitest";
import { INDICATORS, IND_IDS, INTAKE_INDS } from "../src/generated/registry";

describe("generated registry", () => {
  it("lists every indicator, the derived one included", () => {
    expect(IND_IDS).toContain("cabin_ppco2");
    expect(IND_IDS.length).toBe(32);
  });
  it("keeps the intake order of hub/contract.py", () => {
    expect(INTAKE_INDS[0]).toBe("intake_kcal");
    expect(INTAKE_INDS.at(-1)).toBe("intake_vitd_ug");
  });
  it("carries the lane hints", () => {
    expect(INDICATORS.cabin_ppco2.lane).toEqual({ label: "Cabin CO2 (partial pressure)", window: "mean_1h", order: 40, optional: true });
  });
});
```

- [ ] **Steps 2–4:** fail; implement; `gen`; then `npm --prefix console run build && (cd console && npx vitest run)`, where all existing console tests stay green.
- [ ] **Step 5: Commit** `feat(console): generated registry types (D46 step 2)`

---

## Part C — Rollout step 3: hub and console behaviour (Tasks 17–22)

### Task 17: Console lanes from the lane hints, one series per node

**Files:**
- Modify: `console/src/model/lanes.ts`:
  - `LANES` becomes `lanesFrom(INDICATORS)` followed by the `work` lane;
  - add `export function lanesFrom(inds: Record<string, IndicatorInfo>): LaneSpec[]`, which sorts by `lane.order` and skips indicators without a lane;
  - add `export function laneSeriesByNode(readings, rules, window): { node: string; series: LaneSeries }[]`, sorted by node.
- Modify: `console/src/views/lanes.ts`: draw one uPlot series per node. The legend label is the node id when there is more than one node.
- Test: `console/tests/registry-lanes.test.ts`

- [ ] **Step 1: Tests**
  - `LANES` deep-equals today's literal: 8 entries, keys `cabin_temp, cabin_rh, cabin_p, cabin_ppco2, hr, spo2, sleep_h, work`, with the same labels, units, windows and `optional` flags. Copy the literal from `console/src/model/lanes.ts` at `239924d` into the test.
  - `lanesFrom` on a fake map with an extra `cabin_voc` (`lane.order` 35) puts it between `cabin_p` and `cabin_ppco2`.
  - `laneSeriesByNode` on readings from `cabin-1` and `cabin-2` returns two entries, in that order.
  - The existing `console/tests/lanes.test.ts` and `panel*.test.ts` pass unchanged.
- [ ] **Steps 2–5:** fail, implement, build and vitest, commit `feat(console): lanes from registry hints, one series per node (D46 step 3)`.

### Task 18: `unexpected_output`

**Files:**
- Modify: `hub/contract.py`: add `PRODUCES: dict[str, frozenset[tuple[str, str]]]`, node → {(dev, ind)} over the enabled placements of every board. `REASON_CODES` stays as it is: like `topic_node_mismatch`, this reason is raised by the ingest path, not by `parse_reading`, so the Task 1 snapshot and `test_zz_every_reason_code_hit` do not change.
- Modify: `hub/ingest.py`:
  - `Ingestor.__init__` gains `outputs: Mapping[str, frozenset[tuple[str, str]]] | None = None`;
  - in `ingest_reading`, after the `expected_node` check: `if self.outputs is not None and channel in NODE_CHANNELS and r.node in self.outputs and (r.dev, r.ind) not in self.outputs[r.node]: raise ContractError("unexpected_output")`.
- Modify: `hub/api.py`: the `Ingestor(...)` call in the app setup passes `outputs=PRODUCES`.
- Test: `hub/tests/test_ingest_outputs.py`

Why the default is `None`: many existing tests feed hardware channels with pairs that today's registry does not place. `helpers.msg()` defaults to `cabin-1`/`cabin_co2`/`SCD41`, and `test_serial_rig.py` streams `exercise-1`/`load_raw`/`HX711` from the disabled HX711. Those tests keep testing the transport, and the new check is tested on its own, plus once through the app.

- [ ] **Step 1: Tests**

| Case | Ingestor | Message | Channel | Expect |
|---|---|---|---|---|
| placed output | `outputs=PRODUCES` | `msg(node="cabin-1", ind="cabin_temp", unit="C", dev="DHT11", val=22)` | `serial` | stored |
| part not placed | `outputs=PRODUCES` | `msg()` (`cabin-1`/`cabin_co2`/`SCD41`) | `mqtt` | `reason == "unexpected_output"`, 0 rows |
| disabled placement | `outputs=PRODUCES` | `msg(node="exercise-1", ind="load_raw", unit="N", dev="HX711", val=1)` | `serial` | `unexpected_output` |
| software channel | `outputs=PRODUCES` | `msg()` | `http` | stored |
| core node | `outputs=PRODUCES` | `msg(node="manual", ind="body_mass", unit="kg", src="self", dev="manual", val=70)` | `mqtt` | stored |
| no check | default | `msg()` | `mqtt` | stored |
| through the app | `app_factory` test client, as `hub/tests/test_api_readings.py` builds it | the app's ingestor's `outputs is PRODUCES` | — | true |

- [ ] **Steps 2–5:** fail, implement, full pytest gate, commit `feat(hub): reject readings no placement produces on hardware channels (D46 step 3)`.

### Task 19: Commands routed by board

**Files:**
- Modify: `hub/commands.py`:
  - `SERIAL_NODES` becomes the nodes of the one active serial board;
  - add `Route(board: str, transport: str, node: str)` and `route(reg: Registry, cmd: str) -> Route | None`: the first board in file order with a placement (enabled or not) whose part lists `cmd`; `node` is the board's `ack_node` or the placement's node;
  - `CommandRouter.send(node, cmd)` resolves `route(REGISTRY, cmd.cmd)`. With no route it logs `no board serves <cmd>, dropped` and returns. When the route's node differs from `node`, it logs at INFO and uses the route. A serial route goes to the rig; an MQTT route goes to `habitat/v1/cmd/<route.node>` (retained for servo/alarm, as today);
  - `command_topic()` uses `route()` the same way.
- Test: `hub/tests/test_commands_route.py`, and the existing `hub/tests/test_commands.py` stays green.

- [ ] **Step 1: Tests**
  - `route(load_default(), "alarm") == Route("uno-1", "serial", "exercise-1")`.
  - `route(..., "servo")`, `"cal"` and `"tare"` route the same way, through the disabled `servo` and `HX711` placements.
  - On a copy whose `buzzer-passive` placement moved to a new MQTT board `cabin-2.json`, `route(reg, "alarm") == Route("cabin-2", "mqtt", "cabin-2")`, built with the Part A helpers `COPY` and `E`.
  - `CommandRouter(rig=None, publisher=FakePublisher)` sends `alarm` to the rig path, where it logs "no rig link" and drops it, never to MQTT.
  - On a registry with no `alarm` part, `send` logs `no board serves alarm` and returns.
- [ ] **Steps 2–5:** fail, implement, gates, commit `feat(hub): route commands by the board that serves them (D46 step 3)`.

### Task 20: `GET /api/registry` and `board` in the status

**Files:**
- Modify: `hub/contract.py` (`BOARD_OF: dict[str, str]`, node → board id); `hub/api.py`: the new route, and `app.state.node_states` adds `"board": BOARD_OF.get(n.node)`.
- Create: `hub/registry/export.py` with `to_json(reg) -> dict`.
- Test: `hub/tests/test_api_registry.py`

**Interfaces:**
- `GET /api/registry` returns:
  - `hash`;
  - `indicators: [{id, unit, scope, label, lane}]`;
  - `boards: [{id, status, mcu, transport, power_source, nodes, placements: [{part, node, pins, enabled, outputs}]}]`, where `outputs` is the resolved `output_inds`.
- It is read-only and returns no error codes.

- [ ] **Step 1: Tests**
  - Status 200; `hash == REGISTRY.hash`; board ids `["hub", "tilt-1", "uno-1", "vitals-1"]`.
  - The `uno-1` placements[2] is `{"part": "HX711", "enabled": false, "outputs": ["load_raw"], ...}`.
  - After a reading from `cabin-1`, `GET /api/status` `nodes[]` has `{"node": "cabin-1", "board": "uno-1"}`. A core node such as `manual` has `"board": null`.
- [ ] **Steps 2–5:** fail, implement, gates, commit `feat(hub): GET /api/registry and board per node (D46 step 3)`.

### Task 21: Stale-build warning from the serial banner

**Files:**
- Modify: `hub/serial_rig.py`: in `handle_line`'s comment branch, when the line starts with `b"# registry="`, compare the value with `REGISTRY.hash[:8]`. When it differs, `log.warning("rig runs registry %s, hub has %s: reflash the board", got, want)` and `stats["registry_mismatch"] += 1`. Add `registry_mismatch` to `new_stats()`.
- Test: `hub/tests/test_serial_rig.py` (two new cases)

- [ ] **Step 1: Tests:**
  - `handle_line(ing, b"# registry=00000000\n", st)` returns `None`, sets `st["registry_mismatch"] == 1`, and logs the warning (`caplog`);
  - the matching hash leaves the count at 0;
  - the existing stats asserts still pass, since `new_stats()` only gains a key.
- [ ] **Steps 2–5:** fail, implement, gates, commit `feat(hub): warn when the serial board runs an older registry (D46 step 3)`.

### Task 22: Status view grouped by board

**Files:**
- Modify: `console/src/views/status.ts` and its model (`console/src/model/status.ts`): node tiles grouped under their board. Use `/api/status` `nodes[].board` when present, and the generated `BOARDS` otherwise. Nodes with no board go under "Other sources".
- Test: `console/tests/status.test.ts` (new cases)

- [ ] **Step 1: Tests:**
  - status nodes `cabin-1` and `exercise-1` (board `uno-1`), `tilt-1` and `manual` (no board) give the groups `uno-1: [cabin-1, exercise-1]`, `tilt-1: [tilt-1]`, `Other sources: [manual]`;
  - the offline fallback, with no `board` field, gives the same from `BOARDS`.
- [ ] **Steps 2–5:** fail, implement, build and vitest, commit `feat(console): group nodes by board (D46 step 3)`.

---

## Part D — Rollout step 4: the worked example, an SCD41 and a BME280 on the UNO (Tasks 23–29)

Spec §11. The two parts share the UNO's I2C bus on A4/A5: the SCD41 at `0x62` on 5V, the BME280 at `0x76` on 3V3 through a level-shifted breakout. `cabin-1` gains `cabin_co2` and `cabin_p`. The hub then derives `cabin_ppco2` with a measured pressure, so `co2_1h` and `co2_7d` judge it. The archived vitals node is the second example and needs no task: Part A already validates it (S4, `needs`, three I2C addresses, the 100 kHz bus).

### Task 23: `HabitatParts` library and the SCD41 pure block

**Files:**
- Create: `firmware/libraries/HabitatParts/library.properties` (name `HabitatParts`, version `0.1.0`, architectures `avr,esp8266,esp32`)
- Create: `firmware/libraries/HabitatParts/src/SCD41.h`, with the pure block between `// BEGIN PURE` and `// END PURE`
- Test: `firmware/libraries/HabitatParts/test/test_scd41.cpp`, and a new `hub/tests/test_firmware_habitatparts.py` that discovers and runs every `HabitatParts/test/test_*.cpp`. It is a copy of `hub/tests/test_firmware_habitatnode.py` with the library path changed and no ArduinoJson include.

**Interfaces (pure block, namespace `habitat_parts`):**
- `uint8_t scd41Crc(const uint8_t* data, size_t n)`: CRC-8 with polynomial 0x31 and init 0xFF;
- `bool scd41ParseMeasurement(const uint8_t frame[9], uint16_t* co2, float* temp_c, float* rh)`. It is false on any bad CRC. `temp = -45 + 175 * t / 65535` and `rh = 100 * h / 65535`;
- `bool scd41DataReady(uint16_t word)`: `(word & 0x07FF) != 0`;
- `uint8_t scd41Flags(uint16_t co2, uint32_t ms_since_start, uint32_t settle_ms)` returns the bits `Q_SETTLING` (while `ms_since_start < settle_ms`) and `Q_OUT_OF_RANGE` (`co2 > 5000`), with the `ReadingFormat.h` bit values redeclared locally as on the UNO;
- `struct Scd41Fails { uint8_t n = 0, limit = 3; bool fail(); void ok(); }`: true once `limit` reads in a row have failed;
- command words `0x21B1` (start periodic), `0xE4B8` (data ready), `0xEC05` (read), `0x3F86` (stop).

- [ ] **Step 1: Write the host test**

```cpp
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include "../src/SCD41.h"
using namespace habitat_parts;

static void frameWord(uint8_t* out, uint16_t w) { out[0] = w >> 8; out[1] = w & 0xFF; out[2] = scd41Crc(out, 2); }

int main() {
  const uint8_t beef[2] = {0xBE, 0xEF};
  assert(scd41Crc(beef, 2) == 0x92);  // Sensirion datasheet example, as nodes/cabin_pi/tests
  uint8_t f[9];
  frameWord(f, 500); frameWord(f + 3, 0x6667); frameWord(f + 6, 0x8000);  // the Python test's frame
  uint16_t co2; float t, rh;
  assert(scd41ParseMeasurement(f, &co2, &t, &rh) && co2 == 500);
  assert(fabsf(t - (-45.0f + 175.0f * 0x6667 / 65535.0f)) < 0.01f && fabsf(rh - 50.0f) < 0.01f);
  f[0] ^= 1;
  assert(!scd41ParseMeasurement(f, &co2, &t, &rh));  // bad CRC
  assert(scd41DataReady(0x8006) && !scd41DataReady(0x8000));
  assert(scd41Flags(800, 10000, 60000) == Q_SETTLING && scd41Flags(800, 60000, 60000) == 0);
  assert(scd41Flags(5001, 70000, 60000) == Q_OUT_OF_RANGE);
  Scd41Fails fails;
  assert(!fails.fail() && !fails.fail() && fails.fail());
  fails.ok();
  assert(!fails.fail());
  puts("test_scd41 ok");
  return 0;
}
```

- [ ] **Step 2: Run** `c++ -std=c++17 -Wall -Werror -DHABITAT_PARTS_HOST firmware/libraries/HabitatParts/test/test_scd41.cpp -o firmware/build/test_scd41 && firmware/build/test_scd41`. It fails: no header.
- [ ] **Step 3: Implement the pure block.** Wrap the hardware part in `#ifndef HABITAT_PARTS_HOST`, so the host test compiles without `Arduino.h`.
- [ ] **Step 4: Run the test again** (prints `test_scd41 ok`). Run pytest for the discovery test.
- [ ] **Step 5: Commit** `feat(firmware): HabitatParts SCD41 pure block with host tests (D46 step 4)`

### Task 24: SCD41 hardware class and the library-part glue

**Files:**
- Modify: `firmware/libraries/HabitatParts/src/SCD41.h`:
  - `class Scd41 { public: bool begin(TwoWire& w, uint32_t settle_ms, uint8_t fails_limit); bool poll(uint32_t now, Scd41Sample* out); };`
  - `struct Scd41Sample { uint16_t co2; uint8_t q; bool no_contact; }`;
  - `begin` sends stop, waits 500 ms, then start periodic;
  - `poll` checks data ready at most once per second, reads, and fills `out`. After `fails_limit` failed reads in a row it returns a sample with `no_contact` (val 0), as `nodes/cabin_pi` does.
- Modify: `registry/parts/SCD41.json`: `"driver": "SCD41"`.
- Modify: `tools/registry/gen.py` (`board_parts` writer):
  - for a library part, `partsBegin` calls `Wire.begin(); Wire.setClock(I2C_HZ);` once, then `<macro>_dev.begin(Wire, <P>_SETTLE_S * 1000UL, <P>_FAILS_FOR_NO_CONTACT)`;
  - `partsPoll(now)` calls `poll` and, on a sample, `partEmit(<P>_OUT_<IND>, val, q)` for each placed output;
  - `PartOut` constants are generated per placed output.
- Test: `hub/tests/test_registry_gen.py`:
  - with a test registry copy that places the SCD41 on `uno-1` (outputs `cabin_co2`, supply 5V), the rendered `board_parts.h` includes `"SCD41.h"`, calls `Wire.setClock(I2C_HZ)`, and emits with dev `"SCD41"` and ind `"cabin_co2"`;
  - a registry where `driver` is still `none` refuses the enabled placement (the Part A rule).

- [ ] **Steps:** test, fail, implement. Compile a scratch copy of `exercise-uno` with the test registry's generated headers: `arduino-cli compile --fqbn arduino:avr:uno --libraries firmware/libraries`. Commit `feat(firmware): SCD41 driver and generated glue (D46 step 4)`.

### Task 25: The BME280 pure block

**Files:**
- Create: `firmware/libraries/HabitatParts/src/BME280.h`
- Test: `firmware/libraries/HabitatParts/test/test_bme280.cpp`

**Interfaces (pure block):**
- `struct Bme280Calib { uint16_t T1; int16_t T2, T3; uint16_t P1; int16_t P2, P3, P4, P5, P6, P7, P8, P9; };`
- `bool bme280ParseCalib(const uint8_t block1[24], Bme280Calib* c)`: the little-endian words at 0x88–0x9F;
- `int32_t bme280TFine(int32_t adc_T, const Bme280Calib& c)`;
- `uint32_t bme280PressurePa(int32_t adc_P, int32_t t_fine, const Bme280Calib& c)`: the datasheet's 32-bit integer formula, so no 64-bit or double maths on the AVR. It returns 0 on division by zero.

- [ ] **Step 1: Write the test:**
  - take the calibration bytes and the raw ADC values of `nodes/cabin_pi/tests/fakes.py` (`fakes.cal_block1()`, and the raw pressure and temperature words its BME280 tests use);
  - the expected hPa is the Python driver's value for the same inputs: run `.venv/bin/python -c "..."` once with `nodes.cabin_pi.bme280` and paste the number into the test;
  - assert `fabs(bme280PressurePa(...) / 100.0 - expected) < 0.1`;
  - add a zero-divisor case that returns 0.
- [ ] **Steps 2–5:** fail, implement, run, commit `feat(firmware): HabitatParts BME280 compensation with host tests (D46 step 4)`.

### Task 26: BME280 hardware class

**Files:**
- Modify: `firmware/libraries/HabitatParts/src/BME280.h`:
  - `class Bme280 { bool begin(TwoWire& w); bool poll(uint32_t now, uint32_t period_ms, Bme280Sample* out); }`;
  - `begin` reads the chip id (0x60) and the calibration, and sets forced mode with ×1 oversampling;
  - `poll` triggers a forced measurement each period and reads 0xF7–0xFC;
  - the sample's `q` is `Q_SETTLING` on the first reading, and `no_contact` after 3 failed reads.
- Modify: `registry/parts/BME280.json`: `"driver": "BME280"`.
- Test: the `board_parts.h` render case, as in Task 24, for a BME280 placement with `level_shifted: true`. The generated glue reads `cabin_p` in hPa: Pa / 100, 1 decimal.

- [ ] **Steps:** test, fail, implement, compile the scratch copy, commit `feat(firmware): BME280 driver (D46 step 4)`.

### Task 27: Place both parts on `uno-1`

**Files:**
- Modify: `registry/boards/uno-1.json`: append the two placements of spec §11.3:

```json
{ "part": "SCD41", "node": "cabin-1", "pins": { "sda": "A4", "scl": "A5" }, "outputs": ["cabin_co2"],
  "period_ms": 5000, "supply": "5V" },
{ "part": "BME280", "node": "cabin-1", "pins": { "sda": "A4", "scl": "A5" }, "outputs": ["cabin_p"],
  "period_ms": 30000, "supply": "3V3", "level_shifted": true }
```

- Run: `python -m tools.registry gen`. This regenerates `board_config.h`, `board_parts.h`, the README table and the safety rows (the BME280 wiring note), and gives a new hash in every header.
- `hub/tests/test_registry_migration.py` stays as it is and must stay green: SCD41 and BME280 were already devices and `cabin-1` already a node, so no contract table changes. If one does, stop and find out why.
- Test: `hub/tests/test_registry_outputs_uno.py`:
  - over serial, with `outputs=PRODUCES`, `cabin-1`/`cabin_co2`/`SCD41` and `cabin-1`/`cabin_p`/`BME280` are stored;
  - `cabin-1`/`cabin_temp`/`SCD41` gets `unexpected_output` (the DHT11 owns it);
  - the full ingest of one `cabin_co2` and one `cabin_p` reading within 60 s yields a `cabin_ppco2` row whose flags are `["ok"]`, not `assumed_pressure`, and that row gets a `co2_1h` assessment.
  - Use the hub fixtures that `hub/tests/test_derive.py` and `hub/tests/test_assess.py` already use.
- Gates:
  - `python -m tools.registry check`;
  - `builds` with the RAM gate: the UNO's real configuration at 75% or less (the estimate is about 60%);
  - host tests and pytest.

Then reverse one thing on purpose: delete `"level_shifted": true` and confirm `check` fails with `S6: atmega328p logic is 5 V, outside BME280's 1.2-3.6 V`. Put it back.

- [ ] **Steps:** tests, fail, edit, gen, gates, commit `feat(registry): SCD41 and BME280 on the UNO's I2C bus (D46 step 4)`.

### Task 28: Wokwi chips for the SCD41 and the BME280

**Files:**
- Create: `firmware/wokwi/parts/scd41.chip.c`, `scd41.chip.json` (pins `VCC`, `GND`, `SDA`, `SCL`; a `co2` control, 400–5000 ppm). It answers I2C 0x62 for `0x21B1`, `0xE4B8` (ready after 5 s) and `0xEC05` (three words with CRC), and `0x3F86`.
- Create: `firmware/wokwi/parts/bme280.chip.c`, `bme280.chip.json` (I2C 0x76). It answers the chip id 0x60, the calibration block and the raw words of `nodes/cabin_pi/tests/fakes.py`: one fixed pressure. It proves the wiring and the driver path; the host test proves the maths.
- Create: `firmware/wokwi/parts/test/run_chip_tests.sh`, `test_scd41_chip.c`, `test_bme280_chip.c`, built against the existing `firmware/wokwi/full-bench/test/stub/wokwi-api.h` stub.
- Modify: `registry/parts/SCD41.json` (`"wokwi": {"chip": "scd41", "label": "SCD41 CO2 sensor (simulated chip)", "pins": {"sda": "SDA", "scl": "SCL"}}`) and `registry/parts/BME280.json` (the same with `bme280`, "BME280 pressure sensor (simulated chip)").
- Modify: `firmware/wokwi/uno-rig/diagram.json` and `firmware/wokwi/full-bench/diagram.json`: draw both chips with their labels, and wire SDA → `uno:A4`, SCL → `uno:A5`, VCC (SCD41 → `uno:5V`, BME280 → the UNO's 3.3 V pin; check its name in Wokwi's `wokwi-arduino-uno` pin list, probably `3.3V`), GND. Use the red/black/green colour rules of the full-bench README.
- Modify: each twin's `sync.sh`/`check_sync.sh` (copy the chip files) and the full-bench README paste table.
- Test: `python -m tools.registry check` (the twin rules of Task 12); `run_chip_tests.sh`; `hub/tests/test_firmware_full_bench.py` (parts, pins, colours).

- [ ] **Steps:** chip tests first (fail, implement, pass), then the diagrams, then `check`. Commit `feat(wokwi): SCD41 and BME280 chips on the UNO twins (D46 step 4)`.
- [ ] **Operator, after merge:** paste the changed files into the two saved Wokwi projects (links in `docs/decisions/links.md`). Start the simulation and confirm `cabin_co2` and `cabin_p` lines from `cabin-1`. Then update `links.md`.

### Task 29: Bench bring-up (operator only)

No agent does this task. It is listed so the plan ends on the real check of spec §13 step 4.

1. Wire, with the UNO unplugged:
   - the SCD41 breakout (5V, GND, A4 SDA, A5 SCL);
   - the BME280 breakout with a regulator and level shifter (3V3, GND, A4, A5).
   - Tick the generated per-board rows in `docs/safety-checklist.md`.
2. Flash `firmware/exercise-uno` from the merged branch.
3. On the serial monitor:
   - the banner shows `# registry=<hash>` and `# channels ... scd41=on bme280=on`;
   - `cabin-1` lines carry `cabin_co2` every 5 s (`settling` for the first 60 s) and `cabin_p` every 30 s.
4. On the hub:
   - `GET /api/status` shows a `cabin_ppco2` result with a `co2_1h` rule id and no `assumed_pressure` flag;
   - the console's ppCO2 lane is drawn;
   - the hub log has no `registry_mismatch` warning.
5. Record the RAM figure from the compile, and the first hour's readings, in the bench notes.

---

## Execution notes

- **Order.** Parts run in order A → B → C → D. Within a part the tasks run in order, except Tasks 13, 14 and 16, which only need Task 7 and can run in any order after it.
- **Firmware.** Agents never flash a board, never connect to the bench broker, and never start a second `python -m hub` on the bench machine.
- **Each part ends with a PR.** Its gates: the pytest gate, `ruff check .`, `python -m tools.registry check` (from Task 7 on), and, from Part B on, the firmware host tests, the compiles and the console build and vitest. The operator merges.

---

## Coverage against the spec

| Spec | Tasks |
|---|---|
| §4.1 files and folder | 2 |
| §4.2 indicator fields (`reject_outside`, `quiet`, `assess`, `derived`, `lane`, `codes`) | 2, 5 (used), 17 (lanes) |
| §4.3 part fields | 2; `defines` 9; `wokwi.pins` for I2C parts 12; `driver` names 24, 26 |
| §4.4 board fields, `default` | 2, 3 |
| §4.5 MCU tables | 2 (UNO, NodeMCU, host), 12 (ESP32) |
| §5.1–§5.3 structure, pins, buses, rates | 2, 3 |
| §5.4 S1–S6 | 4; S6 exercised by the BME280 in 27 |
| §5.5 what software cannot check | 9 (header comments), 14 (README, checklist rows) |
| §6.1 loading, fail fast, hash | 2, 6 |
| §6.2 contract tables | 5 |
| §6.3 `unexpected_output` | 18 |
| §6.4 commands by board | 19 |
| §6.5 many boards, one serial board | 3 (rules), 9 (`-DBOARD_<ID>` blocks), 19 |
| §6.6 `/api/registry`, `board` in status | 20 |
| §6.7 stale-build warning | 9 (banner), 21 |
| §7.1 `board_config.h` | 9 |
| §7.2 one sketch change | 9, 10 |
| §7.3 `HabitatParts`, `board_parts.h`, `partEmit` | 10, 23–26 |
| §7.4 `ReadingFormat` | 8 |
| §8 console | 16, 17, 22 |
| §9 Wokwi twins | 11, 12, 13, 28 |
| §10 tests and CI, RAM gate | 1–6, 7, 15 |
| §11 CO2 and pressure worked example | 23–29 |
| §12 archived vitals node | 2–4 (validated as data: S4, `needs`, three I2C addresses, 100 kHz) |
| §13 rollout | Parts A–D |
| §14 out of scope | not planned: node self-announce, run-time config, a second serial board, generated diagrams, ground-page lanes, commands without code |

Task count: 29. Part A 6, Part B 10, Part C 6, Part D 7 (one of them, Task 29, is the operator's bench bring-up).
