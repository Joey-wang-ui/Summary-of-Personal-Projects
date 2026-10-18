import base64
import socket
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import Store, ValidationError, validate_project
from metadata import PageMetadata, normalize_url, public_target, website_preview
import test_app
from test_app import project


class MetadataTests(unittest.TestCase):
    def test_url_normalization_and_unsafe_schemes(self):
        self.assertEqual(normalize_url("example.com/work"), "https://example.com/work")
        self.assertEqual(normalize_url("https://example.com/作品"), "https://example.com/%E4%BD%9C%E5%93%81")
        for value in ("javascript:alert(1)", "file:///etc/passwd", "https://user:password@example.com", "https://example.com/hello\nworld"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_url(value)

    def test_open_graph_metadata_with_relative_image(self):
        html = '''<html><head><title>Fallback title</title>
        <meta property="og:title" content="我的工具 &amp; 作品">
        <meta name="description" content="自动生成卡片的测试">
        <meta property="og:image" content="/cover.png"></head></html>'''
        with patch("metadata.public_target"):
            result = website_preview("example.com/project", fetcher=lambda url: (html, "https://example.com/project"))
        self.assertTrue(result["metadata_loaded"])
        self.assertEqual(result["name"], "我的工具 & 作品")
        self.assertEqual(result["cover_url"], "https://example.com/cover.png")

    def test_offline_still_produces_a_card(self):
        def unavailable(url):
            raise OSError("offline")
        result = website_preview("https://example.com/my-app", fetcher=unavailable)
        self.assertEqual(result["url"], "https://example.com/my-app")
        self.assertEqual(result["name"], "example.com")
        self.assertFalse(result["metadata_loaded"])

    def test_does_not_fetch_private_networks(self):
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"):
            with self.subTest(address=address), patch("metadata.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 80))]), self.assertRaises(ValueError):
                public_target("http://example.com")

    def test_proxy_dns_is_supported_without_allowing_local_hosts(self):
        with patch("metadata.socket.getaddrinfo", side_effect=socket.gaierror()), patch("metadata.getproxies", return_value={"https":"http://configured-proxy"}), patch("metadata.proxy_bypass", return_value=False):
            public_target("https://github.com/example/project")
            for value in ("https://localhost", "https://127.0.0.1", "https://app.internal"):
                with self.assertRaises(ValueError):
                    public_target(value)

    def test_invalid_images_and_long_titles(self):
        with patch("metadata.public_target"):
            result = website_preview("example.com", fetcher=lambda url: ('<title>'+"字"*300+'</title><meta property="og:image" content="javascript:alert(1)">', url))
        self.assertEqual(len(result["name"]), 120)
        self.assertEqual(result["cover_url"], "")
        with self.assertRaises(ValidationError):
            validate_project(project(cover_url="data:image/svg+xml;base64,PHN2Zz4="))
        with self.assertRaises(ValidationError):
            validate_project(project(cover_url="data:image/png;base64,"+base64.b64encode(b"not a png").decode()))


class CategoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "library.sqlite3"
        self.store = Store(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_empty_category_persists_and_can_be_renamed(self):
        self.store.save_category({"name": "网站作品", "color": "blue"})
        self.assertIn({"name": "网站作品", "color": "blue"}, Store(self.path).categories())
        saved = self.store.create(project(category="网站作品", url="https://example.com/my-app"))
        self.store.save_category({"name": "我的网站", "color": "green"}, "网站作品")
        self.assertEqual(self.store.list()[0]["category"], "我的网站")
        self.assertEqual(self.store.list()[0]["notes"], saved["notes"])
        self.assertEqual(self.store.delete_category("我的网站"), {"moved": 1})
        self.assertEqual(self.store.list()[0]["category"], "未分类")

    def test_duplicate_category_and_reserved_default(self):
        self.store.save_category({"name": "作品", "color": "blue"})
        for operation in (lambda: self.store.save_category({"name": "作品"}), lambda: self.store.delete_category("未分类"), lambda: self.store.save_category({"name": "其他"}, "未分类")):
            with self.assertRaises(ValidationError):
                operation()

    def test_duplicate_link_and_case_sensitive_paths(self):
        saved = self.store.create(project(url="https://example.com/Work"))
        with self.assertRaises(ValidationError):
            self.store.create(project(url="https://example.com/Work#section"))
        self.store.update(saved["id"], {**saved, "favorite": True})
        self.store.create(project(url="https://example.com/work"))
        self.assertEqual(len(self.store.list()), 2)

    def test_old_backup_and_new_backup_with_covers(self):
        self.store.import_projects([project()])
        cover = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nexample").decode()
        saved = self.store.create(project(name="新卡片", url="https://example.com", repo_url="", cover_url=cover))
        other = Store(Path(self.temp.name) / "other.sqlite3")
        other.import_projects(self.store.list(), self.store.categories()+[{"name":"空分类","color":"blue"}])
        self.assertEqual(next(p for p in other.list() if p["name"]=="新卡片")["cover_url"], cover)
        self.assertIn({"name":"空分类","color":"blue"}, other.categories())
        self.assertEqual(other.import_projects(self.store.list()), {"added":0,"skipped":2})

    def test_invalid_category_backup_does_not_write_projects(self):
        with self.assertRaises(ValidationError):
            self.store.import_projects([project()], [{"name":"bad","color":"invalid"}])
        self.assertEqual(self.store.list(), [])

    def test_legacy_database_migrates_without_losing_notes(self):
        path = Path(self.temp.name) / "old.sqlite3"
        with sqlite3.connect(path) as conn:
            conn.execute("""CREATE TABLE projects (
                id INTEGER PRIMARY KEY, name TEXT, description TEXT, category TEXT, status TEXT,
                tags TEXT, repo_url TEXT, demo_url TEXT, local_path TEXT, notes TEXT,
                favorite INTEGER, created_at TEXT, updated_at TEXT)""")
            conn.execute("INSERT INTO projects VALUES (1,'旧项目','','旧分类','进行中','[]','','','','保留原笔记',0,'2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00')")
        migrated = Store(path)
        self.assertEqual(migrated.list()[0]["notes"], "保留原笔记")
        self.assertEqual(migrated.list()[0]["url"], "")
        self.assertIn({"name":"旧分类","color":"violet"}, migrated.categories())
        self.assertEqual(Store(path).list(), migrated.list())


class CardHTTPTests(test_app.HTTPFixture):
    def test_add_url_and_offline_fallback(self):
        with patch("metadata.fetch_page", side_effect=OSError("offline")):
            status, result = self.request("/api/links", "POST", {"url":"example.com/demo","category":"网站作品"})
        self.assertEqual(status, 201)
        self.assertEqual(result["project"]["name"], "example.com")
        self.assertFalse(result["metadata_loaded"])
        self.assertEqual(self.request("/api/links", "POST", {"url":"https://example.com/demo"})[0], 400)
        self.assertEqual(self.request("/api/links", "POST", {"url":"javascript:alert(1)"})[0], 400)

    def test_categories_and_full_backup(self):
        self.assertEqual(self.request("/api/categories", "POST", {"name":"Website","color":"blue"})[0], 201)
        self.request("/api/projects", "POST", project(category="Website"))
        self.assertEqual(self.request("/api/categories/Website", "PUT", {"name":"Works","color":"rose"})[0], 200)
        self.assertEqual(self.request("/api/projects")[1]["projects"][0]["category"], "Works")
        backup = self.request("/api/export")[1]
        self.assertEqual(backup["version"], 2)
        self.assertIn({"name":"Works","color":"rose"}, backup["categories"])
        self.assertEqual(self.request("/api/categories/Works", "DELETE")[1], {"moved":1})
        self.assertEqual(self.request("/local-store.js")[0], 200)
