import pytest
from datetime import datetime, timezone, timedelta
from app.auth.models import User
from app.reports.services import create_report


def test_digest_token_authorization(app, client, mock_db):
    # Without token
    res_no_token = client.post("/jobs/digest")
    assert res_no_token.status_code == 401

    # With invalid token
    res_bad_token = client.post("/jobs/digest", headers={"X-Job-Token": "bad-token"})
    assert res_bad_token.status_code == 401

    # With valid token
    valid_token = app.config.get("CRON_SECRET_TOKEN", "gcir-dev-cron-token-xyz")
    res_valid = client.post("/jobs/digest", headers={"X-Job-Token": valid_token})
    assert res_valid.status_code == 200


def test_digest_matching_and_exclusions(app, client, mock_db):
    # User 1 (Author)
    user1 = User.create(name="Author", email="u1@example.com", password="pwd",
                        home_coords=[77.190, 28.650], digest_opt_in=True, db=mock_db)
    
    # User 2 (Nearby neighbor)
    user2 = User.create(name="Neighbor", email="u2@example.com", password="pwd",
                        home_coords=[77.192, 28.651], digest_opt_in=True, digest_radius_km=3.0, db=mock_db)

    # User 3 (Far away, 30km away in Greater Noida)
    user3 = User.create(name="Far Resident", email="u3@example.com", password="pwd",
                        home_coords=[77.500, 28.450], digest_opt_in=True, digest_radius_km=3.0, db=mock_db)

    # Issue created by User 1 in Karol Bagh
    report = create_report(user1.id, "garbage", "Garbage on road corner", "url", [77.190, 28.650], db=mock_db)

    valid_token = app.config.get("CRON_SECRET_TOKEN", "gcir-dev-cron-token-xyz")
    res = client.post("/jobs/digest", headers={"X-Job-Token": valid_token})
    assert res.status_code == 200
    data = res.get_json()

    # Should notify user2, but NOT user1 (author) and NOT user3 (too far away)
    assert data["users_notified"] == 1
    assert data["emails_dispatched"] == 1

    # Verify digest_log was written
    log_entry = mock_db.digest_log.find_one({"user_id": user2.doc["_id"]})
    assert log_entry is not None
    assert report["_id"] in log_entry["report_ids"]

    # Run digest again immediately: duplicate suppression should result in 0 new emails!
    res_repeat = client.post("/jobs/digest", headers={"X-Job-Token": valid_token})
    data_repeat = res_repeat.get_json()
    assert data_repeat["emails_dispatched"] == 0
