from flask import Blueprint

bp = Blueprint("notes", __name__)

from . import routes  # noqa: E402, F401