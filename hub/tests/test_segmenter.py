from hub.exercise import Segmenter


def static(seg, n=100, f=100.0):
    for i in range(n):
        assert seg.feed(i * 10, f) is None


def run(seg, spans):
    """spans: list of (t_from, t_to_exclusive, force); returns emitted candidates with time."""
    out = []
    for a, b, f in spans:
        for t in range(a, b, 10):
            c = seg.feed(t, f)
            if c:
                out.append((t, c))
    return out


def test_static_from_first_second():
    seg = Segmenter(10)
    static(seg)
    assert seg.static_n == 100.0


def test_one_rep():
    seg = Segmenter(10)
    static(seg)
    out = []
    for t in range(1000, 1500, 10):
        f = 130.0 if t == 1200 else (115.0 if t < 1400 else 100.0)
        c = seg.feed(t, f)
        if c:
            out.append((t, c))
    assert len(out) == 1
    t, c = out[0]
    assert (c.rep, c.t0_ms, c.t1_ms, c.peak_n) == (1, 1000, 1400, 130.0) and t == 1420


def test_spike_rejected():
    seg = Segmenter(10)
    static(seg)
    got = run(seg, [(1000, 1030, 150.0), (1030, 1500, 100.0)])
    assert got == []


def test_jitter_inside_rep():
    seg = Segmenter(10)
    static(seg)
    spans = [(1000, 1200, 115.0), (1200, 1210, 105.0), (1210, 1400, 115.0), (1400, 1600, 100.0)]
    ((_, c),) = run(seg, spans)
    assert (c.rep, c.t0_ms, c.t1_ms, c.peak_n) == (1, 1000, 1400, 115.0)


def test_eight_reps():
    seg = Segmenter(10)
    static(seg)
    spans, t = [], 1000
    for _ in range(8):
        spans += [(t, t + 400, 120.0), (t + 400, t + 1000, 100.0)]
        t += 1000
    got = [c for _, c in run(seg, spans)]
    assert [c.rep for c in got] == list(range(1, 9))
    assert [c.t0_ms for c in got] == sorted({c.t0_ms for c in got})


def test_static_fallback():
    seg = Segmenter(10)
    assert seg.feed(1200, 100.0) is None
    assert seg.static_n == 10 * 9.81
    assert round((1 + seg.rise_frac) * seg.static_n, 2) == 107.91
