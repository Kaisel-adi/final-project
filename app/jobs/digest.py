from datetime import datetime, timezone, timedelta
from bson import ObjectId
from flask import Blueprint, request, jsonify, current_app
from flask_login import current_user
from app.reports.services import haversine_distance_km, CATEGORIES, get_report_url
from app.services.email import send_email
from app.db import get_db

jobs_bp = Blueprint("jobs", __name__, url_prefix="/jobs")


def dispatch_digest(db=None, lookback_hours: int = 24) -> dict:
    """
    Core business logic to identify unverified reports within resident radii and dispatch digest emails.
    Embeds direct report links so recipients can directly visit and verify incidents on the website.
    Location precedence: verify with last_login_location of users; if null, check home_location.
    Default radius: 5.0 km.
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
        # Verify with last login location of users; if null, check user home location
        u_coords = None
        last_loc = u.get("last_login_location")
        if last_loc and isinstance(last_loc, dict):
            c = last_loc.get("coordinates")
            if c and len(c) == 2:
                u_coords = c

        if not u_coords:
            home_loc = u.get("home_location")
            if home_loc and isinstance(home_loc, dict):
                c = home_loc.get("coordinates")
                if c and len(c) == 2:
                    u_coords = c

        if not u_coords or len(u_coords) != 2:
            continue

        u_lon, u_lat = float(u_coords[0]), float(u_coords[1])
        radius_km = float(u.get("digest_radius_km") or 5.0)
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
        subject = f"Garuda Digest: {len(items)} civic issues near you need community verification"
        
        items_html = ""
        items_text = ""
        report_ids_sent = []

        for item in items:
            report_ids_sent.append(item["_id"])
            report_url = get_report_url(item["_id"])
            items_html += f"""
            <li style="margin-bottom: 14px; padding: 14px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; border-left: 4px solid #0d9488;">
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px;">
                    <strong style="color: #0f172a; font-size: 14px;">{item['cat_label']}</strong>
                    <span style="color: #64748b; font-size: 12px;">{item['dist_km']} km away</span>
                </div>
                <p style="margin: 4px 0 8px 0; color: #334155; font-size: 13px; line-height: 1.5;">{item['description'][:140]}...</p>
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                    <span style="color: #64748b; font-size: 12px;">Community verifications: <strong>{item['upvote_count']} / 10</strong></span>
                    <a href="{report_url}" style="display: inline-block; background-color: #0d9488; color: #ffffff !important; text-decoration: none; padding: 6px 14px; border-radius: 8px; font-size: 12px; font-weight: bold;" target="_blank">View &amp; Verify Report &rarr;</a>
                </div>
            </li>
            """
            items_text += f"- [{item['cat_label']} - {item['dist_km']}km away] {item['description'][:100]}\n  View on Garuda: {report_url}\n\n"

        html_body = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 16px; background: #ffffff;">
            <div style="border-bottom: 2px solid #0d9488; padding-bottom: 12px; margin-bottom: 16px;">
                <h2 style="color: #0d9488; margin: 0; font-size: 20px;">Garuda Civic Verification Digest</h2>
                <p style="color: #64748b; font-size: 13px; margin: 4px 0 0 0;">Community-powered civic action for your neighborhood</p>
            </div>
            <p style="font-size: 14px; color: #334155;">Hello <strong>{u.get('name', 'Resident')}</strong>,</p>
            <p style="font-size: 14px; color: #334155;">New civic issues were recently reported within your <strong>{u.get('digest_radius_km') or 5.0} km</strong> neighborhood radius. Take a minute to review evidence and upvote:</p>
            <ul style="list-style-type: none; padding-left: 0; margin: 16px 0;">
                {items_html}
            </ul>
            <div style="margin-top: 20px; padding-top: 14px; border-top: 1px solid #f1f5f9; font-size: 11px; color: #94a3b8; text-align: center;">
                To adjust your neighborhood radius or unsubscribe, update your profile settings in Garuda.
            </div>
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
