"""Model Studio: build a dataset from real CCTV, label it, train YOLO, version and activate models.

Everything lives under <data dir>/studio:
  images/*.jpg  labels/*.txt (YOLO format)  models/<name>/{best.pt,meta.json}  runs/  dataset/  train.json  train.log
Classes (fixed order - must match what the detector/state machine understand):
  0 customer · 1 staff · 2 table_clean · 3 table_dirty
"""
from __future__ import annotations

import csv
import json
import logging
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("studio")
CLASSES = ["customer", "staff", "table_clean", "table_dirty"]
NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,60}$")


def studio_root(settings) -> Path:
    return Path(settings.db_path).parent / "studio"


def active_model_path(settings, db) -> str:
    """Path of the model workers should load: the activated studio model, else YOLO_MODEL."""
    name = db.get_settings().get("active_model")
    if name:
        p = studio_root(settings) / "models" / name / "best.pt"
        if p.exists():
            return str(p)
    return settings.yolo_model


def dets_to_labels(dets, zones: dict, w: int, h: int) -> list[dict]:
    """Detections (+ tableware items) + table zones -> label boxes in pixel coords."""
    boxes: list[dict] = []
    items = [d for d in dets if d.cls == "item"]
    for d in dets:
        if d.cls == "person":
            boxes.append({"cls": 1 if d.is_staff else 0, "x1": d.x1, "y1": d.y1, "x2": d.x2, "y2": d.y2})
        elif d.cls in ("table_clean", "table_dirty"):
            boxes.append({"cls": CLASSES.index(d.cls), "x1": d.x1, "y1": d.y1, "x2": d.x2, "y2": d.y2})
    for t in zones.get("tables", []):
        bb = t.get("table_bbox")
        if not bb:
            continue
        poly = np.array(t["polygon"], np.float32)
        dirty = any(cv2.pointPolygonTest(poly, ((i.x1 + i.x2) / 2, (i.y1 + i.y2) / 2), False) >= 0 for i in items)
        boxes.append({"cls": 3 if dirty else 2, "x1": bb[0], "y1": bb[1], "x2": bb[2], "y2": bb[3]})
    return boxes


def _clip(b: dict, w: int, h: int) -> dict | None:
    x1, x2 = sorted((max(0.0, min(w, float(b["x1"]))), max(0.0, min(w, float(b["x2"])))))
    y1, y2 = sorted((max(0.0, min(h, float(b["y1"]))), max(0.0, min(h, float(b["y2"])))))
    c = int(b["cls"])
    if x2 - x1 < 4 or y2 - y1 < 4 or not 0 <= c < len(CLASSES):
        return None
    return {"cls": c, "x1": x1, "y1": y1, "x2": x2, "y2": y2}


