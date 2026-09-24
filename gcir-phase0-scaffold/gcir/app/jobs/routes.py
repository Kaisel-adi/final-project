"""Token-protected job endpoints — PRD §5.5, §7, §11 Security.

Hit by external cron only (free hosts sleep, so no in-process
scheduler). Every route here must check JOBS_SECRET_TOKEN before
doing anything.
"""
from flask import Blueprint, current_app, request, abort

bp = Blueprint("jobs", __name__, url_prefix="/jobs")


def _require_token():
    token = request.headers.get("X-Job-Token") or request.args.get("token")
    if token != current_app.config["JOBS_SECRET_TOKEN"]:
        abort(403)


@bp.route("/digest", methods=["POST"])
def digest():
    _require_token()
    # TODO: Week 5 — for each new Reported post since last run, find
    # opted-in users within their radius, group by user, cap at
    # DIGEST_MAX_ITEMS_PER_USER, exclude own/already-upvoted, send,
    # write digest_log
    return "digest job placeholder"
