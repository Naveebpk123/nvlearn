from app.models import Note, User
from werkzeug.security import generate_password_hash


def test_notes_requires_login(client):
    response = client.get("/notes")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_notes_page_loads_for_logged_in_users(logged_in_client):
    response = logged_in_client.get("/notes")
    assert response.status_code == 200
    assert b"My Notes" in response.data


def _create_other_user_and_note(db, in_bin=False):
    """Helper: create a second user + note owned by them."""
    other = User(
        email="other@example.com",
        name="Other",
        password=generate_password_hash("x", method="pbkdf2:sha256", salt_length=16),
    )
    db.session.add(other)
    db.session.commit()

    other_note = Note(
        title="Secret note",
        md_content="secret",
        html_content="<p>secret</p>",
        in_bin=in_bin,
        user_id=other.id,
        meta_data={},
    )
    db.session.add(other_note)
    db.session.commit()
    return other_note

def test_notes_page_only_shows_current_users_notes(logged_in_client, db):
    _create_other_user_and_note(db, in_bin=False)
    my_note = Note(
        title="My visible note",
        md_content="# Mine",
        html_content="<p>Mine</p>",
        in_bin=False,
        user_id=user.id,
        meta_data={},
    )
    db.session.add(my_note)
    db.session.commit()

    response = logged_in_client.get("/notes")
    assert response.status_code == 200
    # Other user's note title must not appear
    assert b"My visible note" in response.data
    assert b"Secret note" not in response.data

def test_user_cannot_edit_other_users_note(logged_in_client, db):
    other_note = _create_other_user_and_note(db, in_bin=False)
    note_id = other_note.id

    response = logged_in_client.get(f"/edit/{note_id}")
    assert response.status_code == 302
    assert "/notes" in response.headers["Location"]

    db.session.refresh(other_note)
    assert other_note.md_content == "secret"
    assert other_note.html_content == "<p>secret</p>"
    assert other_note.in_bin is False


def test_user_cannot_move_other_users_note_to_bin(logged_in_client, db):
    other_note = _create_other_user_and_note(db, in_bin=False)
    note_id = other_note.id

    response = logged_in_client.post(f"/move_to_bin/{note_id}")
    data = response.get_json()
    assert data[1] == "error"

    db.session.refresh(other_note)
    assert other_note.in_bin is False


def test_user_cannot_delete_other_users_note(logged_in_client, db):
    other_note = _create_other_user_and_note(db, in_bin=False)
    note_id = other_note.id

    response = logged_in_client.post(f"/delete/{note_id}")
    data = response.get_json()
    assert data[1] == "error"

    still_there = db.session.get(Note, note_id)
    assert still_there is not None


def test_user_cannot_restore_other_users_note(logged_in_client, db):
    # Note must be in bin for restore to be meaningful
    other_note = _create_other_user_and_note(db, in_bin=True)
    note_id = other_note.id

    response = logged_in_client.post(f"/restore/{note_id}")
    data = response.get_json()
    assert data[1] == "error"

    db.session.refresh(other_note)
    assert other_note.in_bin is True


def test_notes_page_only_shows_current_users_notes(logged_in_client, db):
    _create_other_user_and_note(db, in_bin=False)

    response = logged_in_client.get("/notes")
    assert response.status_code == 200
    # Other user's note title must not appear
    assert b"Secret note" not in response.data


def test_add_note_creates_note_for_current_user(logged_in_client, db, user):
    title = "My first note"
    md_content = "# Hello World\nMy note is **cool**"
    html_content = "<h1>Hello World</h1>\n<p>My note is <strong>cool</strong></p>"

    response = logged_in_client.post(
        "/add_note",
        data={
            "title": title,
            "content": md_content,
            "html_content": html_content,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"My Notes" in response.data
    assert b"My first note" in response.data

    note = db.session.execute(
        db.select(Note)
        .where(Note.title == title)
        .where(Note.user_id == user.id)
    ).scalar_one()

    assert note.md_content == md_content
    assert note.html_content == html_content
    assert note.in_bin is False


def test_edit_note_updates_content(logged_in_client, db, user):
    original_md = "# Hello World"
    original_html = "<h1>Hello World</h1>"

    note = Note(
        title="Note",
        md_content=original_md,
        html_content=original_html,
        in_bin=False,
        user_id=user.id,
        meta_data={},
    )
    db.session.add(note)
    db.session.commit()

    new_md = "# Edited Note\nUnique test marker 7f3a"
    new_html = "<h1>Edited Note</h1><p>Unique test marker 7f3a</p>"

    response = logged_in_client.post(
        f"/edit/{note.id}",
        data={
            "content": new_md,
            "html_content": new_html,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Unique test marker 7f3a" in response.data

    db.session.refresh(note)
    assert note.md_content == new_md
    assert note.html_content == new_html