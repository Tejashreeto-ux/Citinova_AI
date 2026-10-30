"""
CITINOVA AI - Public Route Finder Service

Endpoints:
    GET /api/geocode?q=<place name>
    GET /api/route?from_lat=..&from_lon=..&to_lat=..&to_lon=..

Location search:
    1. Photon (primary)
    2. Nominatim (fallback)

Driving route:
    OSRM public demo server

IMPORTANT:
Travel times are estimates based on road data and typical speeds.
This service does not provide live traffic information.
"""

import math
import os
import threading
import time

import requests
from flask import Blueprint, jsonify, request


route_bp = Blueprint("route_service", __name__)


# --------------------------------------------------
# External service URLs
# --------------------------------------------------

PHOTON_URL = "https://photon.komoot.io/api/"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"


# --------------------------------------------------
# Configuration
# --------------------------------------------------

_contact = os.environ.get(
    "CITINOVA_CONTACT",
    "hackathon-demo"
)

USER_AGENT = f"CITINOVA-AI-Hackathon/1.0 ({_contact})"

REQUEST_TIMEOUT = 12
NOMINATIM_MIN_GAP = 1.1

CACHE_SECONDS = 600
MAX_CACHE_ENTRIES = 200


TRAFFIC_NOTICE = (
    "Travel time is an estimate from OpenStreetMap road data "
    "and typical speeds. No live traffic provider is connected, "
    "so current congestion is not included."
)


# --------------------------------------------------
# Cache and request synchronization
# --------------------------------------------------

_geocode_cache = {}

_nominatim_lock = threading.Lock()

_last_nominatim_call = 0.0


# --------------------------------------------------
# Common helpers
# --------------------------------------------------

def _error(message, status):
    return jsonify({"error": message}), status


def _cache_get(key):

    entry = _geocode_cache.get(key)

    if entry and time.time() - entry[0] < CACHE_SECONDS:
        return entry[1]

    return None


def _cache_put(key, value):

    if len(_geocode_cache) >= MAX_CACHE_ENTRIES:
        _geocode_cache.clear()

    _geocode_cache[key] = (time.time(), value)


def _parse_coordinate(name, low, high):

    raw = request.args.get(name)

    if raw is None or raw.strip() == "":
        raise ValueError(f"Missing parameter: {name}")

    try:
        value = float(raw)

    except ValueError:
        raise ValueError(f"Parameter {name} must be a number")

    if (
        math.isnan(value)
        or math.isinf(value)
        or not (low <= value <= high)
    ):
        raise ValueError(f"Parameter {name} is out of range")

    return value


# --------------------------------------------------
# Photon geocoding
# --------------------------------------------------

def _search_photon(query):

    results = []

    response = requests.get(
        PHOTON_URL,
        params={
            "q": query,
            "limit": 5
        },
        headers={
            "User-Agent": USER_AGENT
        },
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    data = response.json()

    features = data.get("features", [])

    for feature in features:

        try:

            coordinates = feature["geometry"]["coordinates"]

            lon = float(coordinates[0])
            lat = float(coordinates[1])

            props = feature.get("properties", {})

            parts = [
                props.get("name"),
                props.get("city"),
                props.get("state"),
                props.get("country")
            ]

            name = ", ".join(
                str(part)
                for part in parts
                if part
            )

            results.append({
                "name": name or query,
                "lat": lat,
                "lon": lon
            })

        except (KeyError, TypeError, ValueError, IndexError):
            continue

    return results


# --------------------------------------------------
# Nominatim fallback geocoding
# --------------------------------------------------

def _search_nominatim(query):

    global _last_nominatim_call

    results = []

    with _nominatim_lock:

        wait = NOMINATIM_MIN_GAP - (
            time.time() - _last_nominatim_call
        )

        if wait > 0:
            time.sleep(wait)

        response = requests.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "jsonv2",
                "limit": 5
            },
            headers={
                "User-Agent": USER_AGENT
            },
            timeout=REQUEST_TIMEOUT
        )

        _last_nominatim_call = time.time()

    response.raise_for_status()

    places = response.json()

    for place in places:

        try:

            results.append({
                "name": str(place["display_name"]),
                "lat": float(place["lat"]),
                "lon": float(place["lon"])
            })

        except (KeyError, TypeError, ValueError):
            continue

    return results


