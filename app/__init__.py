import logging
import os

from flask import Flask

from .config import Config
from .extensions import db, login_manager, migrate


import sqlite3
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    print(f"[sqlite] connect fired for {type(dbapi_connection).__module__}.{type(dbapi_connection).__name__}")
    if not isinstance(dbapi_connection, sqlite3.Connection):
        print(f"[sqlite] NOT a sqlite3.Connection — skipping")
        return

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL;")
        journal = cursor.execute("PRAGMA journal_mode;").fetchone()
        print(f"[sqlite] journal_mode after set: {journal}")

        cursor.execute("PRAGMA busy_timeout=30000;")
        timeout = cursor.execute("PRAGMA busy_timeout;").fetchone()
        print(f"[sqlite] busy_timeout after set: {timeout}")
    except Exception as e:
        print(f"[sqlite] PRAGMA failed: {type(e).__name__}: {e}")
    finally:
        cursor.close()

def create_app(config_class=Config):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    app = Flask(
        __name__,
        template_folder=os.path.join(base_dir, "templates"),
        static_folder=os.path.join(base_dir, "static"),
    )
    app.config.from_object(config_class)

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    app.logger.setLevel(logging.DEBUG)
    app.logger.info("Flask application initialized — logging is active.")

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    from . import models  # noqa: F401

    from .main import bp as main_bp
    from .auth import bp as auth_bp
    from .notes import bp as notes_bp
    from .uploads import bp as uploads_bp
    from .diagrams import bp as diagrams_bp
    from .ai import bp as ai_bp
    from .practice import bp as practice_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(uploads_bp)
    app.register_blueprint(diagrams_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(practice_bp)

    with app.app_context():
        db.create_all()

    from .jobs import start_scheduler
    start_scheduler(app)

    return app


@login_manager.user_loader
def load_user(user_id):
    from .extensions import db
    from .models import User

    try:
        return db.session.get(User, int(user_id))
    except Exception as e:
        logging.getLogger(__name__).error("Failed to load user_id=%s: %s", user_id, e)
        return None