import os
from pathlib import Path
from flask import Flask, redirect, url_for
from flask_login import LoginManager
from app.config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure upload directory exists
    upload_dir = Path(app.config.get("UPLOAD_FOLDER", app.root_path + "/static/uploads"))
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"
    login_manager.init_app(app)

    from app.auth.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.get_by_id(user_id)

    # Register blueprints
    from app.auth.routes import auth_bp
    app.register_blueprint(auth_bp)

    # Reports Blueprint
    from app.reports.routes import reports_bp
    app.register_blueprint(reports_bp)

    # Feed Blueprint
    from app.feed.routes import feed_bp
    app.register_blueprint(feed_bp)

    # Complaints Blueprint
    from app.complaints.routes import complaints_bp
    app.register_blueprint(complaints_bp)

    # Admin Blueprint
    from app.admin.routes import admin_bp
    app.register_blueprint(admin_bp)

    # Background Jobs Blueprint
    from app.jobs.digest import jobs_bp
    app.register_blueprint(jobs_bp)

    @app.route("/")
    def index():
        return redirect(url_for("feed.feed_view"))

    # Ensure jurisdiction boundaries are loaded if empty
    if not app.config.get("TESTING"):
        with app.app_context():
            try:
                from app.db import get_db
                db = get_db()
                if db.jurisdictions.count_documents({}) == 0:
                    from scripts.etl_boundaries import seed_database
                    seed_database(db)
            except Exception as e:
                app.logger.warning(f"Jurisdiction auto-seed notice: {e}")

    return app
