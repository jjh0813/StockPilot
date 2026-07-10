from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_demo_ui_is_served_at_root():
    response = client.get("/")

    assert response.status_code == 200
    assert "StockPilot Demo" in response.text
    assert "/api/v1/chat/stream" in response.text or "/frontend/app.js" in response.text


def test_demo_ui_assets_are_served():
    response = client.get("/frontend/app.js")

    assert response.status_code == 200
    assert "streamChat" in response.text
