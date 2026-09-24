import pytest
from app.auth.validators import validate_email_format
from app.auth.models import User
from app.auth.services import generate_otp, stage_pending_signup, verify_and_complete_signup


def test_validate_email_format():
    # Valid emails
    assert validate_email_format("resident@example.com") is True
    assert validate_email_format("user.name+civic@delhi.gov.in") is True
    assert validate_email_format("a@b.co") is True

    # Invalid emails
    assert validate_email_format("") is False
    assert validate_email_format(None) is False
    assert validate_email_format("notanemail") is False
    assert validate_email_format("user@") is False
    assert validate_email_format("@domain.com") is False
    assert validate_email_format("user@domain") is False
    assert validate_email_format("user..double@domain.com") is False
    assert validate_email_format("user @domain.com") is False
    assert validate_email_format("user@ domain.com") is False


def test_login_email_validation(client):
    # Invalid email format on login rejected
    res = client.post("/auth/login", data={"email": "invalid-email-format", "password": "anypassword"}, follow_redirects=True)
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Please enter a valid email address." in html


def test_register_email_validation(client):
    # Invalid email format on register rejected
    res = client.post("/auth/register", data={
        "name": "Test User",
        "email": "not-an-email",
        "password": "validpassword123"
    }, follow_redirects=True)
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Please enter a valid email address." in html


def test_full_otp_signup_workflow(client, mock_db):
    email = "citizen@delhi.org"

    # Step 1: Submit valid registration
    res = client.post("/auth/register", data={
        "name": "Civic Citizen",
        "email": email,
        "password": "securepassword123",
        "home_lat": "28.6139",
        "home_lon": "77.2090",
        "digest_opt_in": "on",
        "digest_radius_km": "5.0"
    }, follow_redirects=False)

    assert res.status_code == 302
    assert "/auth/verify-otp" in res.headers["Location"]

    # Verify pending signup in database
    pending = mock_db.pending_signups.find_one({"email": email})
    assert pending is not None
    assert pending["name"] == "Civic Citizen"
    assert len(pending["otp"]) == 6
    assert pending["otp"].isdigit()
    assert pending["password_hash"] != "securepassword123"  # Securely hashed
    otp_code = pending["otp"]

    # Verify user is NOT yet in active users collection
    assert mock_db.users.find_one({"email": email}) is None

    # Step 2: Try submitting wrong OTP
    res_wrong = client.post("/auth/verify-otp", data={
        "email": email,
        "otp": "000000" if otp_code != "000000" else "999999"
    }, follow_redirects=True)
    assert res_wrong.status_code == 200
    html_wrong = res_wrong.get_data(as_text=True)
    assert "Invalid verification code" in html_wrong
    assert mock_db.users.find_one({"email": email}) is None

    # Step 3: Submit correct OTP
    res_correct = client.post("/auth/verify-otp", data={
        "email": email,
        "otp": otp_code
    }, follow_redirects=True)
    assert res_correct.status_code == 200
    html_correct = res_correct.get_data(as_text=True)
    assert "Email verified successfully" in html_correct

    # Verify user now created in db.users
    user = mock_db.users.find_one({"email": email})
    assert user is not None
    assert user["name"] == "Civic Citizen"
    assert user["email_verified"] is True
    assert user["home_location"]["coordinates"] == [77.2090, 28.6139]

    # Verify pending record was cleaned up
    assert mock_db.pending_signups.find_one({"email": email}) is None


def test_resend_otp_generates_new_code(app, client, mock_db):
    email = "resenduser@delhi.org"
    with app.app_context():
        stage_pending_signup(name="Resend User", email=email, password="password123", db=mock_db)

    pending_initial = mock_db.pending_signups.find_one({"email": email})
    initial_otp = pending_initial["otp"]

    # Trigger resend with session
    with client.session_transaction() as sess:
        sess["pending_signup_email"] = email

    # Advance time slightly to bypass cooldown
    import datetime
    mock_db.pending_signups.update_one(
        {"email": email},
        {"$set": {"last_sent_at": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=40)}}
    )

    res = client.post("/auth/resend-otp", data={"email": email}, follow_redirects=True)
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "A new 6-digit verification code has been sent" in html

    pending_updated = mock_db.pending_signups.find_one({"email": email})
    assert len(pending_updated["otp"]) == 6
    assert pending_updated["otp"].isdigit()
