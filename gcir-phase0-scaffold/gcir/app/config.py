import os


class Config:
    """Central config. Values come from environment (.env in dev)."""

    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-key-not-for-production")

    # Database — PRD §8: single Atlas cluster, 2dsphere indexes on
    # reports.location, users.home_location, jurisdictions.geometry
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/gcir")

    # Image storage — PRD §9 (free hosts can wipe local disk, so external only)
    CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET")

    # Email — digests only, PRD §5.5
    EMAIL_API_KEY = os.environ.get("EMAIL_API_KEY")
    EMAIL_FROM_ADDRESS = os.environ.get("EMAIL_FROM_ADDRESS")

    # Job endpoints — PRD §7, §11: external cron hits these with a token,
    # never a real user session
    JOBS_SECRET_TOKEN = os.environ.get("JOBS_SECRET_TOKEN", "change-me-too")

    # Core rules — PRD §4. Configurable per pilot area since the threshold
    # is unreachable in sparse areas.
    VERIFY_THRESHOLD = int(os.environ.get("VERIFY_THRESHOLD", 10))
    UPVOTE_PROXIMITY_KM = float(os.environ.get("UPVOTE_PROXIMITY_KM", 5))

    # Digest cap — PRD §5.5
    DIGEST_MAX_ITEMS_PER_USER = 5

    # Duplicate suggestion radius — PRD §6
    DUPLICATE_RADIUS_M = 200
