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


def admin_only_required(view_func):
    """Decorator to enforce strict administrator privileges."""
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Unauthorized. Administrator privileges required.", "danger")
            return redirect(url_for("admin.dashboard"))
        return view_func(*args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


@admin_bp.route("/")
@admin_bp.route("")
@login_required
@admin_or_moderator_required
def dashboard():
    """Moderation queue and interactive tabbed management."""
    db = get_db()
    active_tab = request.args.get("tab", "all_reports")
    if active_tab == "users" and not current_user.is_admin:
        active_tab = "all_reports"
    cat_dict = dict(CATEGORIES)

    # Basic statistics
    flagged_count = db.reports.count_documents({"is_flagged": True})
    total_reports_count = db.reports.count_documents({"status": {"$ne": "Removed"}})
    verified_count = db.reports.count_documents({"status": "Verified"})
    complained_count = db.reports.count_documents({"status": "Complained"})
    total_users_count = db.users.count_documents({}) if current_user.is_admin else None

    tab_data = {}

    if active_tab == "flagged":
        reports = list(db.reports.find({"is_flagged": True}).sort("created_at", -1))
        for r in reports:
            r["cat_label"] = cat_dict.get(r.get("category"), r.get("category", "General"))
        tab_data["flagged_reports"] = reports

    elif active_tab == "all_reports":
        reports = list(db.reports.find({"status": {"$ne": "Removed"}}).sort("created_at", -1))
        for r in reports:
            r["cat_label"] = cat_dict.get(r.get("category"), r.get("category", "General"))
        tab_data["all_reports"] = reports

    elif active_tab == "verified":
        reports = list(db.reports.find({"status": "Verified"}).sort("created_at", -1))
        for r in reports:
            r["cat_label"] = cat_dict.get(r.get("category"), r.get("category", "General"))
        tab_data["verified_reports"] = reports

    elif active_tab == "complaints":
        reports = list(db.reports.find({"status": "Complained"}).sort("created_at", -1))
        for r in reports:
            r["cat_label"] = cat_dict.get(r.get("category"), r.get("category", "General"))
        tab_data["complaints_reports"] = reports

    elif active_tab == "users" and current_user.is_admin:
        users_list = list(db.users.find({}).sort("created_at", -1))
        report_counts = {
            result["_id"]: result["count"]
            for result in db.reports.aggregate([
                {"$group": {"_id": "$author_id", "count": {"$sum": 1}}}
            ])
        }
        for u in users_list:
            u["report_count"] = report_counts.get(u["_id"], 0)
        tab_data["users_list"] = users_list

    return render_template(
        "admin/dashboard.html",
        active_tab=active_tab,
        flagged_count=flagged_count,
        total_reports_count=total_reports_count,
        verified_count=verified_count,
        complained_count=complained_count,
        total_users_count=total_users_count,
        **tab_data
    )


@admin_bp.route("/reports/<report_id>/verify", methods=["POST"])
@login_required
@admin_or_moderator_required
def verify_report_instantly(report_id):
    """Admin privilege: Instantly verifies any report without waiting for 10 votes."""
    db = get_db()
    rep_oid = ObjectId(report_id)
    report = db.reports.find_one({"_id": rep_oid})
    if not report:
        flash("Report not found.", "warning")
        return redirect(request.referrer or url_for("admin.dashboard"))

    if report.get("status") in {"Verified", "Complained", "Resolved", "Removed"}:
        flash("This report can no longer be verified.", "warning")
        return redirect(request.referrer or url_for("admin.dashboard"))

    now = datetime.now(timezone.utc)
    db.reports.update_one(
        {"_id": rep_oid},
        {
            "$set": {
                "status": "Verified",
                "is_flagged": False,
                "flag_reason": None
            },
            "$push": {
                "status_log": {
                    "status": "Verified",
                    "timestamp": now,
                    "note": f"Fast-track verified by administrator {current_user.name}"
                }
            }
        }
    )
    flash("Report has been verified by admin. Complaint routing is now unlocked!", "success")
    return redirect(request.referrer or url_for("admin.dashboard", tab="verified"))


@admin_bp.route("/reports/<report_id>/remove", methods=["POST"])
@login_required
@admin_or_moderator_required
def remove_report(report_id):
    """Admin privilege: Removes any civic report from the public feed."""
    db = get_db()
    rep_oid = ObjectId(report_id)
    now = datetime.now(timezone.utc)
    db.reports.update_one(
        {"_id": rep_oid},
        {
            "$set": {"status": "Removed", "is_flagged": False},
            "$push": {
                "status_log": {
                    "status": "Removed",
                    "timestamp": now,
                    "note": f"Removed from feed by administrator {current_user.name}"
                }
            }
        }
    )
    flash("Report has been removed from the public feed.", "info")
    return redirect(request.referrer or url_for("admin.dashboard"))


@admin_bp.route("/reports/<report_id>/moderate", methods=["POST"])
@login_required
@admin_or_moderator_required
def moderate_report(report_id):
    """Handles flagged queue moderation (approve/remove)."""
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

    return redirect(url_for("admin.dashboard", tab="flagged"))


@admin_bp.route("/users/<user_id>/role", methods=["POST"])
@login_required
@admin_only_required
def change_user_role(user_id):
    """Admin privilege: Assigns or revokes moderator privileges for users."""
    if str(user_id) == str(current_user.id):
        flash("You cannot alter your own admin role.", "warning")
        return redirect(url_for("admin.dashboard", tab="users"))

    db = get_db()
    new_role = request.form.get("role", "resident")
    if new_role not in ("resident", "moderator"):
        flash("Invalid role assignment.", "danger")
        return redirect(url_for("admin.dashboard", tab="users"))

    target_user = db.users.find_one({"_id": ObjectId(user_id)})
    if not target_user:
        flash("User not found.", "warning")
        return redirect(url_for("admin.dashboard", tab="users"))

    if target_user.get("role") == "admin":
        flash("Cannot modify the role of another administrator.", "danger")
        return redirect(url_for("admin.dashboard", tab="users"))

    db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"role": new_role}})
    role_title = "Moderator" if new_role == "moderator" else "Resident"
    flash(f"User '{target_user.get('name')}' ({target_user.get('email')}) updated to {role_title}.", "success")
    return redirect(url_for("admin.dashboard", tab="users"))


