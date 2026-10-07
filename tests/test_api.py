from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app(FIXTURES / "sdn.xml", FIXTURES / "accounts.csv"))


def test_bulk_screening(client):
    response = client.post("/screenings")
    assert response.status_code == 200
    by_id = {r["account_id"]: r["matches"] for r in response.json()}

    assert len(by_id) == 6
    assert by_id["1"] == [{"uid": "100", "confidence": "HIGH", "match_types": ["NAME_EXACT", "DOB_FULL"]}]
    assert by_id["2"] == [{"uid": "100", "confidence": "HIGH", "match_types": ["NAME_FUZZY", "DOB_FULL"]}]
    assert by_id["3"] == [{"uid": "200", "confidence": "HIGH", "match_types": ["NAME_EXACT", "DOB_YEAR"]}]
    assert by_id["4"] == [{"uid": "200", "confidence": "MED", "match_types": ["NAME_FUZZY", "DOB_YEAR"]}]
    assert by_id["5"] == [{"uid": "200", "confidence": "LOW", "match_types": ["NAME_FUZZY"]}]
    assert by_id["6"] == []  # entities are not screened


def test_bulk_matches_only(client):
    ids = [r["account_id"] for r in client.post("/screenings?matches_only=true").json()]
    assert ids == ["1", "2", "3", "4", "5"]


def test_single_screening(client):
    response = client.get("/screenings/4")
    assert response.status_code == 200
    assert response.json() == {
        "account_id": "4",
        "matches": [{"uid": "200", "confidence": "MED", "match_types": ["NAME_FUZZY", "DOB_YEAR"]}],
    }


def test_single_screening_unknown_account(client):
    assert client.get("/screenings/nope").status_code == 404
