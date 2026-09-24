import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.db import get_db, init_db_indexes
from scripts.etl_boundaries import seed_database
from app.ml.clustering import compute_dbscan_hotspots


DEMO_IMAGES = {
    "pothole": "https://images.unsplash.com/photo-1515162816999-a0c47dc192f7?w=800&auto=format&fit=crop",
    "garbage": "https://images.unsplash.com/photo-1605600659908-0ef719419d41?w=800&auto=format&fit=crop",
    "water_leak": "https://images.unsplash.com/photo-1585829365295-ab7cd400c167?w=800&auto=format&fit=crop",
    "streetlight": "https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=800&auto=format&fit=crop",
    "parks": "https://images.unsplash.com/photo-1448375240586-882707db888b?w=800&auto=format&fit=crop",
    "sewage": "https://images.unsplash.com/photo-1544717305-2782549b5136?w=800&auto=format&fit=crop",
    "other": "https://images.unsplash.com/photo-1584467735871-8e85353a8413?w=800&auto=format&fit=crop"
}


def seed_demo(db=None):
    if db is None:
        db = get_db()
        init_db_indexes(db)
        seed_database(db)

    print("Seeding demo users...")
    db.users.delete_many({})
    db.reports.delete_many({})
    db.upvotes.delete_many({})
    db.digest_log.delete_many({})

    now = datetime.now(timezone.utc)

    # 1. Users
    resident = {
        "name": "Arun Kumar",
        "email": "resident@gcir.local",
        "password_hash": generate_password_hash("password123"),
        "role": "resident",
        "home_location": {"type": "Point", "coordinates": [77.190, 28.650]},  # Karol Bagh
        "last_login_location": {"type": "Point", "coordinates": [77.190, 28.650]},
        "digest_opt_in": True,
        "digest_radius_km": 5.0,
        "created_at": now
    }

    voter = {
        "name": "Pooja Sharma",
        "email": "voter@gcir.local",
        "password_hash": generate_password_hash("password123"),
        "role": "resident",
        "home_location": {"type": "Point", "coordinates": [77.195, 28.652]},  # Karol Bagh nearby
        "digest_opt_in": True,
        "digest_radius_km": 3.0,
        "created_at": now
    }

    admin = {
        "name": "Chief Civic Moderator",
        "email": "admin@gcir.local",
        "password_hash": generate_password_hash("admin123"),
        "role": "admin",
        "home_location": {"type": "Point", "coordinates": [77.2167, 28.6315]},  # Connaught Place
        "digest_opt_in": True,
        "digest_radius_km": 10.0,
        "created_at": now
    }

    r_id = db.users.insert_one(resident).inserted_id
    v_id = db.users.insert_one(voter).inserted_id
    a_id = db.users.insert_one(admin).inserted_id

    # 2. Seed realistic civic reports across Delhi-NCR
    demo_reports = [
        # Karol Bagh Cluster (Dense Hotspot)
        {
            "author_id": r_id,
            "category": "pothole",
            "description": "Deep dangerous pothole right after metro pillar 120 on DB Gupta Road, Karol Bagh.",
            "photo_url": DEMO_IMAGES["pothole"],
            "location": {"type": "Point", "coordinates": [77.1900, 28.6500]},
            "status": "Verified",
            "upvote_count": 11,
            "created_at": now - timedelta(days=2)
        },
        {
            "author_id": v_id,
            "category": "pothole",
            "description": "Secondary crater in road tarmac near pillar 121 Karol Bagh.",
            "photo_url": DEMO_IMAGES["pothole"],
            "location": {"type": "Point", "coordinates": [77.1904, 28.6502]},
            "status": "Reported",
            "upvote_count": 6,
            "created_at": now - timedelta(hours=8)
        },
        {
            "author_id": r_id,
            "category": "garbage",
            "description": "Overflowing public dhalao bin with waste spilling onto road near Karol Bagh market.",
            "photo_url": DEMO_IMAGES["garbage"],
            "location": {"type": "Point", "coordinates": [77.1910, 28.6510]},
            "status": "Reported",
            "upvote_count": 4,
            "created_at": now - timedelta(hours=4)
        },
        # Connaught Place (NDMC)
        {
            "author_id": a_id,
            "category": "streetlight",
            "description": "Two decorative street lamp posts non-functional in Inner Circle Block B.",
            "photo_url": DEMO_IMAGES["streetlight"],
            "location": {"type": "Point", "coordinates": [77.2180, 28.6320]},
            "status": "Complained",
            "upvote_count": 14,
            "created_at": now - timedelta(days=3)
        },
        # Civil Lines
        {
            "author_id": r_id,
            "category": "parks",
            "description": "Heavy eucalyptus branch cracked and resting on electrical wire outside gate.",
            "photo_url": DEMO_IMAGES["parks"],
            "location": {"type": "Point", "coordinates": [77.2210, 28.6810]},
            "status": "Reported",
            "upvote_count": 2,
            "created_at": now - timedelta(hours=10)
        },
        # Rohini Cluster
        {
            "author_id": v_id,
            "category": "water_leak",
            "description": "Continuous clean water leak from municipal supply line flooding road in Sector 10.",
            "photo_url": DEMO_IMAGES["water_leak"],
            "location": {"type": "Point", "coordinates": [77.1120, 28.7210]},
            "status": "Verified",
            "upvote_count": 12,
            "created_at": now - timedelta(days=1)
        },
        {
            "author_id": v_id,
            "category": "water_leak",
            "description": "Underground pipe burst causing low pressure and waterlogging in Rohini Sector 10.",
            "photo_url": DEMO_IMAGES["water_leak"],
            "location": {"type": "Point", "coordinates": [77.1128, 28.7215]},
            "status": "Reported",
            "upvote_count": 5,
            "created_at": now - timedelta(hours=6)
        },
        # Dwarka
        {
            "author_id": r_id,
            "category": "sewage",
            "description": "Manhole overflowing foul black sewage onto main sector road near Sector 6 market.",
            "photo_url": DEMO_IMAGES["sewage"],
            "location": {"type": "Point", "coordinates": [77.0510, 28.5810]},
            "status": "Reported",
            "upvote_count": 7,
            "created_at": now - timedelta(hours=12)
        },
        # Noida Sector 18
        {
            "author_id": v_id,
            "category": "pothole",
            "description": "Dangerous pothole at multi-level parking exit in Sector 18 Noida.",
            "photo_url": DEMO_IMAGES["pothole"],
            "location": {"type": "Point", "coordinates": [77.3260, 28.5710]},
            "status": "Reported",
            "upvote_count": 3,
            "created_at": now - timedelta(hours=5)
        },
        # Ghaziabad RDC
        {
            "author_id": r_id,
            "category": "garbage",
            "description": "Unattended commercial packaging garbage dumped on sidewalk outside office complex.",
            "photo_url": DEMO_IMAGES["garbage"],
            "location": {"type": "Point", "coordinates": [77.4410, 28.6810]},
            "status": "Reported",
            "upvote_count": 1,
            "created_at": now - timedelta(hours=2)
        }
    ]

    for item in demo_reports:
        item["is_flagged"] = False
        item["flag_reason"] = None
        item["cluster_id"] = None
        item["duplicate_of"] = None
        item["status_log"] = [
            {"status": "Reported", "timestamp": item["created_at"], "note": "Demo issue created"}
        ]
        if item["status"] in ("Verified", "Complained"):
            item["status_log"].append({
                "status": "Verified",
                "timestamp": item["created_at"] + timedelta(hours=4),
                "note": "Community verified with upvotes"
            })
        if item["status"] == "Complained":
            item["status_log"].append({
                "status": "Complained",
                "timestamp": item["created_at"] + timedelta(hours=8),
                "note": "Complaint drafted and dispatched by resident"
            })

    inserted_reports = db.reports.insert_many(demo_reports)
    print(f"Successfully seeded {len(inserted_reports.inserted_ids)} demo reports.")

    # Compute DBSCAN clusters on seeded reports
    clusters = compute_dbscan_hotspots(eps_km=0.5, min_samples=2, db=db)
    print(f"Computed {len(clusters)} initial hotspot clusters.")
    print("Demo accounts created:")
    print("  - Resident: resident@gcir.local (password123)")
    print("  - Secondary Voter: voter@gcir.local (password123)")
    print("  - Admin / Mod: admin@gcir.local (admin123)")


if __name__ == "__main__":
    try:
        seed_demo()
    except Exception as e:
        err_msg = str(e)
        if "ServerSelectionTimeoutError" in type(e).__name__ or "WinError 10061" in err_msg:
            print("\n" + "=" * 70)
            print("⚠️  [GCIR Connection Notice] Could not connect to local MongoDB (localhost:27017).")
            print("=" * 70)
            print("Because a local MongoDB daemon ('mongod') is not running on your computer,")
            print("you have two quick ways to proceed:\n")
            print("Option 1: Connect to free MongoDB Atlas (Recommended for cloud/Render)")
            print("  1. Create a free cluster at https://www.mongodb.com/cloud/atlas")
            print("  2. Open your '.env' file and update MONGODB_URI:")
            print("     MONGODB_URI=mongodb+srv://<username>:<password>@cluster0.abcde.mongodb.net/gcir_db?retryWrites=true&w=majority")
            print("  3. Run this script again: python scripts/seed_demo_data.py\n")
            print("Option 2: Zero-Install Standalone Mode (In-Memory)")
            print("  - Just start the web application directly:")
            print("    python wsgi.py")
            print("  - The app will automatically initialize and auto-seed demo data in memory!")
            print("=" * 70 + "\n")
        else:
            raise
