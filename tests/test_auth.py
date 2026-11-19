from app.models import User


# ── Register ──────────────────────────────────────────────────────────────────


def test_register_page_loads(client):
    response = client.get("/register")
    assert response.status_code == 200


def test_register_with_duplicate_email_shows_error(client, user, monkeypatch):
    monkeypatch.setattr("app.auth.routes.send_email_threaded", lambda *a, **kw: True)
    response = client.post(
        "/register",
        data={
            "name": "Duplicate User",
            "email": user.email,
            "password": "password123",
        },
    )
    assert response.status_code == 200
    assert b"already registered" in response.data


def test_register_with_short_password_shows_error(client, monkeypatch):
    monkeypatch.setattr("app.auth.routes.send_email_threaded", lambda *a, **kw: True)
    response = client.post(
        "/register",
        data={
            "name": "New User",
            "email": "new@example.com",
            "password": "123",
        },
    )
    assert response.status_code == 200
    assert b"at least" in response.data


def test_register_with_valid_data_starts_verification(client, db, monkeypatch):
    monkeypatch.setattr("app.auth.routes.send_email_threaded", lambda *a, **kw: True)
    response = client.post(
        "/register",
        data={
            "name": "New User",
            "email": "new@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert "pending_register" in sess
        assert sess["pending_register"]["email"] == "new@example.com"

    created = db.session.scalars(
        db.select(User).where(User.email == "new@example.com")
    ).one_or_none()
    assert created is None


def test_register_verification_with_correct_code_creates_user(client, db, monkeypatch):
    monkeypatch.setattr("app.auth.routes.send_email_threaded", lambda *a, **kw: True)
    client.post(
        "/register",
        data={
            "name": "New User",
            "email": "new@example.com",
            "password": "password123",
        },
    )
    with client.session_transaction() as sess:
        code = sess["pending_auth_code"]

    response = client.post(
        "/register",
        data={"code": code},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"My Notes" in response.data

    created = db.session.scalars(
        db.select(User).where(User.email == "new@example.com")
    ).one_or_none()
    assert created is not None
    assert created.email == "new@example.com"


def test_register_verification_with_wrong_code_shows_error(client, monkeypatch):
    monkeypatch.setattr("app.auth.routes.send_email_threaded", lambda *a, **kw: True)
    client.post(
        "/register",
        data={
            "name": "New User",
            "email": "new@example.com",
            "password": "password123",
        },
    )
    response = client.post("/register", data={"code": "000000"})
    assert response.status_code == 200
    assert b"That verification code is incorrect." in response.data


def test_register_verification_clears_pending_after_success(client, monkeypatch):
    monkeypatch.setattr("app.auth.routes.send_email_threaded", lambda *a, **kw: True)
    client.post(
        "/register",
        data={
            "name": "New User",
            "email": "new@example.com",
            "password": "password123",
        },
    )
    with client.session_transaction() as sess:
        code = sess["pending_auth_code"]

    client.post("/register", data={"code": code}, follow_redirects=True)
    with client.session_transaction() as sess:
        assert sess.get("pending_register") is None
        assert sess.get("pending_auth_code") is None


# ── Login ─────────────────────────────────────────────────────────────────────


def test_login_page_loads(client):
    response = client.get("/login")
    assert response.status_code == 200


def test_login_with_wrong_password_shows_error(client, user, monkeypatch):
    monkeypatch.setattr("app.auth.routes.send_email_threaded", lambda *a, **kw: True)
    response = client.post(
        "/login",
        data={"email": user.email, "password": "wrongpassword"},
    )
    assert response.status_code == 200
    assert b"Incorrect login credentials." in response.data


def test_login_with_unknown_email_shows_error(client, monkeypatch):
    monkeypatch.setattr("app.auth.routes.send_email_threaded", lambda *a, **kw: True)
    response = client.post(
        "/login",
        data={"email": "nobody@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    assert b"Incorrect login credentials." in response.data


def test_login_with_valid_credentials_sends_verification_email(
    client, user, monkeypatch
):
    monkeypatch.setattr("app.auth.routes.send_email_threaded", lambda *a, **kw: True)
    response = client.post(
        "/login",
        data={"email": user.email, "password": "password123"},
    )
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert "pending_login" in sess
        assert sess["pending_login"]["user_id"] == user.id


def test_login_verification_with_correct_code_logs_user_in(client, user, monkeypatch):
    monkeypatch.setattr("app.auth.routes.send_email_threaded", lambda *a, **kw: True)
    client.post(
        "/login",
        data={"email": user.email, "password": "password123"},
    )
    with client.session_transaction() as sess:
        code = sess["pending_auth_code"]

    response = client.post(
        "/login",
        data={"code": code},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"My Notes" in response.data

    notes_response = client.get("/notes")
    assert notes_response.status_code == 200


def test_login_verification_with_wrong_code_shows_error(client, user, monkeypatch):
    monkeypatch.setattr("app.auth.routes.send_email_threaded", lambda *a, **kw: True)
    client.post(
        "/login",
        data={"email": user.email, "password": "password123"},
    )
    response = client.post("/login", data={"code": "000000"})
    assert response.status_code == 200
    assert b"That verification code is incorrect." in response.data


# ── Logout ────────────────────────────────────────────────────────────────────


def test_logout_clears_session(logged_in_client):
    response = logged_in_client.post("/logout")
    data = response.get_json()
    assert data[1] == "success"

    notes_response = logged_in_client.get("/notes")
    assert notes_response.status_code == 302
    assert "/login" in notes_response.headers["Location"]


def test_logout_requires_login(client):
    response = client.post("/logout")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
