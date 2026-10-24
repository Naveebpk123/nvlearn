import json

from flask import (
    abort, current_app, jsonify, render_template, request,
)
from flask_login import current_user, login_required

from . import bp
from ..config import Config
from ..extensions import db
from ..models import Flashcard, Quiz, QuizAttempt

@bp.route("/flashcards/<int:flashcard_id>")
@login_required
def view_flashcards(flashcard_id):
    flashcard_obj = db.session.get(Flashcard, flashcard_id)
    if not flashcard_obj or flashcard_obj.user_id != current_user.id:
        current_app.logger.warning(
            "[view_flashcards] Flashcard not found or unauthorized — flashcard_id=%s, user_id=%s",
            flashcard_id,
            current_user.id,
        )
        abort(404)
    return render_template(
        "view-flashcards.html",
        flashcards=flashcard_obj.card_data[1:],
        cards_id=flashcard_obj.id,
        is_saved=flashcard_obj.is_saved,
    )


@bp.route("/save-flashcards/<int:flashcard_id>", methods=["POST"])
@login_required
def save_flashcard(flashcard_id):
    flashcard_obj = db.session.get(Flashcard, flashcard_id)
    if flashcard_obj and flashcard_obj.user_id == current_user.id:
        if flashcard_obj.is_saved:
            incorrect_attempts = request.json.get("incorrect_attempts", 0)
            flashcard_count = len(flashcard_obj.card_data) - 1 # Subtract one due to the first element being the topic
            flashcard_obj.incorrect_ratio = (incorrect_attempts / flashcard_count) if flashcard_count > 0 else 0.0
            db.session.commit()
            return jsonify({"status": "updated"})
        incorrect_attempts = request.json.get("incorrect_attempts", 0)
        flashcard_obj.is_saved = True
        flashcard_count = len(flashcard_obj.card_data) - 1 # Subtract one due to the first element being the topic
        flashcard_obj.incorrect_ratio = (incorrect_attempts / flashcard_count) if flashcard_count > 0 else 0.0
        db.session.commit()
        return jsonify({"status": "saved"})
    return jsonify({"status": "failed"})


@bp.route("/delete-flashcards/<int:flashcard_id>", methods=["POST"])
@login_required
def delete_flashcard(flashcard_id):
    flashcard_obj = db.session.get(Flashcard, flashcard_id)
    if flashcard_obj and flashcard_obj.user_id == current_user.id:
        db.session.delete(flashcard_obj)
        db.session.commit()
        return jsonify(["Set deleted", "success"])
    return jsonify(["Failed to delete", "error"])


@bp.route("/quiz/<int:quiz_id>")
@login_required
def take_quiz(quiz_id):
    quiz_obj = db.session.get(Quiz, quiz_id)
    if not quiz_obj or quiz_obj.user_id != current_user.id:
        current_app.logger.warning(
            "[take_quiz] Quiz not found or unauthorized — quiz_id=%s, user_id=%s",
            quiz_id,
            current_user.id,
        )
        return render_template(
            "take-quiz.html", quiz_id=quiz_id, quiz_data_json="[]", error=True
        )

    raw_data = quiz_obj.quiz_data
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except Exception:
            pass

    if isinstance(raw_data, dict) and "questions" in raw_data:
        raw_data = raw_data["questions"]
    elif isinstance(raw_data, dict) and "quiz" in raw_data:
        raw_data = raw_data["quiz"]

    return render_template(
        "take-quiz.html",
        quiz_id=quiz_id,
        quiz_data_json=json.dumps(raw_data),
        error=False,
    )


@bp.route("/get-quiz-data/<int:quiz_id>", methods=["POST"])
@login_required
def get_quiz_data(quiz_id):
    quiz_obj = db.session.get(Quiz, quiz_id)
    if not quiz_obj or quiz_obj.user_id != current_user.id:
        current_app.logger.warning(
            "[get_quiz_data] Quiz not found or unauthorized — quiz_id=%s, user_id=%s",
            quiz_id,
            current_user.id,
        )
        return jsonify({"error": "Quiz not found"}), 404
    return jsonify(quiz_obj.quiz_data)


