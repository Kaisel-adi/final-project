import urllib.parse
from datetime import datetime, timezone
from bson import ObjectId
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.complaints.router import lookup_authority_for_point
from app.reports.services import CATEGORIES
from app.db import get_db

complaints_bp = Blueprint("complaints", __name__, url_prefix="/complaints")


@complaints_bp.route("/<report_id>")
@login_required
def draft_view(report_id):
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

    # Strict business rule: Complaint drafter unlocks ONLY at Verified status
    if report.get("status") == "Reported":
        flash("Complaint draft is locked until the report receives 10 community upvotes (Verified).", "warning")
        return redirect(url_for("reports.view", report_id=report_id))

    lon, lat = report["location"]["coordinates"]
    category = report["category"]

    # 1. Authority lookup
    authority = lookup_authority_for_point(lon, lat, category, db=db)

    # 2. Corroborating reports count within 200m
    try:
        corroborating_count = db.reports.count_documents({
            "_id": {"$ne": rep_oid},
            "location": {
                "$geoWithin": {
                    "$centerSphere": [[lon, lat], 0.2 / 6378.1]
                }
            }
        })
    except Exception:
        from app.reports.services import haversine_distance_km
        all_reps = list(db.reports.find({"_id": {"$ne": rep_oid}}))
        corroborating_count = 0
        for r in all_reps:
            c = r.get("location", {}).get("coordinates", [])
            if len(c) == 2 and haversine_distance_km(lon, lat, c[0], c[1]) <= 0.2:
                corroborating_count += 1

    cat_label = dict(CATEGORIES).get(category, category.title())
    gmaps_link = f"https://www.google.com/maps?q={lat},{lon}"
    osm_link = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=18/{lat}/{lon}"

    subject = f"[Civic Grievance - {cat_label}] {authority['name']} - Ref #{str(rep_oid)[-6:]}"

    body = (
        f"To: {authority['body']} / {authority['name']}\n"
        f"Grievance Reference: #{str(rep_oid)}\n\n"
        f"Dear Sir/Madam,\n\n"
        f"I am writing as a concerned local resident to register an official community-verified complaint "
        f"regarding a civic issue in your jurisdiction.\n\n"
        f"-----------------------------------------\n"
        f"ISSUE DETAILS:\n"
        f"- Category: {cat_label}\n"
        f"- Description: {report['description']}\n"
        f"- Coordinates: {lat:.6f}, {lon:.6f}\n"
        f"- Map Link: {gmaps_link}\n"
        f"- Photographic Evidence: {report['photo_url']}\n"
        f"- Community Upvotes: {report.get('upvote_count', 0)} verified nearby residents\n"
        f"- Other Corroborating Reports (<200m): {corroborating_count}\n"
        f"-----------------------------------------\n\n"
        f"This report has been independently verified by community members on the Geo-Tagged Civic Issue Reporter platform.\n"
        f"Kindly inspect the location and initiate prompt remedial action.\n\n"
        f"Sincerely,\n"
        f"{current_user.name}\n"
        f"{current_user.email}\n"
    )

    mailto_params = {
        "subject": subject,
        "body": body
    }
    mailto_url = f"mailto:{authority['contact_email']}?{urllib.parse.urlencode(mailto_params, quote_via=urllib.parse.quote)}"

    return render_template(
        "complaints/draft.html",
        report=report,
        authority=authority,
        corroborating_count=corroborating_count,
        subject=subject,
        body=body,
        mailto_url=mailto_url,
        gmaps_link=gmaps_link,
        osm_link=osm_link,
        cat_label=cat_label
    )


@complaints_bp.route("/<report_id>/mark_sent", methods=["POST"])
@login_required
def mark_sent(report_id):
    db = get_db()
    try:
        rep_oid = ObjectId(report_id)
        report = db.reports.find_one({"_id": rep_oid})
        if report and report.get("status") == "Verified":
            now = datetime.now(timezone.utc)
            db.reports.update_one(
                {"_id": rep_oid},
                {
                    "$set": {"status": "Complained"},
                    "$push": {
                        "status_log": {
                            "status": "Complained",
                            "timestamp": now,
                            "note": f"Complaint email dispatched by {current_user.name}"
                        }
                    }
                }
            )
            flash("Report marked as 'Complained' to authority. Thank you for your civic action!", "success")
    except Exception as e:
        flash("Could not update status.", "danger")

    return redirect(url_for("reports.view", report_id=report_id))
