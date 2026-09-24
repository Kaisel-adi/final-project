import math
from datetime import datetime, timezone
from bson import ObjectId
from flask import current_app
from app.db import get_db

CATEGORIES = [
    ("pothole", "Pothole / Road Damage"),
    ("garbage", "Garbage / Waste Overflow"),
    ("water_leak", "Water Leak / Pipe Burst"),
    ("streetlight", "Broken Streetlight / Dark Spot"),
    ("parks", "Fallen Tree / Park Maintenance"),
    ("sewage", "Sewage Overflow / Blockage"),
    ("other", "Other Civic Issue")
]


def haversine_distance_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees).
    """
    # Convert decimal degrees to radians
    r = 6371.0  # Earth's radius in kilometers
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def create_report(author_id: str, category: str, description: str,
                  photo_url: str, coordinates: list[float], db=None) -> dict:
    """
    Creates a new civic issue report in MongoDB.
    Location is stored strictly as a GeoJSON Point [longitude, latitude].
    """
    if db is None:
        db = get_db()

    valid_cats = [c[0] for c in CATEGORIES]
    if category not in valid_cats:
        raise ValueError(f"Invalid category '{category}'. Allowed: {valid_cats}")

    if not description or len(description.strip()) < 10:
        raise ValueError("Description must be at least 10 characters long.")

    if not coordinates or len(coordinates) != 2:
        raise ValueError("Valid [longitude, latitude] coordinates are required.")

    lon, lat = float(coordinates[0]), float(coordinates[1])
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError(f"Invalid coordinate range: [{lon}, {lat}]")

    now = datetime.now(timezone.utc)
    report_doc = {
        "author_id": ObjectId(author_id),
        "category": category,
        "description": description.strip(),
        "photo_url": photo_url,
        "location": {
            "type": "Point",
            "coordinates": [lon, lat]
        },
        "status": "Reported",
        "upvote_count": 0,
        "cluster_id": None,
        "duplicate_of": None,
        "is_flagged": False,
        "flag_reason": None,
        "status_log": [
            {
                "status": "Reported",
                "timestamp": now,
                "note": "Issue reported by community member"
            }
        ],
        "created_at": now
    }

    res = db.reports.insert_one(report_doc)
    report_doc["_id"] = res.inserted_id

    # Check for potential duplicates within 200m
    try:
        from app.ml.duplicates import check_potential_duplicate
        dup_match = check_potential_duplicate(report_doc, db=db)
        if dup_match:
            db.reports.update_one(
                {"_id": report_doc["_id"]},
                {"$set": {"duplicate_of": dup_match["_id"]}}
            )
            report_doc["duplicate_of"] = dup_match["_id"]
    except Exception:
        pass

    return report_doc


def upvote_report(report_id: str, user, user_coords: list[float] | None = None, db=None) -> dict:
    """
    Processes an upvote for a report adhering strictly to PRD §4 rules:
    - Author cannot upvote own post.
    - Exactly one upvote per account.
    - Soft proximity check (~5 km).
    - Status flips from Reported -> Verified when upvote_count >= VERIFY_THRESHOLD.
    """
    if db is None:
        db = get_db()

    rep_oid = ObjectId(report_id)
    usr_oid = ObjectId(user.id)

    report = db.reports.find_one({"_id": rep_oid})
    if not report:
        raise ValueError("Report not found.")

    if report["author_id"] == usr_oid:
        raise ValueError("Authors cannot upvote their own report.")

    # Check existing upvote
    existing = db.upvotes.find_one({"report_id": rep_oid, "user_id": usr_oid})
    if existing:
        raise ValueError("You have already verified/upvoted this report.")

    # Determine voter's location for soft proximity check
    # Preference: current submission coords -> user's home_location -> user's last_login_location
    voter_point = None
    if user_coords and len(user_coords) == 2:
        voter_point = [float(user_coords[0]), float(user_coords[1])]
    elif getattr(user, "home_location", None):
        voter_point = user.home_location.get("coordinates")
    elif getattr(user, "last_login_location", None):
        voter_point = user.last_login_location.get("coordinates")

    is_distance_flagged = False
    flag_radius = current_app.config.get("PROXIMITY_FLAG_RADIUS_KM", 5.0) if current_app else 5.0

    if voter_point and len(voter_point) == 2:
        rep_lon, rep_lat = report["location"]["coordinates"]
        dist_km = haversine_distance_km(voter_point[0], voter_point[1], rep_lon, rep_lat)
        if dist_km > flag_radius:
            is_distance_flagged = True

    now = datetime.now(timezone.utc)
    upvote_doc = {
        "report_id": rep_oid,
        "user_id": usr_oid,
        "user_location_at_vote": {"type": "Point", "coordinates": voter_point} if voter_point else None,
        "is_distance_flagged": is_distance_flagged,
        "created_at": now
    }
    db.upvotes.insert_one(upvote_doc)

    # Increment upvote count
    new_count = report.get("upvote_count", 0) + 1
    threshold = current_app.config.get("VERIFY_THRESHOLD", 10) if current_app else 10
    
    update_data = {"$set": {"upvote_count": new_count}}

    # Check threshold flip
    new_status = report.get("status")
    if new_count >= threshold and report.get("status") == "Reported":
        new_status = "Verified"
        update_data["$set"]["status"] = "Verified"
        update_data["$push"] = {
            "status_log": {
                "status": "Verified",
                "timestamp": now,
                "note": f"Threshold of {threshold} community upvotes reached. Complaint drafting unlocked."
            }
        }

    db.reports.update_one({"_id": rep_oid}, update_data)
    
    return {
        "success": True,
        "upvote_count": new_count,
        "status": new_status,
        "is_distance_flagged": is_distance_flagged
    }
