import os
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv


# Load .env file if it exists
load_dotenv()

# Gemini Configurations
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
IS_GEMINI_ENABLED = bool(GEMINI_API_KEY)

# Firebase Configurations
# We support either a path to service account key JSON or direct Firebase options
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH")
IS_FIREBASE_ENABLED = bool(FIREBASE_CREDENTIALS_PATH and os.path.exists(FIREBASE_CREDENTIALS_PATH))

# Server configurations
HOST = os.getenv("HOST", "127.0.0.1") 
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

print(f"--- CARBON CONFIGURATION ---")
print(f"Gemini AI Enabled: {IS_GEMINI_ENABLED}")
print(f"Firebase Firestore Enabled: {IS_FIREBASE_ENABLED} (Path: {FIREBASE_CREDENTIALS_PATH})")
if not IS_GEMINI_ENABLED:
    print("WARNING: GEMINI_API_KEY is not set. The app will run using local mock AI responses.")
if not IS_FIREBASE_ENABLED:
    print("WARNING: FIREBASE_CREDENTIALS_PATH is not set or file not found. The app will run using a local JSON database fallback.")
print(f"----------------------------")
