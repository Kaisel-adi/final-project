import time
import math
import logging
from bson import ObjectId
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.reports.services import haversine_distance_km
from app.db import get_db

logger = logging.getLogger(__name__)

# In-memory corpus vectorizer cache to prevent redundant per-comparison re-vectorization
_CORPUS_VECTORIZER_CACHE: dict = {
    "vectorizer": None,
    "last_fitted": 0.0,
    "doc_count": 0
}
CORPUS_CACHE_TTL = 600.0  # 10 minutes cache TTL


def get_cached_or_fitted_vectorizer(db=None) -> TfidfVectorizer | None:
    """
    Returns a cached TF-IDF vectorizer pre-fitted on recent report descriptions.
    Refreshes if cache TTL expires.
    """
    global _CORPUS_VECTORIZER_CACHE
    now = time.time()
    cached = _CORPUS_VECTORIZER_CACHE.get("vectorizer")
    last_fitted = _CORPUS_VECTORIZER_CACHE.get("last_fitted", 0.0)

    if cached is not None and (now - last_fitted) < CORPUS_CACHE_TTL:
        return cached

    if db is None:
        try:
            db = get_db()
        except Exception:
            return cached

    try:
        # Sample recent active report descriptions
        recent_docs = list(db.reports.find(
            {"status": {"$in": ["Reported", "Verified", "Complained", "Resolved"]}},
            {"description": 1}
        ).sort("created_at", -1).limit(500))

        texts = [d.get("description", "").strip() for d in recent_docs if d.get("description", "").strip()]
        if len(texts) >= 5:
            vec = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", max_features=5000)
            vec.fit(texts)
            _CORPUS_VECTORIZER_CACHE = {
                "vectorizer": vec,
                "last_fitted": now,
                "doc_count": len(texts)
            }
            return vec
    except Exception as e:
        logger.debug(f"Could not build corpus vectorizer: {e}")

    return cached


def clear_duplicate_cache() -> None:
    """Explicitly clears the in-memory TF-IDF corpus vectorizer cache."""
    global _CORPUS_VECTORIZER_CACHE
    _CORPUS_VECTORIZER_CACHE = {
        "vectorizer": None,
        "last_fitted": 0.0,
        "doc_count": 0
    }


def compute_batch_text_similarity(target_text: str, candidate_texts: list[str], db=None) -> list[float]:
    """
    Computes cosine similarity between target_text and a list of candidate_texts.
    Uses pre-fitted corpus vectorizer when available, or a single batch fit_transform,
    avoiding redundant vectorizer instantiation per candidate.
    """
    if not target_text or not candidate_texts:
        return [0.0] * len(candidate_texts)

    try:
        corpus_vec = get_cached_or_fitted_vectorizer(db=db)
        if corpus_vec is not None:
            # Transform target and all candidates in a single matrix operation
            all_matrix = corpus_vec.transform([target_text] + candidate_texts)
            if all_matrix[0].nnz > 0 and any(all_matrix[i].nnz > 0 for i in range(1, all_matrix.shape[0])):
                sims = cosine_similarity(all_matrix[0:1], all_matrix[1:])[0]
                return [float(s) for s in sims]

        # Single batch fit_transform across target + all candidate texts
        vec = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
        tfidf_matrix = vec.fit_transform([target_text] + candidate_texts)
        sims = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]
        return [float(s) for s in sims]
    except Exception as e:
        logger.error(f"Error in batch text similarity computation: {e}")
        return [0.0] * len(candidate_texts)


def compute_text_similarity(text1: str, text2: str) -> float:
    """Computes TF-IDF cosine similarity between two issue descriptions with bi-grams."""
    if not text1 or not text2:
        return 0.0
    scores = compute_batch_text_similarity(text1, [text2])
    return scores[0] if scores else 0.0


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

    candidates = []

    # Spatial query for candidates within radius_meters using native $geoNear when supported
    try:
        pipeline = [
            {
                "$geoNear": {
                    "near": {"type": "Point", "coordinates": [lon, lat]},
                    "distanceField": "distance_meters",
                    "maxDistance": radius_meters,
                    "spherical": True,
                    "query": {
                        "_id": {"$ne": rep_id},
                        "category": category,
                        "status": {"$in": ["Reported", "Verified"]}
                    }
                }
            },
            {"$limit": 50}
        ]
        candidates = list(db.reports.aggregate(pipeline))
        for c in candidates:
            if "_dist_km" not in c and "distance_meters" in c:
                c["_dist_km"] = round(c["distance_meters"] / 1000.0, 3)
    except Exception:
        # Fallback with indexed spatial bounding box pre-filtering to prevent scanning entire category
        radius_km = radius_meters / 1000.0
        lat_delta = (radius_km / 111.0) * 1.05
        cos_lat = max(0.1, abs(math.cos(math.radians(lat))))
        lon_delta = (radius_km / (111.0 * cos_lat)) * 1.05

        fallback_query = {
            "_id": {"$ne": rep_id},
            "category": category,
            "status": {"$in": ["Reported", "Verified"]},
            "location.coordinates.0": {"$gte": lon - lon_delta, "$lte": lon + lon_delta},
            "location.coordinates.1": {"$gte": lat - lat_delta, "$lte": lat + lat_delta}
        }
        all_candidates = list(db.reports.find(fallback_query).limit(50))
        for c in all_candidates:
            c_coords = c.get("location", {}).get("coordinates", [])
            if len(c_coords) == 2:
                dist_km = haversine_distance_km(lon, lat, c_coords[0], c_coords[1])
                if dist_km <= radius_km:
                    c["_dist_km"] = round(dist_km, 3)
                    candidates.append(c)

    if not candidates or not description:
        return None

    # Batch vectorization: Compute similarity against all candidates in a single vectorized pass
    cand_descriptions = [c.get("description", "") for c in candidates]
    scores = compute_batch_text_similarity(description, cand_descriptions, db=db)

    best_match = None
    best_score = 0.0

    for cand, score in zip(candidates, scores):
        if score > best_score and score >= similarity_threshold:
            best_score = score
            best_match = cand

    if best_match:
        logger.info(f"Duplicate detected: {rep_id} matches {best_match['_id']} with similarity {best_score:.2f}")

    return best_match
