from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

from app.models import ChatMessage, ChatSession, User

from ai_service import validate_router_response, build_ai_instructions, is_ai_error


def _create_other_user_and_session(db, with_messages=0):
    """Create another user, a ChatSession owned by them, and optional messages."""
    other = User(
        email="other_chat@example.com",
        name="Other Chat User",
        password=generate_password_hash("password123", method="pbkdf2:sha256"),
    )
    db.session.add(other)
    db.session.flush()

    session = ChatSession(user_id=other.id, title="Other session")
    db.session.add(session)
    db.session.flush()

    base_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    for i in range(with_messages):
        role = "user" if i % 2 == 0 else "assistant"
        db.session.add(
            ChatMessage(
                session_id=session.id,
                role=role,
                content=f"Other message {i}",
                created_at=base_time + timedelta(seconds=i),
            )
        )
    db.session.commit()
    return other, session


def _create_own_session(db, user, with_messages=0):
    """Create a ChatSession owned by user with optional messages."""
    session = ChatSession(user_id=user.id, title="My session")
    db.session.add(session)
    db.session.flush()

    base_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    for i in range(with_messages):
        role = "user" if i % 2 == 0 else "assistant"
        db.session.add(
            ChatMessage(
                session_id=session.id,
                role=role,
                content=f"Message {i}",
                created_at=base_time + timedelta(seconds=i),
            )
        )
    db.session.commit()
    return session


# ── Auth guard ────────────────────────────────────────────────────────────────


def test_chat_sessions_list_requires_login(client):
    response = client.get("/api/chat/sessions")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_chat_session_get_requires_login(client):
    response = client.get("/api/chat/sessions/1")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_chat_session_delete_requires_login(client):
    response = client.delete("/api/chat/sessions/1")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# ── List endpoint ─────────────────────────────────────────────────────────────


def test_list_sessions_returns_empty_for_new_user(logged_in_client, db):
    response = logged_in_client.get("/api/chat/sessions")
    assert response.status_code == 200
    assert response.get_json() == []
    assert ChatSession.query.count() == 0


def test_list_sessions_returns_only_current_users_sessions(logged_in_client, db):
    _create_other_user_and_session(db, with_messages=2)

    response = logged_in_client.get("/api/chat/sessions")
    assert response.status_code == 200
    assert response.get_json() == []
    assert ChatSession.query.count() == 1


def test_list_sessions_orders_by_updated_at_desc(logged_in_client, db, user):
    now = datetime.now(timezone.utc)
    older = ChatSession(
        user_id=user.id, title="Older session", updated_at=now - timedelta(hours=2)
    )
    newer = ChatSession(
        user_id=user.id, title="Newer session", updated_at=now - timedelta(minutes=5)
    )
    db.session.add_all([older, newer])
    db.session.commit()

    response = logged_in_client.get("/api/chat/sessions")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2
    assert [item["title"] for item in data] == ["Newer session", "Older session"]


def test_list_sessions_includes_message_count(logged_in_client, db, user):
    session = _create_own_session(db, user, with_messages=3)

    response = logged_in_client.get("/api/chat/sessions")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 1
    assert data[0]["id"] == session.id
    assert data[0]["message_count"] == 3


# ── Get endpoint ──────────────────────────────────────────────────────────────


def test_get_session_returns_messages_oldest_first(logged_in_client, db, user):
    session = _create_own_session(db, user, with_messages=3)

    response = logged_in_client.get(f"/api/chat/sessions/{session.id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == session.id
    assert [m["content"] for m in data["messages"]] == [
        "Message 0",
        "Message 1",
        "Message 2",
    ]


def test_get_session_returns_404_for_missing(logged_in_client, db):
    response = logged_in_client.get("/api/chat/sessions/99999")
    assert response.status_code == 404
    data = response.get_json()
    assert "error" in data
    assert db.session.get(ChatSession, 99999) is None


def test_get_session_returns_404_for_other_users_session(logged_in_client, db):
    _, other_session = _create_other_user_and_session(db, with_messages=1)

    response = logged_in_client.get(f"/api/chat/sessions/{other_session.id}")
    assert response.status_code == 404
    data = response.get_json()
    assert "error" in data
    assert db.session.get(ChatSession, other_session.id) is not None


def test_get_session_returns_iso_timestamps(logged_in_client, db, user):
    session = _create_own_session(db, user, with_messages=2)

    response = logged_in_client.get(f"/api/chat/sessions/{session.id}")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["messages"]) == 2
    for msg in data["messages"]:
        parsed = datetime.fromisoformat(msg["created_at"])
        assert isinstance(parsed, datetime)


# ── Delete endpoint ───────────────────────────────────────────────────────────


