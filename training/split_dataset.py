"""Split images+labels (flat folders) into train/val for YOLO.

  python training/split_dataset.py --images training/images --labels training/labels --out training/dataset --val 0.2
"""
import argparse
import random
import shutil
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--images", default="training/images")
ap.add_argument("--labels", default="training/labels")
ap.add_argument("--out", default="training/dataset")
ap.add_argument("--val", type=float, default=0.2)
ap.add_argument("--seed", type=int, default=1)
a = ap.parse_args()

imgs = sorted(p for p in Path(a.images).iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
imgs = [p for p in imgs if (Path(a.labels) / f"{p.stem}.txt").exists()]
random.Random(a.seed).shuffle(imgs)
n_val = max(1, int(len(imgs) * a.val)) if len(imgs) > 1 else 0
for i, p in enumerate(imgs):
    split = "val" if i < n_val else "train"
    for sub, src in (("images", p), ("labels", Path(a.labels) / f"{p.stem}.txt")):
        d = Path(a.out) / sub / split
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, d / src.name)
print(f"{len(imgs) - n_val} train / {n_val} val -> {a.out}")
