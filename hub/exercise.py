"""Exercise sessions, load-cell rep segmentation and rep alignment (H15, H16; D5, D21)."""

from __future__ import annotations

import logging
import statistics
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from hub.contract import CREWS, ContractError
from hub.ingest import Ingestor
from hub.store import Store, StoredReading, StoredRep
from hub.tilt import tilt_for_rep
from hub.timeutil import parse_iso, to_iso

log = logging.getLogger("hub.exercise")

RIG_NODE = "exercise-1"
EARTH_G = 9.81


@dataclass(frozen=True)
class RepCandidate:
    rep: int
    t0_ms: int
    t1_ms: int
    peak_n: float


class Segmenter:
    """A rep is force above the static load by rise_frac, then back (spec 5.4)."""

    def __init__(
        self,
        mass_kg: float,
        *,
        rise_frac: float = 0.10,
        static_ms: int = 1000,
        min_static_samples: int = 40,
        end_samples: int = 3,
        min_rep_ms: int = 250,
    ) -> None:
        self.mass_kg = mass_kg
        self.rise_frac = rise_frac
        self.static_ms = static_ms
        self.min_static_samples = min_static_samples
        self.end_samples = end_samples
        self.min_rep_ms = min_rep_ms
        self._static: list[float] = []
        self._f0: float | None = None
        self._final = False
        self._n = 0
        self._open: tuple[int, float] | None = None  # (t0, peak)
        self._below: list[int] = []  # times of consecutive samples below the threshold

    @property
    def static_n(self) -> float | None:
        if self._final:
            return self._f0
        if len(self._static) >= self.min_static_samples:
            return statistics.median(self._static)
        return None

    def reset_open(self) -> None:
        """Discard a half-seen rep (rig reboot); the static load is kept."""
        self._open = None
        self._below = []

    def _finalize(self) -> None:
        if len(self._static) >= self.min_static_samples:
            self._f0 = statistics.median(self._static)
        else:
            self._f0 = self.mass_kg * EARTH_G
        self._final = True

    def feed(self, t_ms: int, force_n: float) -> RepCandidate | None:
        if t_ms < self.static_ms and not self._final:
            self._static.append(force_n)
            return None
        if not self._final:
            self._finalize()
        assert self._f0 is not None
        threshold = (1 + self.rise_frac) * self._f0
        if self._open is None:
            if force_n >= threshold:
                self._open = (t_ms, force_n)
                self._below = []
            return None
        t0, peak = self._open
        if force_n >= threshold:
            self._below = []
            self._open = (t0, max(peak, force_n))
            return None
        self._below.append(t_ms)
        if len(self._below) < self.end_samples:
            return None
        t1 = self._below[0]
        self._open, self._below = None, []
        if t1 - t0 < self.min_rep_ms:
            return None
        self._n += 1
        return RepCandidate(self._n, t0, t1, peak)


class SessionError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Session:
    session: str
    mass_kg: float
    g: float
    crew: str | None
    started_at: str
    ended_at: str | None
    camera_reps: int
    load_cell_reps: int

    def to_dict(self) -> dict:
        return asdict(self)


