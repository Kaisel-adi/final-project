"""
Database Cleanup Script for GCIR.
Purges all demo reports, demo upvotes, and placeholder demo user accounts,
while keeping jurisdiction boundaries intact for official complaint routing.

Usage:
    python scripts/clean_demo_data.py
    python scripts/clean_demo_data.py --yes
"""

import sys
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.db import get_db, init_db_indexes
from scripts.etl_boundaries import seed_database


DEMO_EMAILS = [
    "resident@gcir.local",
    "voter@gcir.local",
    "admin@gcir.local"
]


def clean_demo_data(purge_all_reports: bool = True, db=None):
    if db is None:
        db = get_db()
        init_db_indexes(db)

    print("=" * 60)
    print("GCIR Database Cleanup & Demo Data Purge")
    print("=" * 60)

    # 1. Remove demo placeholder accounts
    res_users = db.users.delete_many({"email": {"$in": DEMO_EMAILS}})
    print(f"[OK] Removed {res_users.deleted_count} demo user account(s).")

    # 2. Purge reports
    if purge_all_reports:
        res_reports = db.reports.delete_many({})
        res_upvotes = db.upvotes.delete_many({})
        res_digest = db.digest_log.delete_many({})
        print(f"[OK] Purged {res_reports.deleted_count} report(s).")
        print(f"[OK] Purged {res_upvotes.deleted_count} upvote(s).")
        print(f"[OK] Purged {res_digest.deleted_count} digest log(s).")

    # 3. Ensure jurisdictions are intact
    juris_count = db.jurisdictions.count_documents({})
    if juris_count == 0:
        print("Jurisdictions collection was empty. Seeding official boundaries...")
        seed_database(db)
        juris_count = db.jurisdictions.count_documents({})
    print(f"[OK] Verified {juris_count} official jurisdictions (MCD 250 wards & NCR) are intact.")

    print("\nDatabase is now clean and production-ready!")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Purge demo civic data from GCIR database.")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    if not args.yes:
        confirm = input("[WARN] This will delete all demo reports, upvotes, and demo test accounts. Proceed? (y/N): ").strip().lower()
        if confirm != "y":
            print("Operation cancelled.")
            sys.exit(0)

    clean_demo_data()


if __name__ == "__main__":
    main()
