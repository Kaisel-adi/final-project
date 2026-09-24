import pytest
from app.auth.models import User
from app.reports.services import create_report


def test_admin_dashboard_conditional_classes(client, mock_db):
    admin = User.create(name="Admin User", email="admin@civic.test", password="adminpass", role="admin", db=mock_db)
    resident = User.create(name="Resident User", email="resident@civic.test", password="respass", role="resident", db=mock_db)

    # Login as admin
    with client.session_transaction() as sess:
        sess["_user_id"] = admin.id

    # Test all_reports tab
    res = client.get("/admin/?tab=all_reports")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "stat-tab-card active-primary" in html
    assert "badge badge-admin" in html

    # Test verified tab
    res = client.get("/admin/?tab=verified")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "stat-tab-card active-success" in html

    # Test complaints tab
    res = client.get("/admin/?tab=complaints")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "stat-tab-card active-blue" in html

    # Test users tab
    res = client.get("/admin/?tab=users")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "stat-tab-card active-slate" in html
    assert "user-row " in html
    assert "badge badge-resident" in html

    # Ban resident and verify row-banned class
    from bson import ObjectId
    mock_db.users.update_one({"_id": ObjectId(resident.id)}, {"$set": {"is_banned": True}})
    res = client.get("/admin/?tab=users")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "user-row row-banned" in html

    # Test flagged tab
    res = client.get("/admin/?tab=flagged")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "stat-tab-card active-danger" in html


def test_report_progress_bar_conditional_classes(client, mock_db):
    author = User.create(name="Author", email="author@civic.test", password="pass", db=mock_db)
    
    # Report with 0 upvotes
    rep = create_report(
        author_id=author.id,
        category="pothole",
        description="Dangerous road crater needing fix.",
        photo_url="https://example.com/crater.jpg",
        coordinates=[77.20, 28.60],
        db=mock_db
    )

    res = client.get(f"/reports/{rep['_id']}")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "progress-bar-track" in html
    assert "progress-bar-fill fill-primary" in html

    # Update report to have 10 upvotes
    mock_db.reports.update_one({"_id": rep["_id"]}, {"$set": {"upvote_count": 10}})
    res = client.get(f"/reports/{rep['_id']}")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "progress-bar-track" in html
    assert "progress-bar-fill fill-success" in html
