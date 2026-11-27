"""End-to-end API tests (simulator mode): auth/roles, settings, zones, camera-offline alert, reports, hub."""
import os
import sys
import tempfile
import time
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ.update({
    "DB_PATH": str(Path(_tmp) / "t.db"), "AUTH_ENABLED": "1", "ADMIN_USER": "boss", "ADMIN_PASSWORD": "bosspass1",
    "AUTH_SECRET": "test-secret", "HUB_ENABLED": "1", "CAMERA_OFFLINE_SEC": "3", "WAIT_ALERT_SEC": "30", "CLEAN_ALERT_SEC": "20", "VIDEO_SOURCE": "sim",
    "FRONTEND_DIST": str(Path(_tmp) / "nodist"),
})
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        time.sleep(1.5)
        yield c


def login(c, u, p):
    r = c.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="module")
def owner(client):
    return login(client, "boss", "bosspass1")


def test_open_endpoints_and_401(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/config").json()["auth_required"] is True
    assert client.get("/api/state").status_code == 401
    assert client.post("/api/auth/login", json={"username": "boss", "password": "x"}).status_code == 401


def test_roles(client, owner):
    for name, role in (("sam", "staff"), ("mia", "manager")):
        r = client.post("/api/users", json={"username": name, "password": "secret12", "role": role}, headers=owner)
        assert r.status_code == 200
    staff, mgr = login(client, "sam", "secret12"), login(client, "mia", "secret12")
    assert client.get("/api/state", headers=staff).status_code == 200
    assert client.get("/api/analytics/weekly", headers=staff).status_code == 403
    assert client.get("/api/analytics/weekly", headers=mgr).status_code == 200
    assert client.put("/api/settings", json={"wait_alert_sec": 99}, headers=mgr).status_code == 403
    assert client.get("/api/users", headers=mgr).status_code == 403
    assert client.get("/api/state?token=" + staff["Authorization"][7:]).status_code == 200  # query token
    assert client.get("/api/state", auth=("boss", "bosspass1")).status_code == 200  # basic auth


def test_ws_needs_token(client, owner):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws"):
            pass
    with client.websocket_connect("/ws?token=" + owner["Authorization"][7:]) as ws:
        assert len(ws.receive_json()["tables"]) >= 1


def test_settings_roundtrip_and_validation(client, owner):
    r = client.put("/api/settings", json={"wait_alert_sec": 123, "restaurant_name": "Cafe Doha"}, headers=owner)
    assert r.status_code == 200 and r.json()["wait_alert_sec"] == 123
    time.sleep(0.8)  # snapshot refreshes on the monitor tick
    assert client.get("/api/state", headers=owner).json()["thresholds"]["wait_alert_sec"] == 123
    assert client.put("/api/settings", json={"wait_alert_sec": 1}, headers=owner).status_code == 422
    assert client.put("/api/settings", json={"report_hour": 30}, headers=owner).status_code == 422


def test_zones_edit(client, owner):
    z = client.get("/api/zones", headers=owner).json()
    assert client.put("/api/zones", json={"tables": []}, headers=owner).status_code == 422
    bad = {"tables": [{"id": "T01", "polygon": [[0, 0], [5, 5]]}]}
    assert client.put("/api/zones", json=bad, headers=owner).status_code == 422
    z["tables"].append({"id": "T07", "seats": 6, "section": "C", "polygon": [[10, 10], [60, 10], [60, 60]]})
    assert client.put("/api/zones", json=z, headers=owner).status_code == 200
    time.sleep(0.8)
    st = client.get("/api/state", headers=owner).json()
    t7 = next(t for t in st["tables"] if t["id"] == "T07")
    assert t7["seats"] == 6 and st["restaurant"]["tables_total"] == 7


def test_no_demo_data_and_production_thresholds(client, owner):
    st = client.get("/api/state", headers=owner).json()
    assert "demo" not in st["thresholds"]
    wk = client.get("/api/analytics/weekly", headers=owner).json()
    assert sum(d.get("parties", 0) for d in wk.get("daily", [])) == 0     # no fabricated history


def test_ack_records_name(client, owner):
    from app.main import pipeline      # raise a real alert through the engine instead of waiting for the simulator
    pipeline._raise_alert(time.time(), "service_wait", "T01", "warning", "Table 01: guests waiting 05:00 with no waiter visit",
                          {"number": 1, "guests": 2, "secs": 300})
    time.sleep(0.8)
    alert = next(a for a in client.get("/api/state", headers=owner).json()["alerts"])
    r = client.post(f"/api/alerts/{alert['id']}/ack", json={"name": "Ravi"}, headers=owner)
    assert r.json()["by"] == "Ravi"
    time.sleep(0.8)
    got = next(a for a in client.get("/api/state", headers=owner).json()["alerts"] if a["id"] == alert["id"])
    assert got["acked"] and got["ack_by"] == "Ravi"


def test_reports_and_service_analytics(client, owner):
    from app.main import db           # real analytics need real sessions: record one finished party
    now = time.time()
    sid = db.start_session("T01", now - 3000, 3)
    db.update_session(sid, end_ts=now - 600, guests=3, visits=2, first_visit_ts=now - 2700, cleaned_ts=now - 500)
    pdf = client.get("/api/reports/weekly.pdf", headers=owner)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and len(pdf.content) > 2000
    txt = client.get("/api/reports/weekly.txt", headers=owner).text
    assert "Weekly report" in txt and "Cafe Doha" in txt
    svc = client.get("/api/analytics/weekly", headers=owner).json()["service"]
    assert len(svc["by_shift"]) == 3 and svc["by_section"]
    assert client.post("/api/reports/send", headers=owner).status_code == 409  # no channel configured


def test_hub(client, owner):
    v = client.post("/api/hub/venues", json={"name": "Pearl Bistro", "city": "Doha"}, headers=owner).json()
    assert v["api_key"].startswith("vk_")
    assert client.post("/api/hub/ingest", json={}, headers={"X-Venue-Key": "bad"}).status_code == 401
    summary = {"restaurant": {"capacity_pct": 50, "tables_occupied": 3, "tables_total": 6,
                              "seated_guests": 12, "seat_capacity": 24}, "tables": [], "active_alerts": [],
               "cameras": [{"id": "cam1", "online": True}], "kpis": {}}
    assert client.post("/api/hub/ingest", json=summary, headers={"X-Venue-Key": v["api_key"]}).status_code == 200
    venues = client.get("/api/hub/venues", headers=owner).json()
    me = next(x for x in venues if x["name"] == "Pearl Bistro")
    assert me["online"] and me["summary"]["restaurant"]["seated_guests"] == 12


def test_table_actions_and_detail(client, owner):
    # reserve a free table, it disappears from recommendation / is flagged reserved
    st = client.get("/api/state", headers=owner).json()
    free = next(t for t in st["tables"] if t["state"] == "FREE")
    r = client.post(f"/api/tables/{free['id']}/action", json={"action": "reserve"}, headers=owner)
    assert r.status_code == 200
    time.sleep(0.8)
    st = client.get("/api/state", headers=owner).json()
    assert next(t for t in st["tables"] if t["id"] == free["id"])["reserved"] is True
    assert (st["recommendation"] or {}).get("table") != free["id"]
    assert client.post(f"/api/tables/{free['id']}/action", json={"action": "unreserve"}, headers=owner).status_code == 200
    # not applicable / unknown
    assert client.post(f"/api/tables/{free['id']}/action", json={"action": "mark_clean"}, headers=owner).status_code == 400
    assert client.post("/api/tables/T99/action", json={"action": "reserve"}, headers=owner).status_code == 404
    assert client.post(f"/api/tables/{free['id']}/action", json={"action": "bogus"}, headers=owner).status_code == 400
    d = client.get(f"/api/tables/{free['id']}", headers=owner).json()
    assert {"sessions", "events"} <= set(d)
    assert client.get("/api/tables/T99", headers=owner).status_code == 404
    assert client.post(f"/api/tables/{free['id']}/action", json={"action": "reserve"}).status_code == 401


def test_studio_flow_sim(client, owner):
    assert client.get("/api/studio/overview").status_code == 401
    ov = client.get("/api/studio/overview", headers=owner).json()
    assert ov["classes"] == ["customer", "staff", "table_clean", "table_dirty"] and ov["mode"] == "sim"
    r = client.post("/api/studio/capture", json={}, headers=owner)          # simulator -> labelled for free
    assert r.status_code == 200
    name = r.json()["name"]
    lab = client.get(f"/api/studio/labels/{name}", headers=owner).json()
    assert lab["labeled"] and any(b["cls"] in (2, 3) for b in lab["boxes"])
    # edit labels: keep only one box, roundtrip
    box = {"cls": 1, "x1": 100, "y1": 100, "x2": 160, "y2": 200}
    assert client.put(f"/api/studio/labels/{name}", json={"boxes": [box]}, headers=owner).status_code == 200
    got = client.get(f"/api/studio/labels/{name}", headers=owner).json()["boxes"]
    assert len(got) == 1 and got[0]["cls"] == 1 and abs(got[0]["x1"] - 100) < 1
    assert client.get(f"/api/studio/image/{name}", headers=owner).headers["content-type"] == "image/jpeg"
    assert client.get("/api/studio/images?filter=labeled", headers=owner).json()["total"] >= 1
    st = client.get("/api/studio/overview", headers=owner).json()["stats"]
    assert st["labeled"] >= 1 and st["boxes"]["staff"] >= 1
    assert client.get("/api/studio/export", headers=owner).status_code == 200
    # training refuses with too few images; unknown model activation refused
    assert client.post("/api/studio/train", json={}, headers=owner).status_code == 400
    assert client.post("/api/studio/models/activate", json={"name": "nope"}, headers=owner).status_code == 400
    assert client.delete(f"/api/studio/image/{name}", headers=owner).status_code == 200
    assert client.get(f"/api/studio/labels/{name}", headers=owner).status_code == 404
    assert client.get("/api/studio/image/..%2f..%2fetc%2fpasswd.jpg", headers=owner).status_code == 404


def test_studio_owner_only(client, owner):
    client.post("/api/users", json={"username": "mgr1", "password": "managerpass1", "role": "manager", "name": "M"}, headers=owner)
    mgr = login(client, "mgr1", "managerpass1")
    assert client.get("/api/studio/overview", headers=mgr).status_code == 403


def test_video_source_endpoints(client, owner):
    s = client.get("/api/source", headers=owner).json()
    assert s["cameras"][0]["sim"] is True
    assert client.post("/api/source", json={"cam": "nope", "source": "sim"}, headers=owner).status_code == 404
    assert client.post("/api/source", json={"source": "/etc/passwd"}, headers=owner).status_code == 400
    assert client.post("/api/source", json={"source": "video:missing.mp4"}, headers=owner).status_code == 404
    bad = client.post("/api/source/upload", files={"file": ("x.mp4", b"not a video")}, data={"use_now": "false"}, headers=owner)
    assert bad.status_code == 400
    assert client.post("/api/source", json={"source": "sim"}, headers=owner).json()["mode"] == "sim"


def test_uniform_apply_and_clear(client, owner):
    assert client.post("/api/calibrate/uniform", json={"low": [1, 2], "high": [3, 4, 5]}, headers=owner).status_code == 422
    assert client.post("/api/calibrate/uniform", json={"low": [5, 100, 100], "high": [25, 255, 255]}, headers=owner).status_code == 200
    st = client.get("/api/calibrate/status", headers=owner).json()
    assert st["enabled"] is True and list(st["low"]) == [5, 100, 100]
    client.post("/api/calibrate/uniform", json={"clear": True}, headers=owner)
    assert client.get("/api/calibrate/status", headers=owner).json()["enabled"] is False
