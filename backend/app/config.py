"""Central configuration. Everything can be overridden with environment variables."""
from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


def _num(name: str, default: float) -> float:
    v = os.getenv(name)
    return default if v in (None, "") else float(v)


def _tuple3(name: str, default):
    v = os.getenv(name)
    if not v:
        return default
    a, b, c = (int(x) for x in v.split(","))
    return a, b, c


@dataclass
class Settings:
    # --- video ---------------------------------------------------------
    # "sim"  -> built-in synthetic restaurant (no camera / model needed)
    # path   -> MP4 file (looped) processed with YOLOv8
    # rtsp:// or http:// -> live CCTV stream processed with YOLOv8
    video_source: str = "sim"
    fps: float = 15.0
    jpeg_quality: int = 80
    # --- thresholds (seconds) -----------------------------------------
    demo_mode: bool = True
    wait_alert_sec: float = 300.0     # guests seated, no waiter visit
    clean_alert_sec: float = 120.0    # guests left, table not reset to "Clean Table"
    occupy_confirm_sec: float = 1.5   # presence needed to flip FREE -> OCCUPIED
    leave_confirm_sec: float = 3.0    # absence needed to flip OCCUPIED -> NEEDS_CLEANING
    waiter_visit_sec: float = 1.0     # staff dwell inside zone that counts as a visit
    clean_confirm_sec: float = 2.0    # staff dwell on an empty table that counts as "cleaned"
    count_window: int = 15            # frames used for median guest-count smoothing
    staff_margin_px: float = 25.0     # staff may stand this far outside the zone polygon
    anchor: str = "center"            # "center" (overhead cam) or "foot" (angled cam)
    # --- detection -----------------------------------------------------
    yolo_model: str = "yolov8n.pt"
    yolo_conf: float = 0.35
    yolo_imgsz: int = 960
    yolo_device: str = ""             # "", "cpu", "0" (GPU)
    staff_hsv_low: tuple | None = None       # uniform colour range (OpenCV HSV); None = colour cue off until calibrated
    staff_hsv_high: tuple | None = None
    staff_infer: bool = True          # roaming/vote based staff inference (real cameras only)
    table_diff_thr: float = 0.45      # appearance diff vs clean reference above this = dirty
    item_min: int = 2                 # cups/plates/etc on an unseated table = dirty
    staff_pixel_ratio: float = 0.25
    # --- storage / misc --------------------------------------------------
    db_path: Path = ROOT / "data" / "restaurant.db"
    zones_file: Path = ROOT / "config" / "zones.json"
    frontend_dist: Path = ROOT.parent / "frontend" / "dist"
    timezone: str = "Asia/Qatar"
    seed_demo_data: bool = True
    cors_origins: list = field(default_factory=lambda: ["*"])
    # --- cameras ----------------------------------------------------------
    cameras: dict = field(default_factory=dict)       # {"cam1": "rtsp://..."}; sim -> {"cam1": "sim"}
    camera_offline_sec: float = 10.0
    use_bytetrack: bool = False
    # --- business ---------------------------------------------------------
    restaurant_name: str = "My Restaurant"
    report_enabled: bool = True
    report_weekday: int = 0           # 0 = Monday
    report_hour: int = 9
    # --- auth -------------------------------------------------------------
    auth_enabled: bool = False
    admin_user: str = "manager"
    admin_password: str = ""
    auth_secret: str = ""
    token_hours: float = 12.0
    # --- hub (multi-restaurant) -----------------------------------------------
    hub_enabled: bool = False         # this instance acts as the central hub
    hub_url: str = ""                 # edge: push summaries to this hub
    hub_key: str = ""

    # settings that managers/owners may change at runtime from the dashboard (persisted in SQLite)
    RUNTIME_KEYS = ("wait_alert_sec", "clean_alert_sec", "occupy_confirm_sec", "leave_confirm_sec",
                    "waiter_visit_sec", "clean_confirm_sec", "restaurant_name", "report_enabled",
                    "report_weekday", "report_hour", "camera_offline_sec")

    def load_zones(self) -> dict:
        with open(self.zones_file, "r", encoding="utf-8") as f:
            return json.load(f)


