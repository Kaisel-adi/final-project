import os
from pathlib import Path
from flask import Flask, redirect, url_for, request
from flask_login import LoginManager
from app.config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Cache headers for static assets on mobile/slow connections
    @app.after_request
    def add_performance_headers(response):
        if request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=604800"
        return response

    # Ensure upload directory exists
    upload_dir = Path(app.config.get("UPLOAD_FOLDER", app.root_path + "/static/uploads"))
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"
    login_manager.session_protection = "basic"
    login_manager.init_app(app)

    # Reverse proxy support (Render, Heroku, Nginx)
    try:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    except ImportError:
        pass

    from app.auth.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.get_by_id(user_id)

    @app.template_filter("is_video")
    def is_video_filter(url):
        if not url:
            return False
        url_lower = str(url).lower()
        return (
            any(url_lower.endswith(f".{ext}") for ext in ["mp4", "webm", "mov", "m4v", "ogg"])
            or "/video/upload/" in url_lower
        )

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

    @app.route("/health")
    def health():
        from app.db import is_mock_database, get_db
        from flask import jsonify
        db = get_db()
        is_mock = is_mock_database()
        try:
            user_count = db.users.count_documents({})
            report_count = db.reports.count_documents({})
            db_status = "connected"
        except Exception as e:
            db_status = str(e)
            user_count = -1
            report_count = -1

        return jsonify({
            "status": "healthy",
            "database": {
                "status": db_status,
                "is_mock": is_mock,
                "database_name": app.config.get("DATABASE_NAME", "gcir_db"),
                "total_users": user_count,
                "total_reports": report_count
            }
        })

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
