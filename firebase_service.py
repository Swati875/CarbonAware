"""Firebase and local database service operations."""

import os
import json
import logging
import threading
import copy
from datetime import datetime, timezone
from config import IS_FIREBASE_ENABLED, FIREBASE_CREDENTIALS_PATH

logger = logging.getLogger("firebase_service")

# Initialize Firebase if enabled
db = None
if IS_FIREBASE_ENABLED:
    try:
        # pyrefly: ignore [missing-import]
        import firebase_admin

        # pyrefly: ignore [missing-import]
        from firebase_admin import credentials, firestore

        # Avoid double initialization
        if not getattr(firebase_admin, "_apps", None):
            cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        logger.info("Firebase Firestore client successfully initialized.")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(
            "Error initializing Firebase: %s. Falling back to local database.", e
        )
        db = None

# Local Database Fallback Config & Caching
LOCAL_DB_FILE = "local_db.json"
_LOCAL_DB_CACHE = None
_db_lock = threading.Lock()


def _load_local_db_unlocked() -> dict:
    global _LOCAL_DB_CACHE  # pylint: disable=global-statement
    if _LOCAL_DB_CACHE is not None:
        return _LOCAL_DB_CACHE

    if not os.path.exists(LOCAL_DB_FILE):
        default_db = {
            "history": [],
            "goals": [
                {
                    "id": "goal_car",
                    "title": "Reduce driving by 20km/week",
                    "category": "transport",
                    "completed": False,
                    "target": 20,
                },
                {
                    "id": "goal_green",
                    "title": "Switch 50 kWh to Green Energy",
                    "category": "energy",
                    "completed": False,
                    "target": 50,
                },
                {
                    "id": "goal_diet",
                    "title": "Eat vegetarian for 4 days this week",
                    "category": "diet",
                    "completed": False,
                    "target": 4,
                },
                {
                    "id": "goal_recycle",
                    "title": "Recycle all plastic and metal waste",
                    "category": "waste",
                    "completed": False,
                    "target": 100,
                },
            ],
            "badges": [
                {
                    "id": "badge_welcome",
                    "title": "Eco Explorer",
                    "description": "Welcome to Carbon! You took the first step.",
                    "unlocked": True,
                    "icon": "🌱",
                },
                {
                    "id": "badge_saver",
                    "title": "Carbon Slasher",
                    "description": "Keep total footprint below 30kg CO2.",
                    "unlocked": False,
                    "icon": "⚡",
                },
                {
                    "id": "badge_commute",
                    "title": "Pedal Power",
                    "description": "Log transit km without car usage.",
                    "unlocked": False,
                    "icon": "🚲",
                },
                {
                    "id": "badge_forest",
                    "title": "Forest Friend",
                    "description": "Offsets that equal planting 10 trees.",
                    "unlocked": False,
                    "icon": "🌳",
                },
            ],
        }
        _save_local_db_unlocked(default_db)
        _LOCAL_DB_CACHE = default_db
        return _LOCAL_DB_CACHE
    try:
        with open(LOCAL_DB_FILE, "r", encoding="utf-8") as f:
            _LOCAL_DB_CACHE = json.load(f)
            return _LOCAL_DB_CACHE
    except Exception:  # pylint: disable=broad-exception-caught
        _LOCAL_DB_CACHE = {"history": [], "goals": [], "badges": []}
        return _LOCAL_DB_CACHE


