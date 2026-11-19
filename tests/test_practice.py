import pytest
from app.models import Flashcard, Quiz, QuizAttempt, User
from werkzeug.security import generate_password_hash


def _create_other_user_and_flashcard(db, other_user, is_saved=False):
    """Helper: create a flashcard set owned by other_user."""
    other_flashcard = Flashcard(
        card_data=["Secret Topic", {"front": "Secret Q1", "back": "Secret A1"}],
        is_saved=is_saved,
        user_id=other_user.id,
        incorrect_ratio=0.0,
    )
    db.session.add(other_flashcard)
    db.session.commit()
    return other_flashcard


def _create_other_user_and_quiz(db, other_user, is_saved=False):
    """Helper: create a quiz owned by other_user."""
    other_quiz = Quiz(
        quiz_data=[
            {
                "question": "Secret quiz question?",
                "options": ["A", "B", "C", "D"],
                "answer": "A",
            }
        ],
        is_saved=is_saved,
        user_id=other_user.id,
        tags=["secret"],
    )
    db.session.add(other_quiz)
    db.session.commit()
    return other_quiz


# ── Auth guard ────────────────────────────────────────────────────────────────


def test_practice_hub_requires_login(client):
    response = client.get("/practice-hub")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_practice_hub_loads_for_logged_in_user(logged_in_client):
    response = logged_in_client.get("/practice-hub")
    assert response.status_code == 200
    assert b"Practice Hub" in response.data


# ── Ownership — flashcards ────────────────────────────────────────────────────


def test_user_cannot_view_other_users_flashcards(logged_in_client, db, other_user):
    other_flashcard = _create_other_user_and_flashcard(db, other_user)
    response = logged_in_client.get(f"/flashcards/{other_flashcard.id}")
    assert response.status_code == 404

    still_there = db.session.get(Flashcard, other_flashcard.id)
    assert still_there is not None


def test_user_cannot_delete_other_users_flashcards(logged_in_client, db, other_user):
    other_flashcard = _create_other_user_and_flashcard(db, other_user)
    flashcard_id = other_flashcard.id

    response = logged_in_client.post(f"/delete-flashcards/{flashcard_id}")
    assert response.get_json() == ["Failed to delete", "error"]

    still_there = db.session.get(Flashcard, flashcard_id)
    assert still_there is not None


def test_user_cannot_save_attempts_to_other_users_flashcards(logged_in_client, db, other_user):
    other_flashcard = _create_other_user_and_flashcard(db, other_user, is_saved=False)

    response = logged_in_client.post(
        f"/save-flashcards/{other_flashcard.id}",
        json={"incorrect_attempts": 2},
    )
    assert response.get_json() == {"status": "failed"}

    db.session.refresh(other_flashcard)
    assert other_flashcard.is_saved is False
    assert other_flashcard.incorrect_ratio == 0.0


# ── Ownership — quizzes ───────────────────────────────────────────────────────


def test_user_cannot_view_other_users_quiz(logged_in_client, db, other_user):
    other_quiz = _create_other_user_and_quiz(db, other_user)
    response = logged_in_client.get(f"/quiz/{other_quiz.id}")
    assert response.status_code == 200
    assert b"const isError = true;" in response.data
    assert b"Secret quiz question?" not in response.data

    still_there = db.session.get(Quiz, other_quiz.id)
    assert still_there is not None


def test_user_cannot_delete_other_users_quiz(logged_in_client, db, other_user):
    other_quiz = _create_other_user_and_quiz(db, other_user)
    quiz_id = other_quiz.id

    response = logged_in_client.post(f"/delete-quiz/{quiz_id}")
    assert response.get_json() == ["Failed to delete", "error"]

    still_there = db.session.get(Quiz, quiz_id)
    assert still_there is not None


def test_user_cannot_save_other_users_quiz(logged_in_client, db, other_user):
    other_quiz = _create_other_user_and_quiz(db, other_user, is_saved=False)

    response = logged_in_client.post(
        f"/save-quiz/{other_quiz.id}",
        json={"total_questions": 4, "correct_answers": 3, "incorrect_answers": 1},
    )
    assert response.get_json() == {"error": "failed"}

    db.session.refresh(other_quiz)
    assert other_quiz.is_saved is False
    attempts = db.session.scalars(
        db.select(QuizAttempt).where(QuizAttempt.quiz_id == other_quiz.id)
    ).all()
    assert len(attempts) == 0


def test_user_cannot_get_other_users_quiz_data(logged_in_client, db, other_user):
    other_quiz = _create_other_user_and_quiz(db, other_user)
    response = logged_in_client.post(f"/get-quiz-data/{other_quiz.id}")
    assert response.status_code == 404
    assert response.get_json() == {"error": "Quiz not found"}

    still_there = db.session.get(Quiz, other_quiz.id)
    assert still_there is not None


