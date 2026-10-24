import logging

from flask import Flask

from .config import Config
from .extensions import db, login_manager, migrate


def create_app(config_class=Config):
    app = Flask(__name__)
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

    from . import models  # noqa: F401  — register models

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