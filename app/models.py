from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flask_login import UserMixin
from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db


class Note(db.Model):
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    html_content: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    md_content: Mapped[str] = mapped_column(Text, nullable=True, default=None)
    in_bin: Mapped[bool] = mapped_column(Boolean, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    meta_data: Mapped[Dict[str, Any]] = mapped_column(JSON)
    last_opened: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    mermaid_needs_conversion: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


class User(db.Model, UserMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(1000), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    notes = relationship("Note", backref="author", lazy=True)


class Flashcard(db.Model):
    __tablename__ = "flashcards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_data: Mapped[Dict[str, Any]] = mapped_column(JSON)
    is_saved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    incorrect_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class Quiz(db.Model):
    __tablename__ = "quizzes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_data: Mapped[Dict[str, Any]] = mapped_column(JSON)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    is_saved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    tags: Mapped[List[str]] = mapped_column(JSON, nullable=True, default=list)
    attempts: Mapped[List["QuizAttempt"]] = relationship(
        "QuizAttempt", back_populates="quiz", cascade="all, delete-orphan"
    )


class QuizAttempt(db.Model):
    __tablename__ = "quiz_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(Integer, ForeignKey("quizzes.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    correct_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    incorrect_answers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unanswered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    quiz: Mapped["Quiz"] = relationship("Quiz", back_populates="attempts")


class Diagram(db.Model):
    __tablename__ = "diagrams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    diagram_data: Mapped[Text] = mapped_column(Text, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    note_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notes.id"), nullable=True, default=None
    )
    original_diagram_data: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None
    )
    dirty_since: Mapped[datetime] = mapped_column(DateTime, default=None, nullable=True)