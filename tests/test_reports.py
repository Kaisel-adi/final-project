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
