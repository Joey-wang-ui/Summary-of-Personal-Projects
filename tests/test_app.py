import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app import AppServer, Store, ValidationError, github_projects, validate_project


def project(**changes):
    return {"name": "AI 实验室", "description": "我的学习项目", "category": "学习", "status": "进行中", "tags": ["Python", "AI"], "repo_url": "https://github.com/example/ai-lab", "notes": "下一步：实现工具调用。", **changes}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "projects.sqlite3"
        self.store = Store(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_create_update_restart_delete(self):
        saved = self.store.create(project())
        self.assertEqual(saved["tags"], ["Python", "AI"])
        updated = self.store.update(saved["id"], {**saved, "name": "已完成的项目", "status": "已完成", "favorite": True})
        restarted = Store(self.path)
        self.assertEqual(restarted.list()[0], updated)
        self.assertEqual(updated["created_at"], saved["created_at"])
        self.assertGreater(updated["updated_at"], saved["updated_at"])
        restarted.delete(saved["id"])
        self.assertEqual(self.store.list(), [])
        with self.assertRaises(KeyError):
            self.store.delete(saved["id"])

    def test_import_preserves_notes_and_deduplicates(self):
        saved = self.store.create(project())
        result = self.store.import_projects([
            project(notes="不应覆盖原笔记", repo_url="https://GITHUB.com/EXAMPLE/AI-LAB/"),
            project(name="本地工具", repo_url="", notes="仅本地记录"),
            project(name="本地工具", repo_url="", notes="仅本地记录"),
        ])
        self.assertEqual(result, {"added": 1, "skipped": 2})
        self.assertEqual(next(p for p in self.store.list() if p["id"] == saved["id"])["notes"], saved["notes"])
        repeat = self.store.import_projects(self.store.list())
        self.assertEqual(repeat, {"added": 0, "skipped": 2})

    def test_invalid_import_is_atomic(self):
        with self.assertRaises(ValidationError):
            self.store.import_projects([project(), project(name="")])
        self.assertEqual(self.store.list(), [])

    def test_backup_preserves_dates_and_rejects_invalid_dates(self):
        saved = self.store.create(project())
        restored = Store(Path(self.temp.name) / "restored.sqlite3")
        restored.import_projects([saved])
        self.assertEqual(restored.list()[0]["created_at"], saved["created_at"])
        self.assertEqual(restored.list()[0]["updated_at"], saved["updated_at"])
        with self.assertRaises(ValidationError):
            restored.import_projects([project(name="应该不写入", repo_url=""), {**project(), "updated_at": "bad date"}])
        self.assertEqual(len(restored.list()), 1)

    def test_user_text_is_not_sql(self):
        text = "Robert'); DROP TABLE projects;-- <script>alert(1)</script>"
        saved = self.store.create(project(name=text, notes=text))
        self.assertEqual(self.store.list()[0]["notes"], text)
        self.store.create(project(name="第二个项目"))
        self.assertEqual(len(self.store.list()), 2)
        self.assertEqual(saved["name"], text)

    def test_favorites_are_first(self):
        self.store.create(project(name="收藏", favorite=True))
        self.store.create(project(name="最新"))
        self.assertEqual(self.store.list()[0]["name"], "收藏")


class ValidationTests(unittest.TestCase):
    def test_invalid_fields_rejected(self):
        for changes in ({"name": " "}, {"status": "unknown"}, {"tags": "Python"}, {"favorite": "false"}, {"repo_url": "javascript:alert(1)"}, {"demo_url": "https://user:password@example.com"}, {"notes": "a" * 20001}):
            with self.subTest(changes=list(changes)):
                with self.assertRaises(ValidationError):
                    validate_project(project(**changes))

    def test_defaults_and_tag_normalization(self):
        value = validate_project({"name": "  本地项目  ", "tags": ["Python", " Python ", ""]})
        self.assertEqual(value["name"], "本地项目")
        self.assertEqual(value["tags"], ["Python"])
        self.assertEqual(value["status"], "计划中")
        self.assertEqual(value["category"], "未分类")


class GitHubTests(unittest.TestCase):
    @staticmethod
    def repo(index=1, **changes):
        return {"name": f"project-{index}", "description": "介绍", "language": "Python", "topics": ["ai"], "html_url": f"https://github.com/example/project-{index}", "homepage": "https://example.com", "archived": False, **changes}

    def test_mapping_and_archive_status(self):
        data = [self.repo(), self.repo(2, archived=True, homepage="javascript:alert(1)")]
        result = github_projects("example", opener=lambda *a, **kw: io.BytesIO(json.dumps(data).encode()))
        self.assertFalse(result["truncated"])
        self.assertEqual(result["projects"][0]["tags"], ["Python", "ai"])
        self.assertEqual(result["projects"][0]["status"], "计划中")
        self.assertEqual(result["projects"][1]["status"], "已归档")
        self.assertEqual(result["projects"][1]["demo_url"], "")

    def test_pagination(self):
        requests = []
        def opener(request, **kwargs):
            requests.append(request.full_url)
            rows = [self.repo(i) for i in range(100)] if len(requests) == 1 else [self.repo(100)]
            return io.BytesIO(json.dumps(rows).encode())
        result = github_projects("example", opener=opener)
        self.assertEqual(len(result["projects"]), 101)
        self.assertIn("page=2", requests[1])

    def test_network_errors_are_explained(self):
        for error in (URLError("offline"), HTTPError("https://api.github.com", 403, "rate limited", {}, None), HTTPError("https://api.github.com", 404, "not found", {}, None)):
            def opener(*args, **kwargs):
                raise error
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(ValidationError):
                    github_projects("example", opener=opener)

    def test_username_cannot_change_destination(self):
        for username in ("https://github.com/a", "../private", "a?x=y", "", "a" * 40):
            with self.subTest(username=username):
                with self.assertRaises(ValidationError):
                    github_projects(username)

    def test_public_page_fallback_and_pagination(self):
        requests = []
        def opener(request, **kwargs):
            requests.append(request.full_url)
            if request.full_url.startswith("https://api.github.com/"):
                raise URLError("API not reachable")
            page = 1 if "page=1" in request.full_url else 2
            html = f'''<div id="user-repositories-list"><ul>
              <li itemprop="owns" class="public source"><div><h3>
              <a itemprop="name codeRepository" href="/example/project-{page}"> project-{page} </a>
              </h3><p itemprop="description">My <a href="#">tool</a> &amp; notes</p>
              <span itemprop="programmingLanguage">Python</span></div></li></ul></div>'''
            if page == 1:
                html += '<a class="next_page" href="?page=2">Next</a>'
            return io.BytesIO(html.encode())
        result = github_projects("example", opener=opener)
        self.assertEqual(result["source"], "public-page")
        self.assertFalse(result["truncated"])
        self.assertEqual(len(result["projects"]), 2)
        self.assertEqual(result["projects"][0]["description"], "My tool & notes")
        self.assertEqual(result["projects"][1]["repo_url"], "https://github.com/example/project-2")
        self.assertEqual(len(requests), 3)

    def test_unrecognized_public_page_is_not_an_empty_success(self):
        def opener(request, **kwargs):
            if request.full_url.startswith("https://api.github.com/"):
                raise URLError("API unavailable")
            return io.BytesIO(b'<html><body>Sign in</body></html>')
        with self.assertRaises(ValidationError):
            github_projects("example", opener=opener)


class HTTPFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = AppServer(("127.0.0.1", 0), Path(self.temp.name) / "projects.sqlite3")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.token = self.request("/api/bootstrap")[1]["token"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, method="GET", body=None, token=True, host=None):
        headers = {"Content-Type": "application/json"}
        if token and hasattr(self, "token"):
            headers["X-Local-Token"] = self.token
        if host:
            headers["Host"] = host
        request = Request(self.base + path, method=method, headers=headers, data=None if body is None else json.dumps(body).encode())
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if "application/json" in response.headers["Content-Type"] else raw


class HTTPTests(HTTPFixture):
    def test_static_and_crud_and_backup(self):
        for asset in ("/", "/app.js", "/style.css"):
            self.assertEqual(self.request(asset)[0], 200)
        status, created = self.request("/api/projects", "POST", project())
        self.assertEqual(status, 201)
        status, updated = self.request(f'/api/projects/{created["id"]}', "PUT", {**created, "notes": "记录已更新"})
        self.assertEqual(status, 200)
        self.assertEqual(updated["notes"], "记录已更新")
        backup = self.request("/api/export")[1]
        self.assertEqual(backup["projects"][0]["notes"], "记录已更新")
        self.assertEqual(self.request(f'/api/projects/{created["id"]}', "DELETE")[0], 200)
        self.assertEqual(self.request("/api/projects")[1]["projects"], [])
        self.assertEqual(self.request("/api/import", "POST", backup)[1], {"added": 1, "skipped": 0})
        self.assertEqual(self.request("/api/import", "POST", backup)[1], {"added": 0, "skipped": 1})

    def test_mutation_requires_local_token_and_valid_host(self):
        self.assertEqual(self.request("/api/projects", "POST", project(), token=False)[0], 403)
        self.assertEqual(self.request("/api/bootstrap", host="untrusted.example")[0], 403)
        self.assertEqual(self.request("/api/projects")[1]["projects"], [])

    def test_invalid_backup_and_unknown_project(self):
        self.assertEqual(self.request("/api/import", "POST", {"projects": []})[0], 400)
        self.assertEqual(self.request("/api/projects/999", "PUT", project())[0], 404)
        self.assertEqual(self.request("/api/projects/999", "DELETE")[0], 404)
        self.assertEqual(self.request("/../app.py")[0], 404)

    def test_github_preview_does_not_write(self):
        with patch("app.github_projects", return_value={"projects": [validate_project(project())], "truncated": False}):
            status, data = self.request("/api/github?username=example")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["projects"]), 1)
        self.assertEqual(self.request("/api/projects")[1]["projects"], [])


if __name__ == "__main__":
    unittest.main()
