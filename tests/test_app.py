"""Test suite for RobloxForge.

Run with either:
    python -m unittest discover -s tests -v
    python -m pytest tests -v        (if pytest is installed)
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.features import ALL_FEATURES, build_scripts, build_zip, preview_code  # noqa: E402
from app.snippets import SNIPPETS  # noqa: E402

ALL_IDS = [feature.id for feature in ALL_FEATURES]


class BaseCase(unittest.TestCase):
    def setUp(self) -> None:
        handle, path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        os.unlink(path)
        self.db_path = path
        self.app = create_app(database_path=path)
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(self.db_path + suffix)
            except OSError:
                pass


class TestPages(BaseCase):
    def test_pages_load(self):
        for path in ("/", "/builder", "/editor", "/snippets", "/projects"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"RobloxForge", response.data)

    def test_unknown_project_is_404(self):
        self.assertEqual(self.client.get("/project/9999").status_code, 404)
        self.assertEqual(self.client.get("/editor?project=9999").status_code, 404)

    def test_editor_renders_project_code(self):
        created = self.client.post(
            "/api/projects", json={"name": "Editor demo", "code": "print('hi')"}
        ).get_json()
        response = self.client.get(f"/editor?project={created['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"print(&#39;hi&#39;)", response.data)

    def test_builder_form_post_without_javascript(self):
        response = self.client.post(
            "/builder/result",
            data={
                "project_name": "No JS",
                "features": ["sprint", "kill_brick"],
                "param_sprint_sprint_speed": "42",
                "param_kill_brick_instant_kill": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Sprint.client.luau", response.data)
        self.assertIn(b"KillBrick.server.luau", response.data)


class TestBuilder(BaseCase):
    def test_feature_catalogue_is_complete(self):
        catalogue = self.client.get("/api/features").get_json()
        self.assertTrue(catalogue["ok"])
        ids = [item["id"] for group in catalogue["categories"] for item in group["features"]]
        self.assertEqual(sorted(ids), sorted(ALL_IDS))
        for group in catalogue["categories"]:
            for item in group["features"]:
                self.assertTrue(item["summary"], item["id"])
                self.assertTrue(item["name"], item["id"])

    def test_every_feature_generates_scripts(self):
        for feature_id in ALL_IDS:
            with self.subTest(feature=feature_id):
                response = self.client.post("/api/build", json={"features": [{"id": feature_id}]})
                self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
                payload = response.get_json()
                self.assertGreaterEqual(payload["file_count"], 1)

    def test_every_feature_together(self):
        config = {"project_name": "Everything", "features": [{"id": f} for f in ALL_IDS]}
        payload = self.client.post("/api/build", json=config).get_json()
        self.assertTrue(payload["ok"])
        paths = [script["path"] for script in payload["scripts"]]
        self.assertEqual(len(paths), len(set(paths)), "duplicate output paths")
        self.assertIn("ReplicatedStorage/Shared/StatsAPI.luau", paths)

    def test_build_rejects_empty_selection(self):
        response = self.client.post("/api/build", json={"features": []})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["ok"])

    def test_params_are_coerced_and_clamped(self):
        payload = self.client.post(
            "/api/build",
            json={
                "features": [
                    {
                        "id": "sprint",
                        "params": {"sprint_speed": "99999", "key": "NotAKey", "stamina": "yes"},
                    }
                ]
            },
        ).get_json()
        code = payload["scripts"][0]["code"]
        self.assertIn("local SPRINT_SPEED = 400", code)  # clamped to the max
        self.assertIn("local SPRINT_KEY = Enum.KeyCode.LeftShift", code)  # invalid -> default
        self.assertIn("local STAMINA_ENABLED = true", code)

    def test_generated_code_has_no_template_leftovers(self):
        config = {"features": [{"id": feature_id} for feature_id in ALL_IDS]}
        for script in build_scripts(config):
            with self.subTest(path=script["path"]):
                self.assertNotIn("${", script["code"])
                self.assertNotIn("Traceback", script["code"])
                self.assertNotRegex(script["code"], r"\bNone\b|\bTrue\b|\bFalse\b")
                # every generated luau file should start with a comment banner
                self.assertTrue(script["code"].lstrip().startswith("--"), script["path"])

    def test_script_paths_match_script_type(self):
        config = {"features": [{"id": feature_id} for feature_id in ALL_IDS]}
        for script in build_scripts(config):
            with self.subTest(path=script["path"]):
                if script["script_type"] == "client":
                    self.assertIn("StarterPlayerScripts", script["path"])
                    self.assertTrue(script["path"].endswith(".client.luau"))
                elif script["script_type"] == "server":
                    self.assertIn("ServerScriptService", script["path"])
                    self.assertTrue(script["path"].endswith(".server.luau"))
                else:
                    self.assertIn("ReplicatedStorage", script["path"])
                    self.assertTrue(script["path"].endswith(".luau"))
                    self.assertNotIn(".server.", script["path"])

    def test_stats_module_added_once_and_named_for_stats(self):
        config = {
            "features": [
                {"id": "leaderstats", "params": {"stat_name": "Score", "currency_name": "Gold"}},
                {"id": "coin_collect", "params": {"stat": "Gold"}},
                {"id": "income", "params": {"stat": "Score"}},
            ]
        }
        scripts = build_scripts(config)
        stats = [s for s in scripts if s["path"].endswith("StatsAPI.luau")]
        self.assertEqual(len(stats), 1)
        self.assertIn('"Score"', stats[0]["code"])
        self.assertIn('"Gold"', stats[0]["code"])

    def test_preview_contains_every_file(self):
        config = {"features": [{"id": "sprint"}, {"id": "kill_brick"}]}
        preview = preview_code(config)
        for script in build_scripts(config):
            self.assertIn(script["path"], preview)

    def test_zip_download_structure(self):
        response = self.client.post(
            "/api/download",
            json={
                "project_name": "Zip Test",
                "features": [{"id": "coin_collect"}, {"id": "leaderstats"}],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[:2], b"PK")

        archive = zipfile.ZipFile(io.BytesIO(response.data))
        self.assertIsNone(archive.testzip())
        names = archive.namelist()
        self.assertIn("Zip_Test/default.project.json", names)
        self.assertIn("Zip_Test/README.md", names)
        self.assertTrue(any(name.endswith("CoinCollect.server.luau") for name in names))

        project = json.loads(archive.read("Zip_Test/default.project.json"))
        self.assertEqual(project["name"], "Zip Test")
        self.assertIn("ServerScriptService", project["tree"])

        readme = archive.read("Zip_Test/README.md").decode()
        self.assertIn("Collectable coins", readme)
        self.assertIn("Rojo", readme)

    def test_zip_config_sent_as_form_field(self):
        config = json.dumps({"project_name": "Form Zip", "features": [{"id": "dash"}]})
        response = self.client.post("/api/download", data={"config": config})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[:2], b"PK")

    def test_build_zip_is_deterministic(self):
        config = {"project_name": "Same", "features": [{"id": "sprint"}]}
        self.assertEqual(build_zip(config), build_zip(config))


class TestProjects(BaseCase):
    def test_full_project_lifecycle(self):
        created = self.client.post(
            "/api/projects",
            json={
                "name": "Lifecycle",
                "description": "created in a test",
                "script_type": "server",
                "code": "print('hello')",
            },
        ).get_json()
        self.assertTrue(created["ok"])
        project_id = created["id"]

        fetched = self.client.get(f"/api/projects/{project_id}").get_json()["project"]
        self.assertEqual(fetched["name"], "Lifecycle")
        self.assertEqual(fetched["code"], "print('hello')")

        updated = self.client.patch(
            f"/api/projects/{project_id}",
            json={"code": "print('updated')", "starred": True},
        ).get_json()
        self.assertTrue(updated["ok"])

        fetched = self.client.get(f"/api/projects/{project_id}").get_json()["project"]
        self.assertEqual(fetched["code"], "print('updated')")
        self.assertEqual(fetched["starred"], 1)

        listing = self.client.get("/api/projects").get_json()["projects"]
        self.assertEqual(listing[0]["id"], project_id, "starred project should sort first")

        deleted = self.client.delete(f"/api/projects/{project_id}").get_json()
        self.assertTrue(deleted["ok"])
        self.assertEqual(self.client.get(f"/api/projects/{project_id}").status_code, 404)

    def test_project_validation(self):
        self.assertEqual(self.client.post("/api/projects", json={"name": ""}).status_code, 400)
        self.assertEqual(
            self.client.post("/api/projects", json={"name": "bad", "script_type": "nope"}).status_code,
            400,
        )
        self.assertEqual(
            self.client.patch("/api/projects/424242", json={"name": "x"}).status_code, 404
        )
        self.assertEqual(self.client.delete("/api/projects/424242").status_code, 404)

    def test_projects_page_shows_saved_script(self):
        self.client.post("/api/projects", json={"name": "PAGE-NAME", "code": "print(1)"})
        response = self.client.get("/projects")
        self.assertIn(b"PAGE-NAME", response.data)


class TestSnippets(BaseCase):
    def test_builtins_are_seeded(self):
        payload = self.client.get("/api/snippets").get_json()
        self.assertEqual(payload["count"], len(SNIPPETS))
        self.assertTrue(all(item["builtin"] == 1 for item in payload["snippets"]))

    def test_seeding_is_idempotent(self):
        self.app_context_init()
        payload = self.client.get("/api/snippets").get_json()
        self.assertEqual(payload["count"], len(SNIPPETS))

    def app_context_init(self):
        with self.app.app_context():
            from app import db

            db.init_db()

    def test_search_and_filter(self):
        payload = self.client.get("/api/snippets?q=datastore").get_json()
        self.assertGreaterEqual(payload["count"], 1)
        for snippet in payload["snippets"]:
            haystack = (snippet["title"] + snippet["summary"] + snippet["code"] + snippet["tags"]).lower()
            self.assertIn("datastore", haystack)

        payload = self.client.get("/api/snippets?category=UI").get_json()
        self.assertTrue(all(item["category"] == "UI" for item in payload["snippets"]))

    def test_user_snippets_round_trip(self):
        created = self.client.post(
            "/api/snippets",
            json={"title": "My helper", "code": "return 1", "category": "Mine"},
        ).get_json()
        self.assertTrue(created["ok"])

        payload = self.client.get("/api/snippets?q=My helper").get_json()
        mine = [item for item in payload["snippets"] if item["title"] == "My helper"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["builtin"], 0)
        self.assertEqual(mine[0]["tag_list"], [])

        deleted = self.client.delete(f"/api/snippets/{created['id']}").get_json()
        self.assertTrue(deleted["ok"])

    def test_validation_and_builtin_protection(self):
        self.assertEqual(self.client.post("/api/snippets", json={"title": "no code"}).status_code, 400)
        self.assertEqual(
            self.client.post("/api/snippets", json={"title": "x", "code": "   "}).status_code, 400
        )
        builtin_id = self.client.get("/api/snippets").get_json()["snippets"][0]["id"]
        self.assertEqual(self.client.delete(f"/api/snippets/{builtin_id}").status_code, 403)

    def test_snippets_page_renders(self):
        response = self.client.get("/snippets?q=remote")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Remote", response.data)


class TestSeedContent(BaseCase):
    def test_fresh_install_has_example_projects(self):
        payload = self.client.get("/api/projects").get_json()
        self.assertGreaterEqual(len(payload["projects"]), 1)
        self.assertIn("Example", payload["projects"][0]["name"])

    def test_example_code_is_real(self):
        project = self.client.get("/api/projects").get_json()["projects"][0]
        full = self.client.get(f"/api/projects/{project['id']}").get_json()["project"]
        self.assertGreater(len(full["code"]), 200)
        self.assertIn("--", full["code"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestNoJavaScriptFlow(BaseCase):
    """The builder must work end to end without JS: form -> result page -> zip."""

    def test_form_config_round_trips_through_the_result_page(self):
        import html as html_lib

        response = self.client.post(
            "/builder/result",
            data={"project_name": "Round Trip", "features": ["dash", "leaderstats"]},
        )
        self.assertEqual(response.status_code, 200)

        match = re.search(rb'name="config" value="([^"]+)"', response.data)
        self.assertIsNotNone(match, "result page is missing its download form")
        config_json = html_lib.unescape(match.group(1).decode())

        parsed = json.loads(config_json)
        self.assertEqual(parsed["project_name"], "Round Trip")
        self.assertEqual([entry["id"] for entry in parsed["features"]], ["dash", "leaderstats"])

        download = self.client.post("/api/download", data={"config": config_json})
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data[:2], b"PK")
        names = zipfile.ZipFile(io.BytesIO(download.data)).namelist()
        self.assertIn("Round_Trip/default.project.json", names)
        self.assertTrue(any(name.endswith("Dash.client.luau") for name in names), names)
        self.assertTrue(any(name.endswith("StatsAPI.luau") for name in names), names)
