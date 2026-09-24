from bson import ObjectId
from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user
from app.reports.services import CATEGORIES, haversine_distance_km
from app.db import get_db

feed_bp = Blueprint("feed", __name__, url_prefix="/feed")


@feed_bp.route("")
def feed_view():
    """Renders the nearby feed list and interactive Leaflet map."""
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

    # Build Mongo query
    query = {}
    
    # Non-flagged or unmoderated by default
    query["is_flagged"] = {"$ne": True}

    if category_filter:
        query["category"] = category_filter

    if status_filter and status_filter != "all":
        query["status"] = status_filter

    # Radius filter using $near
    radius_meters = radius_km * 1000.0
    query["location"] = {
        "$near": {
            "$geometry": {
                "type": "Point",
                "coordinates": [center_lon, center_lat]
            },
            "$maxDistance": radius_meters
        }
    }

    try:
        reports = list(db.reports.find(query).limit(100))
    except Exception:
        # Fallback if 2dsphere index query fails (e.g. in test mocks without 2dsphere)
        raw_reports = list(db.reports.find({"is_flagged": {"$ne": True}}).limit(200))
        reports = []
        for r in raw_reports:
            r_coords = r.get("location", {}).get("coordinates", [])
            if len(r_coords) == 2:
                dist = haversine_distance_km(center_lon, center_lat, r_coords[0], r_coords[1])
                if dist <= radius_km:
                    r["_dist_km"] = round(dist, 2)
                    if (not category_filter or r.get("category") == category_filter) and \
                       (not status_filter or status_filter == "all" or r.get("status") == status_filter):
                        reports.append(r)
        reports.sort(key=lambda x: x.get("_dist_km", 999))

    # Calculate precise distance in km for each report if not already done
    for r in reports:
        if "_dist_km" not in r:
            coords = r["location"]["coordinates"]
            r["_dist_km"] = round(haversine_distance_km(center_lon, center_lat, coords[0], coords[1]), 2)

    cat_dict = dict(CATEGORIES)
    for r in reports:
        r["category_label"] = cat_dict.get(r.get("category"), r.get("category"))

    return render_template(
        "feed/feed.html",
        reports=reports,
        center_lat=center_lat,
        center_lon=center_lon,
        radius_km=radius_km,
        category_filter=category_filter,
        status_filter=status_filter,
        categories=CATEGORIES
    )


@feed_bp.route("/api/reports")
def api_reports():
    """Returns GeoJSON FeatureCollection of reports for dynamic Leaflet markers."""
    db = get_db()
    lat = float(request.args.get("lat", 28.6139))
    lon = float(request.args.get("lon", 77.2090))
    radius_km = float(request.args.get("radius", 5.0))
    category = request.args.get("category", "")
    status = request.args.get("status", "")

    query = {"is_flagged": {"$ne": True}}
    if category:
        query["category"] = category
    if status and status != "all":
        query["status"] = status

    try:
        raw_reports = list(db.reports.find({
            **query,
            "location": {
                "$near": {
                    "$geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "$maxDistance": radius_km * 1000.0
                }
            }
        }).limit(100))
    except Exception:
        raw_reports = list(db.reports.find(query).limit(100))

    features = []
    cat_dict = dict(CATEGORIES)
    for r in raw_reports:
        r_coords = r["location"]["coordinates"]
        dist = haversine_distance_km(lon, lat, r_coords[0], r_coords[1])
        if dist <= radius_km:
            features.append({
                "type": "Feature",
                "geometry": r["location"],
                "properties": {
                    "id": str(r["_id"]),
                    "category": r["category"],
                    "category_label": cat_dict.get(r["category"], r["category"]),
                    "description": r["description"][:100],
                    "photo_url": r["photo_url"],
                    "status": r["status"],
                    "upvote_count": r["upvote_count"],
                    "distance_km": round(dist, 2)
                }
            })

    return jsonify({"type": "FeatureCollection", "features": features})
