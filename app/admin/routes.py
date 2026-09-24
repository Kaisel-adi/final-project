from datetime import datetime, timezone
from bson import ObjectId
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.ml.clustering import compute_dbscan_hotspots
from app.reports.services import CATEGORIES
from app.db import get_db

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_or_moderator_required(view_func):
    """Decorator to enforce moderator or admin privileges."""
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_moderator:
            flash("Unauthorized. Moderator privileges required.", "danger")
            return redirect(url_for("feed.feed_view"))
        return view_func(*args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


@admin_bp.route("")
@login_required
@admin_or_moderator_required
def dashboard():
    """Moderation queue and quick overview."""
    db = get_db()
    
    # Flagged reports
    flagged_reports = list(db.reports.find({"is_flagged": True}).sort("created_at", -1))
    
    # Basic statistics
    total_reports = db.reports.count_documents({})
    verified_reports = db.reports.count_documents({"status": "Verified"})
    complained_reports = db.reports.count_documents({"status": "Complained"})
    total_users = db.users.count_documents({})

    return render_template(
        "admin/dashboard.html",
        flagged_reports=flagged_reports,
        total_reports=total_reports,
        verified_reports=verified_reports,
        complained_reports=complained_reports,
        total_users=total_users
    )


@admin_bp.route("/reports/<report_id>/moderate", methods=["POST"])
@login_required
@admin_or_moderator_required
def moderate_report(report_id):
    action = request.form.get("action")  # "approve" (unflag) or "remove"
    db = get_db()
    rep_oid = ObjectId(report_id)

    if action == "approve":
        db.reports.update_one(
            {"_id": rep_oid},
            {"$set": {"is_flagged": False, "flag_reason": None}}
        )
        flash("Report approved and unflagged.", "success")
    elif action == "remove":
        now = datetime.now(timezone.utc)
        db.reports.update_one(
            {"_id": rep_oid},
            {
                "$set": {"status": "Removed", "is_flagged": False},
                "$push": {
                    "status_log": {
                        "status": "Removed",
                        "timestamp": now,
                        "note": f"Removed by moderator {current_user.name}"
                    }
                }
            }
        )
        flash("Report has been removed from public feed.", "info")

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/hotspots")
@login_required
@admin_or_moderator_required
def hotspots():
    """Renders DBSCAN hotspot clusters and map visualization."""
    db = get_db()
    clusters = compute_dbscan_hotspots(eps_km=0.5, min_samples=3, db=db)
    return render_template("admin/hotspots.html", clusters=clusters)


@admin_bp.route("/trigger_digest", methods=["POST"])
@login_required
@admin_or_moderator_required
def trigger_digest_now():
    """Manual on-demand digest execution from admin panel."""
    from app.jobs.digest import run_digest_job
    res = run_digest_job()
    flash("Daily digest job triggered successfully.", "success")
    return redirect(url_for("admin.dashboard"))
