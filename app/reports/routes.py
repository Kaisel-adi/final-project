from bson import ObjectId
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.reports.services import create_report, upvote_report, CATEGORIES, haversine_distance_km
from app.services.storage import save_image
from app.db import get_db

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


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
    if not report:
        flash("Report not found.", "warning")
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
    try:
        nearby_reports = list(db.reports.find({
            "_id": {"$ne": rep_oid},
            "location": {
                "$geoWithin": {
                    "$centerSphere": [[lon, lat], 0.2 / 6378.1]  # 200m radius in radians
                }
            }
        }).limit(10))
    except Exception:
        all_nearby = list(db.reports.find({"_id": {"$ne": rep_oid}}))
        nearby_reports = []
        for nr in all_nearby:
            nr_coords = nr.get("location", {}).get("coordinates", [])
            if len(nr_coords) == 2:
                dist = haversine_distance_km(lon, lat, nr_coords[0], nr_coords[1])
                if dist <= 0.2:
                    nearby_reports.append(nr)
            if len(nearby_reports) >= 10:
                break

    # Category display name
    cat_dict = dict(CATEGORIES)
    category_label = cat_dict.get(report.get("category"), report.get("category"))

    return render_template(
        "reports/view.html",
        report=report,
        author_name=author_name,
        category_label=category_label,
        has_upvoted=has_upvoted,
        is_author=is_author,
        corroborating_count=len(nearby_reports),
        nearby_reports=nearby_reports
    )


@reports_bp.route("/<report_id>/upvote", methods=["POST"])
@login_required
def upvote(report_id):
    user_lat = request.form.get("user_lat")
    user_lon = request.form.get("user_lon")
    user_coords = None
    if user_lat and user_lon:
        try:
            user_coords = [float(user_lon), float(user_lat)]
        except ValueError:
            pass

    try:
        result = upvote_report(report_id, current_user, user_coords=user_coords)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify(result)
        
        flash("Upvote recorded! Thank you for verifying this issue.", "success")
    except ValueError as e:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"success": False, "error": str(e)}), 400
        flash(str(e), "warning")

    return redirect(url_for("reports.view", report_id=report_id))


@reports_bp.route("/<report_id>/flag", methods=["POST"])
@login_required
def flag(report_id):
    db = get_db()
    reason = request.form.get("reason", "Inappropriate or sensitive content")
    try:
        rep_oid = ObjectId(report_id)
        db.reports.update_one(
            {"_id": rep_oid},
            {"$set": {"is_flagged": True, "flag_reason": reason}}
        )
        flash("Thank you. This report has been flagged for moderation review.", "info")
    except Exception as e:
        flash("Failed to flag report.", "danger")
    return redirect(url_for("reports.view", report_id=report_id))
