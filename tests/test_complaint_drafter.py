import pytest
from app.auth.models import User
from app.reports.services import create_report
from scripts.etl_boundaries import seed_database


def test_complaint_locked_when_reported(app, client, mock_db):
    seed_database(mock_db)
    author = User.create(name="Author", email="drafter1@example.com", password="pwd", db=mock_db)
    report = create_report(author.id, "pothole", "Pothole needing complaint", "url", [77.19, 28.65], db=mock_db)

    with client.session_transaction() as sess:
        sess["_user_id"] = str(author.id)

    # Access complaint draft for unverified report (status: Reported)
    response = client.get(f"/complaints/{report['_id']}")
    # Must redirect back to report view
    assert response.status_code == 302
    assert f"/reports/{report['_id']}" in response.headers["Location"]


def test_complaint_unlocked_when_verified(app, client, mock_db):
    seed_database(mock_db)
    author = User.create(name="Author", email="drafter2@example.com", password="pwd", db=mock_db)
    report = create_report(author.id, "pothole", "Pothole needing complaint", "url", [77.19, 28.65], db=mock_db)

    # Transition report status to Verified
    mock_db.reports.update_one({"_id": report["_id"]}, {"$set": {"status": "Verified", "upvote_count": 10}})

    with client.session_transaction() as sess:
        sess["_user_id"] = str(author.id)

    response = client.get(f"/complaints/{report['_id']}")
    assert response.status_code == 200
    content = response.data.decode("utf-8")
    assert "Official Complaint Draft" in content
    assert "dc-karolbagh@mcd.nic.in" in content
    assert "mailto:" in content


def test_mark_complaint_sent(app, client, mock_db):
    author = User.create(name="Author", email="drafter3@example.com", password="pwd", db=mock_db)
    report = create_report(author.id, "pothole", "Pothole needing complaint", "url", [77.19, 28.65], db=mock_db)
    mock_db.reports.update_one({"_id": report["_id"]}, {"$set": {"status": "Verified", "upvote_count": 10}})

    with client.session_transaction() as sess:
        sess["_user_id"] = str(author.id)

    response = client.post(f"/complaints/{report['_id']}/mark_sent")
    assert response.status_code == 302

    updated = mock_db.reports.find_one({"_id": report["_id"]})
    assert updated["status"] == "Complained"
    assert len(updated["status_log"]) == 2
