"""HTTP routes for the page templates."""

from __future__ import annotations

import json

from flask import Blueprint, abort, redirect, render_template, request, url_for

from ..db import get_db
from ..features import ALL_FEATURES, CATEGORIES, normalise_config, preview_code
from ..snippets import SNIPPETS

bp = Blueprint("pages", __name__)


@bp.app_template_filter("json_pretty")
def json_pretty(value) -> str:
    return json.dumps(value, indent=2)


@bp.route("/")
def home():
    featured = [f for f in ALL_FEATURES if f.id in ("sprint", "coin_collect", "kill_brick", "round_system")]
    return render_template(
        "index.html",
        featured=featured,
        categories=CATEGORIES,
        snippet_categories=sorted({s["category"] for s in SNIPPETS}),
        feature_total=len(ALL_FEATURES),
        snippet_total=len(SNIPPETS),
    )


@bp.route("/builder")
def builder():
    preselected = request.args.getlist("feature")
    return render_template(
        "builder.html",
        catalogue=_catalogue(),
        preselected=preselected,
        categories=CATEGORIES,
    )


@bp.route("/builder/result", methods=["POST"])
def builder_result():
    """Non-JS fallback: build server-side and show the preview page."""
    from ..features import build_scripts

    config = _config_from_form()
    scripts = build_scripts(config)
    return render_template(
        "builder_result.html",
        config=config,
        scripts=scripts,
        preview=preview_code(config),
        config_json=json.dumps(config),
    )


@bp.route("/editor")
def editor():
    project_id = request.args.get("project", type=int)
    starter = request.args.get("starter", type=int)
    project = None

    if project_id:
        project = get_db().execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if project is None:
            abort(404)

    template_code = _starter_script(starter) if starter else ""
    return render_template("editor.html", project=project, starter_code=template_code)


@bp.route("/snippets")
def snippets():
    category = request.args.get("category", "")
    query = request.args.get("q", "").strip()

    sql = "SELECT * FROM snippets"
    clauses, params = [], []
    if category:
        clauses.append("category = ?")
        params.append(category)
    if query:
        clauses.append("(title LIKE ? OR summary LIKE ? OR code LIKE ? OR tags LIKE ?)")
        params.extend([f"%{query}%"] * 4)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY builtin DESC, category, title"

    rows = get_db().execute(sql, params).fetchall()
    categories = [row["category"] for row in get_db().execute(
        "SELECT DISTINCT category FROM snippets ORDER BY category"
    ).fetchall()]

    return render_template(
        "snippets.html", snippets=rows, categories=categories, active_category=category, query=query
    )


@bp.route("/project/<int:project_id>")
def project_view(project_id: int):
    project = get_db().execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        abort(404)
    return render_template("project.html", project=project)


@bp.route("/project/<int:project_id>/delete", methods=["POST"])
def project_delete(project_id: int):
    db = get_db()
    db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    db.commit()
    return redirect(url_for("pages.projects"))


@bp.route("/projects")
def projects():
    rows = get_db().execute(
        "SELECT * FROM projects ORDER BY starred DESC, updated_at DESC"
    ).fetchall()
    return render_template("projects.html", projects=rows)


# --------------------------------------------------------------------------- #


def _catalogue() -> list[dict]:
    from ..features import catalogue

    return catalogue()


def _starter_script(starter: int) -> str:
    starter = max(0, min(starter, len(SNIPPETS) - 1))
    return SNIPPETS[starter]["code"].rstrip() + "\n"


def _config_from_form() -> dict:
    """Read a builder configuration out of a plain HTML form post."""
    feature_ids = request.form.getlist("features")
    features = []
    for feature_id in feature_ids:
        feature = next((f for f in ALL_FEATURES if f.id == feature_id), None)
        if feature is None:
            continue
        params = {}
        for param in feature.params:
            field = f"param_{feature_id}_{param.key}"
            if param.kind == "bool":
                params[param.key] = request.form.get(field) == "on"
            else:
                value = request.form.get(field)
                if value not in (None, ""):
                    params[param.key] = value
        features.append({"id": feature_id, "params": params})

    return normalise_config(
        {
            "project_name": request.form.get("project_name") or "My Roblox Project",
            "features": features,
        }
    )