class SessionManager:
    def __init__(self, store: Store, ingestor: Ingestor, clock: Callable[[], datetime]) -> None:
        self.store, self.ingestor, self.clock = store, ingestor, clock
        self._lock = threading.RLock()
        self._end_cbs: list[Callable[[Session], None]] = []
        self._seg: Segmenter | None = None
        self._boot: int | None = None
        self._active_id: str | None = None
        rows = store.session_rows(active_only=True)
        if rows:
            self._activate(rows[0])

    def _to_session(self, row: tuple) -> Session:
        cam, cell = self.store.rep_counts(row[0])
        return Session(row[0], row[1], row[2], row[3], row[4], row[5], cam, cell)

    def _activate(self, row: tuple) -> None:
        self._active_id = row[0]
        self._seg = Segmenter(row[1])
        self._boot = None

    def on_end(self, cb: Callable[[Session], None]) -> None:
        self._end_cbs.append(cb)

    def active(self) -> Session | None:
        with self._lock:
            if self._active_id is None:
                return None
            return self.get(self._active_id)

    def get(self, session: str) -> Session | None:
        row = self.store.session_row(session)
        return self._to_session(row) if row else None

    def list(self) -> list[Session]:
        return [self._to_session(r) for r in self.store.session_rows()]

    def start(self, session: str | None, mass_kg: float, g: float, crew: str | None) -> Session:
        if not mass_kg > 0:
            raise SessionError("bad_value:mass_kg")
        if g < 0:
            raise SessionError("bad_value:g")
        if crew is not None and crew not in CREWS:
            raise SessionError("bad_crew")
        now = self.clock()
        if session is None:
            session = f"s-{int(now.timestamp() * 1000)}"
        elif not 1 <= len(session) <= 64:
            raise SessionError("bad_value:session")
        with self._lock:
            if self.store.session_row(session) is not None:
                raise SessionError("session_exists")
            if self._active_id is not None:
                self.end(self._active_id)
            self.store.insert_session(session, mass_kg, g, crew, now)
            row = self.store.session_row(session)
            assert row is not None
            self._activate(row)
            return self._to_session(row)

    def end(self, session: str) -> Session:
        with self._lock:
            row = self.store.session_row(session)
            if row is None:
                raise SessionError("unknown_session")
            if row[5] is not None:
                return self._to_session(row)
            self.store.end_session(session, self.clock())
            if self._active_id == session:
                self._active_id, self._seg, self._boot = None, None, None
            ended = self._to_session(self.store.session_row(session))  # type: ignore[arg-type]
        for cb in self._end_cbs:
            try:
                cb(ended)
            except Exception:
                log.exception("session end callback failed")
        return ended

    def on_load_raw(self, r: StoredReading) -> StoredRep | None:
        """Ingestor listener: feed one stored load_raw sample to the active session."""
        if r.node != RIG_NODE or r.ind != "load_raw" or r.q != ("ok",):
            return None
        with self._lock:
            if self._active_id is None or self._seg is None:
                return None
            row = self.store.session_row(self._active_id)
            assert row is not None
            t_ms = round((parse_iso(r.measured_at) - parse_iso(row[4])).total_seconds() * 1000)
            if t_ms < 0:
                return None
            if self._boot is not None and r.boot != self._boot:
                self._seg.reset_open()
            self._boot = r.boot
            cand = self._seg.feed(t_ms, r.val)
            if cand is None:
                return None
            rep = {
                "v": 1, "node": RIG_NODE, "boot": r.boot,
                "seq": self.store.next_rep_seq(RIG_NODE, r.boot), "age_ms": 0, "type": "rep",
                "session": row[0], "rep": cand.rep, "src": "load_cell", "peak_n": cand.peak_n,
                "work_j": None, "rom_m": None, "g": EARTH_G, "mass_kg": row[1],
                "t0_ms": cand.t0_ms, "t1_ms": cand.t1_ms,
            }  # fmt: skip
            res = self.ingestor.ingest_rep(rep, channel="internal")
            if res.reason is not None:
                log.warning("load-cell rep rejected: %s", res.reason)
                return None
            return res.stored  # type: ignore[return-value]


# H16: alignment


def latest_reps(reps: list[StoredRep]) -> list[StoredRep]:
    best: dict[tuple[str, int], StoredRep] = {}
    for r in reps:
        key = (r.src, r.rep)
        cur = best.get(key)
        if cur is None or (r.boot, r.seq) > (cur.boot, cur.seq):
            best[key] = r
    return sorted(best.values(), key=lambda r: (r.rep, r.src))


def align(
    camera: list[StoredRep], cell: list[StoredRep]
) -> list[tuple[int, StoredRep | None, StoredRep | None]]:
    cam = {r.rep: r for r in latest_reps(camera)}
    cel = {r.rep: r for r in latest_reps(cell)}
    return [(n, cam.get(n), cel.get(n)) for n in sorted(set(cam) | set(cel))]


def static_load(store: Store, session_row: tuple, seg: Segmenter | None = None) -> float:
    """F0: median of ok load_raw in the first second of the session, else mass x 9.81."""
    seg = seg or Segmenter(session_row[1])
    start = parse_iso(session_row[4])
    rows = store.readings_between(
        "load_raw", start, start + timedelta(milliseconds=seg.static_ms),
        include_start=True, include_end=False,
    )  # fmt: skip
    vals = [r.val for r in rows if r.node == RIG_NODE and r.q == ("ok",)]
    if len(vals) >= seg.min_static_samples:
        return statistics.median(vals)
    return session_row[1] * EARTH_G


def work_cell_j(
    store: Store, session: Session | None, cell: StoredRep | None, camera: StoredRep | None
) -> float | None:
    """Approximation: static cell force x camera displacement (D21)."""
    if session is None or cell is None or camera is None or camera.rom_m is None:
        return None
    row = store.session_row(session.session)
    if row is None:
        return None
    return static_load(store, row) * camera.rom_m


def pairs_for(store: Store, manager: SessionManager, session: str) -> dict | None:
    """Body of GET /api/reps, or None when the session is unknown and has no reps."""
    reps = store.reps_for_session(session)
    sess = manager.get(session)
    if sess is None and not reps:
        return None
    cam = [r for r in reps if r.src == "camera"]
    cel = [r for r in reps if r.src == "load_cell"]
    pairs = []
    for n, c, lc in align(cam, cel):
        pairs.append(
            {
                "rep": n,
                "camera": c.to_dict() if c else None,
                "load_cell": lc.to_dict() if lc else None,
                "work_cell_j": work_cell_j(store, sess, lc, c),
                "tilt": tilt_for_rep(store, c) if c else None,
            }
        )
    return {"session": session, "pairs": pairs}


__all__ = [
    "ContractError", "RepCandidate", "Segmenter", "Session", "SessionError", "SessionManager",
    "align", "latest_reps", "pairs_for", "static_load", "to_iso", "work_cell_j",
]  # fmt: skip
