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
