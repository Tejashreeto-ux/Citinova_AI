"""
CITINOVA AI - automated checks for the Flask backend.

Run from the project root:
    python -m unittest discover -s backend -v

These tests use fake (mocked) replies for Nominatim and OSRM, so they
do not need internet. They check OUR code, not the external services.
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as app_module            # noqa: E402
import route_service                # noqa: E402

client = app_module.app.test_client()


def fake_response(payload, status=200):
    reply = MagicMock()
    reply.status_code = status
    reply.json.return_value = payload
    reply.raise_for_status.side_effect = (
        None if status < 400 else requests.HTTPError("error")
    )
    return reply


OSRM_OK = {
    "code": "Ok",
    "routes": [
        {
            "distance": 12345.6,
            "duration": 1500.2,
            "geometry": {"coordinates": [[77.59, 12.97], [77.60, 12.98]]},
            "legs": [{"steps": [
                {"name": "MG Road", "distance": 500,
                 "maneuver": {"type": "depart", "bearing_after": 90}},
                {"name": "Ring Road", "distance": 800,
                 "maneuver": {"type": "turn", "modifier": "left"}},
                {"name": "", "distance": 0,
                 "maneuver": {"type": "arrive"}},
            ]}],
        },
        {
            "distance": 14000, "duration": 1700,
            "geometry": {"coordinates": [[77.59, 12.97], [77.61, 12.99]]},
            "legs": [{"steps": []}],
        },
    ],
}


class ExistingTrafficApis(unittest.TestCase):
    """The original dashboard endpoints must keep working."""

    def test_root_status(self):
        data = client.get("/").get_json()
        self.assertEqual(data["project"], "CITINOVA AI")

    def test_traffic_has_four_roads(self):
        data = client.get("/api/traffic").get_json()
        self.assertEqual(set(data), {"North", "South", "East", "West"})
        self.assertIn("priority", data["North"])

    def test_signal_default_keys(self):
        data = client.get("/api/signal").get_json()
        for key in ("selected_road", "green_duration", "mode"):
            self.assertIn(key, data)

    def test_yolo_update_changes_counts(self):
        reply = client.post("/api/update-traffic", json={
            "Top Left": 3, "Top Right": 4, "Bottom Left": 5, "Bottom Right": 6})
        self.assertEqual(reply.status_code, 200)
        traffic = client.get("/api/traffic").get_json()
        self.assertEqual(traffic["North"]["vehicles"], 3)
        self.assertEqual(traffic["South"]["vehicles"], 6)

    def test_yolo_update_rejects_bad_data(self):
        self.assertEqual(client.post("/api/update-traffic", json={"Top Left": -1}).status_code, 400)
        self.assertEqual(client.post("/api/update-traffic", json={"Top Left": "abc"}).status_code, 400)
        self.assertEqual(client.post("/api/update-traffic", json={}).status_code, 400)
        self.assertEqual(client.post("/api/update-traffic", data="nope").status_code, 400)


class EmergencyPriority(unittest.TestCase):

    def tearDown(self):
        client.post("/api/emergency-clear")

    def test_invalid_road(self):
        self.assertEqual(client.get("/api/emergency/up").status_code, 400)

    def test_emergency_reaches_signal_endpoint(self):
        reply = client.get("/api/emergency/west").get_json()
        self.assertEqual(reply["mode"], "EMERGENCY PRIORITY")

        signal = client.get("/api/signal").get_json()
        self.assertEqual(signal["selected_road"], "West")
        self.assertEqual(signal["mode"], "EMERGENCY PRIORITY")
        self.assertTrue(signal["emergency_active"])
        self.assertGreater(signal["emergency_seconds_remaining"], 0)

    def test_emergency_expires(self):
        client.get("/api/emergency/south")
        app_module.emergency_state["expires_at"] = time.time() - 1
        signal = client.get("/api/signal").get_json()
        self.assertEqual(signal["mode"], "ADAPTIVE MODE")
        self.assertFalse(signal["emergency_active"])

    def test_clear(self):
        client.get("/api/emergency/east")
        client.post("/api/emergency-clear")
        self.assertEqual(client.get("/api/signal").get_json()["mode"], "ADAPTIVE MODE")


class StaticPages(unittest.TestCase):

    def test_pages_are_served(self):
        for page in ("home.html", "index.html", "route.html",
                     "route.js", "portal.css", "script.js",
                     "traffic3d.js", "style.css"):
            reply = client.get(f"/{page}")
            self.assertEqual(reply.status_code, 200, page)
            reply.close()

    def test_health(self):
        self.assertEqual(client.get("/api/health").get_json()["status"], "ok")


class Geocode(unittest.TestCase):

    def setUp(self):
        route_service._geocode_cache.clear()
        route_service.NOMINATIM_MIN_GAP = 0

    def test_validation(self):
        self.assertEqual(client.get("/api/geocode").status_code, 400)
        self.assertEqual(client.get("/api/geocode?q=ab").status_code, 400)
        self.assertEqual(client.get("/api/geocode?q=" + "x" * 300).status_code, 400)

    @patch("route_service.requests.get")
    def test_success_and_cache(self, mock_get):
        mock_get.return_value = fake_response([
            {"display_name": "Tumakuru, Karnataka, India", "lat": "13.34", "lon": "77.10"},
            {"display_name": "broken entry"},
        ])
        first = client.get("/api/geocode?q=Tumakuru").get_json()
        self.assertEqual(len(first["results"]), 1)
        self.assertAlmostEqual(first["results"][0]["lat"], 13.34)

        second = client.get("/api/geocode?q=tumakuru").get_json()
        self.assertTrue(second["cached"])
        self.assertEqual(mock_get.call_count, 1)

        headers = mock_get.call_args.kwargs["headers"]
        self.assertIn("CITINOVA", headers["User-Agent"])

    @patch("route_service.requests.get")
    def test_no_results(self, mock_get):
        mock_get.return_value = fake_response([])
        self.assertEqual(client.get("/api/geocode?q=zzzzzzzz").status_code, 404)

    @patch("route_service.requests.get", side_effect=requests.Timeout())
    def test_timeout(self, _):
        self.assertEqual(client.get("/api/geocode?q=Mumbai").status_code, 504)

    @patch("route_service.requests.get", side_effect=requests.ConnectionError())
    def test_service_down(self, _):
        self.assertEqual(client.get("/api/geocode?q=Delhi").status_code, 502)

    @patch("route_service.requests.get")
    def test_rate_limited(self, mock_get):
        mock_get.return_value = fake_response([], status=429)
        self.assertEqual(client.get("/api/geocode?q=Chennai").status_code, 503)


class Route(unittest.TestCase):

    URL = "/api/route?from_lat=12.97&from_lon=77.59&to_lat=13.34&to_lon=77.10"

    def test_validation(self):
        self.assertEqual(client.get("/api/route").status_code, 400)
        self.assertEqual(client.get("/api/route?from_lat=abc&from_lon=1&to_lat=1&to_lon=1").status_code, 400)
        self.assertEqual(client.get("/api/route?from_lat=95&from_lon=1&to_lat=1&to_lon=1").status_code, 400)
        self.assertEqual(client.get("/api/route?from_lat=nan&from_lon=1&to_lat=1&to_lon=1").status_code, 400)
        self.assertEqual(client.get("/api/route?from_lat=5&from_lon=5&to_lat=5&to_lon=5").status_code, 400)

    @patch("route_service.requests.get")
    def test_success(self, mock_get):
        mock_get.return_value = fake_response(OSRM_OK)
        data = client.get(self.URL).get_json()

        self.assertEqual(len(data["routes"]), 2)
        first = data["routes"][0]
        self.assertEqual(first["distance_m"], 12346)
        self.assertEqual(first["duration_s"], 1500)
        self.assertEqual(first["coordinates"][0], [12.97, 77.59])   # [lat, lon]
        self.assertEqual(first["steps"][0]["instruction"], "Head east on MG Road")
        self.assertEqual(first["steps"][1]["instruction"], "Turn left onto Ring Road")
        self.assertEqual(first["steps"][2]["instruction"], "Arrive at your destination")

        # Honest labelling: no live traffic is claimed
        self.assertEqual(data["traffic_data"], "none")
        self.assertIn("NOT included", data["notice"])

        called_url = mock_get.call_args.args[0]
        self.assertIn("77.59,12.97;77.1,13.34", called_url)         # lon,lat order

    @patch("route_service.requests.get")
    def test_no_route(self, mock_get):
        mock_get.return_value = fake_response({"code": "NoRoute"}, status=400)
        self.assertEqual(client.get(self.URL).status_code, 404)

    @patch("route_service.requests.get")
    def test_bad_osrm_payload(self, mock_get):
        mock_get.return_value = fake_response({"code": "Ok", "routes": [{"oops": 1}]})
        self.assertEqual(client.get(self.URL).status_code, 502)

    @patch("route_service.requests.get", side_effect=requests.Timeout())
    def test_timeout(self, _):
        self.assertEqual(client.get(self.URL).status_code, 504)

    @patch("route_service.requests.get", side_effect=requests.ConnectionError())
    def test_service_down(self, _):
        self.assertEqual(client.get(self.URL).status_code, 502)


if __name__ == "__main__":
    unittest.main(verbosity=2)