def test_user_cannot_view_other_users_quiz_attempts(logged_in_client, db, other_user):
    other_quiz = _create_other_user_and_quiz(db, other_user)
    response = logged_in_client.get(f"/quiz-attempts/{other_quiz.id}")
    assert response.status_code == 404
    assert response.get_json() == {"error": "Quiz not found"}

    still_there = db.session.get(Quiz, other_quiz.id)
    assert still_there is not None


# ── Happy paths — flashcards ──────────────────────────────────────────────────


def test_save_flashcard_marks_set_as_saved(logged_in_client, db, user):
    flashcard = Flashcard(
        card_data=[
            "Python Basics",
            {"front": "Q1", "back": "A1"},
            {"front": "Q2", "back": "A2"},
        ],
        is_saved=False,
        user_id=user.id,
        incorrect_ratio=0.0,
    )
    db.session.add(flashcard)
    db.session.commit()

    response = logged_in_client.post(
        f"/save-flashcards/{flashcard.id}",
        json={"incorrect_attempts": 0},
    )
    assert response.status_code == 200
    assert response.get_json() == {"status": "saved"}

    db.session.refresh(flashcard)
    assert flashcard.is_saved is True
    assert flashcard.incorrect_ratio == 0.0


def test_save_flashcard_updates_incorrect_ratio(logged_in_client, db, user):
    flashcard = Flashcard(
        card_data=[
            "Biology",
            {"front": "Q1", "back": "A1"},
            {"front": "Q2", "back": "A2"},
            {"front": "Q3", "back": "A3"},
            {"front": "Q4", "back": "A4"},
            {"front": "Q5", "back": "A5"},
        ],
        is_saved=False,
        user_id=user.id,
        incorrect_ratio=0.0,
    )
    db.session.add(flashcard)
    db.session.commit()

    response = logged_in_client.post(
        f"/save-flashcards/{flashcard.id}",
        json={"incorrect_attempts": 3},
    )
    assert response.status_code == 200
    assert response.get_json() == {"status": "saved"}

    db.session.refresh(flashcard)
    assert flashcard.is_saved is True
    assert flashcard.incorrect_ratio == pytest.approx(0.6)


# ── Happy paths — quizzes ─────────────────────────────────────────────────────


def test_save_quiz_marks_quiz_saved_and_records_attempt(logged_in_client, db, user):
    quiz = Quiz(
        quiz_data=[{"question": "Q1", "options": ["A", "B"], "answer": "A"}],
        is_saved=False,
        user_id=user.id,
    )
    db.session.add(quiz)
    db.session.commit()

    response = logged_in_client.post(
        f"/save-quiz/{quiz.id}",
        json={"total_questions": 4, "correct_answers": 3, "incorrect_answers": 1},
    )
    assert response.status_code == 200
    assert response.get_json() == {"status": "saved"}

    db.session.refresh(quiz)
    assert quiz.is_saved is True

    attempts = db.session.scalars(
        db.select(QuizAttempt).where(QuizAttempt.quiz_id == quiz.id)
    ).all()
    assert len(attempts) == 1
    assert attempts[0].correct_answers == 3
    assert attempts[0].incorrect_answers == 1
    assert attempts[0].unanswered == 0


def test_quiz_attempts_returns_history_for_owner(logged_in_client, db, user):
    quiz = Quiz(
        quiz_data=[{"question": "Q1", "options": ["A", "B"], "answer": "A"}],
        is_saved=True,
        user_id=user.id,
    )
    db.session.add(quiz)
    db.session.commit()

    attempt1 = QuizAttempt(
        quiz_id=quiz.id,
        user_id=user.id,
        correct_answers=2,
        incorrect_answers=2,
        unanswered=0,
    )
    attempt2 = QuizAttempt(
        quiz_id=quiz.id,
        user_id=user.id,
        correct_answers=3,
        incorrect_answers=1,
        unanswered=0,
    )
    attempt3 = QuizAttempt(
        quiz_id=quiz.id,
        user_id=user.id,
        correct_answers=4,
        incorrect_answers=0,
        unanswered=0,
    )
    db.session.add_all([attempt1, attempt2, attempt3])
    db.session.commit()

    response = logged_in_client.get(f"/quiz-attempts/{quiz.id}")
    assert response.status_code == 200
    data = response.get_json()

    assert len(data["attempts"]) == 3
    # Most recent first: attempt3 (4), attempt2 (3), attempt1 (2)
    assert [a["correct_answers"] for a in data["attempts"]] == [4, 3, 2]
    assert data["averages"]["average_correct"] == pytest.approx(3.0)
