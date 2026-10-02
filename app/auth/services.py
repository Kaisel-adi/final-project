import secrets
import hashlib
import threading
import logging
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash
from app.auth.validators import validate_email_format, validate_password_strength
from app.auth.models import User
from app.services.email import send_email, send_email_with_status
from app.db import get_db

logger = logging.getLogger(__name__)

OTP_VALIDITY_MINUTES = 15
RESEND_COOLDOWN_SECONDS = 30


def generate_otp() -> str:
    """Generates a cryptographically secure 6-digit numeric OTP."""
    return f"{secrets.randbelow(900000) + 100000}"


def send_verification_otp_email(to_email: str, name: str, otp: str) -> tuple[bool, str]:
    """Dispatches a professional OTP verification email."""
    subject = "Verify Your Email Address — Garuda"

    # Anti-snippet preheader for email notifications:
    # Forces lock-screen and inbox notifications to display this security notice
    # instead of revealing the one-time password in the notification preview.
    preheader_notice = "Security Notice: Open this email to securely view your verification code. Do not share this code."
    anti_snippet_padding = "&#847;&zwnj;&nbsp;&#8199;&shy;" * 45

    html_body = f"""
    <!-- Hidden Preheader: Prevents OTP from leaking into device lock-screen notifications and inbox snippets -->
    <div style="display:none;font-size:1px;color:#ffffff;line-height:1px;max-height:0px;max-width:0px;opacity:0;overflow:hidden;mso-hide:all;">
        {preheader_notice}
    </div>
    <div style="display:none;max-height:0px;overflow:hidden;mso-hide:all;font-size:1px;line-height:1px;">
        {anti_snippet_padding}
    </div>

    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 540px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
        <div style="background: #0d9488; padding: 24px; text-align: center; color: #ffffff;">
            <div style="font-size: 28px; margin-bottom: 4px;"><img src="https://garuda-62ty.onrender.com/static/img/garuda-icon.png" alt="Garuda logo" width="30px" height="30px"></div>
            <h1 style="margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.5px;">Garuda</h1>
            <p style="margin: 4px 0 0 0; font-size: 13px; opacity: 0.9;">See the change. Be the change!</p>
        </div>
        <div style="padding: 28px 24px; color: #334155;">
            <p style="font-size: 15px; margin-top: 0;">Hi <strong>{name}</strong>,</p>
            <p style="font-size: 14px; line-height: 1.6; color: #475569;">
                Thank you for joining Garuda to report and verify civic issues in your neighborhood. Please enter the 6-digit verification code below to confirm ownership of this email address:
            </p>
            <div style="background: #f8fafc; border: 2px dashed #99f6e4; border-radius: 8px; padding: 18px; text-align: center; margin: 24px 0;">
                <div style="font-size: 36px; font-weight: 800; letter-spacing: 8px; color: #0d9488; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;">
                    {otp}
                </div>
                <div style="font-size: 12px; color: #64748b; margin-top: 8px; font-weight: 500;">
                    ⏱️ Code expires in {OTP_VALIDITY_MINUTES} minutes
                </div>
            </div>
            <p style="font-size: 13px; color: #64748b; line-height: 1.5; margin-bottom: 0;">
                If you did not sign up for Garuda, you can safely ignore this email. Someone may have entered your address by mistake.
            </p>
        </div>
        <div style="background: #f1f5f9; border-top: 1px solid #e2e8f0; padding: 14px; text-align: center; font-size: 12px; color: #94a3b8;">
            Garuda &bull; See the change. Be the change!
        </div>
    </div>
    """

    text_body = (
        f"Security Notice: Please open this email in your mailbox to view your verification code. "
        f"For account security, do not share your verification code with anyone.\n\n"
        f"Hi {name},\n\n"
        f"Thank you for joining Garuda to report and verify civic issues in your neighborhood. "
        f"Please enter the 6-digit verification code below to confirm ownership of this email address:\n\n"
        f"Verification Code: {otp}\n\n"
        f"This code will expire in {OTP_VALIDITY_MINUTES} minutes.\n"
        f"If you did not request this, please safely ignore this message."
    )

    return send_email_with_status(to_email=to_email, subject=subject, html_body=html_body, text_body=text_body)


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

    sent, status_msg = send_verification_otp_email(to_email=email_clean, name=name.strip(), otp=otp)
    if not sent:
        logger.error(f"Failed to dispatch verification email to {email_clean}: {status_msg}")
        raise RuntimeError(f"Unable to dispatch verification email: {status_msg}. Please verify your email or check server SMTP configuration.")

    if status_msg == "mock":
        pending_doc["is_mock"] = True

    logger.info(f"Verification OTP generated and sent to {email_clean} ({status_msg})")
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

    return User(user_doc), "Email verified successfully! Welcome to Garuda."


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

    sent, status_msg = send_verification_otp_email(to_email=email_clean, name=pending.get("name", "Resident"), otp=new_otp)
    if not sent:
        logger.error(f"Failed to resend verification OTP to {email_clean}: {status_msg}")
        return False, f"Failed to dispatch verification email: {status_msg}. Please try again later."

    if status_msg == "mock":
        return True, f"A new 6-digit verification code has been sent to your email. [Dev Mode Code: {new_otp}]"

    logger.info(f"New verification OTP sent to {email_clean} ({status_msg})")
    return True, "A new 6-digit verification code has been sent to your email. Please check your inbox and spam folder."


