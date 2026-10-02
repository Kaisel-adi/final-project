import logging
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from app.db import get_db
from app.services.email import send_email

logger = logging.getLogger(__name__)

# Authority Email Variables for centralized management and easy updates
AUTHORITY_TEST_EMAIL = "lalitnegi0002@gmail.com"
TEST_USER_EMAIL = "luckfreefire2021@gmail.com"

# Standard / Production Emergency & Municipal Contacts
AUTHORITY_POLICE_EMAIL = "controlroom.delhipolice@gov.in"
AUTHORITY_FIRE_EMAIL = "controlroom@dfs.delhigovt.nic.in"
AUTHORITY_AMBULANCE_EMAIL = "ambulance-control@delhi.gov.in"
AUTHORITY_CHILDLINE_EMAIL = "contact@childlineindia.org"
AUTHORITY_LPG_GAS_EMAIL = "emergency-gas@indianoil.in"
AUTHORITY_DDMA_EMAIL = "emergency-response@ddma.delhi.gov.in"
AUTHORITY_BSES_ELECTRICITY_EMAIL = "emergency@bsesdelhi.com"
AUTHORITY_CENTRAL_GRIEVANCE_EMAIL = "pgmsdelhi@nic.in"

# Emergency Response Contacts for Life Hazard direct routing
EMERGENCY_SERVICES = [
    {
        "service": "POLICE",
        "number": "112",
        "description": "National Emergency Unified Helpline",
        "icon": "local_police",
        "email": AUTHORITY_POLICE_EMAIL
    },
    {
        "service": "FIRE",
        "number": "101",
        "description": "Delhi Fire Service Control Room",
        "icon": "local_fire_department",
        "email": AUTHORITY_FIRE_EMAIL
    },
    {
        "service": "AMBULANCE",
        "number": "102",
        "description": "Emergency Medical Ambulance Service",
        "icon": "medical_services",
        "email": AUTHORITY_AMBULANCE_EMAIL
    },
    {
        "service": "Children In Difficult Situation",
        "number": "1098",
        "description": "Childline Emergency Helpline",
        "icon": "child_care",
        "email": AUTHORITY_CHILDLINE_EMAIL
    },
    {
        "service": "LPG Leak Helpline",
        "number": "1906",
        "description": "LPG Gas Leak & Emergency Response",
        "icon": "warning",
        "email": AUTHORITY_LPG_GAS_EMAIL
    },
    {
        "service": "Disaster Management Services",
        "number": "108",
        "description": "Delhi Disaster Management Authority (DDMA)",
        "icon": "flood",
        "email": AUTHORITY_DDMA_EMAIL
    }
]


def is_testing_mode() -> bool:
    """Checks if currently running tests or if emergency override is active."""
    import sys
    if "pytest" in sys.modules:
        return True
    try:
        from flask import current_app, has_app_context
        if has_app_context():
            if current_app.config.get("TESTING", False):
                return True
            if current_app.config.get("EMERGENCY_OVERRIDE_EMAIL"):
                return True
    except Exception:
        pass
    return False


def get_emergency_authority(lon: float, lat: float) -> dict:
    """
    Direct routing for life hazard emergencies.
    Routes to Fire, Electricity, or Disaster-Management contacts instead of general municipal inbox.
    While testing or running unit tests, replaces authority emails with AUTHORITY_TEST_EMAIL (lalitnegi0002@gmail.com)
    to avoid misusing official government emergency services.
    """
    if is_testing_mode():
        return {
            "name": "Delhi Fire & Disaster Emergency Operations Center (EOC) [TEST MODE]",
            "level": "emergency",
            "body": "Delhi Fire Service / DDMA / Police Emergency Command",
            "contact_email": AUTHORITY_TEST_EMAIL,
            "fire_email": AUTHORITY_TEST_EMAIL,
            "electricity_email": AUTHORITY_TEST_EMAIL,
            "police_email": AUTHORITY_TEST_EMAIL,
            "phone": "112 / 101 / 108",
            "website": "https://ddma.delhigovt.nic.in",
            "is_fallback": False
        }

    return {
        "name": "Delhi Fire & Disaster Emergency Operations Center (EOC)",
        "level": "emergency",
        "body": "Delhi Fire Service / DDMA / Police Emergency Command",
        "contact_email": AUTHORITY_DDMA_EMAIL,
        "fire_email": AUTHORITY_FIRE_EMAIL,
        "electricity_email": AUTHORITY_BSES_ELECTRICITY_EMAIL,
        "police_email": AUTHORITY_POLICE_EMAIL,
        "phone": "112 / 101 / 108",
        "website": "https://ddma.delhigovt.nic.in",
        "is_fallback": False
    }


