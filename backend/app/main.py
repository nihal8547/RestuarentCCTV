"""FastAPI app: REST + WebSocket + MJPEG stream (+ serves the built React dashboard / PWA)."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import time
from pathlib import Path
from contextlib import asynccontextmanager

import cv2
from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .analytics import weekly_report
from .auth import RANK, AuthMiddleware, AuthService, hash_password
from .config import load_settings
from .db import Database
from .hub import HubPusher, make_api_key
from .pipeline import Pipeline
from .reports import ReportScheduler, build_pdf, build_text
from .training import CLASSES, Studio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

settings = load_settings()
db = Database(settings.db_path)


def _apply_overrides() -> None:
    """Runtime settings edited from the dashboard (stored in SQLite) override .env defaults."""
    for k, v in db.get_settings().items():
        if k in settings.RUNTIME_KEYS:
            setattr(settings, k, v)


_apply_overrides()
auth = AuthService(settings, db)
pipeline = Pipeline(settings, db)


def table_meta() -> tuple[list[str], dict[str, str]]:
    zs = pipeline.zones["tables"]
    return [z["id"] for z in zs], {z["id"]: z["section"] for z in zs}


def make_report() -> dict:
    ids, secs = table_meta()
    return weekly_report(db, settings.timezone, ids, table_sections=secs)


scheduler = ReportScheduler(settings, db, pipeline, make_report)
studio = Studio(settings, db, pipeline)
hub_pusher = HubPusher(settings, pipeline, lambda: make_report()["kpis"]) if settings.hub_url and settings.hub_key else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.purge_demo()          # remove any fake history left by older versions - analytics are real data only
    if auth.enabled and db.count_users() == 0:
        pw = secrets.token_urlsafe(9)
        db.create_user("admin", hash_password(pw), "owner", "Admin", time.time())
        log.warning("No users yet - created owner 'admin' with password: %s  (change it in Settings)", pw)
    pipeline.start()
    scheduler.start()
    if hub_pusher:
        hub_pusher.start()
    yield
    pipeline.stop()
    scheduler.stop()
    if hub_pusher:
        hub_pusher.stop()


app = FastAPI(title="Smart Restaurant Table Management (CCTV AI)", version="0.2.0", lifespan=lifespan)
app.add_middleware(AuthMiddleware, auth=auth)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------ guards
def role(min_role: str):
    def dep(request: Request) -> dict:
        u = request.scope.get("user")
        if not u:
            raise HTTPException(401, "Unauthorized")
        if RANK[u["role"]] < RANK[min_role]:
            raise HTTPException(403, f"{min_role} role required")
        return u
    return dep


staff, manager, owner = Depends(role("staff")), Depends(role("manager")), Depends(role("owner"))


# -------------------------------------------------------------------- open
@app.get("/api/health")
def health():
    snap = pipeline.get_snapshot()
    return {"status": "ok", "mode": pipeline.mode, "fps": snap.get("fps", 0), "ts": time.time()}


@app.get("/api/config")
def config():
    return {"auth_required": auth.enabled, "restaurant_name": settings.restaurant_name,
            "features": {"hub": settings.hub_enabled}, "mode": pipeline.mode,
            "cameras": pipeline.cam_ids, "timezone": settings.timezone}


@app.post("/api/auth/login")
def login(body: dict = Body(...)):
    if not auth.enabled:
        return {"token": "", "user": {"username": "local", "role": "owner", "name": "Local"}}
    u = auth.login(str(body.get("username", "")).strip(), str(body.get("password", "")))
    if not u:
        raise HTTPException(401, "Invalid username or password")
    return {"token": auth.make_token(u),
            "user": {"username": u["username"], "role": u["role"], "name": u["display_name"]}}


@app.get("/api/me")
def me(user: dict = staff):
    return user


# --------------------------------------------------------------- live data
@app.get("/api/state")
def state(user: dict = staff):
    return pipeline.get_snapshot()


@app.get("/api/zones")
def get_zones(user: dict = staff):
    return pipeline.zones


def _validate_zones(z: dict) -> dict:
    fw, fh = pipeline.size
    if not isinstance(z.get("tables"), list) or not z["tables"]:
        raise HTTPException(422, "at least one table is required")
    secs = {s["id"]: s for s in z.get("sections", [])}
    seen, out = set(), []
    for i, t in enumerate(z["tables"], 1):
        tid = str(t.get("id", "")).strip().upper()
        if not tid or tid in seen:
            raise HTTPException(422, f"table id missing or duplicated: {tid!r}")
        seen.add(tid)
        poly = t.get("polygon", [])
        if len(poly) < 3 or any(len(p) != 2 for p in poly):
            raise HTTPException(422, f"{tid}: polygon needs at least 3 points")
        poly = [[int(min(max(p[0], 0), fw)), int(min(max(p[1], 0), fh))] for p in poly]
        seats = int(t.get("seats", 4))
        if not 1 <= seats <= 20:
            raise HTTPException(422, f"{tid}: seats must be 1-20")
        sec = str(t.get("section") or "A")
        secs.setdefault(sec, {"id": sec, "name": f"Section {sec}"})
        digits = "".join(c for c in tid if c.isdigit())
        out.append({"id": tid, "number": int(t.get("number") or (digits or i)), "seats": seats, "section": sec,
                    "shape": t.get("shape", "rect"), "camera": t.get("camera") or pipeline.cam_ids[0],
                    "polygon": poly, "table_bbox": t.get("table_bbox")})
    used = {t["section"] for t in out}
    return {"frame": {"width": fw, "height": fh}, "sections": [s for k, s in sorted(secs.items()) if k in used],
            "tables": out}


@app.put("/api/zones")
def put_zones(body: dict = Body(...), user: dict = owner):
    zones = _validate_zones(body)
    db.set_setting("zones", zones)
    pipeline.reload_zones(zones)
    return zones


@app.get("/api/alerts")
def alerts(hours: float = 24, limit: int = 100, user: dict = staff):
    return db.alerts_since(time.time() - hours * 3600, limit)


@app.post("/api/alerts/{alert_id}/ack")
def ack(alert_id: int, body: dict | None = Body(None), user: dict = staff):
    by = (body or {}).get("name") or user.get("name")
    pipeline.ack_alert(alert_id, by) or db.ack_alert(alert_id, by)
    return {"ok": True, "by": by}


@app.post("/api/tables/{table_id}/action")
def table_action(table_id: str, body: dict = Body(...), user: dict = staff):
    res = pipeline.manual_action(table_id, str(body.get("action", "")), user.get("name") or "staff", time.time())
    if not res["ok"]:
        raise HTTPException(400 if res["error"] != "unknown table" else 404, res["error"])
    time.sleep(0.05)
    return res


@app.post("/api/tables/{table_id}/reference")
def table_reference(table_id: str, body: dict | None = Body(None), user: dict = manager):
    """Store (or clear) the current camera view of an empty, clean table as the 'clean' reference."""
    res = pipeline.set_table_reference(table_id, clear=bool((body or {}).get("clear")))
    if not res["ok"]:
        raise HTTPException(404 if res["error"] == "unknown table" else 400, res["error"])
    return res


@app.get("/api/calibrate/uniform")
def calibrate_uniform(x: int, y: int, cam: str | None = None, user: dict = manager):
    """Click on a waiter's shirt in the raw camera frame -> suggested STAFF_HSV_LOW / STAFF_HSV_HIGH."""
    import cv2
    import numpy as np
    w = pipeline.workers.get(cam) if cam else next(iter(pipeline.workers.values()), None)
    if w is None or w.last_raw is None:
        raise HTTPException(400, "no camera frame yet")
    f = w.last_raw
    r = 10
    patch = f[max(0, y - r): y + r + 1, max(0, x - r): x + r + 1]
    if patch.size == 0:
        raise HTTPException(400, "point outside frame")
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(int)
    lo, hi = np.percentile(hsv, 5, axis=0), np.percentile(hsv, 95, axis=0)
    low = [int(max(0, lo[0] - 8)), int(max(0, lo[1] - 40)), int(max(0, lo[2] - 50))]
    high = [int(min(179, hi[0] + 8)), 255, 255]
    return {"low": ",".join(map(str, low)), "high": ",".join(map(str, high)), "low_list": low, "high_list": high,
            "env": f"STAFF_HSV_LOW={','.join(map(str, low))}\nSTAFF_HSV_HIGH={','.join(map(str, high))}"}


