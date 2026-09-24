import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get("SECRET_KEY", "default-dev-secret-key-change-me")
    
    # Session & Cookie persistence settings (Prevents logout on refresh)
    PERMANENT_SESSION_LIFETIME = 86400 * 30  # 30 days in seconds
    REMEMBER_COOKIE_DURATION = 86400 * 30   # 30 days in seconds
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    
    # MongoDB settings
    MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/gcir_db")
    DATABASE_NAME = os.environ.get("DATABASE_NAME", "gcir_db")
    USE_MOCK_DB = os.environ.get("USE_MOCK_DB", "False").lower() in ("true", "1", "yes")
    
    # Verification & Civic settings
    VERIFY_THRESHOLD = int(os.environ.get("VERIFY_THRESHOLD", "10"))
    PROXIMITY_FLAG_RADIUS_KM = float(os.environ.get("PROXIMITY_FLAG_RADIUS_KM", "5.0"))
    NEARBY_FEED_DEFAULT_RADIUS_KM = float(os.environ.get("NEARBY_FEED_DEFAULT_RADIUS_KM", "5.0"))
    CORROBORATING_RADIUS_METERS = 200.0
    
    # Cron Security Token
    CRON_SECRET_TOKEN = os.environ.get("CRON_SECRET_TOKEN", "gcir-dev-cron-token-xyz")
    
    # File upload settings
    UPLOAD_FOLDER = BASE_DIR / "app" / "static" / "uploads"
    MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15 MB (supports short video clips)
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "mp4", "webm", "mov"}
    
    # Cloudinary settings
    USE_CLOUDINARY = os.environ.get("USE_CLOUDINARY", "False").lower() in ("true", "1", "yes")
    CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
    CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")
    
    # Email settings
    EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "mock").strip().strip('"').strip("'")
    EMAIL_FROM = os.environ.get("EMAIL_FROM", "GCIR Civic Alerts <alerts@gcir.local>").strip().strip('"').strip("'")
    BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "").strip().strip('"').strip("'")
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip().strip('"').strip("'")
    SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "").strip().strip('"').strip("'")
    SMTP_HOST = os.environ.get("SMTP_HOST", "").strip().strip('"').strip("'")
    _smtp_port_str = os.environ.get("SMTP_PORT", "587").strip().strip('"').strip("'")
    SMTP_PORT = int(_smtp_port_str) if _smtp_port_str.isdigit() else 587
    SMTP_USER = os.environ.get("SMTP_USER", "").strip().strip('"').strip("'")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip().strip('"').strip("'")
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "True").strip().strip('"').strip("'").lower() in ("true", "1", "yes")
    SMTP_USE_SSL = os.environ.get("SMTP_USE_SSL", "False").strip().strip('"').strip("'").lower() in ("true", "1", "yes")
    
    # ML settings
    HOTSPOT_DBSCAN_EPS_KM = 0.5  # 500 meters
    HOTSPOT_MIN_SAMPLES = 3
    DUPLICATE_DISTANCE_METERS = 200.0
    DUPLICATE_SIMILARITY_THRESHOLD = 0.65


class TestConfig(Config):
    """Testing configuration."""
    TESTING = True
    SECRET_KEY = "test-secret-key"
    DATABASE_NAME = "gcir_test_db"
    USE_CLOUDINARY = False
    EMAIL_BACKEND = "mock"
