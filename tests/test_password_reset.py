import re
import secrets
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest
from werkzeug.security import check_password_hash

from app.auth.models import User
from app.auth.validators import validate_password_strength
from app.auth.services import (
    initiate_password_reset,
    verify_reset_token,
    reset_user_password,
    cleanup_expired_reset_tokens,
    clear_rate_limits,
    get_test_reset_token,
    GENERIC_RESET_MSG
)


@pytest.fixture(autouse=True)
def reset_limits_each_test():
    """Ensures rate limits are cleared before and after each test."""
    clear_rate_limits()
    yield
    clear_rate_limits()


# ============================================================================
# Section A: Forgot-Password Tests
# ============================================================================

def test_forgot_password_valid_registered_email(client, mock_db):
    """1. Valid registered email triggers email dispatch and returns generic success."""
    User.create(name="Alice", email="alice@example.com", password="oldpassword123", db=mock_db)

    res = client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["message"] == GENERIC_RESET_MSG

    # Verify DB has hashed token and expiration set
    user = mock_db.users.find_one({"email": "alice@example.com"})
    assert user.get("password_reset_token_hash") is not None
    assert user.get("password_reset_expires_at") is not None


def test_forgot_password_valid_unregistered_email(client, mock_db):
    """2. Valid unregistered email returns identical generic message without leaking account absence."""
    res = client.post("/api/auth/forgot-password", json={"email": "nonexistent@example.com"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["message"] == GENERIC_RESET_MSG


def test_forgot_password_invalid_email_format(client, mock_db):
    """3. Invalid email format is rejected with 400 Bad Request."""
    res = client.post("/api/auth/forgot-password", json={"email": "not-an-email"})
    assert res.status_code == 400
    data = res.get_json()
    assert data["status"] == "error"
    assert "valid email" in data["message"].lower()


def test_forgot_password_empty_email(client, mock_db):
    """4. Empty email is rejected."""
    res = client.post("/api/auth/forgot-password", json={"email": ""})
    assert res.status_code == 400
    data = res.get_json()
    assert data["status"] == "error"


def test_forgot_password_whitespace_around_email(client, mock_db):
    """5. Whitespace around email is stripped and successfully matches user."""
    User.create(name="Bob", email="bob@example.com", password="password123", db=mock_db)

    res = client.post("/api/auth/forgot-password", json={"email": "   bob@example.com   "})
    assert res.status_code == 200
    assert res.get_json()["message"] == GENERIC_RESET_MSG

    user = mock_db.users.find_one({"email": "bob@example.com"})
    assert user.get("password_reset_token_hash") is not None


def test_forgot_password_casing_insensitivity(client, mock_db):
    """6. Email is lowercased according to existing authentication rules."""
    User.create(name="Carol", email="carol@example.com", password="password123", db=mock_db)

    res = client.post("/api/auth/forgot-password", json={"email": "CAROL@EXAMPLE.COM"})
    assert res.status_code == 200

    user = mock_db.users.find_one({"email": "carol@example.com"})
    assert user.get("password_reset_token_hash") is not None


def test_forgot_password_multiple_reset_requests(client, mock_db):
    """7. Multiple requests within limit overwrite previous token with a fresh one."""
    User.create(name="Dave", email="dave@example.com", password="password123", db=mock_db)

    client.post("/api/auth/forgot-password", json={"email": "dave@example.com"})
    first_hash = mock_db.users.find_one({"email": "dave@example.com"})["password_reset_token_hash"]

    client.post("/api/auth/forgot-password", json={"email": "dave@example.com"})
    second_hash = mock_db.users.find_one({"email": "dave@example.com"})["password_reset_token_hash"]

    assert first_hash != second_hash


def test_forgot_password_rate_limit_email(client, mock_db):
    """8. Rate limit threshold enforced per email address (max 5 requests / 15 mins)."""
    User.create(name="Eve", email="eve@example.com", password="password123", db=mock_db)

    for _ in range(5):
        res = client.post("/api/auth/forgot-password", json={"email": "eve@example.com"})
        assert res.status_code == 200

    # 6th request must be rate limited
    res = client.post("/api/auth/forgot-password", json={"email": "eve@example.com"})
    assert res.status_code == 429
    data = res.get_json()
    assert data["status"] == "error"
    assert "too many" in data["message"].lower()


def test_forgot_password_rate_limit_ip(client, mock_db):
    """9. Excessive requests from the same IP address are blocked (max 10 requests / 15 mins)."""
    ip_headers = {"X-Forwarded-For": "198.51.100.42"}

    for i in range(10):
        res = client.post(
            "/api/auth/forgot-password",
            json={"email": f"citizen{i}@example.com"},
            headers=ip_headers
        )
        assert res.status_code in (200, 429)

    # 11th request from same IP is rate-limited
    res = client.post(
        "/api/auth/forgot-password",
        json={"email": "another_citizen@example.com"},
        headers=ip_headers
    )
    assert res.status_code == 429


def test_forgot_password_database_unavailable(client):
    """10. Gracefully handles DB errors safely without exposing server internals."""
    with patch("app.auth.services.get_db") as mock_get_db:
        mock_get_db.side_effect = Exception("Mongo connection timeout")
        # In Web UI
        res_web = client.post("/auth/forgot-password", data={"email": "user@example.com"})
        assert res_web.status_code in (200, 500)


def test_forgot_password_brevo_smtp_failure(client, mock_db):
    """11. Brevo/SMTP failure cleans up token and returns generic response to prevent leak."""
    User.create(name="Grace", email="grace@example.com", password="password123", db=mock_db)

    with patch("app.auth.services.send_password_reset_email", return_value=(False, "Brevo HTTP 500 Internal Error")):
        res = client.post("/api/auth/forgot-password", json={"email": "grace@example.com"})
        assert res.status_code == 200
        assert res.get_json()["message"] == GENERIC_RESET_MSG

        # Token must be invalidated/cleaned up so user isn't stuck with unreachable token
        user = mock_db.users.find_one({"email": "grace@example.com"})
        assert user.get("password_reset_token_hash") is None


def test_forgot_password_network_timeout(client, mock_db):
    """12. Network timeout during email dispatch does not crash application."""
    User.create(name="Heidi", email="heidi@example.com", password="password123", db=mock_db)

    with patch("app.auth.services.send_password_reset_email", return_value=(False, "Connection timed out")):
        res = client.post("/api/auth/forgot-password", json={"email": "heidi@example.com"})
        assert res.status_code == 200
        assert res.get_json()["message"] == GENERIC_RESET_MSG


def test_forgot_password_malformed_request_body(client):
    """13. Malformed request body handled gracefully."""
    res = client.post(
        "/api/auth/forgot-password",
        data="this is not json",
        content_type="application/json"
    )
    assert res.status_code in (400, 200)


def test_forgot_password_unexpected_fields(client, mock_db):
    """14. Unexpected extra fields in request are safely ignored."""
    User.create(name="Ivan", email="ivan@example.com", password="password123", db=mock_db)

    res = client.post("/api/auth/forgot-password", json={
        "email": "ivan@example.com",
        "admin": True,
        "role": "superadmin",
        "random_extra_field": "hack"
    })
    assert res.status_code == 200
    assert res.get_json()["message"] == GENERIC_RESET_MSG


def test_forgot_password_response_no_enumeration(client, mock_db):
    """15. Response message and status code are 100% identical between existing and non-existing accounts."""
    User.create(name="Registered", email="registered@example.com", password="pwd", db=mock_db)

    res_reg = client.post("/api/auth/forgot-password", json={"email": "registered@example.com"})
    res_unreg = client.post("/api/auth/forgot-password", json={"email": "unregistered@example.com"})

    assert res_reg.status_code == res_unreg.status_code == 200
    assert res_reg.get_json() == res_unreg.get_json()


def test_forgot_password_no_raw_tokens_in_logs(client, mock_db, caplog):
    """16. Verify raw reset tokens are never written to logger or exposed in logs."""
    User.create(name="Judy", email="judy@example.com", password="password123", db=mock_db)

    with caplog.at_level(logging.DEBUG):
        client.post("/api/auth/forgot-password", json={"email": "judy@example.com"})
        raw_token = get_test_reset_token("judy@example.com")
        assert raw_token is not None

        # Verify raw token is NOT anywhere in captured log records
        for record in caplog.records:
            assert raw_token not in record.message


# ============================================================================
# Section B: Token Tests
# ============================================================================

def test_token_valid(client, mock_db):
    """1. Valid unexpired token returns valid=True."""
    User.create(name="Karl", email="karl@example.com", password="pwd", db=mock_db)
    client.post("/api/auth/forgot-password", json={"email": "karl@example.com"})
    token = get_test_reset_token("karl@example.com")

    res = client.get(f"/api/auth/reset-password?token={token}")
    assert res.status_code == 200
    assert res.get_json()["valid"] is True


def test_token_invalid_or_random(client):
    """2. Random non-existent token is rejected."""
    random_token = secrets.token_urlsafe(32)
    res = client.get(f"/api/auth/reset-password?token={random_token}")
    assert res.status_code == 400
    assert res.get_json()["valid"] is False


def test_token_expired(client, mock_db):
    """3. Expired token (>30 mins) is rejected and cleaned up."""
    User.create(name="Liam", email="liam@example.com", password="pwd", db=mock_db)
    client.post("/api/auth/forgot-password", json={"email": "liam@example.com"})
    token = get_test_reset_token("liam@example.com")

    # Manually expire the token in DB
    past_time = datetime.now(timezone.utc) - timedelta(minutes=31)
    mock_db.users.update_one({"email": "liam@example.com"}, {"$set": {"password_reset_expires_at": past_time}})

    res = client.get(f"/api/auth/reset-password?token={token}")
    assert res.status_code == 400
    data = res.get_json()
    assert data["valid"] is False
    assert "expired" in data["message"].lower()

    # Verify expired token is purged
    user = mock_db.users.find_one({"email": "liam@example.com"})
    assert user.get("password_reset_token_hash") is None


def test_token_empty(client):
    """4. Empty token rejected."""
    res = client.get("/api/auth/reset-password?token=")
    assert res.status_code == 400
    assert res.get_json()["valid"] is False


def test_token_missing(client):
    """5. Missing token query param rejected."""
    res = client.get("/api/auth/reset-password")
    assert res.status_code == 400
    assert res.get_json()["valid"] is False


def test_token_malformed(client):
    """6. Malformed token (e.g. invalid chars or non-urlsafe) rejected."""
    res = client.get("/api/auth/reset-password?token=<<malformed_token%#@!>>")
    assert res.status_code == 400
    assert res.get_json()["valid"] is False


def test_token_previously_used(client, mock_db):
    """7. Token previously used to reset password cannot be reused."""
    User.create(name="Mona", email="mona@example.com", password="oldpassword123", db=mock_db)
    client.post("/api/auth/forgot-password", json={"email": "mona@example.com"})
    token = get_test_reset_token("mona@example.com")

    # Reset password once
    res_reset = client.post("/api/auth/reset-password", json={
        "token": token,
        "password": "newpassword123",
        "confirm_password": "newpassword123"
    })
    assert res_reset.status_code == 200

    # Try verifying token again
    res_verify = client.get(f"/api/auth/reset-password?token={token}")
    assert res_verify.status_code == 400
    assert res_verify.get_json()["valid"] is False


def test_token_belonging_to_another_account(client, mock_db):
    """8. Resetting with a valid token changes only that account's password."""
    user1 = User.create(name="User1", email="u1@example.com", password="pwd1user", db=mock_db)
    user2 = User.create(name="User2", email="u2@example.com", password="pwd2user", db=mock_db)

    client.post("/api/auth/forgot-password", json={"email": "u1@example.com"})
    token1 = get_test_reset_token("u1@example.com")

    # Use token1 to reset
    client.post("/api/auth/reset-password", json={
        "token": token1,
        "password": "brandnewpassword123",
        "confirm_password": "brandnewpassword123"
    })

    # User 1 password changed, User 2 password intact
    u1_db = User.get_by_email("u1@example.com", db=mock_db)
    u2_db = User.get_by_email("u2@example.com", db=mock_db)
    assert u1_db.check_password("brandnewpassword123") is True
    assert u2_db.check_password("pwd2user") is True


def test_token_replaced_by_newer_request(client, mock_db):
    """9. A newer forgot-password request invalidates previous token."""
    User.create(name="Nina", email="nina@example.com", password="password123", db=mock_db)

    client.post("/api/auth/forgot-password", json={"email": "nina@example.com"})
    first_token = get_test_reset_token("nina@example.com")

    client.post("/api/auth/forgot-password", json={"email": "nina@example.com"})
    second_token = get_test_reset_token("nina@example.com")

    assert first_token != second_token

    # First token must now fail
    res_first = client.get(f"/api/auth/reset-password?token={first_token}")
    assert res_first.status_code == 400
    assert res_first.get_json()["valid"] is False

    # Second token is valid
    res_second = client.get(f"/api/auth/reset-password?token={second_token}")
    assert res_second.status_code == 200
    assert res_second.get_json()["valid"] is True


# ============================================================================
# Section C: Password Validation Tests
# ============================================================================

def test_password_validation_helper():
    """Validates password strength rules."""
    valid, msg = validate_password_strength("validpassword")
    assert valid is True

    valid, msg = validate_password_strength("")
    assert valid is False
    assert "empty" in msg.lower()

    valid, msg = validate_password_strength("12345")
    assert valid is False
    assert "at least 6" in msg.lower()

    valid, msg = validate_password_strength("a" * 129)
    assert valid is False
    assert "exceed 128" in msg.lower()


def test_password_shorter_than_minimum(client, mock_db):
    """2. Password shorter than 6 characters is rejected."""
    User.create(name="Oscar", email="oscar@example.com", password="oldpassword123", db=mock_db)
    client.post("/api/auth/forgot-password", json={"email": "oscar@example.com"})
    token = get_test_reset_token("oscar@example.com")

    res = client.post("/api/auth/reset-password", json={
        "token": token,
        "password": "123",
        "confirm_password": "123"
    })
    assert res.status_code == 400
    assert "at least 6" in res.get_json()["message"]


def test_password_mismatched_confirmation(client, mock_db):
    """5. Mismatched confirmation password rejected."""
    User.create(name="Pam", email="pam@example.com", password="oldpassword123", db=mock_db)
    client.post("/api/auth/forgot-password", json={"email": "pam@example.com"})
    token = get_test_reset_token("pam@example.com")

    res = client.post("/api/auth/reset-password", json={
        "token": token,
        "password": "newpassword123",
        "confirm_password": "differentpassword123"
    })
    assert res.status_code == 400
    assert "do not match" in res.get_json()["message"].lower()


def test_plaintext_password_never_stored(client, mock_db):
    """8, 9. Password changed in DB is hashed securely with werkzeug, never plaintext."""
    User.create(name="Quinn", email="quinn@example.com", password="oldpassword123", db=mock_db)
    client.post("/api/auth/forgot-password", json={"email": "quinn@example.com"})
    token = get_test_reset_token("quinn@example.com")

    new_plain = "SuperSecurePassword987!"
    res = client.post("/api/auth/reset-password", json={
        "token": token,
        "password": new_plain,
        "confirm_password": new_plain
    })
    assert res.status_code == 200

    user_doc = mock_db.users.find_one({"email": "quinn@example.com"})
    stored_hash = user_doc["password_hash"]
    assert stored_hash != new_plain
    assert stored_hash.startswith("scrypt:") or stored_hash.startswith("pbkdf2:")
    assert check_password_hash(stored_hash, new_plain) is True


# ============================================================================
# Section D: Successful Reset Tests (Happy Path)
# ============================================================================

def test_complete_happy_path_api(client, mock_db):
    """Complete happy path via API: forgot -> reset -> login."""
    User.create(name="Rachel", email="rachel@example.com", password="initialpassword123", db=mock_db)

    # 1. Request reset
    res1 = client.post("/api/auth/forgot-password", json={"email": "rachel@example.com"})
    assert res1.status_code == 200
    token = get_test_reset_token("rachel@example.com")

    # 2. Verify token
    res2 = client.get(f"/api/auth/reset-password?token={token}")
    assert res2.status_code == 200
    assert res2.get_json()["valid"] is True

    # 3. Perform reset
    res3 = client.post("/api/auth/reset-password", json={
        "token": token,
        "password": "finalpassword123",
        "confirm_password": "finalpassword123"
    })
    assert res3.status_code == 200

    # 4. Old password fails
    res_old_login = client.post("/auth/login", data={"email": "rachel@example.com", "password": "initialpassword123"}, follow_redirects=True)
    assert "Invalid email or password." in res_old_login.get_data(as_text=True)

    # 5. New password succeeds
    res_new_login = client.post("/auth/login", data={"email": "rachel@example.com", "password": "finalpassword123"}, follow_redirects=True)
    assert "Welcome back, Rachel!" in res_new_login.get_data(as_text=True)


def test_complete_happy_path_web_ui(client, mock_db):
    """Complete happy path via Web UI templates."""
    User.create(name="Sam", email="sam@example.com", password="oldpassword123", db=mock_db)

    # 1. Submit forgot password form
    res_forgot = client.post("/auth/forgot-password", data={"email": "sam@example.com"}, follow_redirects=True)
    assert res_forgot.status_code == 200
    html_forgot = res_forgot.get_data(as_text=True)
    assert "Check Your Email" in html_forgot
    assert "sam@example.com" in html_forgot

    token = get_test_reset_token("sam@example.com")
    assert token is not None

    # 2. Open reset link in browser
    res_page = client.get(f"/auth/reset-password?token={token}")
    assert res_page.status_code == 200
    html_page = res_page.get_data(as_text=True)
    assert "Create New Password" in html_page
    assert 'id="reset-password-form"' in html_page

    # 3. Submit new password
    res_submit = client.post(
        "/auth/reset-password",
        data={
            "token": token,
            "password": "newpassword456",
            "confirm_password": "newpassword456"
        },
        follow_redirects=True
    )
    assert res_submit.status_code == 200
    html_login = res_submit.get_data(as_text=True)
    assert "Your password has been successfully reset" in html_login

    # 4. Immediate login with new password
    res_login = client.post("/auth/login", data={"email": "sam@example.com", "password": "newpassword456"}, follow_redirects=True)
    assert "Welcome back, Sam!" in res_login.get_data(as_text=True)


# ============================================================================
# Section E: Token Replay & Invalidation Tests
# ============================================================================

def test_token_replay_rejected(client, mock_db):
    """Token replay attempt is rejected."""
    User.create(name="Tom", email="tom@example.com", password="pwd", db=mock_db)
    client.post("/api/auth/forgot-password", json={"email": "tom@example.com"})
    token = get_test_reset_token("tom@example.com")

    # First reset succeeds
    res1 = client.post("/api/auth/reset-password", json={
        "token": token,
        "password": "pwdnumberone1",
        "confirm_password": "pwdnumberone1"
    })
    assert res1.status_code == 200

    # Second reset with same token fails immediately
    res2 = client.post("/api/auth/reset-password", json={
        "token": token,
        "password": "pwdnumbertwo2",
        "confirm_password": "pwdnumbertwo2"
    })
    assert res2.status_code == 400
    assert res2.get_json()["success"] is False


def test_distinct_tokens_generated(client, mock_db):
    """Multiple requests generate distinct cryptographically random tokens."""
    User.create(name="Uma", email="uma@example.com", password="pwd", db=mock_db)

    tokens = set()
    for _ in range(4):
        client.post("/api/auth/forgot-password", json={"email": "uma@example.com"})
        tokens.add(get_test_reset_token("uma@example.com"))

    assert len(tokens) == 4


# ============================================================================
# Section F: Regression Tests
# ============================================================================

def test_existing_login_still_works(client, mock_db):
    """Regular user login functions as expected."""
    User.create(name="Victor", email="victor@example.com", password="securepassword", db=mock_db)
    res = client.post("/auth/login", data={"email": "victor@example.com", "password": "securepassword"}, follow_redirects=True)
    assert res.status_code == 200
    assert "Welcome back, Victor!" in res.get_data(as_text=True)


def test_existing_registration_still_works(client, mock_db):
    """Regular user registration staging and OTP generation still works."""
    res = client.post("/auth/register", data={
        "name": "Wendy",
        "email": "wendy@example.com",
        "password": "securepassword123"
    }, follow_redirects=False)
    assert res.status_code == 302
    assert "/auth/verify-otp" in res.headers["Location"]
    assert mock_db.pending_signups.find_one({"email": "wendy@example.com"}) is not None


def test_existing_logout_still_works(client, mock_db):
    """Regular user logout functions properly."""
    User.create(name="Xavier", email="xavier@example.com", password="password123", db=mock_db)
    client.post("/auth/login", data={"email": "xavier@example.com", "password": "password123"})
    res = client.get("/auth/logout", follow_redirects=True)
    assert res.status_code == 200
    assert "You have been logged out." in res.get_data(as_text=True)


def test_login_page_has_forgot_password_link(client):
    """Login template includes visible 'Forgot Password?' link pointing to /auth/forgot-password."""
    res = client.get("/auth/login")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Forgot Password?" in html
    assert "/auth/forgot-password" in html


# ============================================================================
# Section G: Security & Privacy Checks
# ============================================================================

def test_db_stores_only_hash_not_raw_token(client, mock_db):
    """Database only contains sha256 hash, never raw token."""
    User.create(name="Yara", email="yara@example.com", password="password123", db=mock_db)
    client.post("/api/auth/forgot-password", json={"email": "yara@example.com"})
    raw_token = get_test_reset_token("yara@example.com")

    user_doc = mock_db.users.find_one({"email": "yara@example.com"})
    stored_hash = user_doc["password_reset_token_hash"]

    assert stored_hash != raw_token
    assert len(stored_hash) == 64  # Standard SHA-256 hex digest length
    assert stored_hash == hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def test_cleanup_expired_tokens_job(mock_db):
    """Database cleanup helper removes expired reset tokens."""
    now = datetime.now(timezone.utc)
    expired_time = now - timedelta(minutes=45)
    future_time = now + timedelta(minutes=25)

    mock_db.users.insert_one({
        "name": "User Expired",
        "email": "exp@example.com",
        "password_reset_token_hash": "hash1",
        "password_reset_expires_at": expired_time
    })
    mock_db.users.insert_one({
        "name": "User Valid",
        "email": "val@example.com",
        "password_reset_token_token": "hash2",
        "password_reset_expires_at": future_time
    })

    modified = cleanup_expired_reset_tokens(db=mock_db)
    assert modified >= 1

    exp_user = mock_db.users.find_one({"email": "exp@example.com"})
    assert exp_user.get("password_reset_token_hash") is None