@app.post("/api/calibrate/uniform")
def apply_uniform(body: dict = Body(...), user: dict = owner):
    """Apply (or clear with {"clear": true}) the uniform colour range live, no restart."""
    if body.get("clear"):
        pipeline.set_uniform(None, None)
        return {"ok": True, "uniform": None}
    low, high = body.get("low"), body.get("high")
    if not (isinstance(low, list) and isinstance(high, list) and len(low) == 3 and len(high) == 3):
        raise HTTPException(422, "low/high must be [h,s,v]")
    pipeline.set_uniform([int(v) for v in low], [int(v) for v in high])
    return {"ok": True, "uniform": {"low": low, "high": high}}


@app.get("/api/calibrate/status")
def uniform_status(user: dict = manager):
    lo, hi = pipeline.uniform()
    return {"enabled": lo is not None, "low": lo, "high": hi}


@app.get("/api/tables/{table_id}")
def table_detail(table_id: str, user: dict = staff):
    if table_id not in {t.id for t in pipeline.trackers}:
        raise HTTPException(404, "unknown table")
    return {"id": table_id, "sessions": db.sessions_for_table(table_id), "events": db.events_for_table(table_id)}


@app.get("/api/events")
def events(limit: int = 100, user: dict = manager):
    return db.recent_events(limit)


