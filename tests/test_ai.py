from app.ai import routes as ai_routes
from app.models import Note


# ── Auth guard ────────────────────────────────────────────────────────────────


def test_ai_chat_requires_login(client):
    response = client.get("/ai-chat")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_ai_chat_loads_for_logged_in_user(logged_in_client):
    response = logged_in_client.get("/ai-chat")
    assert response.status_code == 200
    assert b"Test User" in response.data


def test_ai_response_requires_login(client):
    response = client.post("/ai-response", json={"contents": []})
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# ── Chat action ───────────────────────────────────────────────────────────────


def test_ai_response_chat_returns_html(logged_in_client, monkeypatch):
    monkeypatch.setattr(
        ai_routes,
        "build_ai_instructions",
        lambda **kwargs: [{"action": "chat", "content": "<p>Hello</p>"}],
    )
    response = logged_in_client.post("/ai-response", json={"contents": []})
    assert response.status_code == 200
    data = response.get_json()
    assert data["chat"] == "<p>Hello</p>"
    assert data["flashcard_id"] is None
    assert data["quiz_id"] is None


def test_ai_response_chat_does_not_create_note(logged_in_client, db, user, monkeypatch):
    monkeypatch.setattr(
        ai_routes,
        "build_ai_instructions",
        lambda **kwargs: [{"action": "chat", "content": "<p>Hello</p>"}],
    )
    response = logged_in_client.post("/ai-response", json={"contents": []})
    assert response.status_code == 200
    notes = db.session.scalars(db.select(Note).where(Note.user_id == user.id)).all()
    assert len(notes) == 0


# ── Create-note action ────────────────────────────────────────────────────────


def test_ai_response_create_note_creates_note_for_user(
    logged_in_client, db, user, monkeypatch
):
    monkeypatch.setattr(
        ai_routes,
        "build_ai_instructions",
        lambda **kwargs: [
            {
                "action": "create_note",
                "content": {
                    "title": "AI Study Note",
                    "content": "# AI Study Note",
                    "html_content": "<h1>AI Study Note</h1>",
                    "meta_data": {},
                },
            }
        ],
    )
    monkeypatch.setattr(ai_routes, "upsert_note_vector", lambda note: None)

    response = logged_in_client.post("/ai-response", json={"contents": []})
    assert response.status_code == 200
    note = db.session.scalars(
        db.select(Note).where(Note.user_id == user.id, Note.title == "AI Study Note")
    ).one_or_none()
    assert note is not None
    assert note.md_content == "# AI Study Note"


def test_ai_response_create_note_records_in_response(
    logged_in_client, monkeypatch
):
    monkeypatch.setattr(
        ai_routes,
        "build_ai_instructions",
        lambda **kwargs: [
            {
                "action": "create_note",
                "content": {
                    "title": "AI Study Note",
                    "content": "# AI Study Note",
                    "html_content": "<h1>AI Study Note</h1>",
                    "meta_data": {},
                },
            }
        ],
    )
    monkeypatch.setattr(ai_routes, "upsert_note_vector", lambda note: None)

    response = logged_in_client.post("/ai-response", json={"contents": []})
    assert response.status_code == 200
    data = response.get_json()
    assert "Made new note" in data["chat"]
    assert "AI Study Note" in data["chat"]


# ── Errors ────────────────────────────────────────────────────────────────────


def test_ai_response_handles_router_error(logged_in_client, monkeypatch):
    monkeypatch.setattr(
        ai_routes,
        "build_ai_instructions",
        lambda **kwargs: [
            {
                "action": "error",
                "content": {"error": True, "type": "api_error", "msg": "router failed"},
            }
        ],
    )
    response = logged_in_client.post("/ai-response", json={"contents": []})
    assert response.status_code == 200
    data = response.get_json()
    assert "router failed" in data["chat"]


def test_ai_response_handles_rate_limit_sets_cooldown(logged_in_client, monkeypatch):
    monkeypatch.setattr(
        ai_routes,
        "build_ai_instructions",
        lambda **kwargs: [
            {
                "action": "error",
                "content": {
                    "error": True,
                    "type": "rate_limit",
                    "msg": "rate limit hit",
                },
            }
        ],
    )
    response = logged_in_client.post("/ai-response", json={"contents": []})
    assert response.status_code == 200
    with logged_in_client.session_transaction() as sess:
        assert "note_action_cooldown_until" in sess


def test_ai_response_handles_gemini_error(logged_in_client, db, user, monkeypatch):
    note = Note(
        title="Sample Note",
        md_content="Some content",
        html_content="<p>Some content</p>",
        in_bin=False,
        user_id=user.id,
        meta_data={},
    )
    db.session.add(note)
    db.session.commit()

    monkeypatch.setattr(
        ai_routes,
        "build_ai_instructions",
        lambda **kwargs: [{"action": "note_action", "content": "summarize"}],
    )
    monkeypatch.setattr(
        ai_routes, "get_notes_for_action", lambda *args, **kwargs: ([note], None, False)
    )
    monkeypatch.setattr(
        ai_routes, "chunk_notes_content", lambda notes, user_id=None: ["Some content"]
    )
    monkeypatch.setattr(
        ai_routes,
        "ask_gemini",
        lambda **kwargs: {"error": True, "type": "api_error", "msg": "gemini failed"},
    )

    response = logged_in_client.post("/ai-response", json={"contents": []})
    assert response.status_code == 200
    data = response.get_json()
    assert "gemini failed" in data["chat"]