# --- Secure Password Reset Infrastructure ---

RESET_TOKEN_VALIDITY_MINUTES = 30
GENERIC_RESET_MSG = "If an account exists for this email, password reset instructions have been sent."

_reset_rate_limit_lock = threading.Lock()
_ip_reset_attempts: dict[str, list[datetime]] = {}
_email_reset_attempts: dict[str, list[datetime]] = {}
_test_last_reset_tokens: dict[str, str] = {}

MAX_RESET_PER_IP = 10
MAX_RESET_PER_EMAIL = 5
RESET_WINDOW_SECONDS = 900  # 15 minutes


def clear_rate_limits() -> None:
    """Clears in-memory rate limiting and debug token registries (for test isolation)."""
    with _reset_rate_limit_lock:
        _ip_reset_attempts.clear()
        _email_reset_attempts.clear()
        _test_last_reset_tokens.clear()


def check_reset_rate_limit(ip: str | None, email: str | None) -> tuple[bool, str]:
    """
    Evaluates sliding-window rate limits for password reset requests by IP and email.
    Returns (is_allowed, error_message).
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=RESET_WINDOW_SECONDS)

    with _reset_rate_limit_lock:
        if ip:
            clean_ip = ip.strip()
            ip_hits = [t for t in _ip_reset_attempts.get(clean_ip, []) if t > cutoff]
            _ip_reset_attempts[clean_ip] = ip_hits
            if len(ip_hits) >= MAX_RESET_PER_IP:
                return False, "Too many password reset requests from this IP address. Please wait a while before trying again."

        if email:
            clean_email = email.strip().lower()
            email_hits = [t for t in _email_reset_attempts.get(clean_email, []) if t > cutoff]
            _email_reset_attempts[clean_email] = email_hits
            if len(email_hits) >= MAX_RESET_PER_EMAIL:
                return False, "Too many password reset requests for this email address. Please wait a while before trying again."

    return True, ""


def record_reset_attempt(ip: str | None, email: str | None) -> None:
    """Records an attempt timestamp under current IP and/or email bucket."""
    now = datetime.now(timezone.utc)
    with _reset_rate_limit_lock:
        if ip:
            clean_ip = ip.strip()
            _ip_reset_attempts.setdefault(clean_ip, []).append(now)
        if email:
            clean_email = email.strip().lower()
            _email_reset_attempts.setdefault(clean_email, []).append(now)


def generate_reset_token() -> tuple[str, str]:
    """
    Generates a cryptographically secure random token (URL-safe string)
    and computes its SHA-256 hash. Returns (raw_token, token_hash).
    Only token_hash is persisted to the database.
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return raw_token, token_hash