@app.get("/api/snapshot.jpg")
def snapshot_jpg(cam: str | None = None, raw: bool = False, user: dict = staff):
    if raw:
        jpg = pipeline.raw_jpeg(cam)
    else:
        _, jpg = pipeline.wait_frame(-1, timeout=2, cam=cam)
    if not jpg:
        raise HTTPException(503, "no frame yet")
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/video_feed")
async def video_feed(request: Request, cam: str | None = None):
    async def gen():
        last = -1
        while True:
            if await request.is_disconnected():
                break
            fid, jpg = await asyncio.to_thread(pipeline.wait_frame, last, 1.0, cam)
            if fid == last or not jpg:
                continue
            last = fid
            yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                   + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(pipeline.get_snapshot())
            await asyncio.sleep(0.5)
    except (WebSocketDisconnect, RuntimeError):
        pass


# ---------------------------------------------------------- analytics / reports
@app.get("/api/analytics/weekly")
def analytics(user: dict = manager):
    return make_report()


@app.get("/api/reports/weekly.pdf")
def report_pdf(user: dict = manager):
    r = make_report()
    return Response(build_pdf(r, settings.restaurant_name), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="weekly-report-{r["range"]["to"]}.pdf"'})


@app.get("/api/reports/weekly.txt")
def report_txt(user: dict = manager):
    return Response(build_text(make_report(), settings.restaurant_name), media_type="text/plain; charset=utf-8")


@app.post("/api/reports/send")
def report_send(user: dict = manager):
    if not pipeline.notifier.enabled:
        raise HTTPException(409, "No notification channel configured (set ALERT_WEBHOOK_URL or Telegram vars)")
    scheduler.send_now()
    return {"ok": True}


# -------------------------------------------------------------------- settings
def _settings_view() -> dict:
    s = settings
    return {
        "restaurant_name": s.restaurant_name, "timezone": s.timezone,
        "wait_alert_sec": s.wait_alert_sec, "clean_alert_sec": s.clean_alert_sec,
        "occupy_confirm_sec": s.occupy_confirm_sec, "leave_confirm_sec": s.leave_confirm_sec,
        "waiter_visit_sec": s.waiter_visit_sec, "clean_confirm_sec": s.clean_confirm_sec,
        "camera_offline_sec": s.camera_offline_sec, "report_enabled": s.report_enabled,
        "report_weekday": s.report_weekday, "report_hour": s.report_hour,
        "notifications": {"webhook": bool(pipeline.notifier.webhook),
                          "telegram": bool(pipeline.notifier.tg_token and pipeline.notifier.tg_chat)},
        "cameras": [{"id": c["id"], "online": c["online"], "sim": c["sim"], "source":
                     "simulator" if c["sim"] else "rtsp/file"} for c in pipeline.get_snapshot().get("cameras", [])],
        "hub": {"enabled": s.hub_enabled, "pushing_to": s.hub_url or None},
        "bytetrack": s.use_bytetrack,
    }


_LIMITS = {"wait_alert_sec": (5, 7200), "clean_alert_sec": (5, 7200), "occupy_confirm_sec": (0.2, 30),
           "leave_confirm_sec": (0.5, 120), "waiter_visit_sec": (0.2, 60), "clean_confirm_sec": (0.2, 60),
           "camera_offline_sec": (3, 600), "report_weekday": (0, 6), "report_hour": (0, 23)}


@app.get("/api/settings")
def get_settings(user: dict = manager):
    return _settings_view()


@app.put("/api/settings")
def put_settings(body: dict = Body(...), user: dict = owner):
    changed = {}
    for k, v in body.items():
        if k not in settings.RUNTIME_KEYS:
            continue
        if k == "restaurant_name":
            v = str(v).strip()[:80] or settings.restaurant_name
        elif k == "report_enabled":
            v = bool(v)
        else:
            try:
                v = float(v) if k not in ("report_weekday", "report_hour") else int(v)
            except (TypeError, ValueError):
                raise HTTPException(422, f"{k} must be a number")
            lo, hi = _LIMITS[k]
            if not lo <= v <= hi:
                raise HTTPException(422, f"{k} must be between {lo} and {hi}")
        changed[k] = v
    for k, v in changed.items():
        setattr(settings, k, v)
        db.set_setting(k, v)
    pipeline.apply_settings()
    return _settings_view()


# ----------------------------------------------------------------------- users
@app.get("/api/users")
def users(user: dict = owner):
    return db.list_users()


@app.post("/api/users")
def add_user(body: dict = Body(...), user: dict = owner):
    name, pw, r = str(body.get("username", "")).strip(), str(body.get("password", "")), body.get("role", "staff")
    if len(name) < 3 or len(pw) < 6 or r not in RANK:
        raise HTTPException(422, "username>=3 chars, password>=6 chars, role in staff/manager/owner")
    if db.get_user(name):
        raise HTTPException(409, "username already exists")
    db.create_user(name, hash_password(pw), r, body.get("display_name") or name, time.time())
    return {"ok": True}


@app.delete("/api/users/{user_id}")
def del_user(user_id: int, user: dict = owner):
    target = next((u for u in db.list_users() if u["id"] == user_id), None)
    if not target:
        raise HTTPException(404, "not found")
    if target["username"] == user["username"]:
        raise HTTPException(409, "you cannot delete yourself")
    db.delete_user(user_id)
    return {"ok": True}


@app.put("/api/users/{user_id}/password")
def set_pw(user_id: int, body: dict = Body(...), user: dict = owner):
    pw = str(body.get("password", ""))
    if len(pw) < 6:
        raise HTTPException(422, "password must be >= 6 characters")
    db.set_password(user_id, hash_password(pw))
    return {"ok": True}


# ------------------------------------------------------------------------- hub
def _hub_on():
    if not settings.hub_enabled:
        raise HTTPException(404, "hub is not enabled on this server (HUB_ENABLED=1)")


@app.post("/api/hub/ingest")
def hub_ingest(request: Request, body: dict = Body(...)):
    _hub_on()
    v = db.venue_by_key(request.headers.get("x-venue-key", ""))
    if not v:
        raise HTTPException(401, "invalid venue key")
    db.update_venue_summary(v["id"], time.time(), body)
    return {"ok": True}


@app.get("/api/hub/venues")
def hub_venues(user: dict = owner):
    _hub_on()
    out = []
    for v in db.list_venues():
        summ = json.loads(v["summary"]) if v["summary"] else None
        out.append({"id": v["id"], "name": v["name"], "city": v["city"], "last_seen": v["last_seen"],
                    "online": bool(v["last_seen"] and time.time() - v["last_seen"] < 30), "summary": summ})
    return out


@app.post("/api/hub/venues")
def hub_add(body: dict = Body(...), user: dict = owner):
    _hub_on()
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(422, "name required")
    key = make_api_key()
    vid = db.create_venue(name, body.get("city"), key, time.time())
    return {"id": vid, "name": name, "api_key": key,
            "setup": f"On the restaurant PC set HUB_URL=<this server url> and HUB_KEY={key}"}


@app.delete("/api/hub/venues/{venue_id}")
def hub_del(venue_id: int, user: dict = owner):
    _hub_on()
    db.delete_venue(venue_id)
    return {"ok": True}



# ------------------------------------------------------------ video source (owner)
def _mask(spec: str) -> str:
    import re
    return re.sub(r"(://[^:/@]+):[^@]+@", r"\1:***@", spec)


def _video_dir():
    d = studio.root / "videos"
    d.mkdir(exist_ok=True)
    return d


@app.get("/api/source")
def get_sources(user: dict = owner):
    vids = sorted(p.name for p in _video_dir().iterdir() if p.is_file())
    return {"cameras": [{"id": c, "source": _mask(w.spec), "sim": w.is_sim, "online": w.online(time.time())}
                        for c, w in pipeline.workers.items()], "videos": vids}


@app.post("/api/source")
def set_source(body: dict = Body(...), user: dict = owner):
    cam, src = body.get("cam") or pipeline.cam_ids[0], str(body.get("source", "")).strip()
    if cam not in pipeline.workers:
        raise HTTPException(404, "unknown camera")
    if src.startswith("video:"):
        p = _video_dir() / Path(src[6:]).name
        if not p.is_file():
            raise HTTPException(404, "video not found - upload it first")
        src = str(p)
    elif src != "sim" and not src.lower().startswith(("rtsp://", "rtsps://", "http://", "https://", "rtmp://")):
        raise HTTPException(400, "source must be 'sim', 'video:<uploaded file>' or an rtsp/http(s) URL")
    pipeline.set_source(cam, src)
    return {"ok": True, "mode": pipeline.mode}


@app.post("/api/source/upload")
async def source_upload(file: UploadFile = File(...), cam: str = Form(""), use_now: bool = Form(True),
                        user: dict = owner):
    name = Path(file.filename or "video.mp4").name
    if not name.lower().endswith((".mp4", ".avi", ".mov", ".mkv", ".m4v", ".webm")):
        raise HTTPException(400, "upload a video file")
    dest = _video_dir() / f"{int(time.time())}_{re.sub(r'[^A-Za-z0-9._-]', '_', name)}"
    size = 0
    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > 4 * 1024 ** 3:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, "video larger than 4 GB")
            f.write(chunk)
    cap = cv2.VideoCapture(str(dest))
    ok = cap.isOpened() and cap.read()[0]
    cap.release()
    if not ok:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "cannot decode this video (try mp4/H.264)")
    if use_now:
        pipeline.set_source(cam or pipeline.cam_ids[0], str(dest))
    return {"ok": True, "file": dest.name, "mode": pipeline.mode}