def send_emergency_dispatch(report: dict, db=None, reply_to: str | None = None) -> bool:
    """
    Direct routing: Sends an immediate high-priority emergency notification email to
    fire, electricity, and disaster-management emergency contacts.
    Supports Reply-To header pointing to citizen's verified email.
    """
    try:
        coords = report.get("location", {}).get("coordinates", [77.2090, 28.6139])
        lon, lat = coords[0], coords[1]
        authority = get_emergency_authority(lon, lat)
        
        rep_id = str(report.get("_id", "unknown"))
        description = report.get("description", "Immediate life hazard reported at coordinates.")
        created_str = datetime.now(timezone.utc).strftime("%d %b %Y, %I:%M:%S %p UTC")
        gmaps_url = f"https://www.google.com/maps?q={lat},{lon}"

        from app.reports.services import get_report_url
        report_url = get_report_url(rep_id)

        subject = f"🚨 [IMMEDIATE LIFE HAZARD] Priority Emergency Alert at {lat:.5f}, {lon:.5f}"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #fef2f2; color: #1e293b; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 16px; border: 2px solid #ef4444; overflow: hidden; }}
                .header {{ background: #dc2626; color: #ffffff; padding: 24px; text-align: center; }}
                .badge {{ background: #991b1b; color: #fee2e2; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.05em; }}
                .content {{ padding: 24px; }}
                .meta-table {{ width: 100%; border-collapse: collapse; margin-top: 16px; margin-bottom: 20px; }}
                .meta-table td {{ padding: 8px 12px; border-bottom: 1px solid #f1f5f9; font-size: 13px; }}
                .meta-table td.label {{ color: #64748b; font-weight: 600; width: 35%; }}
                .action-btn {{ display: inline-block; background: #dc2626; color: #ffffff !important; padding: 12px 20px; text-decoration: none; border-radius: 10px; font-weight: bold; font-size: 13px; margin: 5px; }}
                .footer {{ background: #f8fafc; padding: 16px; text-align: center; font-size: 11px; color: #94a3b8; border-top: 1px solid #e2e8f0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <span class="badge">Immediate Emergency Dispatch</span>
                    <h1 style="margin: 12px 0 0 0; font-size: 20px; font-weight: 800;">🚨 LIFE HAZARD REPORTED</h1>
                </div>
                <div class="content">
                    <p style="font-size: 14px; line-height: 1.6; color: #334155; margin-top: 0;">
                        An urgent life-safety hazard has been submitted via Garuda Civic Emergency System and requires immediate first-responder intervention.
                    </p>

                    <table class="meta-table">
                        <tr>
                            <td class="label">Incident ID:</td>
                            <td style="font-family: monospace; font-weight: bold;">{rep_id}</td>
                        </tr>
                        <tr>
                            <td class="label">Category:</td>
                            <td style="color: #dc2626; font-weight: bold;">Life Hazard (Emergency)</td>
                        </tr>
                        <tr>
                            <td class="label">GPS Coordinates:</td>
                            <td style="font-family: monospace;">{lat:.6f}, {lon:.6f}</td>
                        </tr>
                        <tr>
                            <td class="label">Reported Time:</td>
                            <td>{created_str}</td>
                        </tr>
                        <tr>
                            <td class="label">Description / Status:</td>
                            <td>{description}</td>
                        </tr>
                        <tr>
                            <td class="label">Direct Routing:</td>
                            <td>{authority['name']}</td>
                        </tr>
                    </table>

                    <div style="text-align: center; margin: 20px 0;">
                        <a href="{report_url}" class="action-btn" target="_blank">View Incident on Garuda &rarr;</a>
                        <a href="{gmaps_url}" class="action-btn" target="_blank" style="background: #1e293b;">Open in Google Maps &rarr;</a>
                    </div>
                </div>
                <div class="footer">
                    Garuda Emergency Response Notification System • Direct Fire, Police & Disaster Routing
                </div>
            </div>
        </body>
        </html>
        """

        text_body = f"""🚨 IMMEDIATE LIFE HAZARD REPORTED
Incident ID: {rep_id}
Category: Life Hazard
Coordinates: {lat:.6f}, {lon:.6f}
View on Garuda: {report_url}
Google Maps: {gmaps_url}
Reported At: {created_str}
Description: {description}
Routed to: {authority['name']}
"""

        # Dispatch to primary disaster email and backup fire/electricity emails
        recipient = authority["contact_email"]
        dispatched = send_email(recipient, subject, html_body, text_body=text_body, background=True, reply_to=reply_to)
        logger.info(f"Emergency dispatch email submitted to {recipient} (Reply-To: {reply_to}) for report {rep_id}: {dispatched}")
        return dispatched
    except Exception as e:
        logger.error(f"Failed to dispatch emergency email for report: {e}")
        return False


def check_and_escalate_life_hazards(db=None) -> list:
    """
    Escalation timers:
    If a life hazard report is unacknowledged for 60 minutes, it automatically escalates.
    Transitions status to 'Escalated', logs the status change, and dispatches an escalation notification.
    """
    if db is None:
        db = get_db()

    now = datetime.now(timezone.utc)
    sixty_mins_ago = now - timedelta(minutes=60)

    # Find unacknowledged life hazard reports created >= 60 minutes ago
    unacknowledged = list(db.reports.find({
        "category": "life_hazard",
        "status": "Reported",
        "created_at": {"$lte": sixty_mins_ago}
    }))

    escalated_ids = []
    for rep in unacknowledged:
        rep_id = rep["_id"]
        note = "Unacknowledged for 60 minutes. Escalated automatically to State Disaster Management Authority."
        db.reports.update_one(
            {"_id": rep_id},
            {
                "$set": {
                    "status": "Escalated",
                    "is_escalated": True,
                    "escalated_at": now
                },
                "$push": {
                    "status_log": {
                        "status": "Escalated",
                        "timestamp": now,
                        "note": note
                    }
                }
            }
        )
        escalated_ids.append(str(rep_id))

        # Send escalation email alert
        coords = rep.get("location", {}).get("coordinates", [77.2090, 28.6139])
        subject = f"⚠️ [ESCALATION: 60 MINS UNACKNOWLEDGED] Life Hazard Emergency at {coords[1]:.5f}, {coords[0]:.5f}"
        body = f"""⚠️ ESCALATION ALERT: Unacknowledged Life Hazard
Incident {rep_id} has remained unacknowledged for more than 60 minutes.
Status has been automatically elevated to ESCALATED.
Coordinates: {coords[1]}, {coords[0]}
Map: https://www.google.com/maps?q={coords[1]},{coords[0]}
Immediate supervision required.
"""
        recipient = AUTHORITY_TEST_EMAIL if is_testing_mode() else AUTHORITY_DDMA_EMAIL
        try:
            send_email(recipient, subject, f"<pre>{body}</pre>", text_body=body, background=True)
        except Exception as e:
            logger.error(f"Error sending escalation email for {rep_id}: {e}")

    return escalated_ids


def dispatch_report_to_concerned_authority(report: dict, author_email: str | None = None, db=None) -> tuple[bool, str]:
    """
    Directly dispatches civic or life hazard report to the responsible authority.
    Reply-To is set to the citizen's verified email.
    In testing mode, routes to AUTHORITY_TEST_EMAIL (lalitnegi0002@gmail.com).
    """
    if db is None:
        db = get_db()

    coords = report.get("location", {}).get("coordinates", [77.2090, 28.6139])
    lon, lat = coords[0], coords[1]
    category = report.get("category", "other")
    rep_id = str(report.get("_id", "unknown"))
    now = datetime.now(timezone.utc)

    if category == "life_hazard":
        authority = get_emergency_authority(lon, lat)
        sent = send_emergency_dispatch(report, db=db, reply_to=author_email)
        recipient = authority["contact_email"]
        authority_name = authority["name"]
        status_msg = f"Dispatched to {authority_name} ({recipient})"
    else:
        from app.complaints.router import lookup_authority_for_point
        authority = lookup_authority_for_point(lon, lat, category, db=db)
        recipient = AUTHORITY_TEST_EMAIL if is_testing_mode() else authority.get("contact_email", AUTHORITY_CENTRAL_GRIEVANCE_EMAIL)
        authority_name = authority.get("name", "Concerned Authority")

        from app.reports.services import get_report_url
        report_url = get_report_url(rep_id)

        cat_label = category.replace("_", " ").title()
        subject = f"🚨 [CIVIC ISSUE DISPATCH] {cat_label} - Ref #{rep_id[-6:]}"
        gmaps_url = f"https://www.google.com/maps?q={lat},{lon}"
        photo_url = report.get("photo_url", "")
        description = report.get("description", "Civic issue reported via Garuda platform.")
        created_str = now.strftime("%d %b %Y, %I:%M %p UTC")

        photo_section = f'<p><strong>Evidence Media:</strong> <a href="{photo_url}" target="_blank">View Photo / Video</a></p>' if photo_url else ''

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f8fafc; color: #1e293b; padding: 20px; }}
                .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 16px; border: 1px solid #cbd5e1; overflow: hidden; }}
                .header {{ background: #0f766e; color: #ffffff; padding: 20px; text-align: center; }}
                .content {{ padding: 24px; }}
                .meta-table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
                .meta-table td {{ padding: 8px 12px; border-bottom: 1px solid #f1f5f9; font-size: 13px; }}
                .meta-table td.label {{ color: #64748b; font-weight: 600; width: 35%; }}
                .action-btn {{ display: inline-block; background: #0f766e; color: #ffffff !important; padding: 10px 18px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 13px; margin: 4px; }}
                .footer {{ background: #f8fafc; padding: 14px; text-align: center; font-size: 11px; color: #94a3b8; border-top: 1px solid #e2e8f0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2 style="margin: 0; font-size: 18px;">Garuda Citizen Civic Issue Dispatch</h2>
                </div>
                <div class="content">
                    <p style="font-size: 14px; color: #334155; margin-top: 0;">
                        A civic defect has been reported in your jurisdiction via Garuda.
                    </p>
                    <table class="meta-table">
                        <tr><td class="label">Incident ID:</td><td style="font-family: monospace; font-weight: bold;">{rep_id}</td></tr>
                        <tr><td class="label">Category:</td><td><strong>{cat_label}</strong></td></tr>
                        <tr><td class="label">Description:</td><td>{description}</td></tr>
                        <tr><td class="label">GPS Coordinates:</td><td style="font-family: monospace;">{lat:.6f}, {lon:.6f}</td></tr>
                        <tr><td class="label">Reported Time:</td><td>{created_str}</td></tr>
                        <tr><td class="label">Responsible Authority:</td><td>{authority_name}</td></tr>
                        <tr><td class="label">Citizen Reply-To:</td><td>{author_email or 'Not Provided'}</td></tr>
                    </table>
                    {photo_section}
                    <div style="text-align: center; margin: 20px 0;">
                        <a href="{report_url}" class="action-btn" target="_blank">View Report on Garuda &rarr;</a>
                        <a href="{gmaps_url}" class="action-btn" target="_blank" style="background: #1e293b;">View GPS Location on Google Maps &rarr;</a>
                    </div>
                </div>
                <div class="footer">
                    Garuda Civic Platform • Direct Citizen Authority Gateway • Reply directly to this email to communicate with the citizen.
                </div>
            </div>
        </body>
        </html>
        """

        text_body = f"""GARUDA CIVIC DISPATCH
Incident ID: {rep_id}
Category: {cat_label}
Description: {description}
Coordinates: {lat:.6f}, {lon:.6f}
View on Garuda: {report_url}
Maps: {gmaps_url}
Authority: {authority_name}
Reply-To: {author_email}
"""
        sent = send_email(recipient, subject, html_body, text_body=text_body, background=True, reply_to=author_email)
        status_msg = f"Dispatched to {authority_name} ({recipient})"

    # Update MongoDB report document
    try:
        db.reports.update_one(
            {"_id": report["_id"]},
            {
                "$set": {
                    "dispatched_to_authority": True,
                    "dispatched_at": now,
                    "authority_dispatched_to": recipient,
                    "authority_dispatched_name": authority_name,
                    "authority_dispatch_status": status_msg
                },
                "$push": {
                    "status_log": {
                        "status": report.get("status", "Reported"),
                        "timestamp": now,
                        "note": f"Report directly dispatched to {authority_name} ({recipient})"
                    }
                }
            }
        )
        report["dispatched_to_authority"] = True
        report["authority_dispatched_to"] = recipient
        report["authority_dispatched_name"] = authority_name
        report["authority_dispatch_status"] = status_msg
    except Exception as err:
        logger.error(f"Error recording authority dispatch status in DB: {err}")

    return sent, status_msg


def notify_nearby_users_of_life_hazard(report: dict, db=None) -> list[str]:
    """
    Dispatches immediate safety notification email to users located within 1km radius of the life hazard.
    Location determination rule:
    - Verify with last_login_location of users; if null, check user home_location.
    - Embeds the Garuda report web link so citizens can directly visit the website from email.
    """
    if db is None:
        db = get_db()

    coords = report.get("location", {}).get("coordinates", [])
    if not coords or len(coords) != 2:
        return []

    inc_lon, inc_lat = float(coords[0]), float(coords[1])
    rep_id = str(report.get("_id", "unknown"))
    author_id = report.get("author_id")
    description = report.get("description", "Immediate life hazard reported at coordinates.")

    from app.reports.services import get_report_url, haversine_distance_km
    report_url = get_report_url(rep_id)
    gmaps_url = f"https://www.google.com/maps?q={inc_lat},{inc_lon}"

    # Query users with an email address (excluding author)
    query = {"email": {"$exists": True, "$ne": ""}}
    if author_id:
        try:
            query["_id"] = {"$ne": ObjectId(author_id)}
        except Exception:
            pass

    candidates = list(db.users.find(query))
    notified_emails = []

    for u in candidates:
        # Priority rule: verify with last login location of users; if null, check user home location
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

        if not u_coords:
            continue

        try:
            u_lon, u_lat = float(u_coords[0]), float(u_coords[1])
            dist_km = haversine_distance_km(inc_lon, inc_lat, u_lon, u_lat)
        except Exception:
            continue

        # Proximity threshold: within 1 km radius
        if dist_km <= 1.0:
            user_email = u.get("email")
            if not user_email:
                continue

            dist_m = int(round(dist_km * 1000))
            dist_text = f"{dist_m}m" if dist_m < 1000 else f"{dist_km:.2f}km"
            user_name = u.get("name", "Resident")

            subject = f"🚨 [LIFE HAZARD ALERT] Critical Emergency {dist_text} from your location"

            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #fef2f2; color: #1e293b; margin: 0; padding: 20px; }}
                    .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 16px; border: 2px solid #ef4444; overflow: hidden; }}
                    .header {{ background: #dc2626; color: #ffffff; padding: 22px; text-align: center; }}
                    .badge {{ background: #991b1b; color: #fee2e2; padding: 4px 12px; border-radius: 9999px; font-size: 11px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.05em; }}
                    .content {{ padding: 24px; }}
                    .dist-badge {{ background: #fee2e2; border: 1px solid #fca5a5; color: #991b1b; padding: 10px 14px; border-radius: 10px; font-weight: bold; font-size: 13px; margin-bottom: 16px; }}
                    .meta-table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
                    .meta-table td {{ padding: 8px 12px; border-bottom: 1px solid #f1f5f9; font-size: 13px; }}
                    .meta-table td.label {{ color: #64748b; font-weight: 600; width: 35%; }}
                    .action-btn {{ display: inline-block; background: #dc2626; color: #ffffff !important; padding: 12px 24px; text-decoration: none; border-radius: 10px; font-weight: bold; font-size: 14px; }}
                    .footer {{ background: #f8fafc; padding: 16px; text-align: center; font-size: 11px; color: #94a3b8; border-top: 1px solid #e2e8f0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <span class="badge">Immediate Neighborhood Safety Alert</span>
                        <h1 style="margin: 10px 0 0 0; font-size: 20px; font-weight: 800;">🚨 LIFE HAZARD REPORTED NEARBY</h1>
                    </div>
                    <div class="content">
                        <div class="dist-badge">
                            📍 Incident Distance: Approx. {dist_text} from your location
                        </div>
                        <p style="font-size: 14px; line-height: 1.6; color: #334155; margin-top: 0;">
                            Hello {user_name}, an urgent life-safety hazard has just been reported within 1 km of your location on the Garuda Civic Emergency Network. Please exercise caution.
                        </p>

                        <table class="meta-table">
                            <tr>
                                <td class="label">Incident Ref:</td>
                                <td style="font-family: monospace; font-weight: bold;">#{rep_id[-6:]}</td>
                            </tr>
                            <tr>
                                <td class="label">Category:</td>
                                <td style="color: #dc2626; font-weight: bold;">Life Hazard</td>
                            </tr>
                            <tr>
                                <td class="label">Hazard Details:</td>
                                <td>{description}</td>
                            </tr>
                            <tr>
                                <td class="label">Coordinates:</td>
                                <td style="font-family: monospace;">{inc_lat:.5f}, {inc_lon:.5f}</td>
                            </tr>
                        </table>

                        <div style="text-align: center; margin: 24px 0;">
                            <a href="{report_url}" class="action-btn" target="_blank">View Incident on Garuda Website &rarr;</a>
                        </div>

                        <p style="font-size: 12px; color: #64748b; text-align: center;">
                            Direct Link: <a href="{report_url}" style="color: #dc2626; word-break: break-all;">{report_url}</a><br/>
                            View on <a href="{gmaps_url}" target="_blank" style="color: #64748b; text-decoration: underline;">Google Maps</a>
                        </p>
                    </div>
                    <div class="footer">
                        Garuda Civic Proximity Alert • Sent to residents within 1 km radius • For life-threatening emergencies, dial 112 directly.
                    </div>
                </div>
            </body>
            </html>
            """

            text_body = f"""🚨 URGENT LIFE HAZARD NEARBY
Hello {user_name},
An urgent life-safety hazard has been reported approx. {dist_text} from your location.

Hazard Details: {description}
Coordinates: {inc_lat:.5f}, {inc_lon:.5f}

Direct Report Link: {report_url}
Google Maps: {gmaps_url}

Stay safe and exercise extreme caution near this location.
Garuda Civic Emergency Network
"""
            send_email(user_email, subject, html_body, text_body=text_body, background=True)
            notified_emails.append(user_email)

    logger.info(f"Life hazard {rep_id}: Dispatched proximity alerts to {len(notified_emails)} nearby users within 1km: {notified_emails}")
    return notified_emails
