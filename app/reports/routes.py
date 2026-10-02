import math
from datetime import datetime, timezone
from bson import ObjectId
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.reports.services import create_report, upvote_report, CATEGORIES, haversine_distance_km
from app.services.storage import save_image
from app.db import get_db

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


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


@reports_bp.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        category = request.form.get("category")
        description = request.form.get("description", "").strip()
        lat_str = request.form.get("latitude")
        lon_str = request.form.get("longitude")
        photo_file = request.files.get("photo")

        if not photo_file or photo_file.filename == "":
            flash("A photo or video evidence of the issue is required.", "danger")
            return render_template("reports/create.html", categories=CATEGORIES,
                                   description=description, selected_cat=category)

        if not lat_str or not lon_str:
            flash("Coordinates are required. Please use browser location or drop a pin on the map.", "danger")
            return render_template("reports/create.html", categories=CATEGORIES,
                                   description=description, selected_cat=category)

        try:
            lat = float(lat_str)
            lon = float(lon_str)
            coords = [lon, lat]  # GeoJSON [longitude, latitude]
            photo_url = save_image(photo_file)
            
            report = create_report(
                author_id=current_user.id,
                category=category,
                description=description,
                photo_url=photo_url,
                coordinates=coords
            )
            flash("Civic issue successfully reported! It is now live for community verification.", "success")
            return redirect(url_for("reports.view", report_id=str(report["_id"])))
        except Exception as e:
            flash(f"Error submitting report: {str(e)}", "danger")
            return render_template("reports/create.html", categories=CATEGORIES,
                                   description=description, selected_cat=category)

    # Pre-populate map with user's home location if available
    default_lat, default_lon = 28.6139, 77.2090  # Delhi default
    if current_user.home_location:
        coords = current_user.home_location.get("coordinates")
        if coords and len(coords) == 2:
            default_lon, default_lat = coords[0], coords[1]

    return render_template("reports/create.html", categories=CATEGORIES,
                           default_lat=default_lat, default_lon=default_lon)


@reports_bp.route("/<report_id>")
def view(report_id):
    db = get_db()
    try:
        rep_oid = ObjectId(report_id)
    except Exception:
        flash("Invalid report ID.", "danger")
        return redirect(url_for("feed.feed_view"))

    report = db.reports.find_one({"_id": rep_oid})
    if not report or report.get("status") == "Removed":
        flash("This report has been removed and is no longer available.", "warning")
        return redirect(url_for("feed.feed_view"))

    author = db.users.find_one({"_id": report["author_id"]})
    author_name = author.get("name", "Anonymous") if author else "Anonymous"

    # Check if current user has upvoted
    has_upvoted = False
    is_author = False
    if current_user.is_authenticated:
        usr_oid = ObjectId(current_user.id)
        is_author = (report["author_id"] == usr_oid)
        has_upvoted = bool(db.upvotes.find_one({"report_id": rep_oid, "user_id": usr_oid}))

    # Corroborating reports within 200m
    lon, lat = report["location"]["coordinates"]
    nearby_reports = []
    try:
        pipeline = [
            {
                "$geoNear": {
                    "near": {"type": "Point", "coordinates": [lon, lat]},
                    "distanceField": "distance_meters",
                    "maxDistance": 200.0,
                    "spherical": True,
                    "query": {"_id": {"$ne": rep_oid}}
                }
            },
            {"$limit": 10}
        ]
        nearby_reports = list(db.reports.aggregate(pipeline))
        for nr in nearby_reports:
            if "_dist_km" not in nr and "distance_meters" in nr:
                nr["_dist_km"] = round(nr["distance_meters"] / 1000.0, 3)
    except Exception:
        # Bounding box fallback for 200m (0.2km) to avoid full collection scan
        lat_delta = (0.2 / 111.0) * 1.05
        cos_lat = max(0.1, abs(math.cos(math.radians(lat))))
        lon_delta = (0.2 / (111.0 * cos_lat)) * 1.05
        candidate_nearby = list(db.reports.find({
            "_id": {"$ne": rep_oid},
            "location.coordinates.0": {"$gte": lon - lon_delta, "$lte": lon + lon_delta},
            "location.coordinates.1": {"$gte": lat - lat_delta, "$lte": lat + lat_delta}
        }).limit(50))
        nearby_reports = []
        for nr in candidate_nearby:
            nr_coords = nr.get("location", {}).get("coordinates", [])
            if len(nr_coords) == 2:
                dist = haversine_distance_km(lon, lat, nr_coords[0], nr_coords[1])
                if dist <= 0.2:
                    nr["_dist_km"] = round(dist, 3)
                    nearby_reports.append(nr)
            if len(nearby_reports) >= 10:
                break

    # Category display name
    cat_dict = dict(CATEGORIES)
    category_label = cat_dict.get(report.get("category"), report.get("category"))
    report["relative_time"] = get_relative_time(report.get("created_at"))

    # Load comments
    comments = list(db.comments.find({"report_id": rep_oid}).sort("created_at", 1))
    for c in comments:
        c["relative_time"] = get_relative_time(c.get("created_at"))

    # Load post-resolution ratings
    all_ratings = list(db.ratings.find({"report_id": rep_oid}))
    rating_count = len(all_ratings)
    avg_rating = round(sum(r.get("rating", 0) for r in all_ratings) / rating_count, 1) if rating_count > 0 else 0.0
    user_rating = None
    if current_user.is_authenticated:
        ur = db.ratings.find_one({"report_id": rep_oid, "user_id": ObjectId(current_user.id)})
        if ur:
            user_rating = ur.get("rating")

    return render_template(
        "reports/view.html",
        report=report,
        author_name=author_name,
        category_label=category_label,
        has_upvoted=has_upvoted,
        is_author=is_author,
        corroborating_count=len(nearby_reports),
        nearby_reports=nearby_reports,
        comments=comments,
        rating_count=rating_count,
        avg_rating=avg_rating,
        user_rating=user_rating
    )


