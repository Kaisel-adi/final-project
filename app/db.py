import logging
from pymongo import MongoClient, GEOSPHERE, ASCENDING, DESCENDING
from pymongo.database import Database
from flask import current_app, g, has_app_context

logger = logging.getLogger(__name__)

_mongo_client: MongoClient | None = None


def set_mongo_client(client: MongoClient | None) -> None:
    """Explicitly sets or resets the active MongoClient instance (used for testing)."""
    global _mongo_client
    _mongo_client = client


def get_mongo_client(uri: str | None = None) -> MongoClient:
    """Singleton getter for MongoClient with automatic mock fallback if no server reachable."""
    global _mongo_client
    if _mongo_client is None:
        from app.config import Config
        is_testing = current_app and current_app.config.get("TESTING", False)
        use_mock = Config.USE_MOCK_DB or is_testing

        if use_mock:
            import mongomock
            _mongo_client = mongomock.MongoClient()
            return _mongo_client

        if uri is None:
            uri = Config.MONGODB_URI

        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
            client.admin.command("ping")
            _mongo_client = client
        except Exception as e:
            logger.warning(f"Could not connect to MongoDB at {uri}: {e}")
            logger.warning("Switching to in-memory mock database (mongomock) for local development.")
            import mongomock
            _mongo_client = mongomock.MongoClient()

    return _mongo_client


def is_mock_database() -> bool:
    """Returns True if the active database is using mongomock in-memory storage."""
    global _mongo_client
    if _mongo_client is None:
        get_mongo_client()
    try:
        import mongomock
        return isinstance(_mongo_client, mongomock.MongoClient)
    except ImportError:
        return False


def get_db(db_name: str | None = None) -> Database:
    """
    Get the active MongoDB database instance.
    Supports Flask application context or standalone script usage.
    """
    if has_app_context() and "db" in g:
        return g.db

    client = get_mongo_client()
    if db_name is None:
        if has_app_context():
            db_name = current_app.config.get("DATABASE_NAME", "gcir_db")
        else:
            from app.config import Config
            db_name = Config.DATABASE_NAME

    # Ensure the database name is narrowed to a string for typed MongoDB access.
    if not isinstance(db_name, str):
        db_name = "gcir_db"

    return client[db_name]


def close_db(e=None):
    """Close MongoDB connection on teardown if stored in g."""
    db = g.pop("db", None)
    # The client connection pool persists, no need to forcibly kill the client on every request


def init_db_indexes(db: Database) -> dict[str, list[str]]:
    """
    Create all required geospatial (2dsphere) and relational indexes.
    Returns a dictionary of created index names per collection.
    """
    created_indexes = {}
    logger.info("Initializing MongoDB indexes for GCIR...")

    # 1. reports collection
    # 2dsphere index on location is mandatory for $near and $geoWithin
    idx_reports_geo = db.reports.create_index([("location", GEOSPHERE)], name="idx_reports_location_2dsphere")
    idx_reports_status = db.reports.create_index([("status", ASCENDING), ("created_at", DESCENDING)], name="idx_reports_status_created")
    idx_reports_author = db.reports.create_index([("author_id", ASCENDING)], name="idx_reports_author")
    idx_reports_cluster = db.reports.create_index([("cluster_id", ASCENDING)], name="idx_reports_cluster")
    created_indexes["reports"] = [idx_reports_geo, idx_reports_status, idx_reports_author, idx_reports_cluster]

    # 2. users collection
    idx_users_email = db.users.create_index([("email", ASCENDING)], unique=True, name="idx_users_email_unique")
    idx_users_home = db.users.create_index([("home_location", GEOSPHERE)], name="idx_users_home_2dsphere", sparse=True)
    idx_users_last_loc = db.users.create_index([("last_login_location", GEOSPHERE)], name="idx_users_last_loc_2dsphere", sparse=True)
    created_indexes["users"] = [idx_users_email, idx_users_home, idx_users_last_loc]

    # 3. upvotes collection
    # Enforces business rule: Exactly one upvote per account per report
    idx_upvotes_unique = db.upvotes.create_index(
        [("report_id", ASCENDING), ("user_id", ASCENDING)],
        unique=True,
        name="idx_upvotes_report_user_unique"
    )
    idx_upvotes_report = db.upvotes.create_index([("report_id", ASCENDING)], name="idx_upvotes_report")
    created_indexes["upvotes"] = [idx_upvotes_unique, idx_upvotes_report]

    # 4. jurisdictions collection
    # 2dsphere index on geometry for point-in-polygon $geoIntersects queries
    idx_juris_geo = db.jurisdictions.create_index([("geometry", GEOSPHERE)], name="idx_jurisdictions_geometry_2dsphere")
    idx_juris_level = db.jurisdictions.create_index([("level", ASCENDING), ("categories", ASCENDING)], name="idx_juris_level_cat")
    created_indexes["jurisdictions"] = [idx_juris_geo, idx_juris_level]

    # 5. digest_log collection
    idx_digest_user = db.digest_log.create_index([("user_id", ASCENDING), ("sent_at", DESCENDING)], name="idx_digest_user_sent")
    created_indexes["digest_log"] = [idx_digest_user]

    logger.info(f"Successfully initialized indexes: {list(created_indexes.keys())}")
    return created_indexes
