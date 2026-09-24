import logging
from bson import ObjectId
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.reports.services import haversine_distance_km
from app.db import get_db

logger = logging.getLogger(__name__)


def compute_text_similarity(text1: str, text2: str) -> float:
    """Computes TF-IDF cosine similarity between two issue descriptions with bi-grams."""
    if not text1 or not text2:
        return 0.0
    try:
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
        tfidf_matrix = vectorizer.fit_transform([text1, text2])
        sim = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return float(sim)
    except Exception as e:
        logger.error(f"Error computing text similarity: {e}")
        return 0.0


def check_potential_duplicate(report_doc: dict, radius_meters: float = 200.0,
                              similarity_threshold: float = 0.20, db=None) -> dict | None:
    """
    Finds existing reports within radius_meters that share the same category
    and have TF-IDF similarity exceeding similarity_threshold.
    """
    if db is None:
        db = get_db()

    coords = report_doc["location"]["coordinates"]
    lon, lat = coords[0], coords[1]
    rep_id = report_doc.get("_id")
    category = report_doc["category"]
    description = report_doc["description"]

    # Spatial query for candidates within 200m
    try:
        candidates = list(db.reports.find({
            "_id": {"$ne": rep_id},
            "category": category,
            "status": {"$in": ["Reported", "Verified"]},
            "location": {
                "$geoWithin": {
                    "$centerSphere": [[lon, lat], (radius_meters / 1000.0) / 6378.1]
                }
            }
        }))
    except Exception:
        # Fallback without 2dsphere index (e.g. unit test mock)
        all_candidates = list(db.reports.find({
            "_id": {"$ne": rep_id},
            "category": category,
            "status": {"$in": ["Reported", "Verified"]}
        }))
        candidates = []
        for c in all_candidates:
            c_coords = c["location"]["coordinates"]
            dist_km = haversine_distance_km(lon, lat, c_coords[0], c_coords[1])
            if dist_km <= (radius_meters / 1000.0):
                candidates.append(c)

    best_match = None
    best_score = 0.0

    for cand in candidates:
        score = compute_text_similarity(description, cand.get("description", ""))
        if score > best_score and score >= similarity_threshold:
            best_score = score
            best_match = cand

    if best_match:
        logger.info(f"Duplicate detected: {rep_id} matches {best_match['_id']} with similarity {best_score:.2f}")

    return best_match
