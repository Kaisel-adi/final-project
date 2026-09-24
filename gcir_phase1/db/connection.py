"""
MongoDB connection helper. Single place the rest of the app imports from,
so tests can monkeypatch get_db() with a fixture/mongomock instance.
"""
from pymongo import MongoClient
from pymongo.database import Database

from config.settings import MONGO_URI, MONGO_DB_NAME

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client


def get_db() -> Database:
    return get_client()[MONGO_DB_NAME]
