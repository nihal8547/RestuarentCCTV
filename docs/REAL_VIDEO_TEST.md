# Testing with your real restaurant video

You do **not** need a simulator or any code. Three ways, easiest first:

## A. In the dashboard (no restart)
1. Start anything (`./run_demo.sh` or `docker compose up`), log in as owner.
2. **Settings → Video source → Upload & use** - choose an MP4 (CCTV export or phone video, H.264). It loops through the real YOLO AI.
3. **Settings → Table zones**: Add table → click the table corners on the video frame → Seats/Section → *Save & apply zones*.
4. **Settings → Staff uniform colour**: click a waiter's shirt → *Apply*. (Colour cue is OFF until you do this; without it staff are inferred from behaviour only.)
5. For a short clip lower the alert times: Settings → Service alert 30 s / Cleaning alert 20 s (production: 300 / 120).
6. Optional: **Remove demo history** so analytics only show real data. Table drawer → *Set as clean reference* on an empty clean table.

## B. Command line, real-time loop
`./run_real.sh samples/lunch.mp4` (Windows: `run_real.bat samples\lunch.mp4`). Real thresholds, no demo data.

## C. Fast offline analysis (best for a first accuracy check)
```bash
cd backend
python scripts/analyze_video.py ../samples/lunch.mp4 --out ../report --step 3 [--zones my_zones.json] [--demo-thresholds]
```
Runs the whole AI over the video faster than real time (synthetic clock, so a 30-minute clip with the real 5-min/2-min alerts
takes a few minutes) and writes `report/annotated.mp4` (same overlay as the live view), `summary.txt` and `summary.json`
(guests per table, events, alerts, customer/staff tracks).

## What good footage looks like
Fixed camera, high/overhead angle, 720p+, tables not hidden, 10-60 minutes covering seating, a waiter visit and a table being cleared.

## How to judge the result (send me these 3 things)
1. `annotated.mp4` (or a screenshot of the Live tab) - are guests boxed and counted right? Are waiters marked Staff?
2. Table timers vs reality: seated/left times within a few seconds?
3. False alerts: any "no service" / "uncleaned" alert that was wrong?
Then use **Model Studio** to label ~300 frames and train a model for your restaurant (see HOW_IT_WORKS.md).

## Known limits to expect
Heavy occlusion (people behind pillars), very small/far people (raise `YOLO_IMGSZ` to 1280), night/IR footage, uniforms that match customer clothing,
and fast lighting changes (dirty-table appearance cue).
