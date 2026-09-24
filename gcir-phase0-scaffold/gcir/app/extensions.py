"""Shared extension instances, created here to avoid circular imports.

Each is initialized against the real Flask app in app/__init__.py.
"""
from flask_login import LoginManager
from pymongo import MongoClient

login_manager = LoginManager()

_client: MongoClient | None = None
_db = None


def init_mongo(app):
    """Create the Mongo client/db once, store on app config for reuse."""
    global _client, _db
    _client = MongoClient(app.config["MONGO_URI"])
    # Database name is taken from the URI path; PRD calls it "gcir".
    _db = _client.get_default_database()
    app.extensions["mongo_db"] = _db
    return _db


def get_db():
    """Fetch the shared db handle. Call init_mongo(app) first."""
    if _db is None:
        raise RuntimeError("Mongo not initialized — call init_mongo(app) first")
    return _db
