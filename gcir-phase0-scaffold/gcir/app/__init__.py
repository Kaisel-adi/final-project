from flask import Flask

from app.config import Config
from app.extensions import login_manager, init_mongo


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    init_mongo(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    from app.auth.routes import bp as auth_bp
    from app.reports.routes import bp as reports_bp
    from app.feed.routes import bp as feed_bp
    from app.drafter.routes import bp as drafter_bp
    from app.admin.routes import bp as admin_bp
    from app.jobs.routes import bp as jobs_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(feed_bp)
    app.register_blueprint(drafter_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(jobs_bp)

    @app.route("/")
    def index():
        return "GCIR — phase 0 scaffold. See /feed, /reports/new, /auth/login."

    return app
