import time
import logging
import numpy as np
from sklearn.cluster import DBSCAN
from app.db import get_db

logger = logging.getLogger(__name__)

# In-memory hotspots cluster cache with TTL to eliminate redundant CPU/memory spikes
_CLUSTERS_CACHE: dict = {}
DEFAULT_HOTSPOTS_CACHE_TTL = 300.0  # 5 minutes TTL


def clear_hotspots_cache() -> None:
    """Explicitly clears the hotspots cluster cache."""
    global _CLUSTERS_CACHE
    _CLUSTERS_CACHE.clear()


def compute_dbscan_hotspots(
    eps_km: float = 0.5,
    min_samples: int = 3,
    db=None,
    force_refresh: bool = False,
    ttl_seconds: float = DEFAULT_HOTSPOTS_CACHE_TTL
) -> list[dict]:
    """
    Applies DBSCAN clustering on active civic report coordinates using haversine metric.
    Includes in-memory TTL caching based on active report count and latest report timestamp.
    Updates cluster_id on report documents and returns detected hotspot cluster summaries.
    """
    if db is None:
        db = get_db()

    active_filter = {"status": {"$in": ["Reported", "Verified", "Complained"]}}

    # Check cache if not forcing refresh
    if not force_refresh:
        try:
            total_active = db.reports.count_documents(active_filter)
            latest_doc = db.reports.find_one(active_filter, {"_id": 1}, sort=[("created_at", -1)])
            latest_id = str(latest_doc["_id"]) if latest_doc else None
            cache_key = (round(eps_km, 4), min_samples, total_active, latest_id)

            now = time.time()
            if cache_key in _CLUSTERS_CACHE:
                entry = _CLUSTERS_CACHE[cache_key]
                if (now - entry["timestamp"]) < ttl_seconds:
                    logger.debug("Returning cached DBSCAN hotspot clusters.")
                    return entry["data"]
        except Exception as e:
            logger.debug(f"Cache check bypass: {e}")
            cache_key = None
    else:
        cache_key = None

    # Fetch active reports with lean projection (coordinates and category only, skipping descriptions)
    reports = list(db.reports.find(
        active_filter,
        {"_id": 1, "location.coordinates": 1, "category": 1}
    ))

    if len(reports) < min_samples:
        return []

    # Prepare coordinates in [latitude_radians, longitude_radians] for haversine
    # Note: GeoJSON stores [lon, lat], so lat = coords[1], lon = coords[0]
    coords = []
    report_ids = []
    for r in reports:
        c = r["location"]["coordinates"]
        coords.append([c[1], c[0]])
        report_ids.append(r["_id"])

    coords_rad = np.radians(coords)
    kms_per_radian = 6371.0
    epsilon = eps_km / kms_per_radian

    dbscan = DBSCAN(eps=epsilon, min_samples=min_samples, metric="haversine", algorithm="ball_tree")
    labels = dbscan.fit_predict(coords_rad)

    # Group into clusters
    clusters_map = {}
    for idx, label in enumerate(labels):
        rep_id = report_ids[idx]
        cluster_val = int(label) if label != -1 else None
        
        # Update report in db
        db.reports.update_one({"_id": rep_id}, {"$set": {"cluster_id": cluster_val}})

        if label != -1:
            clusters_map.setdefault(label, []).append((coords[idx], reports[idx]))

    # Compute cluster summaries
    cluster_summaries = []
    for label, items in clusters_map.items():
        lat_sum = sum(item[0][0] for item in items)
        lon_sum = sum(item[0][1] for item in items)
        count = len(items)
        categories = {}
        for _, r in items:
            cat = r.get("category", "other")
            categories[cat] = categories.get(cat, 0) + 1

        cluster_summaries.append({
            "cluster_id": int(label),
            "size": count,
            "center": [round(lat_sum / count, 6), round(lon_sum / count, 6)],
            "categories": categories,
            "sample_reports": [str(item[1]["_id"]) for item in items[:5]]
        })

    cluster_summaries.sort(key=lambda c: c["size"], reverse=True)

    if cache_key is not None:
        _CLUSTERS_CACHE[cache_key] = {
            "timestamp": time.time(),
            "data": cluster_summaries
        }

    return cluster_summaries
