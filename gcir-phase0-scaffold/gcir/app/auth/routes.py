"""Auth: sessions + roles — PRD §7 (AUTH), §9 (Flask-Login).

Stub only. Fill in with: register, login, logout, and a User model
that Flask-Login can load via user_loader.
"""
from flask import Blueprint

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/login")
def login():
    # TODO: Week 2 — render login form, verify hashed password
    return "login placeholder"


@bp.route("/logout")
def logout():
    # TODO: Week 2 — flask_login.logout_user()
    return "logout placeholder"
