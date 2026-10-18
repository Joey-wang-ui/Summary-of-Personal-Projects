"""Read public webpage metadata without executing the page or requiring an API key."""

import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, getproxies, proxy_bypass


def normalize_url(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValueError("请输入有效的网址，最长 2048 个字符。")
    value = value.strip()
    if any(ord(char) < 32 or char.isspace() for char in value):
        raise ValueError("网址中不能包含空格或换行。")
    if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value):
        value = "https://" + value
    try:
        parts = urlsplit(value)
        hostname = parts.hostname
        port = parts.port
        if parts.scheme not in ("https", "http") or not hostname or parts.username is not None or parts.password is not None:
            raise ValueError()
        if "\\" in value or any(char in hostname for char in '<>"{}|^`'):
            raise ValueError()
        host = hostname.encode("idna").decode("ascii").lower()
        if ":" in host:
            ipaddress.IPv6Address(host)
            host = "[" + host + "]"
        elif not re.fullmatch(r"[A-Za-z0-9_.-]+", host):
            raise ValueError()
        netloc = host + (f":{port}" if port is not None else "")
        path = quote(parts.path, safe="/%:@!$&'()*+,;=-._~")
        query = quote(parts.query, safe="=&?/%:+,;@!$'()*~-._")
        return urlunsplit((parts.scheme, netloc, path, query, quote(parts.fragment, safe="/%?=&:@!$'()*+,;~-._")))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("网址必须是有效的 http 或 https 地址，且不能包含账号密码。") from exc


def public_target(url):
    parts = urlsplit(normalize_url(url))
    if parts.port not in (None, 80, 443):
        raise ValueError("仅自动读取公开网站的标准端口。")
    host = parts.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal", ".lan", ".home", ".invalid", ".test")):
        raise ValueError("本机或内网网址仅保存链接，不自动读取内容。")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise ValueError("本机或内网网址仅保存链接，不自动读取内容。")
    try:
        addresses = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror:
        # In proxy-only environments DNS belongs to the configured proxy, not this machine.
        # Keep the existing proxy route and its access checks; never fall back to a direct request.
        if literal is None and re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", host) and getproxies().get(parts.scheme) and not proxy_bypass(host):
            return
        raise
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("本机或内网网址仅保存链接，不自动读取内容。")


class PublicRedirects(HTTPRedirectHandler):
    max_redirections = 3
    max_repeats = 2

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        public_target(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


class PageMetadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title = ""
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key not in self.meta and attrs.get("content"):
                self.meta[key] = attrs["content"]

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def fetch_page(url):
    public_target(url)
    request = Request(url, headers={"User-Agent": "ProjectCollection/2.0 (+personal-bookmark-tool)", "Accept": "text/html,application/xhtml+xml"})
    with build_opener(PublicRedirects()).open(request, timeout=8) as response:
        content_type = response.headers.get_content_type()
        if content_type not in ("text/html", "application/xhtml+xml"):
            raise ValueError("该网址不是可读取的网页。")
        charset = response.headers.get_content_charset() or "utf-8"
        html = response.read(512 * 1024).decode(charset, errors="replace")
        return html, response.geturl()


def website_preview(value, fetcher=None):
    url = normalize_url(value)
    domain = urlsplit(url).hostname.removeprefix("www.")
    result = {"url": url, "name": domain[:120], "description": "", "cover_url": "", "metadata_loaded": False}
    try:
        html, final_url = (fetcher or fetch_page)(url)
        parser = PageMetadata()
        parser.feed(html)
        title = parser.meta.get("og:title") or parser.meta.get("twitter:title") or parser.title
        description = parser.meta.get("og:description") or parser.meta.get("description") or parser.meta.get("twitter:description") or ""
        result["name"] = " ".join(title.split())[:120] or result["name"]
        result["description"] = " ".join(description.split())[:2000]
        image = parser.meta.get("og:image:secure_url") or parser.meta.get("og:image") or parser.meta.get("twitter:image")
        if image:
            try:
                cover = normalize_url(urljoin(final_url, image))
                # Validate image destinations too; private covers can still be uploaded locally.
                public_target(cover)
                result["cover_url"] = cover
            except (ValueError, OSError):
                pass
        result["metadata_loaded"] = bool(title or description or result["cover_url"])
    except (OSError, ValueError, LookupError):
        # A blocked, offline or JS-only website must still become a useful saved card.
        pass
    return result
