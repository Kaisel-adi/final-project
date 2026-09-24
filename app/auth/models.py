from datetime import datetime, timezone
from bson import ObjectId
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.db import get_db


class User(UserMixin):
    """User representation integrating with Flask-Login and MongoDB."""
    def __init__(self, doc: dict | None = None):
        doc = doc or {}
        self.doc = doc
        self.id = str(doc.get("_id", ""))
        self.name = doc.get("name", "")
        self.email = doc.get("email", "")
        self.password_hash = doc.get("password_hash", "")
        self.role = doc.get("role", "resident")
        self.home_location = doc.get("home_location")  # GeoJSON Point
        self.last_login_location = doc.get("last_login_location")  # GeoJSON Point
        self.last_login_at = doc.get("last_login_at")
        self.digest_opt_in = doc.get("digest_opt_in", True)
        self.digest_radius_km = float(doc.get("digest_radius_km", 5.0))
        self.created_at = doc.get("created_at")

    @property
    def is_moderator(self) -> bool:
        return self.role in ("moderator", "admin")

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def get_by_id(user_id: str, db=None) -> "User | None":
        if db is None:
            db = get_db()
        try:
            if not user_id:
                return None
            doc = db.users.find_one({"_id": ObjectId(user_id)})
            return User(doc) if doc else None
        except Exception:
            return None

    @staticmethod
    def get_by_email(email: str, db=None) -> "User | None":
        if db is None:
            db = get_db()
        doc = db.users.find_one({"email": email.strip().lower()})
        return User(doc) if doc else None

    @staticmethod
    def create(name: str, email: str, password: str, home_coords: list[float] | None = None,
               role: str = "resident", digest_opt_in: bool = True, digest_radius_km: float = 5.0, db=None) -> "User":
        if db is None:
            db = get_db()

        email_clean = email.strip().lower()
        if db.users.find_one({"email": email_clean}):
            raise ValueError("An account with this email already exists.")

        user_doc = {
            "name": name.strip(),
            "email": email_clean,
            "password_hash": generate_password_hash(password),
            "role": role,
            "digest_opt_in": digest_opt_in,
            "digest_radius_km": float(digest_radius_km),
            "created_at": datetime.now(timezone.utc),
            "last_login_at": datetime.now(timezone.utc),
            "home_location": None,
            "last_login_location": None
        }

        if home_coords and len(home_coords) == 2:
            lon, lat = float(home_coords[0]), float(home_coords[1])
            user_doc["home_location"] = {
                "type": "Point",
                "coordinates": [lon, lat]
            }

        res = db.users.insert_one(user_doc)
        user_doc["_id"] = res.inserted_id
        return User(user_doc)