def test_delete_session_removes_session(logged_in_client, db, user):
    session = _create_own_session(db, user, with_messages=1)
    session_id = session.id

    response = logged_in_client.delete(f"/api/chat/sessions/{session_id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "deleted"
    assert db.session.get(ChatSession, session_id) is None


def test_delete_session_cascades_to_messages(logged_in_client, db, user):
    session = _create_own_session(db, user, with_messages=3)
    session_id = session.id
    assert ChatMessage.query.filter_by(session_id=session_id).count() == 3

    response = logged_in_client.delete(f"/api/chat/sessions/{session_id}")
    assert response.status_code == 200
    assert response.get_json()["status"] == "deleted"
    assert ChatMessage.query.filter_by(session_id=session_id).count() == 0


def test_delete_session_returns_404_for_missing(logged_in_client, db):
    response = logged_in_client.delete("/api/chat/sessions/99999")
    assert response.status_code == 404
    data = response.get_json()
    assert "error" in data
    assert db.session.get(ChatSession, 99999) is None


def test_delete_session_returns_404_for_other_users_session(logged_in_client, db):
    _, other_session = _create_other_user_and_session(db, with_messages=2)

    response = logged_in_client.delete(f"/api/chat/sessions/{other_session.id}")
    assert response.status_code == 404
    data = response.get_json()
    assert "error" in data
    assert db.session.get(ChatSession, other_session.id) is not None
    assert ChatMessage.query.filter_by(session_id=other_session.id).count() == 2


def test_delete_session_does_not_affect_other_sessions(logged_in_client, db, user):
    first = _create_own_session(db, user, with_messages=1)
    second = _create_own_session(db, user, with_messages=2)

    response = logged_in_client.delete(f"/api/chat/sessions/{first.id}")
    assert response.status_code == 200
    assert response.get_json()["status"] == "deleted"
    assert db.session.get(ChatSession, first.id) is None
    assert db.session.get(ChatSession, second.id) is not None
    assert ChatMessage.query.filter_by(session_id=second.id).count() == 2


# ── AI persistence (/ai-response) ─────────────────────────────────────────────


def _mock_ai(monkeypatch):
    monkeypatch.setattr(
        "app.ai.routes.build_ai_instructions",
        lambda **kwargs: [{"action": "chat", "content": "<p>mocked reply</p>"}],
    )


def test_ai_response_creates_new_session_on_first_message(
    logged_in_client, db, user, monkeypatch
):
    _mock_ai(monkeypatch)

    response = logged_in_client.post(
        "/ai-response",
        json={"session_id": None, "contents": [{"role": "user", "contents": "Hello"}]},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["chat"] == "<p>mocked reply</p>"
    assert data["session_id"] is not None
    assert ChatSession.query.filter_by(user_id=user.id).count() == 1
    assert ChatMessage.query.filter_by(session_id=data["session_id"]).count() == 2


def test_ai_response_appends_to_existing_session(
    logged_in_client, db, user, monkeypatch
):
    _mock_ai(monkeypatch)
    session = _create_own_session(db, user, with_messages=2)

    response = logged_in_client.post(
        "/ai-response",
        json={
            "session_id": session.id,
            "contents": [{"role": "user", "contents": "Follow-up"}],
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["session_id"] == session.id
    assert ChatSession.query.filter_by(user_id=user.id).count() == 1
    assert ChatMessage.query.filter_by(session_id=session.id).count() == 4


def test_ai_response_returns_session_id(logged_in_client, db, monkeypatch):
    _mock_ai(monkeypatch)

    response = logged_in_client.post(
        "/ai-response",
        json={"session_id": None, "contents": [{"role": "user", "contents": "Ping"}]},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data["session_id"], int)
    assert db.session.get(ChatSession, data["session_id"]) is not None


def test_ai_response_does_not_reuse_other_users_session(
    logged_in_client, db, user, monkeypatch
):
    _mock_ai(monkeypatch)
    _, other_session = _create_other_user_and_session(db, with_messages=2)

    response = logged_in_client.post(
        "/ai-response",
        json={
            "session_id": other_session.id,
            "contents": [{"role": "user", "contents": "Hijack attempt"}],
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["session_id"] is not None
    assert data["session_id"] != other_session.id
    assert ChatSession.query.filter_by(user_id=user.id).count() == 1
    assert ChatMessage.query.filter_by(session_id=other_session.id).count() == 2


def test_ai_response_persists_user_and_assistant_messages(
    logged_in_client, db, monkeypatch
):
    _mock_ai(monkeypatch)

    response = logged_in_client.post(
        "/ai-response",
        json={
            "session_id": None,
            "contents": [{"role": "user", "contents": "Explain gravity"}],
        },
    )
    assert response.status_code == 200
    session_id = response.get_json()["session_id"]
    messages = (
        ChatMessage.query.filter_by(session_id=session_id)
        .order_by(ChatMessage.id.asc())
        .all()
    )
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[0].content == "Explain gravity"
    assert messages[1].content == "<p>mocked reply</p>"


def test_ai_response_updates_session_updated_at(
    logged_in_client, db, user, monkeypatch
):
    _mock_ai(monkeypatch)
    session = _create_own_session(db, user, with_messages=2)
    session.updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.session.commit()
    before = session.updated_at

    response = logged_in_client.post(
        "/ai-response",
        json={
            "session_id": session.id,
            "contents": [{"role": "user", "contents": "New turn"}],
        },
    )
    assert response.status_code == 200
    assert response.get_json()["session_id"] == session.id
    db.session.refresh(session)
    assert session.updated_at > before

def test_new_session_uses_router_generated_title(logged_in_client, db, user, monkeypatch):
    from app.ai import routes as ai_routes
    monkeypatch.setattr(
        ai_routes, "build_ai_instructions",
        lambda **kw: [
            {"action": "chat", "content": "<p>hi</p>"},
            {"action": "rename_chat", "content": "Router Title"},
        ],
    )
    logged_in_client.post("/ai-response", json={
        "session_id": None,
        "contents": [{"role": "user", "contents": "explain thermodynamics"}],
    })
    session = db.session.scalars(db.select(ChatSession)).first()
    assert session.title == "Router Title"


# ── Rename endpoint ───────────────────────────────────────────────────────────


def test_rename_session_updates_title(logged_in_client, db, user):
    session = _create_own_session(db, user, with_messages=1)

    response = logged_in_client.post(
        f"/api/chat/sessions/{session.id}/rename",
        json={"title": "New Title"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "renamed"
    assert data["title"] == "New Title"
    db.session.refresh(session)
    assert session.title == "New Title"


def test_rename_session_rejects_other_users_session(logged_in_client, db):
    _, other_session = _create_other_user_and_session(db, with_messages=1)
    original_title = other_session.title

    response = logged_in_client.post(
        f"/api/chat/sessions/{other_session.id}/rename",
        json={"title": "Hijacked Title"},
    )
    assert response.status_code == 404
    assert "error" in response.get_json()
    db.session.refresh(other_session)
    assert other_session.title == original_title


def test_rename_session_rejects_empty_title(logged_in_client, db, user):
    session = _create_own_session(db, user, with_messages=1)
    original_title = session.title

    response = logged_in_client.post(
        f"/api/chat/sessions/{session.id}/rename",
        json={"title": " "},
    )
    assert response.status_code == 400
    assert "error" in response.get_json()
    db.session.refresh(session)
    assert session.title == original_title


# ── Session history loading (/ai-response) ────────────────────────────────────


def test_ai_response_prepends_history_from_session(
    logged_in_client, db, user, monkeypatch
):
    session = _create_own_session(db, user, with_messages=2)
    captured = []

    def fake_build(contents, **kwargs):
        captured.append(contents)
        return [{"action": "chat", "content": "<p>ok</p>"}]

    monkeypatch.setattr("app.ai.routes.build_ai_instructions", fake_build)

    response = logged_in_client.post(
        "/ai-response",
        json={
            "session_id": session.id,
            "contents": [{"role": "user", "contents": "Follow-up question"}],
        },
    )
    assert response.status_code == 200
    assert len(captured) == 1
    assert len(captured[0]) == 3
    assert [m["role"] for m in captured[0]] == ["user", "assistant", "user"]
    assert captured[0][0]["contents"] == "Message 0"
    assert captured[0][1]["contents"] == "Message 1"
    assert captured[0][2]["contents"] == "Follow-up question"


def test_ai_response_no_history_when_session_id_null(
    logged_in_client, db, monkeypatch
):
    captured = []

    def fake_build(contents, **kwargs):
        captured.append(contents)
        return [{"action": "chat", "content": "<p>ok</p>"}]

    monkeypatch.setattr("app.ai.routes.build_ai_instructions", fake_build)

    response = logged_in_client.post(
        "/ai-response",
        json={
            "session_id": None,
            "contents": [{"role": "user", "contents": "First question"}],
        },
    )
    assert response.status_code == 200
    assert len(captured) == 1
    assert captured[0] == [{"role": "user", "contents": "First question"}]

def test_rename_does_not_change_updated_at(logged_in_client, db, user):
    """Renaming a session should not bump its updated_at timestamp."""
    import time
    from datetime import datetime, timezone

    chat_session = ChatSession(user_id=user.id, title="Original")
    db.session.add(chat_session)
    db.session.commit()

    original_updated_at = chat_session.updated_at

    time.sleep(0.05)   # ensure any naive update would produce a different timestamp

    response = logged_in_client.post(
        f"/api/chat/sessions/{chat_session.id}/rename",
        json={"title": "Renamed"},
    )
    assert response.status_code == 200

    db.session.refresh(chat_session)
    assert chat_session.title == "Renamed"
    assert chat_session.updated_at == original_updated_at