def send_password_reset_email(to_email: str, name: str, reset_url: str) -> tuple[bool, str]:
    """Dispatches a branded password reset transactional email via Brevo."""
    subject = "Reset your Garuda password"

    preheader_notice = "Security Notice: Use the secure link in this email to reset your Garuda password. This link expires in 30 minutes."
    anti_snippet_padding = "&#847;&zwnj;&nbsp;&#8199;&shy;" * 45

    html_body = f"""
    <!-- Hidden Preheader: Prevents sensitive data from leaking into notifications -->
    <div style="display:none;font-size:1px;color:#ffffff;line-height:1px;max-height:0px;max-width:0px;opacity:0;overflow:hidden;mso-hide:all;">
        {preheader_notice}
    </div>
    <div style="display:none;max-height:0px;overflow:hidden;mso-hide:all;font-size:1px;line-height:1px;">
        {anti_snippet_padding}
    </div>

    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 540px; margin: 0 auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
        <div style="background: #0d9488; padding: 24px; text-align: center; color: #ffffff;">
            <div style="font-size: 28px; margin-bottom: 4px;"><img src="https://garuda-62ty.onrender.com/static/img/garuda-icon.png" alt="Garuda logo" width="30px" height="30px"></div>
            <h1 style="margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.5px;">Garuda</h1>
            <p style="margin: 4px 0 0 0; font-size: 13px; opacity: 0.9;">See the change. Be the change!</p>
        </div>
        <div style="padding: 28px 24px; color: #334155;">
            <p style="font-size: 15px; margin-top: 0;">Hi <strong>{name}</strong>,</p>
            <p style="font-size: 14px; line-height: 1.6; color: #475569;">
                We received a request to reset your password for your Garuda civic account. Click the button below to choose a new password:
            </p>
            <div style="text-align: center; margin: 28px 0;">
                <a href="{reset_url}" style="background-color: #0d9488; color: #ffffff; padding: 12px 28px; font-size: 15px; font-weight: 700; text-decoration: none; border-radius: 8px; display: inline-block; box-shadow: 0 2px 4px rgba(13, 148, 136, 0.2);">
                    Reset Password
                </a>
            </div>
            <p style="font-size: 13px; line-height: 1.5; color: #64748b;">
                If the button above does not work, copy and paste this link into your browser:
            </p>
            <p style="font-size: 12px; line-height: 1.4; color: #0d9488; word-break: break-all; background: #f8fafc; padding: 10px; border-radius: 6px; border: 1px solid #e2e8f0;">
                {reset_url}
            </p>
            <p style="font-size: 13px; color: #64748b; line-height: 1.5; margin-top: 24px;">
                ⏱️ <strong>Note:</strong> This link is single-use and will expire in {RESET_TOKEN_VALIDITY_MINUTES} minutes.<br>
                If you did not request a password reset, you can safely ignore this email. Your current password remains unchanged.
            </p>
        </div>
        <div style="background: #f1f5f9; border-top: 1px solid #e2e8f0; padding: 14px; text-align: center; font-size: 12px; color: #94a3b8;">
            Garuda &bull; See the change. Be the change!
        </div>
    </div>
    """

    text_body = (
        f"Hi {name},\n\n"
        f"We received a request to reset your password for your Garuda civic account.\n"
        f"Please click the link below or copy and paste it into your browser to reset your password:\n\n"
        f"{reset_url}\n\n"
        f"This link is single-use and expires in {RESET_TOKEN_VALIDITY_MINUTES} minutes.\n"
        f"If you did not request this, please safely ignore this email. Your current password remains secure.\n"
    )

    return send_email_with_status(to_email=to_email, subject=subject, html_body=html_body, text_body=text_body)


def initiate_password_reset(
    email: str | None,
    base_url: str = "",
    client_ip: str | None = None,
    db=None
) -> tuple[bool, str, int]:
    """
    Handles password reset initiation with strict enumeration safety:
      - Validates non-empty and email format.
      - Checks rate limits by IP and email.
      - If registered: generates cryptographically secure token, hashes with SHA-256,
        stores hash + 30-min expiry, sends Brevo transactional email.
      - Always returns generic message whether email exists or not.
      - Returns (success, message, http_status_code).
    """
    if not email:
        return False, "Email address is required.", 400

    email_clean = email.strip().lower()
    if not validate_email_format(email_clean):
        return False, "Please enter a valid email address.", 400

    allowed, rate_msg = check_reset_rate_limit(ip=client_ip, email=email_clean)
    if not allowed:
        logger.warning("Password reset rate limit exceeded for client_ip=%s", client_ip)
        return False, rate_msg, 429

    # Record this attempt in the rate limiter
    record_reset_attempt(ip=client_ip, email=email_clean)

    try:
        if db is None:
            db = get_db()
        user = db.users.find_one({"email": email_clean})
    except Exception as db_err:
        logger.error("Database connection failure during password reset: %s", db_err)
        return False, "Service temporarily unavailable. Please try again later.", 500

    if not user:
        # Non-registered email: Return same generic response to prevent account enumeration
        logger.info("Password reset requested for unregistered email address.")
        return True, GENERIC_RESET_MSG, 200

    raw_token, token_hash = generate_reset_token()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=RESET_TOKEN_VALIDITY_MINUTES)

    try:
        # Overwrite any previous reset token with the new hashed token
        db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "password_reset_token_hash": token_hash,
                    "password_reset_expires_at": expires_at
                }
            }
        )
    except Exception as db_err:
        logger.error("Database update error during password reset: %s", db_err)
        return False, "Service temporarily unavailable. Please try again later.", 500

    clean_base = base_url.rstrip("/") if base_url else ""
    reset_url = f"{clean_base}/auth/reset-password?token={raw_token}" if clean_base else f"/auth/reset-password?token={raw_token}"

    # Retain token for unit testing verification if running in test environment
    try:
        from flask import current_app, has_app_context
        if has_app_context() and current_app.config.get("TESTING"):
            with _reset_rate_limit_lock:
                _test_last_reset_tokens[email_clean] = raw_token
    except Exception:
        pass

    sent, status_msg = send_password_reset_email(
        to_email=user["email"],
        name=user.get("name", "Resident"),
        reset_url=reset_url
    )

    if not sent:
        # Never log raw reset token
        logger.error("Failed to send password reset email via transactional provider: %s", status_msg)
        # Invalidate the token so no dangling token is left behind
        try:
            db.users.update_one(
                {"_id": user["_id"]},
                {"$unset": {"password_reset_token_hash": "", "password_reset_expires_at": ""}}
            )
        except Exception:
            pass
        # Return generic message to prevent leaking internal provider failures or account existence
        return True, GENERIC_RESET_MSG, 200

    logger.info("Password reset token generated and email dispatched.")
    return True, GENERIC_RESET_MSG, 200


