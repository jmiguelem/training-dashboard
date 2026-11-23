import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DB_PATH = Path(os.getenv("DB_PATH", ROOT / "data" / "training.db"))
WHOOP_CLIENT_ID = os.getenv("WHOOP_CLIENT_ID", "")
WHOOP_CLIENT_SECRET = os.getenv("WHOOP_CLIENT_SECRET", "")
WHOOP_REDIRECT_URI = os.getenv(
    "WHOOP_REDIRECT_URI", "http://localhost:8000/auth/whoop/callback"
)
# Login. No password set means the API refuses everything (fail closed).
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "30"))
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v2"
WHOOP_SCOPES = "offline read:recovery read:cycles read:sleep read:workout read:profile"

PROFILE_SEED = Path(os.getenv("PROFILE_SEED", ROOT / "data" / "profile.json"))
GARMIN_TOKENS = Path(os.getenv("GARMIN_TOKENS", ROOT / "data" / "garmin_tokens"))

COACH_MODEL = os.getenv("COACH_MODEL", "claude-sonnet-5-5")

AUTO_SYNC = os.getenv("AUTO_SYNC", "1") != "0"
AUTO_SYNC_DAY = os.getenv("AUTO_SYNC_DAY", "sun")
AUTO_SYNC_HOUR = int(os.getenv("AUTO_SYNC_HOUR", "23"))
AUTO_SYNC_MINUTE = int(os.getenv("AUTO_SYNC_MINUTE", "0"))

FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", ROOT / "frontend" / "dist"))
