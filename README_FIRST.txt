CITINOVA AI - FINAL DEMO PACKAGE
================================

WHAT IS INCLUDED
- Flask API backend
- Adaptive traffic decision engine (backend/traffic_engine.py)
- YOLOv8 webcam vehicle detector (backend/vehicle_detection.py)
- Government traffic dashboard (frontend/index.html)
- Project home page and public route finder
- API test file and run scripts

WINDOWS QUICK START (PowerShell)
1. Extract this ZIP to a normal folder, e.g. C:\CITINOVA_AI.
2. Open PowerShell in that folder.
3. Create environment:
      py -m venv venv
4. Activate:
      .\venv\Scripts\Activate.ps1
   If PowerShell blocks activation, run this once in that terminal:
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   Then activate again.
5. Install:
      python -m pip install --upgrade pip
      pip install -r requirements.txt
6. Start backend:
      python backend\app.py
7. Open these pages:
      http://127.0.0.1:5000/
      http://127.0.0.1:5000/index.html   (Government dashboard)
      http://127.0.0.1:5000/home.html    (Project home)
      http://127.0.0.1:5000/route.html   (Public route finder)
8. In a SECOND terminal, activate the same venv and run:
      python backend\vehicle_detection.py
   Allow webcam access. Press Q in the video window to stop.

IMPORTANT DEMO NOTES
- Start Flask before starting YOLO.
- First YOLO run may download yolov8n.pt; internet is required.
- A working webcam is required for live detection. If unavailable, the dashboard
  still works with seeded demo counts and you can demonstrate emergency override.
- The dashboard polls the API every 3 seconds.
- Camera frame is split into four quadrants. The counts are mapped as:
  Top Left -> North; Top Right -> East; Bottom Left -> West; Bottom Right -> South.
- The adaptive engine uses a simple explainable score:
  priority = 2 * vehicle_count + 0.7 * waiting_estimate.
  The road with the highest score receives the next green phase.
- Emergency override takes priority and is a simulation, not a physical traffic
  controller. Do not connect this demo to real signal hardware.
- Route finder uses OpenStreetMap Nominatim and OSRM. Internet is required.
  Travel time is a road-network estimate, NOT live traffic.

API QUICK CHECKS
  GET  http://127.0.0.1:5000/api/health
  GET  http://127.0.0.1:5000/api/traffic
  GET  http://127.0.0.1:5000/api/signal
  GET  http://127.0.0.1:5000/api/emergency/North
  POST http://127.0.0.1:5000/api/update-traffic
       JSON: {"Top Left":12,"Top Right":8,"Bottom Left":5,"Bottom Right":15}
  POST http://127.0.0.1:5000/api/emergency-clear

TROUBLESHOOTING
- ModuleNotFoundError: install dependencies using pip install -r requirements.txt
- Port 5000 already in use: close the other Flask process before starting.
- Webcam unavailable: close Zoom/Teams/Camera app; use seeded dashboard mode.
- YOLO weight download fails: connect to internet or place yolov8n.pt in backend/.
