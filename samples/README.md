# samples/

Drop test videos here (MP4/AVI) and run the app on them:

    VIDEO_SOURCE=samples/lunch.mp4 DEMO_MODE=1 ./run_demo.sh      # Linux/macOS
    set VIDEO_SOURCE=samples\lunch.mp4 && run_demo.bat              # Windows

Then open the Zone Editor (Settings tab) to draw the 6 table polygons on a frame of this video.
Video files are git-ignored.

`pedestrian_test.avi` is OpenCV's public pedestrian test clip (real street footage, NOT a restaurant). Use it only to check that
detection/tracking/zones work end to end:  `./run_real.sh samples/pedestrian_test.avi`