@admin_bp.route("/users/<user_id>/ban", methods=["POST"])
@login_required
@admin_only_required
def toggle_user_ban(user_id):
    """Admin privilege: Suspends or reinstates a user account."""
    if str(user_id) == str(current_user.id):
        flash("You cannot ban yourself.", "warning")
        return redirect(url_for("admin.dashboard", tab="users"))

    db = get_db()
    target_user = db.users.find_one({"_id": ObjectId(user_id)})
    if not target_user:
        flash("User not found.", "warning")
        return redirect(url_for("admin.dashboard", tab="users"))

    if target_user.get("role") == "admin":
        flash("Cannot ban another administrator account.", "danger")
        return redirect(url_for("admin.dashboard", tab="users"))

    current_ban = target_user.get("is_banned", False)
    new_ban = not current_ban
    db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"is_banned": new_ban}})
    action_str = "banned and logged out" if new_ban else "unbanned"
    flash(f"User '{target_user.get('email')}' has been {action_str}.", "info")
    return redirect(url_for("admin.dashboard", tab="users"))


@admin_bp.route("/users/<user_id>/delete", methods=["POST"])
@login_required
@admin_only_required
def delete_user(user_id):
    """Admin privilege: Permanently deletes a user account and associated personal data."""
    if str(user_id) == str(current_user.id):
        flash("You cannot delete your own account from the admin dashboard.", "warning")
        return redirect(url_for("admin.dashboard", tab="users"))

    db = get_db()
    user_oid = ObjectId(user_id)
    target_user = db.users.find_one({"_id": user_oid})
    if not target_user:
        flash("User not found.", "warning")
        return redirect(url_for("admin.dashboard", tab="users"))

    if target_user.get("role") == "admin":
        flash("Cannot delete an administrator account.", "danger")
        return redirect(url_for("admin.dashboard", tab="users"))

    # Adjust upvotes
    user_upvotes = list(db.upvotes.find({"user_id": user_oid}))
    for up in user_upvotes:
        db.reports.update_one({"_id": up["report_id"]}, {"$inc": {"upvote_count": -1}})
    db.upvotes.delete_many({"user_id": user_oid})
    db.digest_log.delete_many({"user_id": user_oid})
    authored_report_ids = [
        report["_id"]
        for report in db.reports.find({"author_id": user_oid}, {"_id": 1})
    ]
    db.upvotes.delete_many({"report_id": {"$in": authored_report_ids}})
    db.reports.delete_many({"author_id": user_oid})
    db.users.delete_one({"_id": user_oid})

    flash(f"User account '{target_user.get('email')}' and associated records permanently deleted.", "info")
    return redirect(url_for("admin.dashboard", tab="users"))


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
    from app.jobs.digest import dispatch_digest
    result = dispatch_digest()
    sent = result.get("emails_dispatched", 0)
    users = result.get("users_notified", 0)
    if sent > 0:
        flash(f"Civic digest dispatched: {sent} email(s) successfully sent to {users} resident(s).", "success")
    else:
        msg = result.get("message", "No matching unverified issues within resident radii to dispatch.")
        flash(f"Digest run completed: {msg}", "info")
    return redirect(url_for("admin.dashboard"))
