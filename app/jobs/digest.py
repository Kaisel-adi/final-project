from datetime import datetime, timezone, timedelta
from bson import ObjectId
from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user
from app.reports.services import haversine_distance_km, CATEGORIES
from app.services.email import send_email
from app.db import get_db

jobs_bp = Blueprint("jobs", __name__, url_prefix="/jobs")


def dispatch_digest(db=None, lookback_hours: int = 24) -> dict:
    """
    Core business logic to identify unverified reports within resident radii and dispatch digest emails.
    """
    if db is None:
        db = get_db()

    now = datetime.now(timezone.utc)
    lookback = now - timedelta(hours=lookback_hours)

    # 1. Fetch unverified "Reported" issues created recently
    recent_reports = list(db.reports.find({
        "status": "Reported",
        "is_flagged": {"$ne": True},
        "created_at": {"$gte": lookback}
    }))

    if not recent_reports:
        return {
            "status": "success",
            "message": f"No new reported issues found in {lookback_hours}h lookback window.",
            "candidates_evaluated": 0,
            "users_notified": 0,
            "emails_dispatched": 0,
            "executed_at": now.isoformat()
        }

    # 2. Fetch all opted-in users with home or last login location
    users = list(db.users.find({"digest_opt_in": True}))
    
    # 3. Fetch past sent report IDs per user to suppress duplicate email items
    digest_history = {}
    for d in db.digest_log.find({"sent_at": {"$gte": lookback}}):
        uid = str(d["user_id"])
        digest_history.setdefault(uid, set()).update(str(r) for r in d.get("report_ids", []))

    user_matches = {}  # { user_id: (u, [reports]) }
    cat_dict = dict(CATEGORIES)

    for u in users:
        u_id_str = str(u["_id"])
        u_coords = None
        if u.get("home_location"):
            u_coords = u["home_location"].get("coordinates")
        elif u.get("last_login_location"):
            u_coords = u["last_login_location"].get("coordinates")

        if not u_coords or len(u_coords) != 2:
            continue

        u_lon, u_lat = u_coords[0], u_coords[1]
        radius_km = float(u.get("digest_radius_km", 5.0))
        past_sent = digest_history.get(u_id_str, set())

        # Find user's existing upvotes to exclude
        user_upvotes = {str(up["report_id"]) for up in db.upvotes.find({"user_id": u["_id"]})}

        matched_for_user = []
        for r in recent_reports:
            r_id_str = str(r["_id"])
            # Exclusion 1: Author cannot be user
            if r["author_id"] == u["_id"]:
                continue
            # Exclusion 2: User already upvoted
            if r_id_str in user_upvotes:
                continue
            # Exclusion 3: Already sent to this user
            if r_id_str in past_sent:
                continue

            r_lon, r_lat = r["location"]["coordinates"]
            dist_km = haversine_distance_km(u_lon, u_lat, r_lon, r_lat)
            if dist_km <= radius_km:
                r_copy = dict(r)
                r_copy["dist_km"] = round(dist_km, 1)
                r_copy["cat_label"] = cat_dict.get(r["category"], r["category"])
                matched_for_user.append(r_copy)

            if len(matched_for_user) >= 5:
                break

        if matched_for_user:
            user_matches[u_id_str] = (u, matched_for_user)

    # 4. Dispatch digest emails and log
    emails_sent = 0
    for u_id_str, (u, items) in user_matches.items():
        subject = f"GCIR Digest: {len(items)} civic issues near you need community verification"
        
        items_html = ""
        items_text = ""
        report_ids_sent = []

        for item in items:
            report_ids_sent.append(item["_id"])
            items_html += f"""
            <li style="margin-bottom: 12px; padding: 10px; background: #f8f9fa; border-radius: 6px;">
                <strong>{item['cat_label']}</strong> ({item['dist_km']} km away)<br/>
                <span>{item['description'][:120]}...</span><br/>
                <span style="color: #666; font-size: 0.85em;">Current verifications: {item['upvote_count']} / 10 required</span>
            </li>
            """
            items_text += f"- [{item['cat_label']} - {item['dist_km']}km away] {item['description'][:100]}\n"

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
            <h2 style="color: #1a73e8;">GCIR Civic Verification Digest</h2>
            <p>Hello {u.get('name', 'Resident')},</p>
            <p>New civic issues were recently reported within your <strong>{u.get('digest_radius_km', 5)} km</strong> neighborhood radius. Take a minute to verify them:</p>
            <ul style="list-style-type: none; padding-left: 0;">
                {items_html}
            </ul>
            <p style="font-size: 0.85em; color: #777;">
                To adjust your neighborhood radius or unsubscribe, update your profile settings in GCIR.
            </p>
        </div>
        """

        dispatched = send_email(u["email"], subject, html_body, items_text)
        if dispatched:
            emails_sent += 1
            db.digest_log.insert_one({
                "user_id": u["_id"],
                "report_ids": report_ids_sent,
                "sent_at": now
            })

    return {
        "status": "success",
        "candidates_evaluated": len(recent_reports),
        "users_notified": len(user_matches),
        "emails_dispatched": emails_sent,
        "executed_at": now.isoformat()
    }


@jobs_bp.route("/digest", methods=["POST", "GET"])
def run_digest_job():
    """
    Scheduled job endpoint executed periodically (e.g. every 6 hours).
    Secured by X-Job-Token header or authenticated Admin / Moderator.
    """
    token = request.headers.get("X-Job-Token") or request.args.get("token")
    secret_token = current_app.config.get("CRON_SECRET_TOKEN")

    is_authorized = (token and token == secret_token) or (
        current_user.is_authenticated and (getattr(current_user, "is_admin", False) or getattr(current_user, "is_moderator", False))
    )
    if not is_authorized:
        return jsonify({"error": "Unauthorized. Invalid or missing job token."}), 401

    try:
        hours = int(request.args.get("hours", 24))
    except (ValueError, TypeError):
        hours = 24

    result = dispatch_digest(lookback_hours=hours)
    return jsonify(result), 200
