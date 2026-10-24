from datetime import datetime, timezone

from flask import (
    current_app, flash, redirect, render_template, request,
    session, url_for, jsonify,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from . import bp
from ..config import Config
from ..extensions import db
from ..models import User
from ..services.auth_service import _clear_pending_auth, _verification_is_valid
from forms import LoginForm, RegisterForm, VerificationForm
from helpers import create_code, send_email_threaded


@bp.route("/register", methods=["GET", "POST"])
def register():
    if session.get("pending_register"):
        form = VerificationForm()
        if form.validate_on_submit():
            is_valid, message = _verification_is_valid(form.code.data.strip())
            if not is_valid:
                flash(message, "error")
                return render_template(
                    "register.html",
                    form=form,
                    show_code=True,
                    verification_email=session.get("pending_auth_email"),
                )
            pending_register = session.get("pending_register")
            try:
                user = User(
                    email=pending_register["email"],
                    name=pending_register["name"],
                    password=pending_register["password"],
                )
                db.session.add(user)
                db.session.commit()
                login_user(user)
                _clear_pending_auth()
                flash(f"Created new account for {user.name}", "success")
                return redirect(url_for("notes.notes"))
            except IntegrityError as e:
                db.session.rollback()
                _clear_pending_auth()
                current_app.logger.warning(
                    "[register] Duplicate email on verification commit: %s", e
                )
                flash("That email address is already registered.", "error")
            except SQLAlchemyError as e:
                db.session.rollback()
                current_app.logger.error("[register] DB error creating user: %s", e)
                flash("An unexpected error occurred. Please try again.", "error")
        return render_template(
            "register.html",
            form=form,
            show_code=True,
            verification_email=session.get("pending_auth_email"),
        )

    form = RegisterForm()
    if form.validate_on_submit():
        try:
            _clear_pending_auth()
            existing_user = db.session.execute(
                db.select(User).where(User.email == form.email.data)
            ).scalar()
            if existing_user:
                flash("That email address is already registered.", "error")
                return render_template("register.html", form=form, show_code=False)

            verification_code = create_code()
            session["pending_register"] = {
                "name": form.name.data,
                "email": form.email.data,
                "password": generate_password_hash(
                    form.password.data, method="pbkdf2:sha256", salt_length=16
                ),
            }
            session["pending_auth_code"] = verification_code
            session["pending_auth_expires_at"] = (
                datetime.now(timezone.utc).timestamp() + Config.VERIFICATION_TTL_SECONDS
            )
            session["pending_auth_email"] = form.email.data
            if not send_email_threaded(
                form.email.data,
                "Your verification code",
                f"Type this 6 digit code to finish your account setup: {verification_code}",
            ):
                raise RuntimeError("Failed to send verification email.")

            flash(f"Type the 6 digit code sent to {form.email.data}.", "success")
            return render_template(
                "register.html",
                form=VerificationForm(),
                show_code=True,
                verification_email=form.email.data,
            )
        except IntegrityError as e:
            db.session.rollback()
            current_app.logger.warning("[register] Duplicate email: %s", e)
            flash("That email address is already registered.", "error")
        except SQLAlchemyError as e:
            db.session.rollback()
            current_app.logger.error("[register] DB error: %s", e)
            flash("An unexpected error occurred. Please try again.", "error")
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("[register] Unexpected error: %s", e)
            flash("Failed to send email. Try to register again.", "error")
    return render_template("register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("pending_login"):
        form = VerificationForm()
        if form.validate_on_submit():
            is_valid, message = _verification_is_valid(form.code.data.strip())
            if not is_valid:
                flash(message, "error")
                return render_template(
                    "login.html",
                    form=form,
                    show_code=True,
                    verification_email=session.get("pending_auth_email"),
                )
            pending_login = session.get("pending_login")
            try:
                user = db.session.get(User, pending_login["user_id"])
                if not user:
                    _clear_pending_auth()
                    flash(
                        "Your account could not be found. Please login again.", "error"
                    )
                    return redirect(url_for("auth.login"))
                login_user(user)
                _clear_pending_auth()
                flash(f"Welcome back {user.name}", "success")
                return redirect(url_for("notes.notes"))
            except SQLAlchemyError as e:
                current_app.logger.error(
                    "[login] DB error during verification: %s", e
                )
                flash("Internal database communication mismatch.", "error")
        return render_template(
            "login.html",
            form=form,
            show_code=True,
            verification_email=session.get("pending_auth_email"),
        )

    form = LoginForm()
    if form.validate_on_submit():
        try:
            _clear_pending_auth()
            user = db.session.execute(
                db.select(User).where(User.email == form.email.data)
            ).scalar()
            if user and check_password_hash(user.password, form.password.data):
                verification_code = create_code()
                session["pending_login"] = {"user_id": user.id}
                session["pending_auth_code"] = verification_code
                session["pending_auth_expires_at"] = (
                    datetime.now(timezone.utc).timestamp()
                    + Config.VERIFICATION_TTL_SECONDS
                )
                session["pending_auth_email"] = user.email
                send_email_threaded(
                    user.email,
                    "Your verification code",
                    f"Type this 6 digit code to finish your login: {verification_code}",
                )
                flash(f"Type the 6 digit code sent to {user.email}.", "success")
                return render_template(
                    "login.html",
                    form=VerificationForm(),
                    show_code=True,
                    verification_email=user.email,
                )
            else:
                flash("Incorrect login credentials.", "error")
        except SQLAlchemyError as e:
            current_app.logger.error(
                "[login] DB error during login for email=%s: %s",
                form.email.data, e,
            )
            flash("Internal database communication mismatch.", "error")
    return render_template("login.html", form=form, show_code=False)

