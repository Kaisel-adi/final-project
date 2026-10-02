import pytest
from bson import ObjectId
from app.reports.services import create_report, upvote_report, haversine_distance_km
from app.auth.models import User
from app import create_app
from app.config import TestConfig


def test_create_report_success(mock_db):
    author = User.create(name="Author", email="author@example.com", password="pwd", db=mock_db)
    coords = [77.190, 28.650]
    
    report = create_report(
        author_id=author.id,
        category="pothole",
        description="Dangerous large pothole in middle of road.",
        photo_url="https://example.com/test.jpg",
        coordinates=coords,
        db=mock_db
    )
    
    assert report["category"] == "pothole"
    assert report["status"] == "Reported"
    assert report["upvote_count"] == 0
    assert report["location"]["coordinates"] == coords
    assert len(report["status_log"]) == 1


def test_create_report_validation_errors(mock_db):
    author = User.create(name="Author", email="author2@example.com", password="pwd", db=mock_db)
    
    # Invalid category
    with pytest.raises(ValueError, match="Invalid category"):
        create_report(author.id, "invalid_cat", "Short desc text here", "url", [77.0, 28.0], db=mock_db)

    # Too short description
    with pytest.raises(ValueError, match="at least 10 characters"):
        create_report(author.id, "pothole", "tiny", "url", [77.0, 28.0], db=mock_db)

    # Invalid coordinates
    with pytest.raises(ValueError, match="Invalid coordinate range"):
        create_report(author.id, "pothole", "Valid description here...", "url", [200.0, 100.0], db=mock_db)


def test_author_cannot_upvote_own_report(mock_db):
    author = User.create(name="Author", email="selfvote@example.com", password="pwd", db=mock_db)
    report = create_report(author.id, "garbage", "Garbage dumped outside gate", "url", [77.19, 28.65], db=mock_db)

    with pytest.raises(ValueError, match="Authors cannot upvote their own report"):
        upvote_report(str(report["_id"]), author, db=mock_db)


def test_upvote_and_status_threshold_flip(mock_db):
    app = create_app(TestConfig)
    with app.app_context():
        author = User.create(name="Author", email="author3@example.com", password="pwd", db=mock_db)
        report = create_report(author.id, "pothole", "Huge road pothole near junction", "url", [77.19, 28.65], db=mock_db)
        rep_id_str = str(report["_id"])

        # Create 9 distinct residents and upvote
        for i in range(1, 10):
            voter = User.create(name=f"Voter {i}", email=f"voter{i}@example.com", password="pwd",
                                home_coords=[77.191, 28.651], db=mock_db)
            res = upvote_report(rep_id_str, voter, db=mock_db)
            assert res["success"] is True
            assert res["upvote_count"] == i
            assert res["status"] == "Reported"

        # 10th upvote should trigger threshold flip to "Verified"
        tenth_voter = User.create(name="Voter 10", email="voter10@example.com", password="pwd",
                                  home_coords=[77.192, 28.652], db=mock_db)
        res10 = upvote_report(rep_id_str, tenth_voter, db=mock_db)
        assert res10["upvote_count"] == 10
        assert res10["status"] == "Verified"

        # Check DB reflects Verified status
        updated_rep = mock_db.reports.find_one({"_id": report["_id"]})
        assert updated_rep["status"] == "Verified"
        assert updated_rep["upvote_count"] == 10
        assert len(updated_rep["status_log"]) == 2


def test_proximity_soft_check(mock_db):
    app = create_app(TestConfig)
    with app.app_context():
        author = User.create(name="Author", email="author4@example.com", password="pwd", db=mock_db)
        # Report in Karol Bagh Delhi
        report = create_report(author.id, "pothole", "Pothole in Karol Bagh", "url", [77.190, 28.650], db=mock_db)

        # Voter 1 is nearby (< 1km away in Karol Bagh)
        nearby_voter = User.create(name="Near Voter", email="near@example.com", password="pwd",
                                   home_coords=[77.195, 28.652], db=mock_db)
        res_near = upvote_report(str(report["_id"]), nearby_voter, db=mock_db)
        assert res_near["is_distance_flagged"] is False

        # Voter 2 is far away (> 20km away in Greater Noida)
        far_voter = User.create(name="Far Voter", email="far@example.com", password="pwd",
                                home_coords=[77.500, 28.450], db=mock_db)
        res_far = upvote_report(str(report["_id"]), far_voter, db=mock_db)
        # Soft check: vote is accepted (success is True) but flagged for distance!
        assert res_far["success"] is True
        assert res_far["is_distance_flagged"] is True