# ------------------------------------------------------------ model studio (owner only)
def _yolo_info() -> dict:
    info = {"installed": False, "version": None, "torch": None, "cuda": False, "device_name": None}
    try:
        import ultralytics
        info.update(installed=True, version=ultralytics.__version__)
        import torch
        info.update(torch=torch.__version__, cuda=bool(torch.cuda.is_available()))
        if info["cuda"]:
            info["device_name"] = torch.cuda.get_device_name(0)
    except Exception:
        pass
    return info


@app.get("/api/studio/overview")
def studio_overview(user: dict = owner):
    snap = pipeline.get_snapshot()
    return {"classes": CLASSES, "stats": studio.stats(), "jobs": studio.job_list(),
            "active_model": db.get_settings().get("active_model"), "model_in_use": pipeline.model_path(),
            "yolo": _yolo_info(), "mode": pipeline.mode, "cameras": snap.get("cameras", []),
            "frame": {"w": pipeline.size[0], "h": pipeline.size[1]}}


@app.post("/api/studio/upload")
async def studio_upload(file: UploadFile = File(...), every: float = Form(2.0), max_frames: int = Form(300),
                        user: dict = owner):
    if not (file.filename or "").lower().endswith((".mp4", ".avi", ".mov", ".mkv", ".m4v")):
        raise HTTPException(400, "upload a video file (mp4/avi/mov/mkv)")
    tmp = studio.root / "uploads" / f"{int(time.time() * 1000)}_{secrets.token_hex(3)}_{(file.filename or 'video').split('/')[-1]}"
    size = 0
    with open(tmp, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > 4 * 1024 ** 3:
                f.close()
                tmp.unlink(missing_ok=True)
                raise HTTPException(413, "video larger than 4 GB - cut it into shorter clips")
            f.write(chunk)
    return studio.extract_video(tmp, max(0.2, every), max(1, min(2000, max_frames)))


@app.post("/api/studio/capture")
def studio_capture(body: dict = Body(default={}), user: dict = owner):
    count, interval = int(body.get("count", 1)), float(body.get("interval", 5))
    if count <= 1:
        name = studio.capture(body.get("cam"))
        if not name:
            raise HTTPException(400, "no camera frame yet")
        return {"name": name}
    return studio.capture_series(body.get("cam"), min(count, 500), max(0.3, interval))


@app.get("/api/studio/images")
def studio_images(filter: str = "all", offset: int = 0, limit: int = 60, user: dict = owner):
    return studio.images(filter, offset, min(limit, 500))


@app.get("/api/studio/image/{name}")
def studio_image(name: str, user: dict = owner):
    p = studio.image_path(name)
    if not p:
        raise HTTPException(404, "not found")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/studio/labels/{name}")
def studio_get_labels(name: str, user: dict = owner):
    r = studio.get_boxes(name)
    if r is None:
        raise HTTPException(404, "not found")
    return r


@app.put("/api/studio/labels/{name}")
def studio_put_labels(name: str, body: dict = Body(...), user: dict = owner):
    if not studio.save_boxes(name, body.get("boxes", [])):
        raise HTTPException(404, "not found")
    return {"ok": True}


@app.delete("/api/studio/image/{name}")
def studio_del_image(name: str, user: dict = owner):
    if not studio.delete_image(name):
        raise HTTPException(404, "not found")
    return {"ok": True}


@app.post("/api/studio/autolabel")
def studio_autolabel(body: dict = Body(default={}), user: dict = owner):
    if not _yolo_info()["installed"]:
        raise HTTPException(400, "ultralytics is not installed (INSTALL_YOLO=1)")
    return studio.autolabel(bool(body.get("only_unlabeled", True)))


@app.get("/api/studio/export")
def studio_export(user: dict = owner):
    return FileResponse(studio.export_zip(), media_type="application/zip", filename="restaurant-dataset.zip")


@app.get("/api/studio/train")
def studio_train_state(user: dict = owner):
    return studio.train_state()


@app.post("/api/studio/train")
def studio_train(body: dict = Body(default={}), user: dict = owner):
    try:
        return studio.start_training(body)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/studio/train/cancel")
def studio_train_cancel(user: dict = owner):
    return studio.cancel_training()


@app.get("/api/studio/models")
def studio_models(user: dict = owner):
    return studio.models()


@app.get("/api/studio/check")
def studio_check(user: dict = owner):
    return studio.dataset_check()


@app.post("/api/studio/models/activate")
def studio_activate(body: dict = Body(...), user: dict = owner):
    try:
        return studio.activate(body.get("name"), bool(body.get("force")))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/studio/models/import")
async def studio_import(file: UploadFile = File(...), name: str = Form(...), user: dict = owner):
    if not (file.filename or "").lower().endswith(".pt"):
        raise HTTPException(400, "upload a .pt file")
    tmp = studio.root / "uploads" / f"{secrets.token_hex(4)}.pt"
    with open(tmp, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
    try:
        return studio.import_model(tmp, name.strip())
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/studio/models/{name}")
def studio_delete_model(name: str, user: dict = owner):
    try:
        studio.delete_model(name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


# Serve the built dashboard (npm run build) if present -> single-process production deploy.
if settings.frontend_dist.exists():
    app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
