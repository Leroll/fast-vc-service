"""在构建时适配仓库文档链接，不改写 Markdown 源文件。"""

from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
import posixpath
import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor
from mkdocs.exceptions import PluginError
from mkdocs.structure.files import File


ROOT = Path(__file__).resolve().parents[2]
GENERATED = {
    "project.md": "README.md",
    "contributing.md": "CONTRIBUTING.md",
    "en/project.md": "docs/en/README.md",
}
ATTR = re.compile(r'''(\b(?:href|src)\s*=\s*)(["'])(.*?)\2''', re.IGNORECASE)


class RawHTMLLinks(HTMLParser):
    """只替换 HTML 标签属性，正文、实体与代码示例保持原样。"""

    def __init__(self, markup, rewrite):
        super().__init__(convert_charrefs=False)
        self.markup = markup
        self.rewrite = rewrite
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        original = self.get_starttag_text()

        def replace(match):
            url = self.rewrite(unescape(match[3]), rendered=True)
            return f'{match[1]}{match[2]}{escape(url, quote=True)}{match[2]}'

        self.markup = self.markup.replace(original, ATTR.sub(replace, original))


class RepositoryLinks(Treeprocessor):
    def __init__(self, md, extension):
        super().__init__(md)
        self.extension = extension

    def run(self, root):
        for element in root.iter():
            for attribute in ("href", "src"):
                if attribute in element.attrib:
                    element.set(attribute, self.extension.rewrite(element.get(attribute)))
        # Python-Markdown 将原生 HTML 暂存于 stash，它不会经过上面的树遍历。
        for i, markup in enumerate(self.md.htmlStash.rawHtmlBlocks):
            if isinstance(markup, str):
                self.md.htmlStash.rawHtmlBlocks[i] = RawHTMLLinks(
                    markup, self.extension.rewrite
                ).markup


class LinkExtension(Extension):
    def extendMarkdown(self, md):
        # inline(20) 之后、MkDocs relpath(0) 之前，保留内置的链接与锚点验证。
        md.treeprocessors.register(RepositoryLinks(md, self), "repository_links", 15)

    def rewrite(self, value, rendered=False):
        url = urlsplit(value)
        if url.scheme or url.netloc or not url.path or url.path.startswith("/"):
            return value
        target = posixpath.normpath(
            posixpath.join(posixpath.dirname(self.origin), unquote(url.path))
        )
        if target in self.published:
            file = self.published[target]
            if rendered:
                # 原生 HTML 不经过 MkDocs 的 relpath 处理，直接转成网页相对地址。
                path = posixpath.relpath(file.dest_uri, posixpath.dirname(self.page.file.dest_uri))
            else:
                path = posixpath.relpath(file.src_uri, posixpath.dirname(self.page.file.src_uri))
            return urlunsplit(("", "", quote(path, safe="/"), url.query, url.fragment))
        local = (ROOT / target).resolve()
        if not local.is_relative_to(ROOT) or not local.exists():
            raise PluginError(f"{self.origin}: 仓库链接不存在或越界: {value}")
        # 文档以外的文件链接回公开仓库；图片使用 raw 地址，不复制音频或其他素材。
        if local.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}:
            base = self.repo.replace("https://github.com/", "https://raw.githubusercontent.com/")
            path = f"{base}/main/{quote(target, safe='/')}"
        else:
            kind = "tree" if local.is_dir() else "blob"
            path = f"{self.repo}/{kind}/main/{quote(target, safe='/')}"
        return path + (f"?{url.query}" if url.query else "") + (f"#{url.fragment}" if url.fragment else "")


links = LinkExtension()


def on_config(config):
    config.markdown_extensions.append(links)
    return config


def on_files(files, config):
    # docs 只作为 Markdown 来源；额外文件不自动获得网站发布资格。
    for file in list(files):
        if (
            file.abs_src_path
            and Path(file.abs_src_path).is_relative_to(ROOT / "docs")
            and not file.is_documentation_page()
        ):
            files.remove(file)
    for uri, source in GENERATED.items():
        if files.get_file_from_path(uri):
            raise PluginError(f"生成页面路径与已有文档冲突: {uri}")
        file = File.generated(config, uri, content=(ROOT / source).read_text(encoding="utf-8"))
        file.edit_uri = posixpath.relpath(source, "docs")
        files.append(file)
    links.published = {
        GENERATED.get(file.src_uri, f"docs/{file.src_uri}"): file
        for file in files.documentation_pages()
    }
    links.repo = config.repo_url.rstrip("/")
    return files


def on_page_markdown(markdown, page, config, files):
    links.page = page
    links.origin = GENERATED.get(page.file.src_uri, f"docs/{page.file.src_uri}")
    english = page.file.src_uri.startswith("en/") or page.file.src_uri == "changelog/releases_en.md"
    if english:
        page.meta["lang"] = "en"
    if page.file.src_uri.startswith((
        "specs/", "changelog/20", "design/archive/", "getting_started/",
        "perfermance_tests/version",
    )):
        page.meta["search"] = {"exclude": True}
    # 入口本身带有版本说明，便于直接在 GitHub 阅读；其他网页统一补充。
    if links.origin in {"README.md", "docs/README.md", "docs/en/README.md", "docs/en/index.md"}:
        return markdown
    historical = page.file.src_uri.startswith((
        "specs/", "changelog/", "design/archive/", "getting_started/", "perfermance_tests/",
    ))
    releases = config.repo_url.rstrip("/") + "/releases"
    if english:
        notice = f"> **Documentation version: main development branch.** For a released version, read the documentation at its [release tag]({releases})."
        if historical:
            notice += " This page contains historical records; interpret them in the context of their date or version."
    else:
        notice = f"> **文档版本：main 开发分支。** 使用已发布版本时，请阅读对应[发布标签]({releases})中的文档。"
        if historical:
            notice += " 本页包含历史记录，请按其日期或版本理解内容。"
    rendered, count = re.subn(r"^(# .+\n)", lambda match: match[1] + "\n" + notice + "\n", markdown, count=1, flags=re.M)
    # 历史笔记可能没有 H1；只调整网页展示，不改写历史 Markdown。
    return rendered if count else notice + "\n\n" + markdown


def on_serve(server, config, builder):
    for source in GENERATED.values():
        server.watch(str(ROOT / source))
    return server
