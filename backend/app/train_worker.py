"""Subprocess that trains YOLO (started by Studio.start_training). Usage: python -m app.train_worker cfg.json"""
import json
import shutil
import sys
import time
from pathlib import Path


def main() -> None:
    cfg = json.loads(Path(sys.argv[1]).read_text())
    root, name = Path(cfg["root"]), cfg["name"]
    from ultralytics import YOLO

    model = YOLO(cfg["base"])
    model.train(data=cfg["data"], epochs=cfg["epochs"], imgsz=cfg["imgsz"], batch=cfg["batch"],
                device=cfg["device"] or None, project=str(root / "runs"), name=name, exist_ok=True,
                patience=20, plots=False, workers=2, fliplr=0.5, hsv_h=0.015, hsv_s=0.5, hsv_v=0.4)
    best = root / "runs" / name / "weights" / "best.pt"
    if not best.exists():
        best = root / "runs" / name / "weights" / "last.pt"
    bm = YOLO(str(best))
    m = bm.val(data=cfg["data"], imgsz=cfg["imgsz"], device=cfg["device"] or None, plots=False, verbose=False)
    names = [str(v) for v in bm.names.values()]
    per = {}
    try:
        for i, ci in enumerate(m.box.ap_class_index):
            per[names[int(ci)]] = round(float(m.box.ap50[i]), 3)
    except Exception:
        pass
    best_conf = best_f1 = None
    prec, rec = {}, {}
    try:                                   # confidence that maximises F1 on the held-out set (used as the live threshold)
        f1 = m.box.f1_curve.mean(0)
        k = int(f1.argmax())
        best_conf, best_f1 = round(float(m.box.px[k]), 3), round(float(f1[k]), 3)
        for i, ci in enumerate(m.box.ap_class_index):
            prec[names[int(ci)]], rec[names[int(ci)]] = round(float(m.box.p[i]), 3), round(float(m.box.r[i]), 3)
    except Exception:
        pass
    d = root / "models" / name
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, d / "best.pt")
    (d / "meta.json").write_text(json.dumps({
        "source": "trained", "created": time.time(), "base": cfg["base"], "epochs": cfg["epochs"],
        "imgsz": cfg["imgsz"], "n_train": cfg["n_train"], "n_val": cfg["n_val"], "labeled": cfg["labeled"],
        "boxes": cfg["boxes"], "classes": [n.lower() for n in names], "usable": True,
        "best_conf": best_conf, "best_f1": best_f1, "per_class_precision": prec, "per_class_recall": rec,
        "map50": round(float(m.box.map50), 4), "map5095": round(float(m.box.map), 4), "per_class_ap50": per}))
    print("TRAINING COMPLETE", name)


if __name__ == "__main__":
    main()
