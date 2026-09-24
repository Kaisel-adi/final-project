import numpy as np
from sklearn.cluster import DBSCAN
from app.db import get_db


def compute_dbscan_hotspots(eps_km: float = 0.5, min_samples: int = 3, db=None) -> list[dict]:
    """
    Applies DBSCAN clustering on active civic report coordinates using haversine metric.
    Updates cluster_id on report documents and returns detected hotspot cluster summaries.
    """
    if db is None:
        db = get_db()

    # Fetch active reports with valid coordinates
    reports = list(db.reports.find(
        {"status": {"$in": ["Reported", "Verified", "Complained"]}},
        {"_id": 1, "location": 1, "category": 1, "description": 1}
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
    return cluster_summaries
