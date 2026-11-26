"""Fill a hub (HUB_ENABLED=1) with 3 fake restaurants so the 'All Venues' screen has something to show.
Usage: python scripts/seed_demo_venues.py http://localhost:8000 owner_user owner_password"""
import json
import sys
import urllib.request

base, user, pw = (sys.argv + ["http://localhost:8000", "admin", ""])[1:4]


def call(path, body=None, headers=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=h, method="POST" if body is not None else "GET")
    return json.loads(urllib.request.urlopen(req).read())


H = {"Authorization": "Bearer " + call("/api/auth/login", {"username": user, "password": pw})["token"]}
for name, city, occ, guests, alerts, cam_down in [
    ("Pearl Bistro", "Doha", 4, 16, ["Table 02: 3 guest(s) waiting 05:12 with no waiter visit"], False),
    ("Lusail Grill", "Lusail", 1, 5, [], False),
    ("Corniche Shawarma", "Doha", 5, 20, [], True),
]:
    v = call("/api/hub/venues", {"name": name, "city": city}, H)
    states = ["OCCUPIED"] * occ + ["FREE"] * (6 - occ)
    call("/api/hub/ingest", {
        "restaurant": {"capacity_pct": round(100 * guests / 24), "tables_occupied": occ, "tables_total": 6,
                       "seated_guests": guests, "seat_capacity": 24, "needs_cleaning": 0},
        "tables": [{"id": f"T0{i + 1}", "state": s, "guests": 3 if s == "OCCUPIED" else 0, "timer": "12:03"}
                   for i, s in enumerate(states)],
        "active_alerts": [{"kind": "service_wait", "table": "T02", "message": m, "ts": 0} for m in alerts],
        "cameras": [{"id": "cam1", "online": not cam_down}], "kpis": {}}, {"X-Venue-Key": v["api_key"]})
    print("seeded", name, "(note: demo venues go OFFLINE after 30 s because nothing keeps pushing)")