@bp.route("/save-quiz/<int:quiz_id>", methods=["POST"])
@login_required
def save_quiz(quiz_id):
    quiz_obj = db.session.get(Quiz, quiz_id)
    if not quiz_obj or quiz_obj.user_id != current_user.id:
        current_app.logger.warning(
            "[get_quiz_data] Quiz not found or unauthorized — quiz_id=%s, user_id=%s",
            quiz_id,
            current_user.id,
        )
        return jsonify({"error": "failed"})
    total_questions = request.json.get("total_questions", 0)
    correct_answers = request.json.get("correct_answers", 0)
    incorrect_answers = request.json.get("incorrect_answers", 0)
    quiz_obj.is_saved = True
    attempt = QuizAttempt(
        user_id=current_user.id,
        correct_answers=correct_answers,
        incorrect_answers=incorrect_answers,
        unanswered=total_questions - (correct_answers + incorrect_answers),
    )
    quiz_obj.attempts.append(attempt)
    db.session.commit()
    return jsonify({"status": "saved"})


@bp.route("/delete-quiz/<int:quiz_id>", methods=["POST"])
@login_required
def delete_quiz(quiz_id):
    quiz_obj = db.session.get(Quiz, quiz_id)
    if quiz_obj and quiz_obj.user_id == current_user.id:
        db.session.delete(quiz_obj)
        db.session.commit()
        return jsonify(["Quiz deleted", "success"])
    return jsonify(["Failed to delete", "error"])

@bp.route('/quiz-attempts/<int:quiz_id>')
@login_required
def quiz_attempts(quiz_id):
    quiz_obj = db.session.get(Quiz, quiz_id)
    if not quiz_obj or quiz_obj.user_id != current_user.id:
        current_app.logger.warning(
            "[quiz_attempts] Quiz not found or unauthorized — quiz_id=%s, user_id=%s",
            quiz_id,
            current_user.id,
        )
        return jsonify({"error": "Quiz not found"}), 404
    attempts_data = [
        {
            "correct_answers": attempt.correct_answers,
            "incorrect_answers": attempt.incorrect_answers,
            "unanswered": attempt.unanswered,
            "total_questions": attempt.correct_answers + attempt.incorrect_answers + attempt.unanswered,
            "percentage_score": round((attempt.correct_answers * 100.0 / (attempt.correct_answers + attempt.incorrect_answers + attempt.unanswered)), 2) if (attempt.correct_answers + attempt.incorrect_answers + attempt.unanswered) > 0 else 0.0
        }
        for attempt in quiz_obj.attempts
    ]
    averages = {
        "average_correct": sum(a["correct_answers"] for a in attempts_data) / len(attempts_data) if attempts_data else 0,
        "average_incorrect": sum(a["incorrect_answers"] for a in attempts_data) / len(attempts_data) if attempts_data else 0,
        "average_unanswered": sum(a["unanswered"] for a in attempts_data) / len(attempts_data) if attempts_data else 0,
        "average_percentage": sum(a["percentage_score"] for a in attempts_data) / len(attempts_data) if attempts_data else 0
    }
    return jsonify({"attempts": attempts_data[::-1], "averages": averages})  # Return attempts in reverse order (most recent first)

