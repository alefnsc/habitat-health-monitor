from datetime import UTC, datetime, timedelta

from hub.store import Store

T = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def test_food_log_table(tmp_path):
    s = Store(tmp_path / "f.db")
    items = [{"food_id": "rice", "servings": 2}]
    a = s.insert_meal("crew-a", T - timedelta(hours=60), T, items)  # older than 48 h is accepted
    b = s.insert_meal("crew-b", T - timedelta(hours=1), T, items)
    c = s.insert_meal(None, T, T, items)
    assert a < b < c
    rows = s.meals_between(T - timedelta(hours=24), T, None)
    assert [r.meal_id for r in rows] == [b, c] and rows[0].items == items
    assert [r.meal_id for r in s.meals_between(T - timedelta(hours=24), T, "crew-b")] == [b]
    assert s.meals_between(T - timedelta(hours=1), T, "crew-b") == []  # start is exclusive
    assert rows[0].to_dict()["crew"] == "crew-b"
