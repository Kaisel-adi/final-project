import pytest
import mongomock
from app import create_app
from app.config import TestConfig
from app.db import set_mongo_client


@pytest.fixture(scope="session")
def mock_mongo():
    """Returns a mongomock client for unit testing without MongoDB server."""
    client = mongomock.MongoClient()
    return client


@pytest.fixture(autouse=True)
def setup_mock_client(mock_mongo):
    """Automatically wires the mock mongo client into app.db for every test."""
    set_mongo_client(mock_mongo)
    yield
    set_mongo_client(None)


@pytest.fixture
def mock_db(mock_mongo):
    """Provides a fresh, clean mock database for each test."""
    db = mock_mongo[TestConfig.DATABASE_NAME]
    # Drop all collections between tests
    for col in db.list_collection_names():
        db.drop_collection(col)
    return db


@pytest.fixture
def app(mock_db):
    """Creates a test Flask application."""
    test_app = create_app(TestConfig)
    return test_app


@pytest.fixture
def client(app):
    """Creates a test client for the Flask app."""
    return app.test_client()
