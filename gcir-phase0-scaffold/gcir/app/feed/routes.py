"""Nearby feed + upvotes — PRD §5.2, §5.3.

$near query sorted by distance; filters by category/status/radius.
Upvote flips status to Verified at VERIFY_THRESHOLD (config, §4).
"""
from flask import Blueprint

bp = Blueprint("feed", __name__, url_prefix="/feed")


@bp.route("/")
def nearby():
    # TODO: Week 3 — Leaflet map + list, $near sorted by distance
    return "nearby feed placeholder"


@bp.route("/<report_id>/upvote", methods=["POST"])
def upvote(report_id):
    # TODO: Week 3 — one vote per account, author can't upvote own,
    # soft proximity check (UPVOTE_PROXIMITY_KM), flip status at threshold
    return "upvote placeholder"