# --------------------------------------------------
# Geocoding API endpoint
# --------------------------------------------------

@route_bp.route("/api/geocode", methods=["GET"])
def geocode():

    query = " ".join(
        request.args.get("q", "").split()
    )

    if len(query) < 3:
        return _error(
            "Please enter at least 3 characters.",
            400
        )

    if len(query) > 200:
        return _error(
            "Search text is too long.",
            400
        )

    cache_key = query.lower()

    cached = _cache_get(cache_key)

    if cached is not None:

        return jsonify({
            "results": cached,
            "cached": True
        })

    results = []

    # First try Photon
    try:

        results = _search_photon(query)

    except requests.Timeout:

        print("Photon search timed out.")

    except requests.RequestException as error:

        print("Photon service error:", error)

    except ValueError as error:

        print("Photon response error:", error)

    # If Photon fails or finds nothing, use Nominatim
    if not results:

        try:

            results = _search_nominatim(query)

        except requests.Timeout:

            return _error(
                "Location search timed out. Please try again.",
                504
            )

        except requests.HTTPError as error:

            status = (
                error.response.status_code
                if error.response is not None
                else 502
            )

            if status == 429:

                return _error(
                    "Location search services are busy. "
                    "Please try again later.",
                    503
                )

            return _error(
                "Location search service returned an error.",
                502
            )

        except (requests.RequestException, ValueError):

            return _error(
                "Location search service is unavailable.",
                502
            )

    if not results:

        return _error(
            f'No location found for "{query}". '
            "Try a more specific place name.",
            404
        )

    _cache_put(cache_key, results)

    return jsonify({
        "results": results,
        "cached": False
    })


# --------------------------------------------------
# Compass direction helper
# --------------------------------------------------