@reports_bp.route("/<report_id>/rate", methods=["POST"])
@login_required
def rate(report_id):
    """Post-resolution star rating (1.0 to 5.0, with half-star hold support)."""
    db = get_db()
    try:
        rep_oid = ObjectId(report_id)
        report = db.reports.find_one({"_id": rep_oid})
        if not report or report.get("status") == "Removed":
            err_msg = "This report has been removed and is no longer available."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
                return jsonify({"success": False, "error": err_msg, "not_found": True, "redirect_url": url_for("feed.feed_view")}), 404
            flash(err_msg, "warning")
            return redirect(url_for("feed.feed_view"))

        if report.get("status") != "Resolved":
            return jsonify({"success": False, "error": "Ratings are only available once an issue is Resolved"}), 400

        data = request.get_json(silent=True) or request.form
        rating_val = float(data.get("rating", 0))
        if not (1.0 <= rating_val <= 5.0):
            return jsonify({"success": False, "error": "Rating must be between 1 and 5 stars"}), 400

        # Upsert rating
        now = datetime.now(timezone.utc)
        db.ratings.update_one(
            {"report_id": rep_oid, "user_id": ObjectId(current_user.id)},
            {"$set": {"rating": rating_val, "updated_at": now}, "$setOnInsert": {"created_at": now}},
            upsert=True
        )

        all_ratings = list(db.ratings.find({"report_id": rep_oid}))
        rating_count = len(all_ratings)
        avg_rating = round(sum(r.get("rating", 0) for r in all_ratings) / rating_count, 1)

        # Update report cache
        db.reports.update_one(
            {"_id": rep_oid},
            {"$set": {"avg_rating": avg_rating, "rating_count": rating_count}}
        )

        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"success": True, "avg_rating": avg_rating, "rating_count": rating_count, "user_rating": rating_val})

        flash(f"Thank you for rating municipal resolution: {rating_val} stars!", "success")
    except Exception as e:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"success": False, "error": str(e)}), 400
        flash(f"Error submitting rating: {str(e)}", "danger")

    return redirect(url_for("reports.view", report_id=report_id))


