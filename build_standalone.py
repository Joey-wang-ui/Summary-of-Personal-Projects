"""Build a personal HTML copy, or an empty public website with --public."""

import argparse
import json
from pathlib import Path

from app import ROOT, Store


def build(output=None, database=None, *, include_data=True):
    if include_data:
        store = Store(database or ROOT / "data" / "projects.sqlite3")
        seed = {"projects": store.list(), "categories": store.categories()}
    else:
        seed = {"projects": [], "categories": [
            {"name": "未分类", "color": "slate"},
            {"name": "网站作品", "color": "blue"},
            {"name": "AI 工具", "color": "violet"},
            {"name": "学习与实验", "color": "green"},
        ]}
    serialized = json.dumps(seed, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="/style.css">', "<style>" + css + "</style>")
    scripts = ["window.FORCE_LOCAL_MODE=true;window.LOCAL_SEED=" + serialized + ";"]
    for filename in ("local-store.js", "app.js"):
        html = html.replace(f'<script src="/{filename}" defer></script>', "")
        scripts.append((ROOT / "static" / filename).read_text(encoding="utf-8"))
    inline = "\n".join("<script>" + script.replace("</script", "<\\/script") + "</script>" for script in scripts)
    html = html.replace("</body>", inline + "\n</body>")
    target = Path(output or ROOT / "打开项目库.html")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="构建拾作网页；--public 生成不含个人卡片的公开版本。")
    parser.add_argument("--public", action="store_true", help="不读取本地数据库，生成空白作品库")
    parser.add_argument("--output", type=Path, help="HTML 输出位置")
    args = parser.parse_args()
    output = args.output or (ROOT / "index.html" if args.public else None)
    print(build(output, include_data=not args.public))
