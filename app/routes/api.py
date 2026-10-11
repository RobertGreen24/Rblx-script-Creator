"""JSON API used by the JavaScript in the builder, editor and snippets pages."""

from __future__ import annotations

import io
import json

from flask import Blueprint, jsonify, request, send_file

from .. import db
from ..features import (
    ALL_FEATURES,
    build_scripts,
    build_zip,
    catalogue,
    normalise_config,
    preview_code,
)

bp = Blueprint("api", __name__)


def _json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


def _config_from(data: dict) -> dict:
    """Pull a builder config out of a JSON body or a form field."""
    raw = data.get("config") if "config" in data else data
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    return normalise_config(raw)


def _payload() -> dict:
    if request.is_json:
        return request.get_json(silent=True) or {}
    if request.form:
        return request.form.to_dict(flat=True)
    try:
        return json.loads(request.get_data(as_text=True) or "{}")
    except ValueError:
        return {}


# ----------------------------------------------------------------- features -- #


@bp.get("/features")
def features():
    return jsonify({"ok": True, "categories": catalogue(), "count": len(ALL_FEATURES)})


@bp.post("/build")
def build():
    data = _payload()
    config = _config_from(data)
    if not config["features"]:
        return _json_error("Pick at least one feature before generating.")
    scripts = build_scripts(config)
    if not scripts:
        return _json_error("None of those features produced any code.")
    return jsonify(
        {
            "ok": True,
            "scripts": scripts,
            "preview": preview_code(config),
            "file_count": len(scripts),
            "lines": sum(script["code"].count("\n") for script in scripts),
        }
    )


@bp.post("/download")
def download():
    data = _payload()
    config = _config_from(data)
    if not config["features"]:
        return _json_error("Nothing to download - pick some features first.")

    archive = build_zip(config)
    name = "robloxforge-project.zip"
    return send_file(
        io.BytesIO(archive),
        mimetype="application/zip",
        as_attachment=True,
        download_name=name,
    )


# ----------------------------------------------------------------- projects -- #


@bp.get("/projects")
def list_projects():
    conn = db.get_db()
    rows = conn.execute(
        "SELECT id, name, description, script_type, source, starred, updated_at FROM projects "
        "ORDER BY starred DESC, updated_at DESC"
    ).fetchall()
    return jsonify({"ok": True, "projects": [dict(row) for row in rows]})


@bp.post("/projects")
def create_project():
    data = _payload()
    name = (data.get("name") or "").strip()
    if not name:
        return _json_error("Give the project a name.")

    script_type = data.get("script_type") or "server"
    if script_type not in ("server", "client", "module"):
        return _json_error("script_type must be server, client or module.")

    conn = db.get_db()
    now = db.utcnow()
    cursor = conn.execute(
        """INSERT INTO projects
           (name, description, script_type, source, config, code, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            name[:120],
            (data.get("description") or "")[:400],
            script_type,
            data.get("source") or "editor",
            json.dumps(data.get("config") or {}),
            data.get("code") or "",
            now,
            now,
        ),
    )
    conn.commit()
    return jsonify({"ok": True, "id": cursor.lastrowid, "message": f"Saved '{name}'."})


@bp.get("/projects/<int:project_id>")
def get_project(project_id: int):
    row = db.get_db().execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        return _json_error("That project no longer exists.", 404)
    project = dict(row)
    project["config"] = json.loads(project["config"] or "{}")
    return jsonify({"ok": True, "project": project})


@bp.patch("/projects/<int:project_id>")
def update_project(project_id: int):
    data = _payload()
    conn = db.get_db()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        return _json_error("That project no longer exists.", 404)

    fields, values = [], []
    for column in ("name", "description", "code", "script_type"):
        if column in data and data[column] is not None:
            fields.append(f"{column} = ?")
            values.append(str(data[column]))
    if "starred" in data:
        fields.append("starred = ?")
        values.append(1 if data["starred"] in (True, "true", 1, "1") else 0)
    if "config" in data:
        fields.append("config = ?")
        values.append(json.dumps(data["config"]))

    if not fields:
        return _json_error("Nothing to update.")

    fields.append("updated_at = ?")
    values.append(db.utcnow())
    values.append(project_id)
    conn.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    return jsonify({"ok": True, "message": "Project updated."})


@bp.delete("/projects/<int:project_id>")
def delete_project(project_id: int):
    conn = db.get_db()
    cursor = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    if cursor.rowcount == 0:
        return _json_error("That project no longer exists.", 404)
    return jsonify({"ok": True, "message": "Project deleted."})


# ----------------------------------------------------------------- snippets -- #


@bp.get("/snippets")
def list_snippets():
    conn = db.get_db()
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

    rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    for row in rows:
        row["tag_list"] = [t for t in (row.get("tags") or "").split(",") if t]
    return jsonify({"ok": True, "snippets": rows, "count": len(rows)})


@bp.post("/snippets")
def create_snippet():
    data = _payload()
    title = (data.get("title") or "").strip()
    code = data.get("code") or ""
    if not title:
        return _json_error("Your snippet needs a title.")
    if not code.strip():
        return _json_error("Your snippet needs some code.")

    conn = db.get_db()
    cursor = conn.execute(
        """INSERT INTO snippets
           (title, category, summary, code, tags, script_type, builtin, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
        (
            title[:120],
            (data.get("category") or "My snippets").strip()[:60] or "My snippets",
            (data.get("summary") or "").strip()[:300],
            code,
            (data.get("tags") or "").strip()[:200],
            data.get("script_type") or "server",
            db.utcnow(),
        ),
    )
    conn.commit()
    return jsonify({"ok": True, "id": cursor.lastrowid, "message": f"Saved snippet '{title}'."})


@bp.delete("/snippets/<int:snippet_id>")
def delete_snippet(snippet_id: int):
    conn = db.get_db()
    row = conn.execute("SELECT builtin FROM snippets WHERE id = ?", (snippet_id,)).fetchone()
    if row is None:
        return _json_error("That snippet no longer exists.", 404)
    if row["builtin"]:
        return _json_error("Built-in snippets cannot be deleted.", 403)
    conn.execute("DELETE FROM snippets WHERE id = ?", (snippet_id,))
    conn.commit()
    return jsonify({"ok": True, "message": "Snippet deleted."})
