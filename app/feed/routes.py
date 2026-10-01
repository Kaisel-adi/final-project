import math
from datetime import datetime, timezone
from bson import ObjectId
from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user
from app.reports.services import CATEGORIES, haversine_distance_km
from app.db import get_db

feed_bp = Blueprint("feed", __name__, url_prefix="/feed")


def get_relative_time(dt):
    if not dt:
        return "Recent"
    now = datetime.now(timezone.utc)
    if getattr(dt, "tzinfo", None) is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "Just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 30:
        return f"{days}d ago"
    return dt.strftime("%d %b %Y")


REPORT_FEED_PROJECTION = {
    "_id": 1,
    "category": 1,
    "description": 1,
    "photo_url": 1,
    "location": 1,
    "status": 1,
    "upvote_count": 1,
    "created_at": 1,
    "landmark": 1,
    "author_id": 1,
    "is_flagged": 1,
}


def fetch_feed_reports(db, center_lon, center_lat, radius_km, match_query, sort_by="distance", skip=0, limit=10):
    """Queries reports using spatial optimization ($geoNear or bounding box fallback), applies sorting, and projects lightweight fields."""
    radius_meters = radius_km * 1000.0
    reports = []
    total_reports_count = 0

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
            {"$project": {**REPORT_FEED_PROJECTION, "distance_meters": 1}}
        ]

        if sort_by == "likes":
            pipeline.append({"$sort": {"upvote_count": -1, "distance_meters": 1}})
        elif sort_by == "date":
            pipeline.append({"$sort": {"created_at": -1}})
        elif sort_by in ["pending", "reported"]:
            pipeline.append({"$addFields": {"_sort_priority": {"$cond": [{"$eq": ["$status", "Reported"]}, 0, 1]}}})
            pipeline.append({"$sort": {"_sort_priority": 1, "created_at": -1}})
        elif sort_by == "verified":
            pipeline.append({"$addFields": {"_sort_priority": {"$cond": [{"$eq": ["$status", "Verified"]}, 0, 1]}}})
            pipeline.append({"$sort": {"_sort_priority": 1, "upvote_count": -1, "created_at": -1}})
        # default is "distance" (sorted nearest first by $geoNear)

        pipeline.append({"$skip": skip})
        pipeline.append({"$limit": limit})

        reports = list(db.reports.aggregate(pipeline))

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
        # Fallback when $geoNear or 2dsphere index is unsupported (e.g. mongomock in unit tests)
        lat_delta = (radius_km / 111.0) * 1.05
        cos_lat = max(0.1, abs(math.cos(math.radians(center_lat))))
        lon_delta = (radius_km / (111.0 * cos_lat)) * 1.05

        fallback_query = {
            **match_query,
            "location.coordinates.0": {"$gte": center_lon - lon_delta, "$lte": center_lon + lon_delta},
            "location.coordinates.1": {"$gte": center_lat - lat_delta, "$lte": center_lat + lat_delta}
        }
        raw_reports = list(db.reports.find(fallback_query, projection=REPORT_FEED_PROJECTION))
        matching_reports = []
        for r in raw_reports:
            r_coords = r.get("location", {}).get("coordinates", [])
            if len(r_coords) == 2:
                dist = haversine_distance_km(center_lon, center_lat, r_coords[0], r_coords[1])
                if dist <= radius_km:
                    r["_dist_km"] = round(dist, 2)
                    matching_reports.append(r)

        if sort_by == "likes":
            matching_reports.sort(key=lambda x: (x.get("upvote_count", 0), -x.get("_dist_km", 999)), reverse=True)
        elif sort_by == "date":
            matching_reports.sort(
                key=lambda x: x.get("created_at") or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True
            )
        elif sort_by in ["pending", "reported"]:
            def _pending_key(x):
                is_rep = 0 if x.get("status") == "Reported" else 1
                cat = x.get("created_at")
                ts = cat.timestamp() if cat and hasattr(cat, "timestamp") else 0
                return (is_rep, -ts)
            matching_reports.sort(key=_pending_key)
        elif sort_by == "verified":
            def _verified_key(x):
                is_ver = 0 if x.get("status") == "Verified" else 1
                return (is_ver, -x.get("upvote_count", 0))
            matching_reports.sort(key=_verified_key)
        else:  # distance
            matching_reports.sort(key=lambda x: x.get("_dist_km", 999))

        total_reports_count = len(matching_reports)
        reports = matching_reports[skip: skip + limit]

    return reports, total_reports_count