def _compass(bearing):

    if bearing is None:
        return ""

    names = [
        "north",
        "north-east",
        "east",
        "south-east",
        "south",
        "south-west",
        "west",
        "north-west"
    ]

    return names[
        int(((bearing % 360) + 22.5) // 45) % 8
    ]


# --------------------------------------------------
# Turn-by-turn instructions
# --------------------------------------------------

TURN_TEXT = {
    "left": "Turn left",
    "right": "Turn right",
    "slight left": "Bear left",
    "slight right": "Bear right",
    "sharp left": "Turn sharp left",
    "sharp right": "Turn sharp right",
    "straight": "Continue straight",
    "uturn": "Make a U-turn"
}


def build_instruction(step):

    maneuver = step.get("maneuver", {})

    kind = maneuver.get("type", "")

    modifier = maneuver.get("modifier", "")

    name = step.get("name") or ""

    onto = f" onto {name}" if name else ""

    along = f" on {name}" if name else ""

    if kind == "depart":

        direction = _compass(
            maneuver.get("bearing_after")
        )

        return f"Head {direction}{along}".replace(
            "Head  ",
            "Head "
        ).strip()

    if kind == "arrive":

        side = {
            "left": " (on your left)",
            "right": " (on your right)"
        }.get(modifier, "")

        return f"Arrive at your destination{side}"

    if kind in (
        "roundabout",
        "rotary",
        "roundabout turn"
    ):

        exit_number = maneuver.get("exit")

        if exit_number:

            return (
                f"At the roundabout, take exit "
                f"{exit_number}{onto}"
            )

        return f"Enter the roundabout{onto}"

    if kind in ("exit roundabout", "exit rotary"):

        return f"Exit the roundabout{onto}"

    if kind == "merge":

        return (
            f"Merge {modifier}{onto}"
            if modifier
            else f"Merge{onto}"
        )

    if kind == "fork":

        return (
            f"Keep {modifier or 'straight'} at the fork{onto}"
        )

    if kind in ("on ramp", "off ramp"):

        return f"Take the ramp{onto}"

    if kind == "end of road":

        action = TURN_TEXT.get(
            modifier,
            "Turn"
        )

        return (
            f"At the end of the road, "
            f"{action.lower()}{onto}"
        )

    if kind in ("continue", "new name"):

        if modifier in ("", "straight"):

            return f"Continue straight{along}"

        return f"{TURN_TEXT.get(modifier, 'Continue')}{onto}"

    base = TURN_TEXT.get(
        modifier,
        "Continue"
    )

    if modifier in ("straight", "uturn", ""):

        return f"{base}{along}"

    return f"{base}{onto}"


# --------------------------------------------------
# Format OSRM route response
# --------------------------------------------------

def _format_route(route_data, index):

    # OSRM coordinates: [longitude, latitude]
    # Leaflet coordinates: [latitude, longitude]

    coordinates = [
        [lat, lon]
        for lon, lat in
        route_data["geometry"]["coordinates"]
    ]

    steps = []

    for leg in route_data.get("legs", []):

        for step in leg.get("steps", []):

            steps.append({
                "instruction": build_instruction(step),
                "distance_m": round(
                    step.get("distance", 0)
                ),
                "road": step.get("name") or ""
            })

    return {
        "index": index,

        "label": (
            "Recommended (fastest)"
            if index == 0
            else f"Alternative {index}"
        ),

        "distance_m": round(
            route_data["distance"]
        ),

        "duration_s": round(
            route_data["duration"]
        ),

        "coordinates": coordinates,

        "steps": steps
    }


# --------------------------------------------------
# Driving route API endpoint
# --------------------------------------------------

@route_bp.route("/api/route", methods=["GET"])
def route():

    try:

        from_lat = _parse_coordinate(
            "from_lat", -90, 90
        )

        from_lon = _parse_coordinate(
            "from_lon", -180, 180
        )

        to_lat = _parse_coordinate(
            "to_lat", -90, 90
        )

        to_lon = _parse_coordinate(
            "to_lon", -180, 180
        )

    except ValueError as problem:

        return _error(str(problem), 400)

    if (
        abs(from_lat - to_lat) < 1e-5
        and abs(from_lon - to_lon) < 1e-5
    ):

        return _error(
            "Source and destination are the same place.",
            400
        )

    url = (
        f"{OSRM_URL}/"
        f"{from_lon},{from_lat};"
        f"{to_lon},{to_lat}"
    )

    try:

        response = requests.get(
            url,

            params={
                "overview": "full",
                "geometries": "geojson",
                "steps": "true",
                "alternatives": "true"
            },

            headers={
                "User-Agent": USER_AGENT
            },

            timeout=REQUEST_TIMEOUT + 10
        )

        response.raise_for_status()

        data = response.json()

    except requests.Timeout:

        return _error(
            "Routing service timed out. Please try again.",
            504
        )

    except (requests.RequestException, ValueError):

        return _error(
            "Routing service is unavailable right now.",
            502
        )

    code = (
        data.get("code")
        if isinstance(data, dict)
        else None
    )

    if code == "NoRoute":

        return _error(
            "No driving route was found between these places.",
            404
        )

    if code != "Ok" or not data.get("routes"):

        return _error(
            "Routing service could not calculate this route.",
            502
        )

    try:

        routes = [
            _format_route(route_data, index)
            for index, route_data in
            enumerate(data["routes"][:3])
        ]

    except (KeyError, TypeError, ValueError):

        return _error(
            "Routing service returned unexpected data.",
            502
        )

    return jsonify({

        "routes": routes,

        "mode": "driving",

        "traffic_data": "none",

        "estimate_type": (
            "free-flow estimate (not live traffic)"
        ),

        "notice": TRAFFIC_NOTICE,

        "attribution": (
            "Routing: OSRM | "
            "Map data: OpenStreetMap contributors"
        )

    })