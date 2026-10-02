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


def test_digest_embeds_report_links_and_uses_location_precedence(app, client, mock_db, monkeypatch):
    """
    Verifies that the digest job:
    1. Dispatches to opted-in users within 5km radius.
    2. Prioritizes last_login_location, falling back to home_location if null.
    3. Embeds direct report web links in the email body.
    """
    # Incident Author
    author = User.create(name="Author", email="author_digest@example.com", password="pwd",
                         home_coords=[77.2090, 28.6139], db=mock_db)

    # Opted-in user: Home is 40km away, but last_login_location is within 2km of report
    u1 = User.create(name="Mobile Citizen", email="mobile_optin@example.com", password="pwd",
                     home_coords=[77.7000, 28.1000], digest_opt_in=True, db=mock_db)
    mock_db.users.update_one(
        {"_id": u1.doc["_id"]},
        {"$set": {"last_login_location": {"type": "Point", "coordinates": [77.2200, 28.6140]}}}
    )

    # Opted-out user within 1km (should NOT be emailed)
    u2 = User.create(name="Opted Out", email="optout@example.com", password="pwd",
                     home_coords=[77.2100, 28.6140], digest_opt_in=False, db=mock_db)

    # User outside 5km radius (7km away, should NOT be emailed)
    u3 = User.create(name="Beyond 5km", email="far_5km@example.com", password="pwd",
                     home_coords=[77.2900, 28.6140], digest_opt_in=True, db=mock_db)

    # Create unverified report
    rep = create_report(author.id, "pothole", "Dangerous pothole near metro station exit",
                        "url", [77.2090, 28.6139], db=mock_db)

    sent_emails = []
    from app.jobs import digest as digest_module
    monkeypatch.setattr(digest_module, "send_email", lambda to, subj, html, text_body=None: (
        sent_emails.append({"to": to, "subject": subj, "html": html, "text": text_body}), True
    )[1])

    valid_token = app.config.get("CRON_SECRET_TOKEN", "gcir-dev-cron-token-xyz")
    res = client.post("/jobs/digest", headers={"X-Job-Token": valid_token})
    assert res.status_code == 200
    data = res.get_json()

    recipients = [e["to"] for e in sent_emails]
    # u1 (within 5km via last_login_location) received digest
    assert "mobile_optin@example.com" in recipients
    # u2 (opted out) did NOT receive
    assert "optout@example.com" not in recipients
    # u3 (beyond 5km) did NOT receive
    assert "far_5km@example.com" not in recipients

    # Verify report link is embedded in the digest email
    rep_id_str = str(rep["_id"])
    for em in sent_emails:
        assert f"/reports/{rep_id_str}" in em["html"]
        assert f"/reports/{rep_id_str}" in em["text"]

