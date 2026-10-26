import os
import time

import pytest
from fastapi.testclient import TestClient

from server import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / "data"), autosave_seconds=3600)) as c:
        yield c


def wait_scan(c, job_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        job = c.get(f"/api/scan/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("scan timeout")


def test_health_and_root(client):
    assert client.get("/api/health").json()["status"] == "ok"
    root = client.get("/api/node").json()
    assert root["path"] == "/my-project" and root["type"] == "folder"


def test_crud_move_rename_delete(client):
    assert client.post("/api/folders", json={"path": "/my-project/docs"}).status_code == 201
    assert client.post("/api/files", json={"path": "/my-project/docs/a.txt", "size": 5}).status_code == 201
    assert client.post("/api/rename", json={"path": "/my-project/docs/a.txt", "new_name": "b.txt"}).json()["path"] == "/my-project/docs/b.txt"
    assert client.post("/api/move", json={"path": "/my-project/docs/b.txt", "dest": "/my-project/src"}).json()["path"] == "/my-project/src/b.txt"
    assert client.delete("/api/node", params={"path": "/my-project/src/b.txt"}).status_code == 200
    assert client.get("/api/node", params={"path": "/my-project/src/b.txt"}).status_code == 404


def test_error_codes(client):
    assert client.get("/api/node", params={"path": "/my-project/nope"}).status_code == 404
    assert client.post("/api/files", json={"path": "/my-project/README.md"}).status_code == 409   # duplicado
    assert client.post("/api/files", json={"path": "relative/x"}).status_code == 400              # ruta inválida
    assert client.post("/api/files", json={"path": "/my-project/x", "size": -1}).status_code == 422  # validación
    assert client.post("/api/move", json={"path": "/my-project/src", "dest": "/my-project/src/x"}).status_code in (400, 404)
    assert client.delete("/api/node", params={"path": "/my-project"}).status_code == 400
    assert client.get("/api/children", params={"path": "/my-project/README.md"}).status_code == 409


def test_pagination_stats_find_render(client):
    for i in range(250):
        client.post("/api/files", json={"path": f"/my-project/big/f{i:03}.py", "size": 1, "parents": True})
    p1 = client.get("/api/children", params={"path": "/my-project/big", "limit": 100}).json()
    p3 = client.get("/api/children", params={"path": "/my-project/big", "offset": 200, "limit": 100}).json()
    assert p1["total"] == 250 and len(p1["items"]) == 100 and len(p3["items"]) == 50
    assert p1["items"][0]["name"] == "f000.py"
    st = client.get("/api/stats", params={"path": "/my-project/big"}).json()
    assert st["files"] == 250 and st["size"] == 250
    found = client.get("/api/find", params={"pattern": "*.py", "limit": 10}).json()
    assert len(found["results"]) == 10 and found["truncated"] is True
    txt = client.get("/api/render", params={"path": "/my-project/big", "limit": 20}).json()["text"]
    assert txt.splitlines()[-1].startswith("... (")


def test_cache_invalidated_on_mutation(client):
    before = client.get("/api/stats").json()["files"]
    client.post("/api/files", json={"path": "/my-project/new.txt", "size": 1})
    assert client.get("/api/stats").json()["files"] == before + 1


def test_scan_large_folder_and_truncation(client, tmp_path):
    base = tmp_path / "big"
    for d in range(10):
        (base / f"d{d}").mkdir(parents=True)
        for f in range(300):
            (base / f"d{d}" / f"f{f}.txt").write_text("x")
    job = wait_scan(client, client.post("/api/scan", json={"directory": str(base)}).json()["id"])
    assert job["status"] == "done" and job["nodes"] == 10 + 3000 and not job["truncated"]
    assert client.get("/api/stats").json()["files"] == 3000
    assert client.get("/api/node").json()["name"] == "big"

    job = wait_scan(client, client.post("/api/scan", json={"directory": str(base), "max_nodes": 100}).json()["id"])
    assert job["status"] == "done" and job["truncated"] and job["nodes"] == 100


def test_scan_errors_do_not_touch_live_tree(client, tmp_path):
    before = client.get("/api/stats").json()
    assert client.post("/api/scan", json={"directory": str(tmp_path / "missing")}).status_code == 404
    base = tmp_path / "s"
    base.mkdir()
    (base / "a.txt").write_text("x")
    jid = client.post("/api/scan", json={"directory": str(base)}).json()["id"]
    client.delete(f"/api/scan/{jid}")  # cancelar (o ya terminó): ambos casos son válidos
    job = wait_scan(client, jid)
    assert job["status"] in ("cancelled", "done")
    if job["status"] == "cancelled":
        assert client.get("/api/stats").json() == before


def test_allowed_root(client, tmp_path, monkeypatch):
    allowed, outside = tmp_path / "ok", tmp_path / "no"
    allowed.mkdir(); outside.mkdir()
    monkeypatch.setenv("EXPLORER_ALLOWED_ROOT", str(allowed))
    assert client.post("/api/scan", json={"directory": str(outside)}).status_code == 403
    assert client.post("/api/scan", json={"directory": str(allowed)}).status_code == 202


def test_persistence_and_recovery(tmp_path):
    data = str(tmp_path / "d")
    with TestClient(create_app(data, autosave_seconds=3600)) as c:
        c.post("/api/files", json={"path": "/my-project/keep.txt", "size": 7})
        assert c.post("/api/snapshot").json()["saved"] is True
        c.post("/api/files", json={"path": "/my-project/keep2.txt"})
    # el apagado guarda; reiniciar conserva los datos
    with TestClient(create_app(data, autosave_seconds=3600)) as c:
        assert c.get("/api/node", params={"path": "/my-project/keep2.txt"}).status_code == 200
    # snapshot principal corrupto -> usa el respaldo .bak
    snap = os.path.join(data, "snapshot.json")
    assert os.path.exists(snap + ".bak")
    with open(snap, "w") as f:
        f.write("{corrupto")
    with TestClient(create_app(data, autosave_seconds=3600)) as c:
        assert c.get("/api/node", params={"path": "/my-project/keep.txt"}).status_code == 200
    # ambos corruptos -> arranca limpio sin caerse
    with open(snap, "w") as f:
        f.write("x")
    with open(snap + ".bak", "w") as f:
        f.write("y")
    with TestClient(create_app(data, autosave_seconds=3600)) as c:
        assert c.get("/api/health").status_code == 200


def test_autosave_thread(tmp_path):
    data = tmp_path / "a"
    with TestClient(create_app(str(data), autosave_seconds=0.1)) as c:
        c.post("/api/files", json={"path": "/my-project/auto.txt"})
        time.sleep(0.6)
        assert (data / "snapshot.json").exists()


def test_index_served(client):
    assert client.get("/").status_code == 200