@bp.route("/practice-hub")
@login_required
def practice_hub():
    all_flashcards = db.session.scalars(
        db.select(Flashcard)
        .where(Flashcard.user_id == current_user.id)
        .where(Flashcard.is_saved == True)
    ).all()
    all_quizzes = db.session.scalars(
        db.select(Quiz)
        .where(Quiz.user_id == current_user.id)
        .where(Quiz.is_saved == True)
    ).all()

    all_attempts = []
    all_tags = []
    quiz_stats_by_tag = {}
    overall_stats = {}
    graph_data = None
    recent_attempts_graph_data = None

    if all_quizzes:
        for quiz in all_quizzes:
            all_attempts.extend(quiz.attempts)
            all_tags.extend(quiz.tags)

        # Overall Percentages
        all_correct_percentages = [
            (a.correct_answers * 100.0 / (a.correct_answers + a.incorrect_answers + a.unanswered))
            for a in all_attempts if (a.correct_answers + a.incorrect_answers + a.unanswered) > 0
        ]
        all_incorrect_percentages = [
            (a.incorrect_answers * 100.0 / (a.correct_answers + a.incorrect_answers + a.unanswered))
            for a in all_attempts if (a.correct_answers + a.incorrect_answers + a.unanswered) > 0
        ]
        all_unanswered_percentages = [
            (a.unanswered * 100.0 / (a.correct_answers + a.incorrect_answers + a.unanswered))
            for a in all_attempts if (a.correct_answers + a.incorrect_answers + a.unanswered) > 0
        ]

        average_correct_answers_percentage = round(sum(all_correct_percentages) / len(all_correct_percentages), 2) if all_correct_percentages else 0.0
        average_incorrect_answers_percentage = round(sum(all_incorrect_percentages) / len(all_incorrect_percentages), 2) if all_incorrect_percentages else 0.0
        average_unanswered_percentage = round(sum(all_unanswered_percentages) / len(all_unanswered_percentages), 2) if all_unanswered_percentages else 0.0

        # Overall Most Recent 5 Attempts
        recent_attempts = sorted(all_attempts, key=lambda a: a.attempted_at, reverse=True)[:5]
        
        recent_correct = [
            (a.correct_answers * 100.0 / (a.correct_answers + a.incorrect_answers + a.unanswered))
            for a in recent_attempts if (a.correct_answers + a.incorrect_answers + a.unanswered) > 0
        ]
        recent_incorrect = [
            (a.incorrect_answers * 100.0 / (a.correct_answers + a.incorrect_answers + a.unanswered))
            for a in recent_attempts if (a.correct_answers + a.incorrect_answers + a.unanswered) > 0
        ]
        recent_unanswered = [
            (a.unanswered * 100.0 / (a.correct_answers + a.incorrect_answers + a.unanswered))
            for a in recent_attempts if (a.correct_answers + a.incorrect_answers + a.unanswered) > 0
        ]

        recent_attempts_data = {
            'recent_attempts_average_correct': round(sum(recent_correct) / len(recent_correct), 2) if recent_correct else 0.0,
            'recent_attempts_average_incorrect': round(sum(recent_incorrect) / len(recent_incorrect), 2) if recent_incorrect else 0.0,
            'recent_attempts_average_unanswered': round(sum(recent_unanswered) / len(recent_unanswered), 2) if recent_unanswered else 0.0
        }

        overall_stats = {
            "total_quizzes": len(all_quizzes),
            "average_correct_answers_percentage": average_correct_answers_percentage,
            "average_incorrect_answers_percentage": average_incorrect_answers_percentage,
            "average_unanswered_percentage": average_unanswered_percentage,
            "recent_attempts_data": recent_attempts_data
        }

        # Process Tag Metrics
        tag_counts = {}
        for tag in all_tags:
            clean_tag = tag.strip()
            tag_counts[clean_tag] = tag_counts.get(clean_tag, 0) + 1

        capitalised_default_tags = [tag.title() for tag in DEFAULT_TAGS]
        main_tags = list(set([tag.title() for tag, count in tag_counts.items() if count > 2 or tag.title() in capitalised_default_tags]))

        if main_tags:
            for tag in main_tags:
                related_quizzes = [quiz for quiz in all_quizzes if tag.lower() in [t.lower() for t in quiz.tags]]
                tag_attempts = []
                for quiz in related_quizzes:
                    tag_attempts.extend(quiz.attempts)

                # Tag Overall Averages
                tag_correct = [
                    (a.correct_answers * 100.0 / (a.correct_answers + a.incorrect_answers + a.unanswered))
                    for a in tag_attempts if (a.correct_answers + a.incorrect_answers + a.unanswered) > 0
                ]
                tag_incorrect = [
                    (a.incorrect_answers * 100.0 / (a.correct_answers + a.incorrect_answers + a.unanswered))
                    for a in tag_attempts if (a.correct_answers + a.incorrect_answers + a.unanswered) > 0
                ]
                tag_unanswered = [
                    (a.unanswered * 100.0 / (a.correct_answers + a.incorrect_answers + a.unanswered))
                    for a in tag_attempts if (a.correct_answers + a.incorrect_answers + a.unanswered) > 0
                ]

                # Tag Recent 5 Attempts 
                recent_tag_attempts = sorted(tag_attempts, key=lambda a: a.attempted_at, reverse=True)[:5]
                
                tag_recent_correct = [
                    (a.correct_answers * 100.0 / (a.correct_answers + a.incorrect_answers + a.unanswered))
                    for a in recent_tag_attempts if (a.correct_answers + a.incorrect_answers + a.unanswered) > 0
                ]
                tag_recent_incorrect = [
                    (a.incorrect_answers * 100.0 / (a.correct_answers + a.incorrect_answers + a.unanswered))
                    for a in recent_tag_attempts if (a.correct_answers + a.incorrect_answers + a.unanswered) > 0
                ]
                tag_recent_unanswered = [
                    (a.unanswered * 100.0 / (a.correct_answers + a.incorrect_answers + a.unanswered))
                    for a in recent_tag_attempts if (a.correct_answers + a.incorrect_answers + a.unanswered) > 0
                ]

                quiz_stats_by_tag[tag] = {
                    "total_quizzes": len(related_quizzes),
                    "average_correct_answers_percentage": round(sum(tag_correct) / len(tag_correct), 2) if tag_correct else 0.0,
                    "average_incorrect_answers_percentage": round(sum(tag_incorrect) / len(tag_incorrect), 2) if tag_incorrect else 0.0,
                    "average_unanswered_percentage": round(sum(tag_unanswered) / len(tag_unanswered), 2) if tag_unanswered else 0.0,
                    "recent_attempts_data": {
                        "recent_attempts_average_correct": round(sum(tag_recent_correct) / len(tag_recent_correct), 2) if tag_recent_correct else 0.0,
                        "recent_attempts_average_incorrect": round(sum(tag_recent_incorrect) / len(tag_recent_incorrect), 2) if tag_recent_incorrect else 0.0,
                        "recent_attempts_average_unanswered": round(sum(tag_recent_unanswered) / len(tag_recent_unanswered), 2) if tag_recent_unanswered else 0.0,
                    }
                }

            graph_data = {
                "tags": list(quiz_stats_by_tag.keys()),
                "average_correct_answers_percentages": [stats["average_correct_answers_percentage"] for stats in quiz_stats_by_tag.values()],
                "average_incorrect_answers_percentages": [stats["average_incorrect_answers_percentage"] for stats in quiz_stats_by_tag.values()],
                "average_unanswered_percentages": [stats["average_unanswered_percentage"] for stats in quiz_stats_by_tag.values()]
            }
            recent_attempts_graph_data = {
                "tags": list(quiz_stats_by_tag.keys()),
                "recent_attempts_average_correct": [stats["recent_attempts_data"]["recent_attempts_average_correct"] for stats in quiz_stats_by_tag.values()],
                "recent_attempts_average_incorrect": [stats["recent_attempts_data"]["recent_attempts_average_incorrect"] for stats in quiz_stats_by_tag.values()],
                "recent_attempts_average_unanswered": [stats["recent_attempts_data"]["recent_attempts_average_unanswered"] for stats in quiz_stats_by_tag.values()]
            }

    return render_template(
        "practice-hub.html",
        flashcards=all_flashcards,
        quizzes=all_quizzes,
        saved_flashcards=len(all_flashcards),
        saved_quizzes=len(all_quizzes),
        overall_stats=overall_stats,
        quiz_stats_by_tag=quiz_stats_by_tag,
        graph_data=graph_data,
        recent_attempts_graph_data=recent_attempts_graph_data
    )
