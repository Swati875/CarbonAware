import os
import unittest
import threading
# pyrefly: ignore [missing-import]
from fastapi.testclient import TestClient

# Make sure we don't accidentally load Firestore or load specific fallback config for tests
os.environ["FIREBASE_CREDENTIALS_PATH"] = ""
os.environ["GEMINI_API_KEY"] = ""

from main import app
from carbon_utils import calculate_footprint
import firebase_service

class CarbonAppTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # Clear cache and delete local db file before running to start clean
        if os.path.exists(firebase_service.LOCAL_DB_FILE):
            try:
                os.remove(firebase_service.LOCAL_DB_FILE)
            except Exception:
                pass
        firebase_service._LOCAL_DB_CACHE = None

    def tearDown(self):
        # Clean local db after each test
        if os.path.exists(firebase_service.LOCAL_DB_FILE):
            try:
                os.remove(firebase_service.LOCAL_DB_FILE)
            except Exception:
                pass
        firebase_service._LOCAL_DB_CACHE = None

    def test_calculate_footprint_math(self):
        data = {
            "transport": {
                "car_km": 100.0,
                "bus_km": 50.0,
                "flight_km": 0.0
            },
            "energy": {
                "grid_kwh": 100.0,
                "green_kwh": 50.0
            },
            "diet": "balanced",
            "waste": {
                "landfill_kg": 10.0,
                "recycled_kg": 20.0
            }
        }
        res = calculate_footprint(data)
        # transport = (100 * 0.2) + (50 * 0.04) = 20 + 2 = 22.0
        # energy = (100 * 0.45) + (50 * 0.02) = 45 + 1.0 = 46.0
        # diet = 1.8 * 7 = 12.6
        # waste = (10 * 0.5) + (20 * 0.05) = 5 + 1 = 6.0
        # total = 22 + 46 + 12.6 + 6 = 86.6
        # trees = 86.6 / 0.42 = 206.19
        self.assertAlmostEqual(res["breakdown"]["transport"], 22.0)
        self.assertAlmostEqual(res["breakdown"]["energy"], 46.0)
        self.assertAlmostEqual(res["breakdown"]["diet"], 12.6)
        self.assertAlmostEqual(res["breakdown"]["waste"], 6.0)
        self.assertAlmostEqual(res["total"], 86.6)
        self.assertAlmostEqual(res["trees_needed"], 206.19)

    def test_api_calculate_success(self):
        payload = {
            "transport": {"car_km": 50, "bus_km": 10, "flight_km": 0},
            "energy": {"grid_kwh": 20, "green_kwh": 10},
            "diet": "vegan",
            "waste": {"landfill_kg": 5, "recycled_kg": 5}
        }
        response = self.client.post("/api/calculate", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total", data)
        self.assertIn("breakdown", data)
        self.assertIn("id", data)

    def test_api_calculate_validation_failure(self):
        # Negative value which fails ge=0.0 constraint
        payload = {
            "transport": {"car_km": -10, "bus_km": 10, "flight_km": 0},
            "energy": {"grid_kwh": 20, "green_kwh": 10},
            "diet": "vegan",
            "waste": {"landfill_kg": 5, "recycled_kg": 5}
        }
        response = self.client.post("/api/calculate", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_api_get_history(self):
        # Seed some data
        payload = {
            "transport": {"car_km": 0, "bus_km": 0, "flight_km": 0},
            "energy": {"grid_kwh": 0, "green_kwh": 0},
            "diet": "vegetarian",
            "waste": {"landfill_kg": 0, "recycled_kg": 0}
        }
        self.client.post("/api/calculate", json=payload)
        
        response = self.client.get("/api/history")
        self.assertEqual(response.status_code, 200)
        history = response.json()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["inputs"]["diet"], "vegetarian")

    def test_api_get_goals_and_toggle(self):
        response = self.client.get("/api/goals")
        self.assertEqual(response.status_code, 200)
        goals = response.json()
        self.assertTrue(len(goals) > 0)
        
        goal_id = goals[0]["id"]
        # Toggle goal completed to True
        toggle_res = self.client.post(f"/api/goals/{goal_id}/toggle", json={"completed": True})
        self.assertEqual(toggle_res.status_code, 200)
        updated_goals = toggle_res.json()
        
        # Check if the goal state is updated in response
        updated_goal = next(g for g in updated_goals if g["id"] == goal_id)
        self.assertTrue(updated_goal["completed"])

    def test_api_get_badges(self):
        response = self.client.get("/api/badges")
        self.assertEqual(response.status_code, 200)
        badges = response.json()
        self.assertTrue(len(badges) > 0)

    def test_api_coach_mock_fallback(self):
        payload = {
            "message": "Give me some energy saving tips",
            "last_calculation": None
        }
        response = self.client.post("/api/coach", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("response", data)
        self.assertIn("Energy Efficiency Tips", data["response"])

    def test_api_coach_validation_failure(self):
        # Invalid last_calculation schema (negative values or wrong type)
        payload = {
            "message": "Hi",
            "last_calculation": {
                "breakdown": {"transport": -10.0, "energy": 0, "diet": 0, "waste": 0},
                "total": -10.0,
                "trees_needed": 0,
                "inputs": {
                    "transport": {"car_km": 0, "bus_km": 0, "flight_km": 0},
                    "energy": {"grid_kwh": 0, "green_kwh": 0},
                    "diet": "balanced",
                    "waste": {"landfill_kg": 0, "recycled_kg": 0}
                }
            }
        }
        response = self.client.post("/api/coach", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_api_metrics(self):
        response = self.client.get("/api/metrics")
        self.assertEqual(response.status_code, 200)
        metrics = response.json()
        self.assertIn("uptime_seconds", metrics)
        self.assertIn("energy_consumed_kwh", metrics)
        self.assertIn("emissions_g_co2", metrics)

    def test_security_headers_present(self):
        # Send simple request to home or endpoints
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        
        headers = response.headers
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(headers.get("X-XSS-Protection"), "1; mode=block")
        self.assertEqual(headers.get("Referrer-Policy"), "no-referrer")
        self.assertIn("default-src 'self'", headers.get("Content-Security-Policy", ""))
        self.assertIn("Strict-Transport-Security", headers)

    def test_caching_and_locking_concurrency(self):
        # Run concurrent calls to save_calculation locally and verify caching/lock safety
        payload = {
            "transport": {"car_km": 10, "bus_km": 0, "flight_km": 0},
            "energy": {"grid_kwh": 10, "green_kwh": 0},
            "diet": "balanced",
            "waste": {"landfill_kg": 5, "recycled_kg": 0}
        }
        
        exceptions = []
        def run_post():
            try:
                res = self.client.post("/api/calculate", json=payload)
                if res.status_code != 200:
                    exceptions.append(f"Bad status code: {res.status_code}")
            except Exception as e:
                exceptions.append(str(e))

        threads = [threading.Thread(target=run_post) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No exceptions should have been raised during concurrent reads/writes
        self.assertEqual(len(exceptions), 0)
        
        # Verify history length
        history_res = self.client.get("/api/history")
        self.assertEqual(len(history_res.json()), 10)

if __name__ == "__main__":
    unittest.main()
