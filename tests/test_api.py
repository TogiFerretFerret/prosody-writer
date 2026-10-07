from uuid import uuid4
from fastapi.testclient import TestClient
from prosody_writer.app import app

client = TestClient(app)


def test_editor_and_functional_scan():
    page = client.get("/")
    assert page.status_code == 200
    assert '<style>' in page.text
    assert '<script>' in page.text
    assert 'href="/static/style.css"' not in page.text
    assert 'src="/static/editor.js"' not in page.text
    assert client.get('/index.html').status_code == 200
    assert client.get("/static/editor.js").status_code == 200
    response = client.post("/api/scan", json={"session": str(uuid4()), "revision": 3,
        "text": "Shall I compare thee to a summer's day?"})
    assert response.status_code == 200
    assert response.json()["revision"] == 3
    assert response.json()["lines"][0]["scansion"] == "-+-+-+-+-+"


def test_request_limits():
    payload = {"session": str(uuid4()), "revision": 1, "text": "a" * 12001}
    assert client.post("/api/scan", json=payload).status_code == 422
    payload["text"] = "\n" * 200
    assert client.post("/api/scan", json=payload).status_code == 422
