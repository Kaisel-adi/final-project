"""Report service — PRD §5.1.

Handles: photo upload to image storage, browser-Geolocation capture
(EXIF GPS not trusted), inserting the report as GeoJSON [lon, lat].
"""
from flask import Blueprint

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.route("/new", methods=["GET", "POST"])
def new_report():
    # TODO: Week 2 — validate category/description/photo, insert with
    # status="Reported", upvote_count=0
    return "new report placeholder"