def enrich_feed_reports(db, reports, center_lon, center_lat):
    """Enriches lightweight reports with author info, relative times, and batch comments count."""
    cat_dict = dict(CATEGORIES)
    
    for r in reports:
        if "_dist_km" not in r:
            if "distance_meters" in r:
                r["_dist_km"] = round(r["distance_meters"] / 1000.0, 2)
            elif "location" in r and "coordinates" in r.get("location", {}):
                coords = r["location"]["coordinates"]
                if len(coords) == 2:
                    r["_dist_km"] = round(haversine_distance_km(center_lon, center_lat, coords[0], coords[1]), 2)
                else:
                    r["_dist_km"] = 0.0
            else:
                r["_dist_km"] = 0.0

    # Batch load author names
    author_ids = [r["author_id"] for r in reports if "author_id" in r]
    users_map = {}
    if author_ids:
        try:
            for u in db.users.find({"_id": {"$in": author_ids}}, projection={"_id": 1, "name": 1}):
                users_map[u["_id"]] = u.get("name", "Community Resident")
        except Exception:
            pass

    # Batch load comments count via single aggregation ($group)
    report_ids = [r["_id"] for r in reports if "_id" in r]
    comments_map = {}
    if report_ids:
        try:
            count_pipeline = [
                {"$match": {"report_id": {"$in": report_ids}}},
                {"$group": {"_id": "$report_id", "count": {"$sum": 1}}}
            ]
            for c in db.comments.aggregate(count_pipeline):
                comments_map[c["_id"]] = c["count"]
        except Exception:
            pass

    # Batch load user upvotes so the UI can accurately distinguish liked vs unliked reports
    user_upvoted_set = set()
    if current_user.is_authenticated:
        try:
            usr_oid = ObjectId(current_user.id)
            if report_ids:
                upvotes = db.upvotes.find(
                    {"user_id": usr_oid, "report_id": {"$in": report_ids}},
                    projection={"report_id": 1}
                )
                user_upvoted_set = {u["report_id"] for u in upvotes}
        except Exception:
            pass

    for r in reports:
        r["category_label"] = cat_dict.get(r.get("category"), r.get("category", "General"))
        a_name = users_map.get(r.get("author_id"), "Community Resident")
        r["author_name"] = a_name
        names = a_name.split() if a_name else ["Resident"]
        r["author_initials"] = (names[0][0] + (names[-1][0] if len(names) > 1 else "")).upper()
        r["relative_time"] = get_relative_time(r.get("created_at"))

        desc = r.get("description", "").strip()
        first_line = desc.split("\n")[0]
        r["card_title"] = first_line[:65] + ("..." if len(first_line) > 65 else "")
        r["card_snippet"] = desc
        r["comments_count"] = comments_map.get(r["_id"], 0)
        if "upvote_count" not in r:
            r["upvote_count"] = 0
        r["has_upvoted"] = r.get("_id") in user_upvoted_set

    return reports


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

    active_view = request.args.get("view")
    if not active_view:
        if "per_page" in request.args or "category" in request.args or "q" in request.args or "status" in request.args:
            active_view = "list"
        else:
            active_view = "dashboard"

    # Radius logic: Community list view defaults to fixed 100km; Home dashboard defaults to 5km
    if "radius" in request.args:
        try:
            radius_km = float(request.args.get("radius"))
        except (ValueError, TypeError):
            radius_km = 100.0 if active_view == "list" else 5.0
    else:
        radius_km = 100.0 if active_view == "list" else 5.0

    sort_by = request.args.get("sort", "distance").lower()
    category_filter = request.args.get("category", "")
    status_filter = request.args.get("status", "")
    search_query = request.args.get("q", "").strip()

    # Pagination parameters: Initial visit loads 10 reports (or explicit per_page if set)
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    if "per_page" in request.args:
        try:
            per_page = min(max(1, int(request.args.get("per_page"))), 100)
        except (ValueError, TypeError):
            per_page = 10
    else:
        per_page = 10

    skip = (page - 1) * per_page

    # Build match query for active, non-flagged reports
    match_query: dict[str, object] = {"is_flagged": {"$ne": True}}
    if category_filter:
        match_query["category"] = category_filter
    if status_filter and status_filter != "all":
        match_query["status"] = status_filter
    if search_query:
        match_query["$or"] = [
            {"description": {"$regex": search_query, "$options": "i"}},
            {"category": {"$regex": search_query, "$options": "i"}}
        ]

    raw_reports, total_reports_count = fetch_feed_reports(
        db=db,
        center_lon=center_lon,
        center_lat=center_lat,
        radius_km=radius_km,
        match_query=match_query,
        sort_by=sort_by,
        skip=skip,
        limit=per_page
    )

    reports = enrich_feed_reports(db, raw_reports, center_lon, center_lat)

    total_pages = max(1, (total_reports_count + per_page - 1) // per_page) if total_reports_count > 0 else 1

    # Community 4-Metric Grid
    try:
        active_count = db.reports.count_documents({"is_flagged": {"$ne": True}, "status": {"$ne": "Resolved"}})
        in_prog_count = db.reports.count_documents({"is_flagged": {"$ne": True}, "status": {"$in": ["Verified", "Complained"]}})
        res_count = db.reports.count_documents({"is_flagged": {"$ne": True}, "status": "Resolved"})
        high_pri_count = db.reports.count_documents({
            "is_flagged": {"$ne": True},
            "$or": [
                {"category": {"$in": ["life_hazard", "traffic_hazard", "pedestrian_hazard"]}},
                {"status": "Verified"}
            ]
        })
    except Exception:
        active_count = total_reports_count
        in_prog_count = 0
        res_count = 0
        high_pri_count = 0

    community_metrics = {
        "active_issues": active_count,
        "in_progress": in_prog_count,
        "resolved_today": res_count,
        "high_priority": high_pri_count
    }

    # User Complaints Summary (for authenticated users)
    user_summary = None
    if current_user.is_authenticated:
        try:
            usr_oid = ObjectId(current_user.id)
            u_total = db.reports.count_documents({"author_id": usr_oid})
            u_resolved = db.reports.count_documents({"author_id": usr_oid, "status": "Resolved"})
            u_pending = db.reports.count_documents({"author_id": usr_oid, "status": "Reported"})
            u_prog = db.reports.count_documents({"author_id": usr_oid, "status": {"$in": ["Verified", "Complained"]}})
            user_summary = {
                "total_issues": u_total,
                "resolved": u_resolved,
                "pending": u_pending,
                "in_progress": u_prog,
                "avg_response_time": "2.3 days"
            }
        except Exception:
            pass

    # Build JSON-serializable issues list for Leaflet map widget
    map_issues = [
        {
            "id": str(r["_id"]),
            "status": r.get("status", "Reported"),
            "category": r.get("category", "other"),
            "category_label": r.get("category_label", "Civic Issue"),
            "location": r.get("location", {}),
            "description": r.get("description", "")[:100]
        }
        for r in reports if "location" in r and "coordinates" in r.get("location", {})
    ]

    return render_template(
        "feed/feed.html",
        reports=reports,
        map_issues=map_issues,
        center_lat=center_lat,
        center_lon=center_lon,
        radius_km=radius_km,
        sort_by=sort_by,
        category_filter=category_filter,
        status_filter=status_filter,
        search_query=search_query,
        active_view=active_view,
        categories=CATEGORIES,
        total_reports_count=total_reports_count,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        community_metrics=community_metrics,
        user_summary=user_summary
    )


@feed_bp.route("/api/chunk")
def api_feed_chunk():
    """Returns next chunk of 5 reports rendered as HTML cards for seamless infinite scroll loading."""
    db = get_db()
    
    center_lat = float(request.args.get("lat", 28.6139))
    center_lon = float(request.args.get("lon", 77.2090))
    active_view = request.args.get("view", "dashboard")

    if "radius" in request.args:
        try:
            radius_km = float(request.args.get("radius"))
        except (ValueError, TypeError):
            radius_km = 100.0 if active_view == "list" else 5.0
    else:
        radius_km = 100.0 if active_view == "list" else 5.0

    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except (ValueError, TypeError):
        offset = 0

    try:
        limit = min(max(1, int(request.args.get("limit", 10 if offset == 0 else 5))), 50)
    except (ValueError, TypeError):
        limit = 10 if offset == 0 else 5

    sort_by = request.args.get("sort", "distance").lower()
    category_filter = request.args.get("category", "")
    status_filter = request.args.get("status", "")
    search_query = request.args.get("q", "").strip()

    match_query: dict[str, object] = {"is_flagged": {"$ne": True}}
    if category_filter:
        match_query["category"] = category_filter
    if status_filter and status_filter != "all":
        match_query["status"] = status_filter
    if search_query:
        match_query["$or"] = [
            {"description": {"$regex": search_query, "$options": "i"}},
            {"category": {"$regex": search_query, "$options": "i"}}
        ]

    raw_reports, total_count = fetch_feed_reports(
        db=db,
        center_lon=center_lon,
        center_lat=center_lat,
        radius_km=radius_km,
        match_query=match_query,
        sort_by=sort_by,
        skip=offset,
        limit=limit
    )

    enriched_reports = enrich_feed_reports(db, raw_reports, center_lon, center_lat)
    html_cards = render_template("feed/_cards.html", reports=enriched_reports)

    next_offset = offset + len(enriched_reports)
    has_more = next_offset < total_count

    return jsonify({
        "success": True,
        "count": len(enriched_reports),
        "total": total_count,
        "offset": offset,
        "next_offset": next_offset,
        "has_more": has_more,
        "html": html_cards
    })


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
            {"$project": {**REPORT_FEED_PROJECTION, "distance_meters": 1}},
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
        raw_reports = list(db.reports.find(fallback_query, projection=REPORT_FEED_PROJECTION))

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
