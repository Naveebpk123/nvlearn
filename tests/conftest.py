import pytest

from app import create_app
from app.config import Config
from app.extensions import db as _db
from app.models import User
from werkzeug.security import generate_password_hash


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-key"


@pytest.fixture
def app():
    """Create an isolated Flask app with an in-memory SQLite database."""
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    """Return a Flask test client for unauthenticated requests."""
    return app.test_client()


@pytest.fixture
def db(app):
    """Return the SQLAlchemy database instance bound to the test app."""
    return _db


@pytest.fixture
def user(app, db):
    """Create and commit a primary test user."""
    user = User(
        email="test@example.com",
        name="Test User",
        password=generate_password_hash("password123", method="pbkdf2:sha256"),
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def logged_in_client(client, user):
    """Return a test client with the primary user's session pre-authenticated."""
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return client


@pytest.fixture
def other_user(app, db):
    """Create and commit a secondary user for cross-user ownership tests."""
    other = User(
        email="other@example.com",
        name="Other",
        password=generate_password_hash("x", method="pbkdf2:sha256", salt_length=16),
    )
    db.session.add(other)
    db.session.commit()
    return other