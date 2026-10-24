from flask import Blueprint

bp = Blueprint("diagrams", __name__)

from . import routes  # noqa: E402, F401