"""Complaint drafter — PRD §5.4. Only unlocks for Verified reports.

Draft includes category, coordinates + map link, photo link, upvote
count, and count of other reports within DUPLICATE_RADIUS_M (200m).
Delivery is mailto: + copy button — no server-sent mail (see §5.4).
"""
from flask import Blueprint

bp = Blueprint("drafter", __name__, url_prefix="/drafter")


@bp.route("/<report_id>")
def draft(report_id):
    # TODO: Week 4 — require status == "Verified", call
    # router.service.find_authority, build mailto: link
    return "complaint draft placeholder"
