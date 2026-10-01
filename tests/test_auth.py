import pytest
from app.auth.models import User
from app import create_app
from app.config import TestConfig


def test_user_creation_and_password_check(mock_db):
    user = User.create(
        name="Test User",
        email="test@example.com",
        password="secretpassword",
        home_coords=[77.190, 28.650],
        db=mock_db
    )
    assert user.name == "Test User"
    assert user.email == "test@example.com"
    assert user.check_password("secretpassword") is True
    assert user.check_password("wrongpassword") is False
    assert user.home_location["coordinates"] == [77.190, 28.650]


def test_duplicate_email_rejected(mock_db):
    User.create(name="User 1", email="dup@example.com", password="pwd", db=mock_db)
    with pytest.raises(ValueError, match="already exists"):
        User.create(name="User 2", email="dup@example.com", password="pwd", db=mock_db)


def test_user_lookup(mock_db):
    user = User.create(name="Find Me", email="findme@example.com", password="pwd", db=mock_db)
    found_by_email = User.get_by_email("findme@example.com", db=mock_db)
    assert found_by_email is not None
    assert found_by_email.id == user.id

    found_by_id = User.get_by_id(user.id, db=mock_db)
    assert found_by_id is not None
    assert found_by_id.email == "findme@example.com"


def test_user_roles(mock_db):
    resident = User.create(name="Res", email="res@example.com", password="pwd", role="resident", db=mock_db)
    admin = User.create(name="Admin", email="admin@example.com", password="pwd", role="admin", db=mock_db)
    
    assert resident.is_moderator is False
    assert resident.is_admin is False
    assert admin.is_moderator is True
    assert admin.is_admin is True


def test_login_ui_elements(client):
    res = client.get("/auth/login")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Password eye toggle button
    assert 'id="toggle-password"' in html
    assert 'id="toggle-password-icon"' in html
    assert 'visibility' in html

    # Mandatory red asterisks
    assert 'Email Address <span class="text-rose-500 font-bold ml-0.5" aria-hidden="true">*</span>' in html
    assert 'Password <span class="text-rose-500 font-bold ml-0.5" aria-hidden="true">*</span>' in html

    # Translucent CTA button (btn-cta-auth & bg-emerald-600/85)
    assert 'btn-cta-auth' in html
    assert 'bg-emerald-600/85' in html

    # Interactive validation script
    assert 'border-rose-500' in html


def test_register_ui_elements(client):
    res = client.get("/auth/register")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Password eye toggle button
    assert 'id="toggle-password"' in html
    assert 'id="toggle-password-icon"' in html
    assert 'visibility' in html

    # Mandatory red asterisks for Name, Email, Password
    assert 'Full Name <span class="text-rose-500 font-bold ml-0.5" aria-hidden="true">*</span>' in html
    assert 'Email Address <span class="text-rose-500 font-bold ml-0.5" aria-hidden="true">*</span>' in html
    assert 'Password <span class="text-rose-500 font-bold ml-0.5" aria-hidden="true">*</span>' in html

    # Translucent CTA button
    assert 'btn-cta-auth' in html
    assert 'bg-emerald-600/85' in html

    # Interactive validation script
    assert 'border-rose-500' in html


def test_verify_otp_ui_elements(client):
    res = client.get("/auth/verify-otp?email=citizen@example.com")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Mandatory red asterisk for OTP
    assert 'Enter 6-Digit Code <span class="text-rose-500 font-bold ml-0.5" aria-hidden="true">*</span>' in html

    # Translucent CTA button
    assert 'btn-cta-auth' in html
    assert 'bg-emerald-600/85' in html

    # Interactive validation script
    assert 'border-rose-500' in html

