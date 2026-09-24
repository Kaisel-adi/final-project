import logging
from shapely.geometry import Point, shape
from app.db import get_db

logger = logging.getLogger(__name__)

LEVEL_PRIORITY = {
    "ward": 4,
    "sector": 3,
    "district": 2,
    "state": 1
}


def lookup_authority_for_point(lon: float, lat: float, category: str, db=None) -> dict:
    """
    Hierarchically routes coordinates and issue category to the responsible authority.
    Uses MongoDB $geoIntersects if supported, with automatic Shapely fallback for testing.
    Rules:
    - Point-in-polygon containment on jurisdiction boundaries.
    - Filtered by category.
    - Highest specificity level wins (ward > sector > district > state).
    - Fallback: District or State body with 'is_fallback': True.
    """
    if db is None:
        db = get_db()

    query = {
        "geometry": {
            "$geoIntersects": {
                "$geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat]
                }
            }
        },
        "categories": category
    }

    try:
        matched_jurisdictions = list(db.jurisdictions.find(query))
    except Exception as e:
        logger.info(f"Mongo $geoIntersects fallback to Shapely: {e}")
        matched_jurisdictions = []
        pt = Point(lon, lat)
        all_juris = list(db.jurisdictions.find({"categories": category}))
        for j in all_juris:
            try:
                poly = shape(j["geometry"])
                if poly.contains(pt):
                    matched_jurisdictions.append(j)
            except Exception:
                continue

    # Sort matches by specificity (most specific level wins)
    matched_jurisdictions.sort(
        key=lambda j: LEVEL_PRIORITY.get(j.get("level", "state"), 0),
        reverse=True
    )

    if matched_jurisdictions:
        top_match = matched_jurisdictions[0]
        return {
            "name": top_match.get("name"),
            "level": top_match.get("level"),
            "body": top_match.get("body"),
            "contact_email": top_match.get("contact_email"),
            "phone": top_match.get("phone", "N/A"),
            "website": top_match.get("website", ""),
            "is_fallback": (top_match.get("level") in ("district", "state"))
        }

    # Ultimate fallback: Find state-level authority for category or generic state body
    fallback_doc = db.jurisdictions.find_one({"level": "state"})
    if fallback_doc:
        return {
            "name": fallback_doc.get("name"),
            "level": "state",
            "body": fallback_doc.get("body"),
            "contact_email": fallback_doc.get("contact_email"),
            "phone": fallback_doc.get("phone", "N/A"),
            "website": fallback_doc.get("website", ""),
            "is_fallback": True
        }

    return {
        "name": "NCT of Delhi Central Grievance Cell",
        "level": "state",
        "body": "Government of NCT of Delhi",
        "contact_email": "pgmsdelhi@nic.in",
        "phone": "1031",
        "website": "https://pgms.delhi.gov.in",
        "is_fallback": True
    }
