from flask import Blueprint

bp = Blueprint("practice", __name__)

from . import routes  # noqa: E402, F401