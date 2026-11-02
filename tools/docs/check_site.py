"""检查生成 HTML 的本地链接、锚点、资源与搜索索引，不访问外部网络。"""

import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from mkdocs.config import load_config


ROOT = Path(__file__).resolve().parents[2]


class PageLinks(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.links = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "a" and attrs.get("name"):
            self.ids.add(attrs["name"])
        for key in ("href", "src"):
            if attrs.get(key):
                self.links.append(attrs[key])


def check_site(site, site_url):
    site = site.resolve()
    pages = {
        file: PageLinks(file.read_text(encoding="utf-8"))
        for file in site.rglob("*.html")
    }
    if not pages or not (site / "index.html").is_file():
        raise ValueError("未找到网站首页；请先执行 mkdocs build --strict")
    base = urlsplit(site_url)
    prefix = base.path.rstrip("/") + "/"
    errors = []
    checked = 0

    def check(source, value):
        nonlocal checked
        address = urlsplit(urljoin(site_url, source.relative_to(site).as_posix()))
        target = urlsplit(urljoin(address.geturl(), value))
        if (target.scheme, target.netloc) != (base.scheme, base.netloc):
            return
        if not target.path.startswith(prefix):
            errors.append(f"{source.relative_to(site)}: 链接越出项目路径: {value}")
            return
        path = (site / unquote(target.path[len(prefix):])).resolve()
        if not path.is_relative_to(site):
            errors.append(f"{source.relative_to(site)}: 链接越出构建目录: {value}")
            return
        if path.is_dir():
            path /= "index.html"
        checked += 1
        if not path.is_file():
            errors.append(f"{source.relative_to(site)}: 目标不存在: {value}")
        elif target.fragment and path in pages:
            anchor = unquote(target.fragment)
            if anchor not in pages[path].ids:
                errors.append(f"{source.relative_to(site)}: 锚点不存在: {value}")

    for source, page in pages.items():
        for value in page.links:
            check(source, value)
    index = json.loads((site / "search/search_index.json").read_text(encoding="utf-8"))
    for entry in index["docs"]:
        check(site / "index.html", entry["location"])
    if errors:
        raise ValueError("\n".join(errors))
    return len(pages), checked, len(index["docs"])


if __name__ == "__main__":
    config = load_config(str(ROOT / "mkdocs.yml"))
    try:
        pages, links, entries = check_site(Path(config.site_dir), config.site_url)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"通过：{pages} 个 HTML 页面，{links} 个本地链接与资源引用，{entries} 条搜索记录。")