def test_feed_and_view_liked_state_distinction(client, mock_db):
    author = User.create(name="Author User", email="author_state@example.com", password="pwd", db=mock_db)
    voter = User.create(name="Voter User", email="voter_state@example.com", password="pwd",
                        home_coords=[77.200, 28.610], db=mock_db)

    rep1 = create_report(author.id, "pothole", "Pothole in Block A", "https://img.local/1.jpg", [77.201, 28.611], db=mock_db)
    rep2 = create_report(author.id, "garbage", "Garbage on Block B", "https://img.local/2.jpg", [77.202, 28.612], db=mock_db)

    # Voter upvotes rep1 only
    upvote_report(str(rep1["_id"]), voter, db=mock_db)

    # Log in as voter
    with client.session_transaction() as sess:
        sess["_user_id"] = voter.id

    # 1. Feed page rendering
    res_feed = client.get("/feed?view=list")
    assert res_feed.status_code == 200
    feed_html = res_feed.get_data(as_text=True)

    # Rep1 card should clearly be marked as liked/upvoted
    assert f'data-report-id="{rep1["_id"]}"' in feed_html
    assert 'is-liked' in feed_html
    assert 'data-has-upvoted="true"' in feed_html
    assert 'favorite' in feed_html

    # Rep2 card should be unliked
    assert f'data-report-id="{rep2["_id"]}"' in feed_html
    assert 'data-has-upvoted="false"' in feed_html
    assert 'favorite_border' in feed_html

    # 2. Infinite scroll chunk API (/feed/api/chunk)
    res_chunk = client.get("/feed/api/chunk?offset=0&limit=10")
    assert res_chunk.status_code == 200
    chunk_json = res_chunk.get_json()
    assert chunk_json["success"] is True
    chunk_html = chunk_json["html"]

    assert f'data-report-id="{rep1["_id"]}"' in chunk_html
    assert 'data-has-upvoted="true"' in chunk_html
    assert f'data-report-id="{rep2["_id"]}"' in chunk_html
    assert 'data-has-upvoted="false"' in chunk_html

    # 3. Report details view for liked report
    res_view1 = client.get(f"/reports/{rep1['_id']}")
    assert res_view1.status_code == 200
    view1_html = res_view1.get_data(as_text=True)
    assert "You have verified & upvoted this civic issue." in view1_html

    # 4. Report details view for unliked report
    res_view2 = client.get(f"/reports/{rep2['_id']}")
    assert res_view2.status_code == 200
    view2_html = res_view2.get_data(as_text=True)
    assert "Upvote & Verify Incident" in view2_html


def test_removed_report_behavior(client, mock_db):
    author = User.create(name="Author", email="rep_author@civic.test", password="pwd", db=mock_db)
    viewer = User.create(name="Viewer", email="rep_viewer@civic.test", password="pwd", db=mock_db)

    rep = create_report(
        author_id=author.id,
        category="pothole",
        description="Hazardous pothole on bridge",
        photo_url="https://example.com/pothole.jpg",
        coordinates=[77.20, 28.60],
        db=mock_db
    )
    rep_id = str(rep["_id"])

    # Simulate admin permanently removing report
    mock_db.reports.delete_one({"_id": rep["_id"]})

    # 1. Visiting details page of removed report redirects to feed
    res_view = client.get(f"/reports/{rep_id}")
    assert res_view.status_code == 302
    assert "/feed" in res_view.headers["Location"]

    # Login as viewer
    with client.session_transaction() as sess:
        sess["_user_id"] = viewer.id

    ajax_headers = {"X-Requested-With": "XMLHttpRequest"}

    # 2. Trying to upvote removed report returns 404 with not_found=True
    res_upvote = client.post(f"/reports/{rep_id}/upvote", headers=ajax_headers)
    assert res_upvote.status_code == 404
    data_upvote = res_upvote.get_json()
    assert data_upvote["not_found"] is True
    assert "/feed" in data_upvote["redirect_url"]

    # 3. Trying to comment on removed report returns 404 with not_found=True
    res_comment = client.post(f"/reports/{rep_id}/comments", data={"comment": "Still an issue!"}, headers=ajax_headers)
    assert res_comment.status_code == 404
    data_comment = res_comment.get_json()
    assert data_comment["not_found"] is True
    assert "/feed" in data_comment["redirect_url"]

    # 4. Trying to flag removed report redirects to feed
    res_flag = client.post(f"/reports/{rep_id}/flag", data={"reason": "Spam"}, headers=ajax_headers)
    assert res_flag.status_code == 404
    data_flag = res_flag.get_json()
    assert data_flag["not_found"] is True