@reports_bp.route("/<report_id>/comments", methods=["POST"])
@login_required
def add_comment(report_id):
    """Down-scroll community comment submission on report details."""
    db = get_db()
    is_ajax = (request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json or request.accept_mimetypes.accept_json)
    try:
        rep_oid = ObjectId(report_id)
        report = db.reports.find_one({"_id": rep_oid})
        if not report or report.get("status") == "Removed":
            err_msg = "This report has been removed and is no longer available."
            if is_ajax:
                return jsonify({"success": False, "error": err_msg, "not_found": True, "redirect_url": url_for("feed.feed_view")}), 404
            flash(err_msg, "warning")
            return redirect(url_for("feed.feed_view"))

        json_data = request.get_json(silent=True) if request.is_json else None
        comment_text = (json_data.get("comment") if json_data else request.form.get("comment", "")).strip()
        if not comment_text or len(comment_text) < 2:
            if is_ajax:
                return jsonify({"success": False, "error": "Comment cannot be empty."}), 400
            flash("Comment cannot be empty.", "warning")
            return redirect(url_for("reports.view", report_id=report_id))

        now = datetime.now(timezone.utc)
        names = current_user.name.split() if current_user.name else ["Citizen"]
        initials = (names[0][0] + (names[-1][0] if len(names) > 1 else "")).upper()

        comment_doc = {
            "report_id": rep_oid,
            "user_id": ObjectId(current_user.id),
            "user_name": current_user.name,
            "user_initials": initials,
            "is_moderator": getattr(current_user, "is_moderator", False),
            "comment": comment_text,
            "created_at": now
        }
        res = db.comments.insert_one(comment_doc)
        total_comments = db.comments.count_documents({"report_id": rep_oid})

        if is_ajax:
            return jsonify({
                "success": True,
                "comment": {
                    "id": str(res.inserted_id),
                    "user_name": current_user.name,
                    "user_initials": initials,
                    "is_moderator": getattr(current_user, "is_moderator", False),
                    "comment": comment_text,
                    "relative_time": "Just now",
                    "created_at_str": now.strftime("%d %b %Y, %I:%M %p")
                },
                "comments_count": total_comments
            })

        flash("Comment added to community timeline.", "success")
    except Exception as e:
        if is_ajax:
            return jsonify({"success": False, "error": str(e)}), 400
        flash(f"Failed to post comment: {str(e)}", "danger")

    return redirect(url_for("reports.view", report_id=report_id))


@reports_bp.route("/<report_id>/upvote", methods=["POST"])
@login_required
def upvote(report_id):
    json_data = request.get_json(silent=True) if request.is_json else None
    user_lat = (json_data.get("user_lat") if json_data else request.form.get("user_lat"))
    user_lon = (json_data.get("user_lon") if json_data else request.form.get("user_lon"))
    user_coords = None
    if user_lat and user_lon:
        try:
            user_coords = [float(user_lon), float(user_lat)]
        except ValueError:
            pass

    is_ajax = (request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json or request.accept_mimetypes.accept_json)

    try:
        result = upvote_report(report_id, current_user, user_coords=user_coords)
        if is_ajax:
            return jsonify(result)
        
        flash("Upvote recorded! Thank you for verifying this issue.", "success")
    except ValueError as e:
        is_not_found = (str(e) == "Report not found.")
        err_msg = "This report has been removed and is no longer available." if is_not_found else str(e)
        if is_ajax:
            return jsonify({
                "success": False,
                "error": err_msg,
                "not_found": is_not_found,
                "redirect_url": url_for("feed.feed_view") if is_not_found else None
            }), 404 if is_not_found else 400
        flash(err_msg, "warning")
        if is_not_found:
            return redirect(url_for("feed.feed_view"))
        return redirect(url_for("reports.view", report_id=report_id))
    except Exception as e:
        if is_ajax:
            return jsonify({"success": False, "error": str(e)}), 500
        flash("Error processing upvote.", "danger")

    return redirect(url_for("reports.view", report_id=report_id))


@reports_bp.route("/<report_id>/flag", methods=["POST"])
@login_required
def flag(report_id):
    db = get_db()
    is_ajax = (request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json or request.accept_mimetypes.accept_json)
    reason = request.form.get("reason", "Inappropriate or sensitive content")
    try:
        rep_oid = ObjectId(report_id)
        report = db.reports.find_one({"_id": rep_oid})
        if not report or report.get("status") == "Removed":
            err_msg = "This report has been removed and is no longer available."
            if is_ajax:
                return jsonify({"success": False, "error": err_msg, "not_found": True, "redirect_url": url_for("feed.feed_view")}), 404
            flash(err_msg, "warning")
            return redirect(url_for("feed.feed_view"))

        db.reports.update_one(
            {"_id": rep_oid},
            {"$set": {"is_flagged": True, "flag_reason": reason}}
        )
        if is_ajax:
            return jsonify({"success": True, "message": "Thank you. This report has been flagged for moderation review."})
        flash("Thank you. This report has been flagged for moderation review.", "info")
    except Exception as e:
        if is_ajax:
            return jsonify({"success": False, "error": "Failed to flag report."}), 500
        flash("Failed to flag report.", "danger")
    return redirect(url_for("reports.view", report_id=report_id))
