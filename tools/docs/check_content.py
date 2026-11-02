"""离线校验文档中的配置和机器示例；按 Git 变更提醒复核文档与译文。"""

import argparse
import ast
from fnmatch import fnmatchcase
import json
from pathlib import Path
import re
import shlex
import subprocess
import tomllib

import yaml


ROOT = Path(__file__).resolve().parents[2]
FENCE = re.compile(r"^```(json|python|bash|sh)[ \t]*\n(.*?)^```[ \t]*$", re.M | re.S)
PYTHON_HEREDOC = re.compile(r"python(?:3)?\s+-\s+<<['\"]?(\w+)['\"]?\n(.*?)^\1[ \t]*$", re.M | re.S)


def read_policy(root):
    return tomllib.loads((root / "tools/docs/content.toml").read_text(encoding="utf-8"))


def normalized_example(language, body):
    """只做语法检查，不执行示例；返回用于比较双语示例的表示。"""
    if language == "json":
        return json.dumps(json.loads(body), sort_keys=True, ensure_ascii=False)
    if language == "python":
        return ast.dump(ast.parse(body))
    result = subprocess.run(["bash", "-n"], input=body, text=True, capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.strip())
    for match in PYTHON_HEREDOC.finditer(body):
        ast.parse(match[2])
    return "\n".join(line.rstrip() for line in body.strip().splitlines()
                     if not line.lstrip().startswith("#"))


def client_parser(root):
    """仅读取 argparse 的字面量声明，不导入音频客户端及其依赖。"""
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError(message)

    parser = Parser(add_help=False)
    source = root / "examples/websocket/simple_protocol_ws_client.py"
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "parser"
                and node.func.attr == "add_argument"):
            continue
        options = {}
        for keyword in node.keywords:
            if keyword.arg == "type":
                options["type"] = {"int": int, "float": float, "str": str}[keyword.value.id]
            elif keyword.arg in {"choices", "action", "default", "required", "nargs"}:
                options[keyword.arg] = ast.literal_eval(keyword.value)
        parser.add_argument(*(ast.literal_eval(arg) for arg in node.args), **options)
    return parser


def examples(text, path, errors, parser):
    result = []
    for match in FENCE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        try:
            result.append((match[1], normalized_example(match[1], match[2])))
            if match[1] in {"bash", "sh"}:
                for command in match[2].replace("\\\n", " ").splitlines():
                    if command.startswith("uv run python examples/websocket/simple_protocol_ws_client.py "):
                        parser.parse_args(shlex.split(command)[4:])
        except (ValueError, SyntaxError) as exc:
            errors.append(f"{path}:{line}: {match[1]} 示例语法错误：{exc}")
    return result


def display_value(value):
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return "[" + ", ".join(display_value(item) for item in value) + "]"
    return str(value)


def check_config_tables(root, errors):
    config = yaml.safe_load((root / "configs/prod.yaml").read_text(encoding="utf-8"))
    tree = ast.parse((root / "src/fast_vc_service/config.py").read_text(encoding="utf-8"))
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    sections = {node.target.id: node.annotation.id for node in classes["ConfigData"].body
                if isinstance(node, ast.AnnAssign) and isinstance(node.annotation, ast.Name)}
    fields = {section: {node.target.id for node in classes[cls].body
                       if isinstance(node, ast.AnnAssign)} for section, cls in sections.items()}
    checked = 0
    for path in ("docs/getting-started/configuration.md", "docs/en/getting-started/configuration.md"):
        rows = 0
        for number, line in enumerate((root / path).read_text(encoding="utf-8").splitlines(), 1):
            cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
            if len(cells) != 3 or not re.match(r"^(app|buffer|realtime_vc|models)\.", cells[0]):
                continue
            rows += 1
            keys = cells[0].split(" / ")
            values = cells[1].split(" / ")
            if len(keys) != len(values):
                errors.append(f"{path}:{number}: 配置字段与示例值数量不匹配")
                continue
            section = keys[0].split(".", 1)[0]
            for key, value in zip(keys, values):
                if "." in key:
                    section, key = key.split(".", 1)
                checked += 1
                if key not in fields.get(section, set()):
                    errors.append(f"{path}:{number}: 配置类不存在字段 {section}.{key}")
                try:
                    expected = display_value(config[section][key])
                except KeyError:
                    errors.append(f"{path}:{number}: prod.yaml 未设置 {section}.{key}")
                    continue
                if value != expected:
                    errors.append(f"{path}:{number}: {section}.{key} 示例值 {value!r} 与 prod.yaml 的 {expected!r} 不一致")
        if not rows:
            errors.append(f"{path}: 未找到常用配置表")
    return checked


def check_content(root=ROOT):
    policy = read_policy(root)
    errors = []
    blocks = {}
    parser = client_parser(root)
    for path in set(policy["translations"]) | set(policy["translations"].values()):
        if not (root / path).is_file():
            errors.append(f"同步映射中的文档不存在：{path}")
            continue
        blocks[path] = examples((root / path).read_text(encoding="utf-8"), path, errors, parser)
    for source, translation in policy["translations"].items():
        if source in blocks and translation in blocks and blocks[source] != blocks[translation]:
            errors.append(f"双语机器示例不一致：{source} ↔ {translation}")
    for paths in policy["review"].values():
        for path in paths:
            if not (root / path).is_file():
                errors.append(f"源码复核映射中的文档不存在：{path}")
    checked = check_config_tables(root, errors)
    return errors, len(policy["translations"]), sum(map(len, blocks.values())), checked


def review_warnings(changed, policy):
    warnings = []
    for source, translation in policy["translations"].items():
        if (source in changed) != (translation in changed):
            updated, other = (source, translation) if source in changed else (translation, source)
            warnings.append(f"仅 {updated} 发生变更，请复核 {other} 是否需要同步；纯文字修正可说明无需同步。")
    for pattern, paths in policy["review"].items():
        hits = sorted(path for path in changed if fnmatchcase(path, pattern))
        if hits:
            targets = set(paths) | {policy["translations"][path] for path in paths
                                   if path in policy["translations"]}
            warnings.append(f"源码/配置变更 {', '.join(hits)}：请复核 {', '.join(sorted(targets))}；文件同时改动仍需核对语义。")
    return warnings


def changed_files(root, base):
    # 校验基线，避免浅克隆或无效引用使同步提醒悄悄失效。
    revision = subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}"],
        cwd=root, text=True, stderr=subprocess.PIPE,
    ).strip()
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "--no-renames", "-z", revision, "--"], cwd=root,
    ).decode().split("\0")
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=root,
    ).decode().split("\0")
    return set(changed + untracked) - {""}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="比较基线，例如 origin/main；包含基线后的提交及本地修改")
    args = parser.parse_args()
    errors, pairs, blocks, fields = check_content()
    if args.base and set(args.base) != {"0"}:
        try:
            changed = changed_files(ROOT, args.base)
        except subprocess.CalledProcessError as exc:
            raise SystemExit(f"无法读取比较基线 {args.base}，请先获取对应 Git 历史：{exc.stderr}") from exc
        for warning in review_warnings(changed, read_policy(ROOT)):
            print(f"提醒：{warning}")
    else:
        print("未指定有效比较基线；已执行内容检查，跳过变更影响提醒。")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"通过：{pairs} 对文档，{blocks} 个机器示例，{fields} 个配置值；未执行服务或 GPU 推理。")


if __name__ == "__main__":
    main()
