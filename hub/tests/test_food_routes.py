from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hub.api import create_app
from hub.food.catalog import load_catalog
from hub.food.log import FoodWriter
from hub.food.routes import FoodState, router
from hub.tests.test_food_log import MealStore, T

FIX = Path(__file__).parent / "fixtures" / "catalog_test.json"
MEAL_M = {"crew": "crew-a", "items": [{"food_id": "fx-bar", "servings": 2},
                                        {"food_id": "fx-drink", "servings": 1}]}  # fmt: skip


@pytest.fixture
def client(settings, clock):
    clock.set(T)
    store = MealStore(settings.db_path)
    app = create_app(settings, clock=clock, store=store)
    cat = load_catalog(FIX)
    app.state.food = FoodState(cat, FoodWriter(store, app.state.ingestor, cat, clock, boot=1))
    app.include_router(router)
    with TestClient(app) as c:
        yield c
    store.close()


def test_http_log(client):
    r = client.post("/api/food/log", json=MEAL_M)
    assert r.status_code == 201
    b = r.json()
    assert isinstance(b["meal_id"], int) and len(b["readings"]) == 9
    assert all(
        set(x) == {"ind", "id", "duplicate"} and x["duplicate"] is False for x in b["readings"]
    )
    assert all(isinstance(x["id"], int) for x in b["readings"])
    assert b["not_reported"] == ["intake_vitd_ug"]
    assert {e["status"] for e in b["results"]} == {"unknown"}


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({"crew": "crew-a", "items": []}, "empty_meal"),
        ({"crew": "crew-a", "items": [{"food_id": "zz", "servings": 1}]}, "unknown_food:zz"),
        ({"crew": "crew-z", "items": [{"food_id": "fx-bar", "servings": 1}]}, "bad_crew"),
        ({"items": [{"food_id": "fx-bar", "servings": 1}], "eaten_at": "nonsense"}, "bad_time"),
    ],
)
def test_http_422(client, body, reason):
    r = client.post("/api/food/log", json=body)
    assert r.status_code == 422 and r.json() == {"reason": reason}


def test_http_catalog(client):
    r = client.get("/api/food/catalog")
    assert r.status_code == 200 and len(r.json()["items"]) == 3


def test_not_wired_is_503(settings, clock):
    app = create_app(settings, clock=clock)
    app.include_router(router)
    with TestClient(app) as c:
        assert c.get("/api/food/catalog").status_code == 503
