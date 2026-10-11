"""RobloxForge - a small web app for building Roblox (Luau) scripts.

The app is a Flask application factory so it can be run directly with
``python run.py`` or served by any WSGI server (waitress, gunicorn, ...).
"""

from __future__ import annotations

import os

from flask import Flask

from . import db

__version__ = "1.0.0"


def create_app(database_path: str | None = None) -> Flask:
    """Build and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)

    os.makedirs(app.instance_path, exist_ok=True)

    app.config.update(
        SECRET_KEY=os.environ.get("PROJECTX_SECRET_KEY", "dev-secret-change-me"),
        DATABASE=database_path or os.environ.get("PROJECTX_DB")
        or os.path.join(app.instance_path, "robloxforge.db"),
        JSON_SORT_KEYS=False,
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,
    )

    db.init_app(app)

    from .routes import api, pages

    app.register_blueprint(pages.bp)
    app.register_blueprint(api.bp, url_prefix="/api")

    with app.app_context():
        db.init_db()

    @app.context_processor
    def inject_globals():
        from . import features as feature_lib
        from . import snippets as snippet_lib

        return {
            "app_name": "RobloxForge",
            "app_version": __version__,
            "feature_count": len(feature_lib.ALL_FEATURES),
            "snippet_count": len(snippet_lib.SNIPPETS),
        }

    @app.errorhandler(404)
    def not_found(error):
        from flask import jsonify, render_template, request

        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": "Not found."}), 404
        if not request.accept_mimetypes.accept_html:
            return error, 404
        return render_template("404.html"), 404

    @app.template_filter("timeago")
    def timeago(value: str) -> str:
        from datetime import datetime, timezone

        if not value:
            return "never"
        try:
            stamp = datetime.fromisoformat(value)
        except ValueError:
            return value
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - stamp
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{seconds // 60} min ago"
        if seconds < 86400:
            return f"{seconds // 3600} h ago"
        if seconds < 2592000:
            return f"{seconds // 86400} d ago"
        return stamp.strftime("%d %b %Y")

    @app.template_filter("shortcode")
    def shortcode(code: str, limit: int = 220) -> str:
        code = (code or "").strip()
        if len(code) <= limit:
            return code
        return code[:limit].rstrip() + "\n..."

    return app
