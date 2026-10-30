
import os
import time

from flask import Flask, jsonify, request
from flask_cors import CORS

from route_service import route_bp
from traffic_engine import (
    select_signal,
    calculate_priority,
    ROADS
)

# The frontend folder is served by Flask too, so the whole project runs
# from one command:  http://127.0.0.1:5000/home.html
FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "frontend"
)

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)

# Public Route Finder endpoints (/api/geocode and /api/route)
app.register_blueprint(route_bp)

# Initial traffic data (used until YOLO sends actual counts)
traffic_data = {
    "North": {"vehicles": 15, "waiting": 25},
    "South": {"vehicles": 8, "waiting": 18},
    "East": {"vehicles": 22, "waiting": 35},
    "West": {"vehicles": 5, "waiting": 40}
}

# Temporary mapping from camera zones to road labels
ZONE_MAPPING = {
    "Top Left": "North",
    "Top Right": "East",
    "Bottom Left": "West",
    "Bottom Right": "South"
}


# Emergency priority is remembered for a short time so that /api/signal
# (used by the dashboard AND the 3D simulation) shows it too.
emergency_state = {"road": None, "expires_at": 0.0}


def get_active_emergency():
    """Return (road, seconds_remaining) or (None, 0) if none is active."""
    road = emergency_state["road"]
    remaining = emergency_state["expires_at"] - time.time()

    if road and remaining > 0:
        return road, remaining

    emergency_state["road"] = None
    return None, 0


@app.route("/")
def home():
    return jsonify({
        "project": "CITINOVA AI",
        "status": "Backend Running",
        "message": "Intelligent Traffic Management System"
    })


# Get traffic information
@app.route("/api/traffic", methods=["GET"])
def get_traffic():
    result = {}

    for road, data in traffic_data.items():
        result[road] = {
            "vehicles": data["vehicles"],
            "waiting": data["waiting"],
            "priority": calculate_priority(
                data["vehicles"],
                data["waiting"]
            )
        }

    return jsonify(result)


# Get adaptive traffic signal decision
@app.route("/api/signal", methods=["GET"])
def get_signal():
    emergency_road, remaining = get_active_emergency()

    road, duration, mode = select_signal(
        traffic_data,
        emergency=emergency_road
    )

    return jsonify({
        "selected_road": road,
        "green_duration": duration,
        "mode": mode,
        "emergency_active": emergency_road is not None,
        "emergency_seconds_remaining": int(round(remaining))
    })


# Emergency vehicle priority
@app.route("/api/emergency/<road>", methods=["GET"])
def emergency(road):
    road = road.capitalize()

    if road not in ROADS:
        return jsonify({"error": "Invalid road"}), 400

    selected, duration, mode = select_signal(
        traffic_data,
        emergency=road
    )

    # Remember it so /api/signal (and the 3D simulation) follow it
    emergency_state["road"] = selected
    emergency_state["expires_at"] = time.time() + duration

    return jsonify({
        "emergency_road": selected,
        "green_duration": duration,
        "mode": mode
    })


# Cancel emergency priority early (it also expires automatically)
@app.route("/api/emergency-clear", methods=["POST"])
def clear_emergency():
    emergency_state["road"] = None
    emergency_state["expires_at"] = 0.0

    return jsonify({"status": "cleared"})


# Simple health check used by the homepage status indicator
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "project": "CITINOVA AI"})


# Receive YOLO vehicle counts
@app.route("/api/update-traffic", methods=["POST"])
def update_traffic():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON data"}), 400

    updated = {}

    for zone, road in ZONE_MAPPING.items():
        if zone not in data:
            continue

        try:
            count = int(data[zone])

            if count < 0:
                raise ValueError

        except (ValueError, TypeError):
            return jsonify({
                "error": f"Invalid vehicle count for {zone}"
            }), 400

        traffic_data[road]["vehicles"] = count
        updated[road] = count

    if not updated:
        return jsonify({
            "error": "No valid zone counts provided"
        }), 400

    return jsonify({
        "status": "success",
        "message": "YOLO traffic counts received",
        "updated_roads": updated
    })


if __name__ == "__main__":
    print("===================================")
    print("       CITINOVA AI BACKEND")
    print("===================================")
    app.run(host="127.0.0.1", port=5000, debug=True)
