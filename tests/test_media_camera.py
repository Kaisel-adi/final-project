import io
import pytest
from app.services.storage import save_image, save_media
from app.reports.services import create_report
from app.auth.models import User
from werkzeug.datastructures import FileStorage


def test_save_media_video_support(app):
    with app.app_context():
        # Test valid MP4 upload
        video_file = FileStorage(
            stream=io.BytesIO(b"fake mp4 video bytes"),
            filename="civic_clip.mp4",
            content_type="video/mp4"
        )
        url = save_media(video_file)
        assert url.endswith(".mp4")
        assert "/static/uploads/" in url

        # Test valid WebM upload
        webm_file = FileStorage(
            stream=io.BytesIO(b"fake webm video bytes"),
            filename="issue_recording.webm",
            content_type="video/webm"
        )
        url_webm = save_image(webm_file)
        assert url_webm.endswith(".webm")

        # Test rejected extension
        bad_file = FileStorage(
            stream=io.BytesIO(b"malicious script"),
            filename="exploit.exe",
            content_type="application/octet-stream"
        )
        with pytest.raises(ValueError, match="File type .exe not allowed"):
            save_media(bad_file)


def test_report_create_page_renders_camera_ui(client, mock_db):
    user = User.create(name="Civic Citizen", email="citizen@test.com", password="pass", db=mock_db)
    with client.session_transaction() as sess:
        sess["_user_id"] = user.id

    res = client.get("/reports/create")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Check for Open Camera button and camera modal
    assert "btn-open-camera" in html
    assert "btn-trigger-upload" in html
    assert "camera-modal" in html
    assert "btn-flip-camera" in html
    assert "btn-snap-photo" in html
    assert "btn-record-video" in html
    assert "camera-video" in html
    assert "media-preview-box" in html


def test_report_view_renders_video_player(client, mock_db):
    author = User.create(name="Reporter", email="reporter@test.com", password="pass", db=mock_db)
    
    # Create report with video URL
    rep_video = create_report(
        author_id=author.id,
        category="water_leak",
        description="Severe pipeline bursting on main road.",
        photo_url="/static/uploads/test_video.mp4",
        coordinates=[77.21, 28.62],
        db=mock_db
    )

    res = client.get(f"/reports/{rep_video['_id']}")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Verify video tag is rendered instead of img
    assert "<video src=\"/static/uploads/test_video.mp4\" controls" in html
    assert "Video Evidence" in html