class Studio:
    def __init__(self, settings, db, pipeline):
        self.s, self.db, self.pipe = settings, db, pipeline
        self.root = studio_root(settings)
        for d in ("images", "labels", "models", "runs", "uploads"):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._train_proc: subprocess.Popen | None = None

    # ------------------------------------------------------------- jobs
    def _job(self, kind: str, total: int = 0) -> dict:
        j = {"id": f"{kind}-{int(time.time() * 1000)}", "kind": kind, "status": "running", "done": 0,
             "total": total, "message": "", "started": time.time()}
        with self._lock:
            self.jobs[j["id"]] = j
            for k in [k for k, v in self.jobs.items() if v["status"] != "running"][:-8]:
                self.jobs.pop(k, None)
        return j

    def job_list(self) -> list[dict]:
        with self._lock:
            return sorted(self.jobs.values(), key=lambda j: -j["started"])[:8]

    @property
    def frame_size(self) -> tuple[int, int]:
        return self.pipe.size

    # ---------------------------------------------------------- dataset
    def _save_image(self, frame: np.ndarray, prefix: str) -> str:
        w, h = self.frame_size
        if frame.shape[1] != w or frame.shape[0] != h:
            frame = cv2.resize(frame, (w, h))
        name = f"{prefix}_{int(time.time() * 1000)}_{random.randint(100, 999)}.jpg"
        cv2.imwrite(str(self.root / "images" / name), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        return name

    def capture(self, cam: str | None) -> str | None:
        w = self.pipe.workers.get(cam or self.pipe.cam_ids[0])
        if w is None or w.last_raw is None:
            return None
        name = self._save_image(w.last_raw.copy(), f"live-{w.cam_id}")
        if w.is_sim and w.last_dets is not None:          # simulator knows the ground truth -> label for free
            fw, fh = self.frame_size
            self.save_boxes(name, dets_to_labels(w.last_dets, self.pipe.zones, fw, fh))
        return name

    def capture_series(self, cam: str | None, count: int, interval: float) -> dict:
        j = self._job("capture", count)

        def run():
            try:
                for i in range(count):
                    if self.capture(cam) is None:
                        j["message"] = "no camera frame"
                    j["done"] = i + 1
                    time.sleep(interval)
                j["status"] = "done"
            except Exception as e:  # pragma: no cover
                j["status"], j["message"] = "failed", str(e)
        threading.Thread(target=run, daemon=True).start()
        return j

    def extract_video(self, path: Path, every: float, max_frames: int, min_diff: float = 4.0) -> dict:
        j = self._job("extract", max_frames)

        def run():
            try:
                cap = cv2.VideoCapture(str(path))
                if not cap.isOpened():
                    raise RuntimeError("cannot open video")
                fps = cap.get(cv2.CAP_PROP_FPS) or 25
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                step, i, saved, prev = max(1, int(fps * every)), 0, 0, None
                prefix = re.sub(r"[^A-Za-z0-9]+", "-", path.stem)[:24] or "video"
                while saved < max_frames:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    if i % step == 0:
                        small = cv2.cvtColor(cv2.resize(frame, (64, 36)), cv2.COLOR_BGR2GRAY).astype(np.float32)
                        if prev is None or float(np.mean(np.abs(small - prev))) >= min_diff:
                            self._save_image(frame, prefix)
                            prev, saved = small, saved + 1
                            j["done"] = saved
                    i += 1
                    if total:
                        j["message"] = f"{min(100, int(100 * i / total))}% of video scanned"
                cap.release()
                j["status"], j["message"] = "done", f"{saved} frames extracted"
            except Exception as e:
                j["status"], j["message"] = "failed", str(e)
            finally:
                path.unlink(missing_ok=True)
        threading.Thread(target=run, daemon=True).start()
        return j

    def _names(self) -> list[str]:
        return sorted(p.name for p in (self.root / "images").glob("*.jpg"))

    def images(self, flt: str = "all", offset: int = 0, limit: int = 60) -> dict:
        names = self._names()
        rows = []
        for n in names:
            lp = self.root / "labels" / (Path(n).stem + ".txt")
            lab = lp.exists()
            if flt == "unlabeled" and lab or flt == "labeled" and not lab:
                continue
            rows.append({"name": n, "labeled": lab})
        return {"total": len(rows), "items": rows[offset: offset + limit]}

    def image_path(self, name: str) -> Path | None:
        p = self.root / "images" / Path(name).name
        return p if p.suffix == ".jpg" and p.exists() else None

    def get_boxes(self, name: str) -> dict | None:
        ip = self.image_path(name)
        if ip is None:
            return None
        img = cv2.imread(str(ip))
        h, w = img.shape[:2]
        lp = self.root / "labels" / (ip.stem + ".txt")
        boxes = []
        if lp.exists():
            for line in lp.read_text().splitlines():
                p = line.split()
                if len(p) == 5:
                    c, cx, cy, bw, bh = int(p[0]), *(float(v) for v in p[1:])
                    boxes.append({"cls": c, "x1": (cx - bw / 2) * w, "y1": (cy - bh / 2) * h,
                                  "x2": (cx + bw / 2) * w, "y2": (cy + bh / 2) * h})
        return {"name": ip.name, "width": w, "height": h, "labeled": lp.exists(), "boxes": boxes}

    def save_boxes(self, name: str, boxes: list[dict]) -> bool:
        ip = self.image_path(name)
        if ip is None:
            return False
        img = cv2.imread(str(ip))
        h, w = img.shape[:2]
        lines = []
        for b in boxes:
            c = _clip(b, w, h)
            if c:
                lines.append(f"{c['cls']} {(c['x1'] + c['x2']) / 2 / w:.6f} {(c['y1'] + c['y2']) / 2 / h:.6f} "
                             f"{(c['x2'] - c['x1']) / w:.6f} {(c['y2'] - c['y1']) / h:.6f}")
        (self.root / "labels" / (ip.stem + ".txt")).write_text("\n".join(lines))
        return True

    def delete_image(self, name: str) -> bool:
        ip = self.image_path(name)
        if ip is None:
            return False
        ip.unlink()
        (self.root / "labels" / (ip.stem + ".txt")).unlink(missing_ok=True)
        return True

    def stats(self) -> dict:
        per = {c: 0 for c in CLASSES}
        imgs = labeled = 0
        for p in (self.root / "images").glob("*.jpg"):
            imgs += 1
            lp = self.root / "labels" / (p.stem + ".txt")
            if lp.exists():
                labeled += 1
                for line in lp.read_text().splitlines():
                    try:
                        per[CLASSES[int(line.split()[0])]] += 1
                    except (ValueError, IndexError):
                        pass
        warnings = []
        if labeled < 100:
            warnings.append(f"Only {labeled} labelled images - aim for 300+ (min ~100) before trusting a trained model.")
        if per["table_dirty"] < 50:
            warnings.append("Few 'table_dirty' examples (<50). Label more dirty-table frames or the model will rarely detect them.")
        if per["staff"] < 50:
            warnings.append("Few 'staff' examples (<50). Staff vs customer will be unreliable.")
        return {"images": imgs, "labeled": labeled, "boxes": per, "warnings": warnings if imgs else []}

    # -------------------------------------------------------- auto-label
    def autolabel(self, only_unlabeled: bool = True) -> dict:
        names = [r["name"] for r in self.images("unlabeled" if only_unlabeled else "all", 0, 10 ** 6)["items"]]
        j = self._job("autolabel", len(names))

        def run():
            try:
                from .detector import YoloDetector
                s = self.s
                det = YoloDetector(active_model_path(s, self.db), min(s.yolo_conf, 0.3), s.yolo_imgsz, s.yolo_device,
                                   *self.pipe.uniform(), s.staff_pixel_ratio, False)
                fw, fh = self.frame_size
                for i, n in enumerate(names):
                    img = cv2.imread(str(self.root / "images" / n))
                    if img is not None:
                        self.save_boxes(n, dets_to_labels(det.detect(img), self.pipe.zones, fw, fh))
                    j["done"] = i + 1
                j["status"], j["message"] = "done", "Pre-labelled. Now review & fix in the Label tab."
            except Exception as e:
                log.exception("autolabel failed")
                j["status"], j["message"] = "failed", str(e)
        threading.Thread(target=run, daemon=True).start()
        return j

    def export_zip(self) -> Path:
        out = self.root / "export.zip"
        yaml = "path: .\ntrain: images\nval: images\nnames:\n" + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES))
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for p in (self.root / "images").glob("*.jpg"):
                lp = self.root / "labels" / (p.stem + ".txt")
                if lp.exists():
                    z.write(p, f"images/{p.name}")
                    z.write(lp, f"labels/{lp.name}")
            z.writestr("data.yaml", yaml)
        return out

    # ------------------------------------------------------------ train
    def _build_dataset(self, val_split: float, seed: int = 1) -> tuple[Path, int, int]:
        ds = self.root / "dataset"
        shutil.rmtree(ds, ignore_errors=True)
        pairs = [(p, self.root / "labels" / (p.stem + ".txt")) for p in sorted((self.root / "images").glob("*.jpg"))]
        pairs = [(i, l) for i, l in pairs if l.exists()]
        random.Random(seed).shuffle(pairs)
        n_val = max(1, int(len(pairs) * val_split)) if len(pairs) > 1 else 0
        for k, (img, lab) in enumerate(pairs):
            sp = "val" if k < n_val else "train"
            for sub, src in (("images", img), ("labels", lab)):
                d = ds / sub / sp
                d.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, d / src.name)
        (ds / "data.yaml").write_text(
            f"path: {ds}\ntrain: images/train\nval: images/val\nnames:\n"
            + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES)))
        return ds / "data.yaml", len(pairs) - n_val, n_val

    def train_state(self) -> dict:
        f = self.root / "train.json"
        st = json.loads(f.read_text()) if f.exists() else {"status": "idle"}
        if st.get("status") == "running":
            alive = self._train_proc is not None and self._train_proc.poll() is None
            if not alive:
                meta = self.root / "models" / st.get("name", "?") / "meta.json"
                st["status"] = "done" if meta.exists() else "failed"
                f.write_text(json.dumps(st))
        st["metrics"] = self._read_results(st.get("name"))
        log_f = self.root / "train.log"
        st["log"] = "\n".join(log_f.read_text(errors="ignore").splitlines()[-25:]) if log_f.exists() else ""
        return st

    def _read_results(self, name: str | None) -> list[dict]:
        if not name:
            return []
        f = self.root / "runs" / name / "results.csv"
        if not f.exists():
            return []
        rows = []
        with open(f, newline="") as fh:
            for r in csv.DictReader(fh):
                r = {k.strip(): v.strip() for k, v in r.items()}
                try:
                    rows.append({"epoch": int(float(r["epoch"])),
                                 "map50": round(float(r.get("metrics/mAP50(B)", 0)), 4),
                                 "map5095": round(float(r.get("metrics/mAP50-95(B)", 0)), 4),
                                 "box_loss": round(float(r.get("train/box_loss", 0)), 4),
                                 "cls_loss": round(float(r.get("train/cls_loss", 0)), 4)})
                except (KeyError, ValueError):
                    pass
        return rows

    def start_training(self, p: dict) -> dict:
        if self.train_state().get("status") == "running":
            raise ValueError("a training job is already running")
        try:
            import ultralytics  # noqa: F401,F811
        except ImportError:
            raise ValueError("ultralytics is not installed on this server (build with INSTALL_YOLO=1), "
                             "or export the dataset and train on a GPU machine / Colab, then import the .pt here")
        st = self.stats()
        if st["labeled"] < 8:
            raise ValueError(f"need at least 8 labelled images, have {st['labeled']}")
        name = (p.get("name") or time.strftime("model-%Y%m%d-%H%M")).strip()
        if not NAME_RE.match(name) or (self.root / "models" / name).exists():
            raise ValueError("invalid or already used model name")
        data, n_train, n_val = self._build_dataset(float(p.get("val_split", 0.2)))
        cfg = {"name": name, "base": p.get("base", "yolov8n.pt"), "epochs": int(p.get("epochs", 50)),
               "imgsz": int(p.get("imgsz", 960)), "batch": int(p.get("batch", 8)), "device": p.get("device", ""),
               "data": str(data), "root": str(self.root), "n_train": n_train, "n_val": n_val,
               "labeled": st["labeled"], "boxes": st["boxes"]}
        if cfg["base"] not in ("yolov8n.pt", "yolov8s.pt", "yolov8m.pt") and not Path(cfg["base"]).exists():
            raise ValueError("base must be yolov8n.pt / yolov8s.pt / yolov8m.pt")
        (self.root / "train.json").write_text(json.dumps({**cfg, "status": "running", "started": time.time()}))
        (self.root / "train_cfg.json").write_text(json.dumps(cfg))
        shutil.rmtree(self.root / "runs" / name, ignore_errors=True)
        logf = open(self.root / "train.log", "w")
        self._train_proc = subprocess.Popen(
            [sys.executable, "-m", "app.train_worker", str(self.root / "train_cfg.json")],
            stdout=logf, stderr=subprocess.STDOUT, cwd=str(Path(__file__).resolve().parents[1]))
        return self.train_state()

    def cancel_training(self) -> dict:
        if self._train_proc and self._train_proc.poll() is None:
            self._train_proc.terminate()
            f = self.root / "train.json"
            st = json.loads(f.read_text())
            st["status"] = "cancelled"
            f.write_text(json.dumps(st))
        return self.train_state()

    # ----------------------------------------------------------- models
    def models(self) -> list[dict]:
        active = self.db.get_settings().get("active_model")
        out = []
        for d in sorted((self.root / "models").iterdir(), key=lambda p: -p.stat().st_mtime):
            mf = d / "meta.json"
            if (d / "best.pt").exists():
                meta = json.loads(mf.read_text()) if mf.exists() else {}
                out.append({"name": d.name, "active": d.name == active, **meta})
        return out

    def _inspect(self, path: Path) -> dict:
        from ultralytics import YOLO
        m = YOLO(str(path))
        names = [str(v).lower() for v in getattr(m, "names", {}).values()]
        known = {"customer", "person", "guest", "staff", "waiter", "table_clean", "table_dirty"}
        return {"classes": names, "usable": bool(known & set(names))}

    def import_model(self, tmp: Path, name: str) -> dict:
        if not NAME_RE.match(name) or (self.root / "models" / name).exists():
            tmp.unlink(missing_ok=True)
            raise ValueError("invalid or already used model name")
        try:
            info = self._inspect(tmp)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            raise ValueError(f"not a valid YOLOv8 .pt file: {e}")
        d = self.root / "models" / name
        d.mkdir(parents=True)
        shutil.move(str(tmp), d / "best.pt")
        meta = {"source": "imported", "created": time.time(), **info}
        (d / "meta.json").write_text(json.dumps(meta))
        return {"name": name, **meta}

    def activate(self, name: str | None) -> dict:
        if name:
            p = self.root / "models" / name / "best.pt"
            if not p.exists():
                raise ValueError("unknown model")
            info = self._inspect(p)
            if not info["usable"]:
                raise ValueError(f"model classes {info['classes']} are not usable (need customer/staff/table_* names)")
        self.db.set_setting("active_model", name)
        self.pipe.reload_models()
        return {"active": name}

    def delete_model(self, name: str) -> None:
        if self.db.get_settings().get("active_model") == name:
            raise ValueError("deactivate the model first")
        shutil.rmtree(self.root / "models" / Path(name).name, ignore_errors=True)