def _save_local_db_unlocked(data: dict):
    global _LOCAL_DB_CACHE  # pylint: disable=global-statement
    _LOCAL_DB_CACHE = data
    temp_file = LOCAL_DB_FILE + ".tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        if os.path.exists(LOCAL_DB_FILE):
            os.remove(LOCAL_DB_FILE)
        os.rename(temp_file, LOCAL_DB_FILE)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Failed to write local DB atomically: %s", e)
        # Fallback to direct write
        with open(LOCAL_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def _load_local_db() -> dict:
    with _db_lock:
        return copy.deepcopy(_load_local_db_unlocked())


def _save_local_db(data: dict):
    with _db_lock:
        _save_local_db_unlocked(copy.deepcopy(data))


# Data Access Layer Methods
def save_calculation(calc_data: dict) -> dict:
    """Saves a footprint calculation to the database."""
    calc_data["timestamp"] = datetime.now(timezone.utc).isoformat()

    if db:
        try:
            # Save to Firestore
            # Use 'default_user' as placeholder client ID
            doc_ref = db.collection("history").document()
            doc_ref.set(calc_data)
            calc_data["id"] = doc_ref.id

            # Recalculate Badges based on Firestore state
            update_badges_firestore(calc_data)
            return calc_data
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Firestore save failed: %s. Saving locally.", e)

    # Local Save Fallback with transactional lock
    with _db_lock:
        local_data = _load_local_db_unlocked()

        # Set ID
        calc_data["id"] = f"calc_{len(local_data['history']) + 1}"
        local_data["history"].append(calc_data)

        # Dynamic Badge Unlocking
        total_co2 = calc_data["total"]

        # Carbon Slasher: total CO2 below 30
        if total_co2 < 30.0:
            for badge in local_data["badges"]:
                if badge["id"] == "badge_saver":
                    badge["unlocked"] = True

        # Pedal Power: if bus_km > 0 or flight_km > 0, and car_km == 0
        inputs = calc_data.get("inputs", {})
        trans = inputs.get("transport", {})
        if float(trans.get("car_km", 0)) == 0 and (float(trans.get("bus_km", 0)) > 0):
            for badge in local_data["badges"]:
                if badge["id"] == "badge_commute":
                    badge["unlocked"] = True

        # Forest Friend: offset/trees_needed calculation check
        if calc_data.get("trees_needed", 0) <= 5:  # low footprint, friendly to forest
            for badge in local_data["badges"]:
                if badge["id"] == "badge_forest":
                    badge["unlocked"] = True

        _save_local_db_unlocked(local_data)
    return calc_data


def get_history() -> list:
    """Retrieves the calculation history."""
    if db:
        try:
            docs = (
                db.collection("history")
                .order_by("timestamp", direction=firestore.Query.DESCENDING)
                .limit(50)
                .stream()
            )
            history = []
            for doc in docs:
                data = doc.to_dict()
                data["id"] = doc.id
                history.append(data)
            return history
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Firestore fetch history failed: %s. Fetching locally.", e)

    with _db_lock:
        local_data = copy.deepcopy(_load_local_db_unlocked())
    # Return sorted by newest first
    return sorted(
        local_data["history"], key=lambda x: x.get("timestamp", ""), reverse=True
    )


def get_goals() -> list:
    """Retrieves the user's goals."""
    if db:
        try:
            docs = db.collection("goals").stream()
            goals = []
            for doc in docs:
                g = doc.to_dict()
                g["id"] = doc.id
                goals.append(g)
            if goals:
                return goals
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Firestore goals fetch failed: %s. Fetching locally.", e)

    with _db_lock:
        local_data = copy.deepcopy(_load_local_db_unlocked())
    return local_data["goals"]


def toggle_goal(goal_id: str, completed: bool) -> list:
    """Toggles a goal's completion status."""
    if db:
        try:
            doc_ref = db.collection("goals").document(goal_id)
            doc_ref.update({"completed": completed})
            return get_goals()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Firestore toggle goal failed: %s. Toggling locally.", e)

    with _db_lock:
        local_data = _load_local_db_unlocked()
        for goal in local_data["goals"]:
            if goal["id"] == goal_id:
                goal["completed"] = completed
                break
        _save_local_db_unlocked(local_data)
        return copy.deepcopy(local_data["goals"])


def get_badges() -> list:
    """Retrieves the user's badges."""
    if db:
        try:
            docs = db.collection("badges").stream()
            badges = []
            for doc in docs:
                b = doc.to_dict()
                b["id"] = doc.id
                badges.append(b)
            if badges:
                return badges
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Firestore badges fetch failed: %s. Fetching locally.", e)

    with _db_lock:
        local_data = copy.deepcopy(_load_local_db_unlocked())
    return local_data["badges"]


def update_badges_firestore(last_calc: dict = None):
    """Updates the user's badges in Firestore based on the last calculation."""
    # Helper to sync/check badges in Firestore based on logs
    try:
        # Default badges status
        badges_ref = db.collection("badges")

        # Check welcome
        welcome_ref = badges_ref.document("badge_welcome")
        if not welcome_ref.get().exists:
            welcome_ref.set(
                {
                    "id": "badge_welcome",
                    "title": "Eco Explorer",
                    "description": "Welcome to Carbon! You took the first step.",
                    "unlocked": True,
                    "icon": "🌱",
                }
            )

        if last_calc:
            # Carbon Slasher
            if last_calc.get("total", 100) < 30.0:
                badges_ref.document("badge_saver").set(
                    {
                        "id": "badge_saver",
                        "title": "Carbon Slasher",
                        "description": "Keep total footprint below 30kg CO2.",
                        "unlocked": True,
                        "icon": "⚡",
                    },
                    merge=True,
                )

            # Pedal Power
            inputs = last_calc.get("inputs", {})
            trans = inputs.get("transport", {})
            if float(trans.get("car_km", 0)) == 0 and float(trans.get("bus_km", 0)) > 0:
                badges_ref.document("badge_commute").set(
                    {
                        "id": "badge_commute",
                        "title": "Pedal Power",
                        "description": "Log transit km without car usage.",
                        "unlocked": True,
                        "icon": "🚲",
                    },
                    merge=True,
                )

            # Forest Friend
            if last_calc.get("trees_needed", 100) <= 5:
                badges_ref.document("badge_forest").set(
                    {
                        "id": "badge_forest",
                        "title": "Forest Friend",
                        "description": "Offsets that equal planting 10 trees.",
                        "unlocked": True,
                        "icon": "🌳",
                    },
                    merge=True,
                )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error updating badges in Firestore: %s", e)
