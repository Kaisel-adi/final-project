import math
from bson import ObjectId
from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user
from app.reports.services import CATEGORIES, haversine_distance_km
from app.db import get_db

feed_bp = Blueprint("feed", __name__, url_prefix="/feed")


@feed_bp.route("")
def feed_view():
    """Renders the nearby feed list and interactive Leaflet map with pagination and geospatial optimization."""
    db = get_db()
    
    # 1. Determine user/view center coordinates
    center_lat = 28.6139  # Default to Delhi Center
    center_lon = 77.2090
    
    if current_user.is_authenticated and current_user.home_location:
        h_coords = current_user.home_location.get("coordinates")
        if h_coords and len(h_coords) == 2:
            center_lon, center_lat = h_coords[0], h_coords[1]

    # Query parameters
    lat_param = request.args.get("lat")
    lon_param = request.args.get("lon")
    if lat_param and lon_param:
        try:
            center_lat, center_lon = float(lat_param), float(lon_param)
        except ValueError:
            pass

    radius_km = float(request.args.get("radius", 5.0))
    category_filter = request.args.get("category", "")
    status_filter = request.args.get("status", "")

    # Pagination parameters
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = min(max(1, int(request.args.get("per_page", 20))), 100)
    except (ValueError, TypeError):
        per_page = 20

    skip = (page - 1) * per_page
    radius_meters = radius_km * 1000.0

    # Build match query for active, non-flagged reports
    match_query: dict[str, object] = {"is_flagged": {"$ne": True}}
    if category_filter:
        match_query["category"] = category_filter
    if status_filter and status_filter != "all":
        match_query["status"] = status_filter

    reports = []
    total_reports_count = 0

    # Try native MongoDB $geoNear aggregation stage for optimal performance and native distance calculation
    try:
        pipeline = [
            {
                "$geoNear": {
                    "near": {"type": "Point", "coordinates": [center_lon, center_lat]},
                    "distanceField": "distance_meters",
                    "maxDistance": radius_meters,
                    "spherical": True,
                    "query": match_query
                }
            },
            {"$skip": skip},
            {"$limit": per_page}
        ]
        reports = list(db.reports.aggregate(pipeline))
        for r in reports:
            # Native geospatial distance computed in database query
            if "_dist_km" not in r and "distance_meters" in r:
                r["_dist_km"] = round(r["distance_meters"] / 1000.0, 2)

        count_pipeline = [
            {
                "$geoNear": {
                    "near": {"type": "Point", "coordinates": [center_lon, center_lat]},
                    "distanceField": "distance_meters",
                    "maxDistance": radius_meters,
                    "spherical": True,
                    "query": match_query
                }
            },
            {"$count": "total"}
        ]
        count_res = list(db.reports.aggregate(count_pipeline))
        total_reports_count = count_res[0]["total"] if count_res else len(reports)
    except Exception:
        # Fallback when $geoNear or 2dsphere index is unsupported (e.g., mongomock in unit tests)
        # Apply spatial bounding box pre-filtering directly in MongoDB query to avoid full collection scans
        lat_delta = (radius_km / 111.0) * 1.05
        cos_lat = max(0.1, abs(math.cos(math.radians(center_lat))))
        lon_delta = (radius_km / (111.0 * cos_lat)) * 1.05

        fallback_query = {
            **match_query,
            "location.coordinates.0": {"$gte": center_lon - lon_delta, "$lte": center_lon + lon_delta},
            "location.coordinates.1": {"$gte": center_lat - lat_delta, "$lte": center_lat + lat_delta}
        }
        raw_reports = list(db.reports.find(fallback_query))
        matching_reports = []
        for r in raw_reports:
            r_coords = r.get("location", {}).get("coordinates", [])
            if len(r_coords) == 2:
                dist = haversine_distance_km(center_lon, center_lat, r_coords[0], r_coords[1])
                if dist <= radius_km:
                    r["_dist_km"] = round(dist, 2)
                    matching_reports.append(r)

        matching_reports.sort(key=lambda x: x.get("_dist_km", 999))
        total_reports_count = len(matching_reports)
        reports = matching_reports[skip: skip + per_page]

    # Precise distance fallback safeguard if any missing
    for r in reports:
        if "_dist_km" not in r:
            coords = r["location"]["coordinates"]
            r["_dist_km"] = round(haversine_distance_km(center_lon, center_lat, coords[0], coords[1]), 2)

    cat_dict = dict(CATEGORIES)
    for r in reports:
        r["category_label"] = cat_dict.get(r.get("category"), r.get("category"))

    total_pages = max(1, (total_reports_count + per_page - 1) // per_page) if total_reports_count > 0 else 1

    return render_template(
        "feed/feed.html",
        reports=reports,
        center_lat=center_lat,
        center_lon=center_lon,
        radius_km=radius_km,
        category_filter=category_filter,
        status_filter=status_filter,
        categories=CATEGORIES,
        total_reports_count=total_reports_count,
        page=page,
        per_page=per_page,
        total_pages=total_pages
    )


@feed_bp.route("/api/reports")
def api_reports():
    """Returns GeoJSON FeatureCollection of reports for dynamic Leaflet markers with pagination and native distance calculation."""
    db = get_db()
    lat = float(request.args.get("lat", 28.6139))
    lon = float(request.args.get("lon", 77.2090))
    radius_km = float(request.args.get("radius", 5.0))
    category = request.args.get("category", "")
    status = request.args.get("status", "")

    # Pagination parameters
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        limit = min(max(1, int(request.args.get("limit", 100))), 200)
    except (ValueError, TypeError):
        limit = 100

    skip = (page - 1) * limit
    radius_meters = radius_km * 1000.0

    query: dict[str, object] = {"is_flagged": {"$ne": True}}
    if category:
        query["category"] = category
    if status and status != "all":
        query["status"] = status

    features = []
    cat_dict = dict(CATEGORIES)

    # Use native $geoNear aggregation stage when supported
    try:
        pipeline = [
            {
                "$geoNear": {
                    "near": {"type": "Point", "coordinates": [lon, lat]},
                    "distanceField": "distance_meters",
                    "maxDistance": radius_meters,
                    "spherical": True,
                    "query": query
                }
            },
            {"$skip": skip},
            {"$limit": limit}
        ]
        raw_reports = list(db.reports.aggregate(pipeline))
        for r in raw_reports:
            dist_km = round(r.get("distance_meters", 0.0) / 1000.0, 2)
            features.append({
                "type": "Feature",
                "geometry": r["location"],
                "properties": {
                    "id": str(r["_id"]),
                    "category": r["category"],
                    "category_label": cat_dict.get(r["category"], r["category"]),
                    "description": r.get("description", "")[:100],
                    "photo_url": r.get("photo_url", ""),
                    "status": r.get("status", "Reported"),
                    "upvote_count": r.get("upvote_count", 0),
                    "distance_km": dist_km
                }
            })
    except Exception:
        # Fallback with indexed spatial bounding box pre-filtering
        lat_delta = (radius_km / 111.0) * 1.05
        cos_lat = max(0.1, abs(math.cos(math.radians(lat))))
        lon_delta = (radius_km / (111.0 * cos_lat)) * 1.05

        fallback_query = {
            **query,
            "location.coordinates.0": {"$gte": lon - lon_delta, "$lte": lon + lon_delta},
            "location.coordinates.1": {"$gte": lat - lat_delta, "$lte": lat + lat_delta}
        }
        raw_reports = list(db.reports.find(fallback_query))

        candidates = []
        for r in raw_reports:
            r_coords = r.get("location", {}).get("coordinates", [])
            if len(r_coords) == 2:
                dist = haversine_distance_km(lon, lat, r_coords[0], r_coords[1])
                if dist <= radius_km:
                    candidates.append((dist, r))

        candidates.sort(key=lambda x: x[0])
        paginated_candidates = candidates[skip: skip + limit]

        for dist, r in paginated_candidates:
            features.append({
                "type": "Feature",
                "geometry": r["location"],
                "properties": {
                    "id": str(r["_id"]),
                    "category": r["category"],
                    "category_label": cat_dict.get(r["category"], r["category"]),
                    "description": r.get("description", "")[:100],
                    "photo_url": r.get("photo_url", ""),
                    "status": r.get("status", "Reported"),
                    "upvote_count": r.get("upvote_count", 0),
                    "distance_km": round(dist, 2)
                }
            })

    return jsonify({
        "type": "FeatureCollection",
        "features": features,
        "pagination": {
            "page": page,
            "limit": limit,
            "count": len(features)
        }
    })
