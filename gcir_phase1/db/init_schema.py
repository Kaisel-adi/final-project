"""
Creates the collections and indexes listed in PRD §8.

Run once (and safe to re-run — Mongo index creation is idempotent):
    python -m db.init_schema

Indexes created:
  - reports.location            : 2dsphere   (nearby feed, §5.2)
  - users.home_location         : 2dsphere   (digest radius, §5.5)
  - users.last_login_location   : 2dsphere   (fallback location, §5.6)
  - jurisdictions.geometry      : 2dsphere   (authority lookup, §5.4)
  - upvotes.(report_id,user_id) : unique     (one vote per account, §4)
  - digest_log.(user_id,sent_at): compound   (dedupe check, §5.5)
"""
import logging

from pymongo import ASCENDING, GEOSPHERE
from pymongo.errors import OperationFailure

from db.connection import get_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_schema() -> None:
    db = get_db()

    # reports
    db.reports.create_index([("location", GEOSPHERE)], name="reports_location_2dsphere")
    db.reports.create_index([("status", ASCENDING)], name="reports_status")
    db.reports.create_index([("category", ASCENDING)], name="reports_category")
    logger.info("reports indexes ready")

    # users
    db.users.create_index([("home_location", GEOSPHERE)], name="users_home_location_2dsphere")
    db.users.create_index([("last_login_location", GEOSPHERE)], name="users_last_login_2dsphere")
    db.users.create_index([("email", ASCENDING)], name="users_email_unique", unique=True)
    logger.info("users indexes ready")

    # jurisdictions
    db.jurisdictions.create_index([("geometry", GEOSPHERE)], name="jurisdictions_geometry_2dsphere")
    db.jurisdictions.create_index([("level", ASCENDING)], name="jurisdictions_level")
    db.jurisdictions.create_index([("categories", ASCENDING)], name="jurisdictions_categories")
    logger.info("jurisdictions indexes ready")

    # upvotes — one vote per account per report (PRD §4)
    db.upvotes.create_index(
        [("report_id", ASCENDING), ("user_id", ASCENDING)],
        name="upvotes_report_user_unique",
        unique=True,
    )
    logger.info("upvotes indexes ready")

    # digest_log
    db.digest_log.create_index([("user_id", ASCENDING), ("sent_at", ASCENDING)], name="digest_log_user_sent")
    logger.info("digest_log indexes ready")


if __name__ == "__main__":
    try:
        init_schema()
        print("Schema/index initialization complete.")
    except OperationFailure as e:
        print(f"Mongo operation failed — check GCIR_MONGO_URI and Atlas network access: {e}")
        raise