def load_settings() -> Settings:
    _src = os.getenv("VIDEO_SOURCE", "sim")
    demo = _bool("DEMO_MODE", _src == "sim")          # real camera/video -> real (production) thresholds by default
    s = Settings(
        video_source=os.getenv("VIDEO_SOURCE", "sim"),
        fps=_num("FPS", 15),
        jpeg_quality=int(_num("JPEG_QUALITY", 80)),
        demo_mode=demo,
        # Demo mode shrinks the alert thresholds so alerts are visible within a minute.
        wait_alert_sec=_num("WAIT_ALERT_SEC", 30 if demo else 300),
        clean_alert_sec=_num("CLEAN_ALERT_SEC", 20 if demo else 120),
        occupy_confirm_sec=_num("OCCUPY_CONFIRM_SEC", 1.5),
        leave_confirm_sec=_num("LEAVE_CONFIRM_SEC", 3.0),
        waiter_visit_sec=_num("WAITER_VISIT_SEC", 1.0),
        clean_confirm_sec=_num("CLEAN_CONFIRM_SEC", 2.0),
        count_window=int(_num("COUNT_WINDOW", 15)),
        staff_margin_px=_num("STAFF_MARGIN_PX", 25),
        anchor=os.getenv("ANCHOR", "center"),
        yolo_model=os.getenv("YOLO_MODEL", "yolov8n.pt"),
        yolo_conf=_num("YOLO_CONF", 0.25),
        yolo_imgsz=int(_num("YOLO_IMGSZ", 960)),
        yolo_device=os.getenv("YOLO_DEVICE", ""),
        staff_hsv_low=_tuple3("STAFF_HSV_LOW", None),
        staff_hsv_high=_tuple3("STAFF_HSV_HIGH", None),
        staff_infer=_bool("STAFF_INFER", True),
        table_diff_thr=_num("TABLE_DIFF_THR", 0.45),
        item_min=int(_num("ITEM_MIN", 2)),
        staff_pixel_ratio=_num("STAFF_PIXEL_RATIO", 0.25),
        db_path=Path(os.getenv("DB_PATH", str(ROOT / "data" / "restaurant.db"))),
        zones_file=Path(os.getenv("ZONES_FILE", str(ROOT / "config" / "zones.json"))),
        frontend_dist=Path(os.getenv("FRONTEND_DIST", str(ROOT.parent / "frontend" / "dist"))),
        timezone=os.getenv("RESTAURANT_TZ", "Asia/Qatar"),
        seed_demo_data=_bool("SEED_DEMO_DATA", _src == "sim"),
        cors_origins=os.getenv("CORS_ORIGINS", "*").split(","),
        camera_offline_sec=_num("CAMERA_OFFLINE_SEC", 10),
        use_bytetrack=_bool("USE_BYTETRACK", False),
        restaurant_name=os.getenv("RESTAURANT_NAME", "My Restaurant"),
        report_enabled=_bool("WEEKLY_REPORT", True),
        report_weekday=int(_num("REPORT_WEEKDAY", 0)),
        report_hour=int(_num("REPORT_HOUR", 9)),
        admin_user=os.getenv("ADMIN_USER", os.getenv("DASHBOARD_USER", "manager")),
        admin_password=os.getenv("ADMIN_PASSWORD", os.getenv("DASHBOARD_PASSWORD", "")),
        auth_secret=os.getenv("AUTH_SECRET", ""),
        token_hours=_num("TOKEN_HOURS", 12),
        hub_enabled=_bool("HUB_ENABLED", False),
        hub_url=os.getenv("HUB_URL", "").rstrip("/"),
        hub_key=os.getenv("HUB_KEY", ""),
    )
    s.auth_enabled = _bool("AUTH_ENABLED", bool(s.admin_password))
    if not s.auth_secret:
        s.auth_secret = secrets.token_hex(32)  # tokens reset on restart unless AUTH_SECRET is set
    cams = os.getenv("CAMERAS", "").strip()
    s.cameras = json.loads(cams) if cams else {"cam1": s.video_source}
    return s
