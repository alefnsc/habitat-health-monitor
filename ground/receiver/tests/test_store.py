from receiver.store import arrivals_after, ingest, open_db, summary

T = "2026-11-15T13:00:12.000Z"


def _item(i: int) -> dict:
    return {"id": i, "kind": "reading", "created_at": T, "payload": {"n": i}}


def test_ingest_counts_and_ignores_duplicates(tmp_path):
    conn = open_db(tmp_path / "g.db")
    r1 = ingest(conn, None, [_item(1), _item(2)], T)
    assert (r1.max_id, r1.stored, r1.arrival_id) == (2, 2, 1)
    r2 = ingest(conn, None, [_item(2), _item(3)], T)
    assert (r2.max_id, r2.stored, r2.arrival_id) == (3, 1, 2)


def test_arrivals_carry_only_new_items(tmp_path):
    conn = open_db(tmp_path / "g.db")
    ingest(conn, {"b": 1}, [_item(1), _item(2)], T)
    ingest(conn, None, [_item(2), _item(3)], T)
    a = arrivals_after(conn, 0, 10)
    assert [x.arrival_id for x in a] == [1, 2]
    assert a[0].beacon == {"b": 1} and a[1].beacon is None
    assert [i["id"] for i in a[1].items] == [3]
    assert a[1].items[0]["payload"] == {"n": 3}


def test_summary_empty(tmp_path):
    conn = open_db(tmp_path / "g.db")
    s = summary(conn)
    assert (s.stored, s.min_id, s.max_id, s.missing_ids, s.arrivals) == (0, None, None, 0, 0)
    assert s.last_arrival_at is None
