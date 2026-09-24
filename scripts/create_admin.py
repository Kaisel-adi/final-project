"""
Secure Admin Account Provisioning Script for GCIR.
Allows creating or resetting an administrator/moderator account without hardcoding credentials in Git.

Usage:
  Interactive:
    python scripts/create_admin.py

  Non-interactive (e.g. CI/CD or deployment):
    python scripts/create_admin.py --email your-email@domain.com --password YourSecretPassword --name "Admin Name"
"""

import sys
import getpass
import argparse
from pathlib import Path
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.db import get_db, init_db_indexes


def provision_admin(email: str, password: str, name: str = "Civic Administrator", db=None):
    if db is None:
        db = get_db()
        init_db_indexes(db)

    email_clean = email.strip().lower()
    if not email_clean or "@" not in email_clean:
        raise ValueError("Invalid email address.")

    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")

    now = datetime.now(timezone.utc)
    hashed = generate_password_hash(password)

    # Check if user already exists
    existing = db.users.find_one({"email": email_clean})

    if existing:
        db.users.update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "name": name,
                    "password_hash": hashed,
                    "role": "admin",
                    "updated_at": now
                }
            }
        )
        print(f"✓ Updated existing account '{email_clean}' to role: admin with new password.")
        return str(existing["_id"])
    else:
        doc = {
            "name": name,
            "email": email_clean,
            "password_hash": hashed,
            "role": "admin",
            "home_location": {"type": "Point", "coordinates": [77.2167, 28.6315]},  # Delhi center default
            "last_login_location": None,
            "digest_opt_in": True,
            "digest_radius_km": 10.0,
            "created_at": now,
            "last_login_at": now
        }
        res = db.users.insert_one(doc)
        print(f"✓ Successfully created new admin account: '{email_clean}'")
        return str(res.inserted_id)


def main():
    parser = argparse.ArgumentParser(description="Create or update an Admin user for GCIR.")
    parser.add_argument("--email", help="Admin email address")
    parser.add_argument("--password", help="Admin password")
    parser.add_argument("--name", default="Civic Administrator", help="Admin display name")

    args = parser.parse_args()

    email = args.email
    password = args.password
    name = args.name

    if not email:
        email = input("Enter Admin Email: ").strip()

    if not password:
        password = getpass.getpass("Enter Admin Password (min 8 chars): ").strip()
        confirm = getpass.getpass("Confirm Password: ").strip()
        if password != confirm:
            print("❌ Passwords do not match. Aborting.")
            sys.exit(1)

    try:
        provision_admin(email, password, name)
    except Exception as e:
        print(f"❌ Error provisioning admin: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
