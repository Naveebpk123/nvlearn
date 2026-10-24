from flask import Blueprint

bp = Blueprint("main", __name__)

from . import routes  # noqa: E402, F401


@bp.errorhandler(404)
def page_not_found(error):
    from flask import current_app, render_template, request
    current_app.logger.warning(
        "[404] Page not found: %s %s", request.method, request.url
    )
    return render_template("404.html"), 404