import secrets
import logging
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash
from app.auth.validators import validate_email_format
from app.auth.models import User
from app.services.email import send_email
from app.db import get_db

logger = logging.getLogger(__name__)

OTP_VALIDITY_MINUTES = 15
RESEND_COOLDOWN_SECONDS = 30


def generate_otp() -> str:
    """Generates a cryptographically secure 6-digit numeric OTP."""
    return f"{secrets.randbelow(900000) + 100000}"


def send_verification_otp_email(to_email: str, name: str, otp: str) -> bool:
    """Dispatches a professional OTP verification email."""
    subject = f"Verify Your Email — GCIR Code: {otp}"

    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 540px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
        <div style="background: #1a73e8; padding: 24px; text-align: center; color: #ffffff;">
            <div style="font-size: 28px; margin-bottom: 4px;">🏛️</div>
            <h1 style="margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.5px;">Geo-Tagged Civic Issue Reporter</h1>
            <p style="margin: 4px 0 0 0; font-size: 13px; opacity: 0.9;">Email Ownership Verification</p>
        </div>
        <div style="padding: 28px 24px; color: #334155;">
            <p style="font-size: 15px; margin-top: 0;">Hi <strong>{name}</strong>,</p>
            <p style="font-size: 14px; line-height: 1.6; color: #475569;">
                Thank you for joining GCIR to report and verify civic issues in your neighborhood. Please enter the 6-digit verification code below to confirm ownership of this email address:
            </p>
            <div style="background: #f8fafc; border: 2px dashed #93c5fd; border-radius: 8px; padding: 18px; text-align: center; margin: 24px 0;">
                <div style="font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #1a73e8; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;">
                    {otp}
                </div>
                <div style="font-size: 12px; color: #64748b; margin-top: 8px; font-weight: 500;">
                    ⏱️ Code expires in {OTP_VALIDITY_MINUTES} minutes
                </div>
            </div>
            <p style="font-size: 13px; color: #64748b; line-height: 1.5; margin-bottom: 0;">
                If you did not sign up for GCIR, you can safely ignore this email. Someone may have entered your address by mistake.
            </p>
        </div>
        <div style="background: #f1f5f9; border-top: 1px solid #e2e8f0; padding: 14px; text-align: center; font-size: 12px; color: #94a3b8;">
            Geo-Tagged Civic Issue Reporter &bull; Delhi-NCR Civic Network
        </div>
    </div>
    """

    text_body = f"""Hi {name},

Thank you for signing up for GCIR.

Your 6-digit email verification code is: {otp}

This code will expire in {OTP_VALIDITY_MINUTES} minutes.
If you did not request this, please safely ignore this message.
"""

    return send_email(to_email=to_email, subject=subject, html_body=html_body, text_body=text_body)


def stage_pending_signup(
    name: str,
    email: str,
    password: str,
    home_coords: list[float] | None = None,
    digest_opt_in: bool = True,
    digest_radius_km: float = 5.0,
    db=None
) -> dict:
    """
    Validates email format, verifies no existing account,
    generates OTP, stages pending signup in MongoDB, and sends verification email.
    """
    if db is None:
        db = get_db()

    email_clean = email.strip().lower()
    if not validate_email_format(email_clean):
        raise ValueError("Invalid email format.")

    if db.users.find_one({"email": email_clean}):
        raise ValueError("An account with this email already exists.")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=OTP_VALIDITY_MINUTES)
    otp = generate_otp()

    pending_doc = {
        "name": name.strip(),
        "email": email_clean,
        "password_hash": generate_password_hash(password),
        "home_coords": home_coords,
        "digest_opt_in": digest_opt_in,
        "digest_radius_km": float(digest_radius_km),
        "otp": otp,
        "created_at": now,
        "last_sent_at": now,
        "expires_at": expires_at
    }

    db.pending_signups.update_one(
        {"email": email_clean},
        {"$set": pending_doc},
        upsert=True
    )

    send_verification_otp_email(to_email=email_clean, name=name.strip(), otp=otp)
    logger.info(f"Verification OTP generated and sent to {email_clean}")
    return pending_doc


def verify_and_complete_signup(email: str, entered_otp: str, db=None) -> tuple[User | None, str]:
    """
    Verifies the 6-digit OTP against pending signups.
    If valid and unexpired, promotes to active user in db.users.
    """
    if db is None:
        db = get_db()

    email_clean = email.strip().lower()
    clean_otp = entered_otp.strip()

    pending = db.pending_signups.find_one({"email": email_clean})
    if not pending:
        return None, "No pending registration found for this email. Please sign up again."

    # Check expiration
    now = datetime.now(timezone.utc)
    exp = pending.get("expires_at")
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp and now > exp:
        return None, "Verification code has expired. Please request a new code."

    # Check OTP
    if pending.get("otp") != clean_otp:
        return None, "Invalid verification code. Please check your email and try again."

    # Prevent duplicate if account was created concurrently
    if db.users.find_one({"email": email_clean}):
        db.pending_signups.delete_one({"email": email_clean})
        return None, "An account with this email already exists. Please log in."

    # Create active user
    user_doc = {
        "name": pending["name"],
        "email": pending["email"],
        "password_hash": pending["password_hash"],
        "role": "resident",
        "digest_opt_in": pending.get("digest_opt_in", True),
        "digest_radius_km": float(pending.get("digest_radius_km", 5.0)),
        "created_at": datetime.now(timezone.utc),
        "last_login_at": datetime.now(timezone.utc),
        "home_location": None,
        "last_login_location": None,
        "email_verified": True
    }

    coords = pending.get("home_coords")
    if coords and len(coords) == 2:
        user_doc["home_location"] = {
            "type": "Point",
            "coordinates": [float(coords[0]), float(coords[1])]
        }

    res = db.users.insert_one(user_doc)
    user_doc["_id"] = res.inserted_id

    # Clean up pending record
    db.pending_signups.delete_one({"email": email_clean})
    logger.info(f"User {email_clean} successfully verified and activated.")

    return User(user_doc), "Email verified successfully! Welcome to GCIR."


def resend_verification_otp(email: str, db=None) -> tuple[bool, str]:
    """Resends a new OTP code subject to a cooldown period."""
    if db is None:
        db = get_db()

    email_clean = email.strip().lower()
    pending = db.pending_signups.find_one({"email": email_clean})
    if not pending:
        return False, "No pending registration found for this email. Please sign up again."

    now = datetime.now(timezone.utc)
    last_sent = pending.get("last_sent_at")
    if last_sent:
        if last_sent.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=timezone.utc)
        elapsed = (now - last_sent).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            remaining = int(RESEND_COOLDOWN_SECONDS - elapsed)
            return False, f"Please wait {remaining} seconds before requesting another code."

    new_otp = generate_otp()
    new_expires = now + timedelta(minutes=OTP_VALIDITY_MINUTES)

    db.pending_signups.update_one(
        {"email": email_clean},
        {
            "$set": {
                "otp": new_otp,
                "last_sent_at": now,
                "expires_at": new_expires
            }
        }
    )

    send_verification_otp_email(to_email=email_clean, name=pending.get("name", "Resident"), otp=new_otp)
    logger.info(f"New verification OTP sent to {email_clean}")
    return True, "A new 6-digit verification code has been sent to your email."
