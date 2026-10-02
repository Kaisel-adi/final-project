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


def test_admin_ajax_actions(client, mock_db):
    from bson import ObjectId
    admin = User.create(name="Super Admin", email="superadmin@civic.test", password="adminpassword", role="admin", db=mock_db)
    target_user = User.create(name="Target User", email="target@civic.test", password="userpassword", role="resident", db=mock_db)
    
    rep = create_report(
        author_id=target_user.id,
        category="garbage",
        description="Piled garbage at market square.",
        photo_url="https://example.com/garbage.jpg",
        coordinates=[77.21, 28.61],
        db=mock_db
    )
    # Flag the report
    mock_db.reports.update_one({"_id": rep["_id"]}, {"$set": {"is_flagged": True}})

    # Login as admin
    with client.session_transaction() as sess:
        sess["_user_id"] = admin.id

    ajax_headers = {"X-Requested-With": "XMLHttpRequest"}

    # 1. AJAX verify report
    res_verify = client.post(f"/admin/reports/{rep['_id']}/verify", headers=ajax_headers)
    assert res_verify.status_code == 200
    data_verify = res_verify.get_json()
    assert data_verify["success"] is True
    assert data_verify["status"] == "Verified"
    db_rep = mock_db.reports.find_one({"_id": rep["_id"]})
    assert db_rep["status"] == "Verified"

    # 2. AJAX moderate (unflag) report
    res_mod = client.post(f"/admin/reports/{rep['_id']}/moderate", data={"action": "approve"}, headers=ajax_headers)
    assert res_mod.status_code == 200
    data_mod = res_mod.get_json()
    assert data_mod["success"] is True
    assert data_mod["action"] == "approve"
    db_rep = mock_db.reports.find_one({"_id": rep["_id"]})
    assert db_rep.get("is_flagged") is False

    # 3. AJAX change user role
    res_role = client.post(f"/admin/users/{target_user.id}/role", data={"role": "moderator"}, headers=ajax_headers)
    assert res_role.status_code == 200
    data_role = res_role.get_json()
    assert data_role["success"] is True
    assert data_role["new_role"] == "moderator"
    db_user = mock_db.users.find_one({"_id": ObjectId(target_user.id)})
    assert db_user["role"] == "moderator"

    # 4. AJAX toggle user ban
    res_ban = client.post(f"/admin/users/{target_user.id}/ban", headers=ajax_headers)
    assert res_ban.status_code == 200
    data_ban = res_ban.get_json()
    assert data_ban["success"] is True
    assert data_ban["is_banned"] is True
    db_user = mock_db.users.find_one({"_id": ObjectId(target_user.id)})
    assert db_user["is_banned"] is True

    # 5. AJAX remove report
    res_rm = client.post(f"/admin/reports/{rep['_id']}/remove", headers=ajax_headers)
    assert res_rm.status_code == 200
    data_rm = res_rm.get_json()
    assert data_rm["success"] is True
    assert data_rm["status"] == "Removed"
    db_rep = mock_db.reports.find_one({"_id": rep["_id"]})
    assert db_rep is None

