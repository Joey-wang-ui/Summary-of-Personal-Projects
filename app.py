"""A personal project library. Python standard library only; no cloud storage."""

from __future__ import annotations

import argparse
import base64
import binascii
import hmac
import json
import re
import secrets
import sqlite3
import threading
import webbrowser
from contextlib import contextmanager
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from metadata import normalize_url, website_preview

ROOT = Path(__file__).resolve().parent
STATUSES = ("计划中", "进行中", "已完成", "已归档")
FIELDS = ("name", "description", "category", "status", "tags", "repo_url", "demo_url", "local_path", "notes", "favorite", "url", "cover_url")
MAX_BODY = 50 * 1024 * 1024
COLORS = ("violet", "blue", "green", "orange", "rose", "slate")


class ValidationError(ValueError):
    pass


class GitHubUnavailable(ValidationError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def validate_project(raw):
    if not isinstance(raw, dict):
        raise ValidationError("项目必须是一个对象。")
    result = {}
    for field, limit in (("name", 120), ("description", 2000), ("category", 80),
                         ("status", 20), ("repo_url", 2048), ("demo_url", 2048),
                         ("local_path", 2048), ("notes", 20000), ("url", 2048), ("cover_url", 700000)):
        value = raw.get(field, "")
        if not isinstance(value, str) or len(value) > limit:
            raise ValidationError(f"{field} 格式错误或内容过长。")
        result[field] = value.strip()
    if not result["name"]:
        raise ValidationError("请填写项目名称。")
    result["category"] = result["category"] or "未分类"
    result["status"] = result["status"] or "计划中"
    if result["status"] not in STATUSES:
        raise ValidationError("项目状态无效。")
    for field in ("repo_url", "demo_url", "url"):
        value = result[field]
        if not value:
            continue
        try:
            valid = urlsplit(value).scheme in ("http", "https")
            normalized = normalize_url(value)
        except ValueError:
            valid = False
        if not valid or any(ord(char) < 32 for char in value):
            raise ValidationError("链接必须是有效的 http 或 https 地址，且不能包含账号密码。")
        result[field] = normalized
    cover = result["cover_url"]
    if cover:
        if cover.startswith("data:"):
            match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)", cover)
            try:
                if not match:
                    raise ValueError()
                payload = base64.b64decode(match[2], validate=True)
                correct = (match[1] == "png" and payload.startswith(b"\x89PNG\r\n\x1a\n")) or (match[1] == "jpeg" and payload.startswith(b"\xff\xd8\xff")) or (match[1] == "webp" and payload.startswith(b"RIFF") and payload[8:12] == b"WEBP")
                if not correct:
                    raise ValueError()
            except (ValueError, binascii.Error) as exc:
                raise ValidationError("封面只支持 PNG、JPEG 或 WebP 图片。") from exc
        else:
            try:
                if len(cover) > 2048 or urlsplit(cover).scheme not in ("http", "https"):
                    raise ValueError()
                result["cover_url"] = normalize_url(cover)
            except ValueError as exc:
                raise ValidationError("请填写有效的封面图片网址，或上传图片。") from exc
    tags = raw.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 30 or any(not isinstance(tag, str) or len(tag) > 60 for tag in tags):
        raise ValidationError("标签最多 30 个，每个最多 60 个字符。")
    result["tags"] = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
    favorite = raw.get("favorite", False)
    if not isinstance(favorite, bool):
        raise ValidationError("收藏标记必须是布尔值。")
    result["favorite"] = favorite
    return result


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
                status TEXT NOT NULL, tags TEXT NOT NULL, repo_url TEXT NOT NULL,
                demo_url TEXT NOT NULL, local_path TEXT NOT NULL, notes TEXT NOT NULL,
                favorite INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""")
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(projects)")}
            for column in ("url", "cover_url"):
                if column not in columns:
                    conn.execute(f"ALTER TABLE projects ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
            conn.execute("CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY, color TEXT NOT NULL, created_at TEXT NOT NULL)")
            conn.execute("INSERT OR IGNORE INTO categories VALUES (?,?,?)", ("未分类", "slate", now()))
            conn.execute("INSERT OR IGNORE INTO categories (name,color,created_at) SELECT DISTINCT category,'violet',? FROM projects", (now(),))

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def decode(row):
        if row is None:
            raise KeyError("项目不存在，可能已被删除。")
        project = dict(row)
        project["tags"] = json.loads(project["tags"])
        project["favorite"] = bool(project["favorite"])
        return project

    @staticmethod
    def values(project):
        return tuple(json.dumps(project[key], ensure_ascii=False) if key == "tags" else project[key] for key in FIELDS)

    @classmethod
    def insert(cls, conn, project, created_at=None, updated_at=None):
        timestamp = now()
        conn.execute("INSERT OR IGNORE INTO categories VALUES (?,?,?)", (project["category"], "violet", timestamp))
        cursor = conn.execute(
            "INSERT INTO projects (" + ",".join(FIELDS) + ",created_at,updated_at) VALUES (" + ",".join("?" for _ in range(len(FIELDS) + 2)) + ")",
            cls.values(project) + (created_at or timestamp, updated_at or timestamp),
        )
        return cls.decode(conn.execute("SELECT * FROM projects WHERE id = ?", (cursor.lastrowid,)).fetchone())

    def list(self):
        with self.connect() as conn:
            return [self.decode(row) for row in conn.execute("SELECT * FROM projects ORDER BY favorite DESC, updated_at DESC, id DESC")]

    def create(self, raw):
        project = validate_project(raw)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.check_duplicate(conn, project)
            return self.insert(conn, project)

    def update(self, project_id, raw):
        project = validate_project(raw)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.check_duplicate(conn, project, project_id)
            conn.execute("INSERT OR IGNORE INTO categories VALUES (?,?,?)", (project["category"], "violet", now()))
            cursor = conn.execute(
                "UPDATE projects SET " + ",".join(key + " = ?" for key in FIELDS) + ",updated_at = ? WHERE id = ?",
                self.values(project) + (now(), project_id),
            )
            if cursor.rowcount != 1:
                raise KeyError("项目不存在，可能已被删除。")
            return self.decode(conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())

    def delete(self, project_id):
        with self.connect() as conn:
            if conn.execute("DELETE FROM projects WHERE id = ?", (project_id,)).rowcount != 1:
                raise KeyError("项目不存在，可能已被删除。")

    @staticmethod
    def check_duplicate(conn, project, except_id=None):
        # Old records without a primary URL remain compatible; new pasted links cannot duplicate them.
        if not project["url"]:
            return
        key = url_key(project["url"])
        for row in conn.execute("SELECT id,url,repo_url,demo_url FROM projects"):
            if row["id"] != except_id and any(url_key(row[field]) == key for field in ("url", "repo_url", "demo_url") if row[field]):
                raise ValidationError("这个网址已经收藏过了，可以直接编辑已有卡片。")

    def categories(self):
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT name,color FROM categories ORDER BY created_at,name")]

    def save_category(self, raw, old_name=None):
        category = validate_category(raw)
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if old_name is None:
                if conn.execute("SELECT 1 FROM categories WHERE name=?", (category["name"],)).fetchone():
                    raise ValidationError("这个分类已经存在。")
                conn.execute("INSERT INTO categories VALUES (?,?,?)", (category["name"], category["color"], now()))
            else:
                if not conn.execute("SELECT 1 FROM categories WHERE name=?", (old_name,)).fetchone():
                    raise KeyError()
                if old_name == "未分类" and category["name"] != old_name:
                    raise ValidationError("未分类是默认分类，不能改名。")
                if category["name"] != old_name and conn.execute("SELECT 1 FROM categories WHERE name=?", (category["name"],)).fetchone():
                    raise ValidationError("这个分类名称已被使用。")
                conn.execute("UPDATE categories SET name=?,color=? WHERE name=?", (category["name"], category["color"], old_name))
                if category["name"] != old_name:
                    conn.execute("UPDATE projects SET category=?,updated_at=? WHERE category=?", (category["name"], now(), old_name))
        return category

    def delete_category(self, name):
        if name == "未分类":
            raise ValidationError("默认的未分类不能删除。")
        with self.connect() as conn:
            if conn.execute("DELETE FROM categories WHERE name=?", (name,)).rowcount != 1:
                raise KeyError()
            moved = conn.execute("UPDATE projects SET category='未分类',updated_at=? WHERE category=?", (now(), name)).rowcount
        return {"moved": moved}

    def import_projects(self, raw_projects, raw_categories=None):
        if not isinstance(raw_projects, list) or len(raw_projects) > 2000:
            raise ValidationError("导入内容必须是项目列表，一次最多 2000 个。")
        # Validate everything before writing, so an invalid backup cannot be partly imported.
        if raw_categories is not None and (not isinstance(raw_categories, list) or len(raw_categories) > 500):
            raise ValidationError("备份中的分类列表无效。")
        categories = [validate_category(category) for category in (raw_categories or [])]
        projects = []
        for raw in raw_projects:
            project = validate_project(raw)
            timestamps = {}
            for key in ("created_at", "updated_at"):
                if key not in raw:
                    continue
                try:
                    value = raw[key]
                    if not isinstance(value, str) or len(value) > 64:
                        raise ValueError()
                    parsed = datetime.fromisoformat(value)
                    if parsed.tzinfo is None:
                        raise ValueError()
                    timestamps[key] = parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")
                except ValueError as exc:
                    raise ValidationError("备份中的项目时间格式无效，未导入任何记录。") from exc
            projects.append((project, timestamps))
        added = skipped = 0
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for category in categories:
                conn.execute("INSERT OR IGNORE INTO categories VALUES (?,?,?)", (category["name"], category["color"], now()))
            existing = [self.decode(row) for row in conn.execute("SELECT * FROM projects")]
            urls = {url_key(project[field]) for project in existing for field in ("url", "repo_url", "demo_url") if project[field]}
            signatures = {json.dumps({key: project[key] for key in FIELDS}, ensure_ascii=False, sort_keys=True) for project in existing}
            for project, timestamps in projects:
                project_urls = {url_key(project[field]) for field in ("url", "repo_url", "demo_url") if project[field]}
                signature = json.dumps(project, ensure_ascii=False, sort_keys=True)
                if project_urls.intersection(urls) or signature in signatures:
                    skipped += 1
                    continue
                self.insert(conn, project, **timestamps)
                urls.update(project_urls)
                signatures.add(signature)
                added += 1
        return {"added": added, "skipped": skipped}


def url_key(value):
    parts = urlsplit(value)
    path = parts.path.rstrip("/")
    if parts.hostname and parts.hostname.lower() == "github.com":
        path = path.casefold().removesuffix(".git")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def validate_category(raw):
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not 1 <= len(raw["name"].strip()) <= 80:
        raise ValidationError("分类名称不能为空，最多 80 个字符。")
    color = raw.get("color", "violet")
    if color not in COLORS:
        raise ValidationError("请选择支持的分类颜色。")
    return {"name": raw["name"].strip(), "color": color}


def github_projects(username, opener=urlopen):
    if not isinstance(username, str) or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", username):
        raise ValidationError("请填写 GitHub 用户名，而非完整链接。")
    try:
        return github_api_projects(username, opener)
    except GitHubUnavailable:
        # Public HTML is a useful fallback when the unauthenticated API is unavailable.
        return github_page_projects(username, opener)


def github_api_projects(username, opener):
    projects = []
    # Public repositories only. No credentials, arbitrary destinations or local files.
    for page in range(1, 11):
        url = f"https://api.github.com/users/{username}/repos?per_page=100&sort=updated&page={page}"
        request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Local-Project-Collection/1.0"})
        try:
            with opener(request, timeout=20) as response:
                repos = json.load(response)
        except HTTPError as exc:
            if exc.code == 404:
                raise ValidationError("找不到该 GitHub 用户，请检查用户名。") from exc
            if exc.code in (403, 429):
                raise GitHubUnavailable("GitHub 暂时限制了请求，请稍后重试；也可以手动添加项目链接。") from exc
            raise GitHubUnavailable("GitHub 暂时无法访问，请稍后重试或手动添加链接。") from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise GitHubUnavailable("无法连接 GitHub，请检查网络；离线时仍可手动添加项目和导入备份。") from exc
        if not isinstance(repos, list):
            raise ValidationError("GitHub 返回了无法识别的数据。")
        for repo in repos:
            homepage = repo.get("homepage") or ""
            if urlsplit(homepage).scheme not in ("http", "https"):
                homepage = ""
            projects.append(validate_project({
                "name": repo["name"], "description": repo.get("description") or "",
                "category": "GitHub 项目", "status": "已归档" if repo.get("archived") else "计划中",
                "tags": list(dict.fromkeys(([repo["language"]] if repo.get("language") else []) + repo.get("topics", [])))[:30],
                "repo_url": repo["html_url"], "demo_url": homepage,
                "notes": "从 GitHub 导入。请按实际进度设置项目状态。",
            }))
        if len(repos) < 100:
            return {"projects": projects, "truncated": False, "source": "api"}
    return {"projects": projects, "truncated": True, "source": "api"}


class GitHubProfileParser(HTMLParser):
    """Read only repository-list metadata, never scripts or embedded account data."""

    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__()
        self.found_list = False
        self.depth = 0
        self.item_depth = 0
        self.capture = None
        self.capture_depth = 0
        self.current = None
        self.projects = []
        self.has_next = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "next_page" in attrs.get("class", "").split() and attrs.get("href"):
            self.has_next = True
        if attrs.get("id") == "user-repositories-list":
            self.found_list = True
            self.depth = 1
            return
        if not self.depth or tag in self.VOID_TAGS:
            return
        self.depth += 1
        if tag == "li" and attrs.get("itemprop") == "owns":
            self.item_depth = self.depth
            self.current = {"name": "", "description": "", "language": "", "repo_url": "", "archived": "archived" in attrs.get("class", "").split()}
        if self.current is not None:
            field = {"name codeRepository": "name", "description": "description", "programmingLanguage": "language"}.get(attrs.get("itemprop"))
            if field:
                self.capture, self.capture_depth = field, self.depth
                if field == "name":
                    href = attrs.get("href", "")
                    if re.fullmatch(r"/[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", href):
                        self.current["repo_url"] = "https://github.com" + href

    def handle_data(self, data):
        if self.current is not None:
            if self.capture:
                self.current[self.capture] += data
            if data.strip().lower() in ("archived", "public archive"):
                self.current["archived"] = True

    def handle_endtag(self, tag):
        if not self.depth or tag in self.VOID_TAGS:
            return
        if self.depth == self.capture_depth:
            self.capture = None
        if self.current is not None and self.depth == self.item_depth:
            item = self.current
            if not item["repo_url"] or not item["name"].strip():
                raise ValidationError("GitHub 公开页面结构发生变化，请改用手动添加链接。")
            self.projects.append(validate_project({
                "name": item["name"].strip(), "description": item["description"].strip(),
                "category": "GitHub 项目", "status": "已归档" if item["archived"] else "计划中",
                "tags": [item["language"].strip()] if item["language"].strip() else [],
                "repo_url": item["repo_url"],
                "notes": "从 GitHub 公开页面导入。请按实际进度设置项目状态；可手动补充演示地址。",
            }))
            self.current = None
        self.depth -= 1


def github_page_projects(username, opener):
    projects = []
    for page in range(1, 11):
        request = Request(f"https://github.com/{username}?tab=repositories&page={page}", headers={"User-Agent": "Local-Project-Collection/1.0"})
        try:
            with opener(request, timeout=20) as response:
                html = response.read().decode("utf-8")
        except (URLError, TimeoutError, OSError, UnicodeDecodeError) as exc:
            raise ValidationError("无法读取 GitHub 公开仓库，请检查用户名和网络，或手动添加项目链接。") from exc
        parser = GitHubProfileParser()
        parser.feed(html)
        if not parser.found_list:
            raise ValidationError("暂时无法识别 GitHub 的公开仓库页面，请稍后重试或手动添加项目链接。")
        projects.extend(parser.projects)
        if not parser.has_next:
            return {"projects": projects, "truncated": False, "source": "public-page"}
    return {"projects": projects, "truncated": True, "source": "public-page"}


class AppServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, database):
        self.store = Store(database)
        self.token = secrets.token_urlsafe(32)
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Keep project titles, URLs, local paths and other user data out of logs.
        pass

    def reply(self, status, value, content_type="application/json; charset=utf-8"):
        body = json.dumps(value, ensure_ascii=False).encode() if not isinstance(value, bytes) else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https: http:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def dispatch(self, method):
        port = self.server.server_address[1]
        if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return self.reply(403, {"error": "仅允许通过本机地址访问。"})
        if method != "GET":
            token = self.headers.get("X-Local-Token", "")
            if not hmac.compare_digest(token.encode("utf-8"), self.server.token.encode("utf-8")):
                return self.reply(403, {"error": "页面已过期，请刷新后重试。"})
        path = urlsplit(self.path).path
        try:
            if method == "GET":
                if path == "/api/bootstrap":
                    return self.reply(200, {"token": self.server.token, "projects": self.server.store.list(), "categories": self.server.store.categories()})
                if path == "/api/projects":
                    return self.reply(200, {"projects": self.server.store.list(), "categories": self.server.store.categories()})
                if path == "/api/categories":
                    return self.reply(200, {"categories": self.server.store.categories()})
                if path == "/api/export":
                    return self.reply(200, {"format": "project-collection", "version": 2, "exported_at": now(), "projects": self.server.store.list(), "categories": self.server.store.categories()})
                if path == "/api/github":
                    username = parse_qs(urlsplit(self.path).query).get("username", [""])[0]
                    return self.reply(200, github_projects(username))
                files = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/local-store.js": ("local-store.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}
                if path in files:
                    name, content_type = files[path]
                    return self.reply(200, (ROOT / "static" / name).read_bytes(), content_type)
            if method == "POST" and path == "/api/projects":
                return self.reply(201, self.server.store.create(self.read_json()))
            if method == "POST" and path in ("/api/preview", "/api/links"):
                raw = self.read_json()
                if not isinstance(raw, dict):
                    raise ValidationError("请输入一个网址。")
                try:
                    url = normalize_url(raw.get("url"))
                except ValueError as exc:
                    raise ValidationError(str(exc)) from exc
                draft = validate_project({"name": "网址卡片", "url": url, "category": raw.get("category", "未分类")})
                if path == "/api/links":
                    with self.server.store.connect() as conn:
                        self.server.store.check_duplicate(conn, draft)
                preview = website_preview(url)
                if path == "/api/preview":
                    return self.reply(200, preview)
                github = urlsplit(url).hostname == "github.com" and len(urlsplit(url).path.strip("/").split("/")) == 2
                saved = self.server.store.create({
                    **draft, "name": preview["name"], "description": preview["description"], "cover_url": preview["cover_url"],
                    "repo_url": url if github else "", "demo_url": "" if github else url,
                })
                return self.reply(201, {"project": saved, "metadata_loaded": preview["metadata_loaded"]})
            if method == "POST" and path == "/api/categories":
                return self.reply(201, self.server.store.save_category(self.read_json()))
            if method == "POST" and path == "/api/import":
                data = self.read_json()
                if not isinstance(data, dict) or data.get("format") != "project-collection" or data.get("version") not in (1, 2):
                    raise ValidationError("请选择本工具导出的 JSON 备份，或使用 GitHub 导入。")
                return self.reply(200, self.server.store.import_projects(data.get("projects"), data.get("categories")))
            category = re.fullmatch(r"/api/categories/(.+)", path)
            if category and method == "PUT":
                return self.reply(200, self.server.store.save_category(self.read_json(), unquote(category[1])))
            if category and method == "DELETE":
                return self.reply(200, self.server.store.delete_category(unquote(category[1])))
            match = re.fullmatch(r"/api/projects/(\d+)", path)
            if match and method == "PUT":
                return self.reply(200, self.server.store.update(int(match[1]), self.read_json()))
            if match and method == "DELETE":
                self.server.store.delete(int(match[1]))
                return self.reply(200, {"deleted": True})
            return self.reply(404, {"error": "找不到这个页面或项目。"})
        except (ValidationError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            return self.reply(400, {"error": str(exc) if isinstance(exc, ValidationError) else "请求不是有效的 JSON。"})
        except KeyError:
            return self.reply(404, {"error": "项目不存在，可能已被删除。"})
        except sqlite3.Error:
            return self.reply(500, {"error": "无法读写本地数据库，请检查磁盘空间和目录权限。"})

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValidationError("请求长度无效。")
        if not 0 < length <= MAX_BODY:
            raise ValidationError("请求不能为空，且最大为 50 MB。")
        return json.loads(self.rfile.read(length))

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_PUT(self):
        self.dispatch("PUT")

    def do_DELETE(self):
        self.dispatch("DELETE")


def main():
    parser = argparse.ArgumentParser(description="个人项目库：所有数据保存在本机，无需安装第三方依赖。")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--open", action="store_true", help="启动后自动打开本机浏览器")
    args = parser.parse_args()
    try:
        server = AppServer(("127.0.0.1", args.port), args.data_dir / "projects.sqlite3")
    except OSError as exc:
        parser.exit(1, f"启动失败：{exc}\n可使用 --port 8766 更换端口。\n")
    print(f"个人项目库已启动。请在本机浏览器打开 http://127.0.0.1:{server.server_port}", flush=True)
    print(f"数据目录：{args.data_dir.resolve()}；按 Ctrl+C 停止。", flush=True)
    if args.open:
        threading.Thread(target=webbrowser.open, args=(f"http://127.0.0.1:{server.server_port}",), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