def get_test_reset_token(email: str) -> str | None:
    """Helper for testing assertions: retrieves test reset token for email if stored."""
    with _reset_rate_limit_lock:
        return _test_last_reset_tokens.get(email.strip().lower())


def verify_reset_token(raw_token: str | None, db=None) -> tuple[bool, dict | None, str]:
    """
    Verifies reset token:
      - Validates non-empty
      - Hashes token using SHA-256
      - Finds matching user record with unexpired token
      - Invalidates expired token if found
    Returns (is_valid, user_doc, error_or_success_message).
    """
    if not raw_token or not raw_token.strip():
        return False, None, "Reset token is missing or invalid."

    token_clean = raw_token.strip()
    token_hash = hashlib.sha256(token_clean.encode("utf-8")).hexdigest()

    try:
        if db is None:
            db = get_db()
        user = db.users.find_one({"password_reset_token_hash": token_hash})
    except Exception as db_err:
        logger.error("Database connection failure during token verification: %s", db_err)
        return False, None, "Database service is temporarily unavailable."

    if not user:
        return False, None, "This password reset link is invalid or has already been used."

    now = datetime.now(timezone.utc)
    exp = user.get("password_reset_expires_at")
    if exp:
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now > exp:
            # Clean up expired token
            try:
                db.users.update_one(
                    {"_id": user["_id"]},
                    {"$unset": {"password_reset_token_hash": "", "password_reset_expires_at": ""}}
                )
            except Exception:
                pass
            return False, None, "This password reset link has expired. Please request a new one."

    return True, user, "Reset token is valid."


def reset_user_password(
    raw_token: str | None,
    new_password: str | None,
    confirm_password: str | None,
    db=None
) -> tuple[bool, str, int]:
    """
    Resets the user's password using the single-use token:
      - Verifies token validity and expiration
      - Validates new password strength and matching confirmation
      - Hashes new password with generate_password_hash
      - Updates user password and unsets reset token hash and expiration
    Returns (success, message, http_status_code).
    """
    if db is None:
        db = get_db()

    is_valid, user, token_msg = verify_reset_token(raw_token, db=db)
    if not is_valid or not user:
        return False, token_msg, 400

    valid_pwd, pwd_err = validate_password_strength(new_password)
    if not valid_pwd:
        return False, pwd_err, 400

    if not confirm_password:
        return False, "Please confirm your new password.", 400

    if new_password != confirm_password:
        return False, "Passwords do not match.", 400

    new_hash = generate_password_hash(new_password)

    # Atomically update password and invalidate reset token immediately
    try:
        db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "password_hash": new_hash,
                    "password_updated_at": datetime.now(timezone.utc)
                },
                "$unset": {
                    "password_reset_token_hash": "",
                    "password_reset_expires_at": ""
                }
            }
        )
    except Exception as db_err:
        logger.error("Database update error during password reset: %s", db_err)
        return False, "Failed to update password due to a database error. Please try again.", 500

    logger.info("Password successfully reset and reset token invalidated.")
    return True, "Your password has been successfully reset. Please log in with your new password.", 200


def cleanup_expired_reset_tokens(db=None) -> int:
    """Removes expired reset tokens from users collection."""
    if db is None:
        db = get_db()
    now = datetime.now(timezone.utc)
    res = db.users.update_many(
        {"password_reset_expires_at": {"$lt": now}},
        {"$unset": {"password_reset_token_hash": "", "password_reset_expires_at": ""}}
    )
    return getattr(res, "modified_count", 0)
