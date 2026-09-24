"""Moderation + analytics — PRD §5.7, §6.

Flag/remove reports; DBSCAN hotspot map; duplicate suggestions
(TF-IDF cosine similarity within ~200m).
"""
from flask import Blueprint

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/moderation")
def moderation():
    # TODO: Week 7 — list flagged reports, remove action (role-gated)
    return "moderation placeholder"


@bp.route("/analytics/hotspots")
def hotspots():
    # TODO: Week 6 — serve precomputed DBSCAN cluster_id groupings
    return "hotspots placeholder"
