"""project_index —— CindraCode 的项目索引器 (Cindra 的护城河)。

扫描一个 UE C++ 工程的 .h/.cpp, 用正则抽出符号: UCLASS/USTRUCT/UENUM 及其
父类、UFUNCTION/UPROPERTY 成员。把每个符号做成一个可检索的"卡片", 复用
docs_index.LexicalIndex (BM25) 做检索 —— 这样 CindraCode 生成代码前能先查
"本工程已经有哪些类/约定", 让产出符合现有工程规范, 而不是凭空写。

和 CindraDocs 同构: docs 索引知识库文档, project 索引工程符号; 共用同一个
LexicalIndex。离线、纯标准库、确定性, 这台 Mac 上即可验证。
"""

from __future__ import annotations

import os
import re

from .docs_index import LexicalIndex

# 默认示例工程: 与本文件同级的 sample_project/
SAMPLE_PROJECT = os.path.join(os.path.dirname(__file__), "sample_project")

# UCLASS/USTRUCT 定义: 捕获 类前缀+名 和 (可选) 父类。要求声明后跟 `:` 或 `{`,
# 以排除前向声明 (class UFoo;)。
#   class SAMPLEGAME_API ACindraCharacter : public ACharacter
#   struct SAMPLEGAME_API FCindraItemData\n{
_RE_TYPE = re.compile(
    r"\b(class|struct)\s+(?:\w+_API\s+)([AUF]\w+)\s*"
    r"(?::\s*public\s+([AUF]\w+))?\s*[:{]"
)
# UENUM: enum class ECindraItemRarity : uint8
_RE_ENUM = re.compile(r"\benum\s+class\s+(E\w+)")
# UFUNCTION 标记 + 紧随其后的函数声明 (取函数名)。
_RE_UFUNCTION = re.compile(r"UFUNCTION\s*\(([^)]*)\)\s*[\s\S]{0,200}?\b(\w+)\s*\(", re.MULTILINE)
# UPROPERTY 标记 + 紧随其后的成员声明 (取类型和成员名)。
_RE_UPROPERTY = re.compile(
    r"UPROPERTY\s*\(([^)]*)\)\s*[\s\S]{0,160}?\b([\w:<>*]+)\s+(\w+)\s*[=;{]", re.MULTILINE
)


def _iter_source_files(root: str):
    for dirpath, _dirs, files in os.walk(root):
        for fn in sorted(files):
            if fn.endswith((".h", ".cpp", ".hpp")):
                yield os.path.join(dirpath, fn)


def _leading_comment(src: str, decl_start: int) -> str:
    """取声明前紧邻的连续注释行 (// 或块注释), 这里常含中文业务语义。"""
    head = src[:decl_start].rstrip()
    lines = head.splitlines()
    out: list[str] = []
    for line in reversed(lines):
        s = line.strip()
        if s.startswith("//") or s.startswith("*") or s.startswith("/*") or s.endswith("*/"):
            out.append(s.lstrip("/* ").rstrip("*/ "))
        elif s == "":
            continue
        else:
            break
    return " ".join(reversed(out))


def _file_header_comment(src: str) -> str:
    """取文件最开头的连续注释块 (文件级说明, 常含整文件的中文业务语义)。"""
    out: list[str] = []
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("//") or s.startswith("/*") or s.startswith("*") or s.endswith("*/"):
            out.append(s.lstrip("/* ").rstrip("*/ "))
        elif s == "":
            if out:  # 注释块结束
                break
            continue
        else:
            break
    return " ".join(out)


def extract_symbols(root: str = SAMPLE_PROJECT) -> list[dict]:
    """扫描工程, 返回符号卡片 [{id, kind, name, parent, file, text}]。

    每张卡片的 text 汇总便于检索/给 agent 当上下文的信息: 文件头注释 + 声明前
    导注释(常含中文语义)、类型、父类、它的 UFUNCTION/UPROPERTY 成员。中文
    query 命中注释, 英文 query 命中符号名/成员。
    """
    symbols: list[dict] = []
    seen: set[str] = set()
    for path in _iter_source_files(root):
        rel = os.path.relpath(path, root)
        with open(path, encoding="utf-8", errors="replace") as f:
            src = f.read()
        file_doc = _file_header_comment(src)

        # 头文件里抽类型定义 (避免 .cpp 重复抽到同名)
        if path.endswith((".h", ".hpp")):
            for m in _RE_TYPE.finditer(src):
                ckind, name, parent = m.group(1), m.group(2), m.group(3)
                if name in seen:
                    continue
                seen.add(name)
                comment = _leading_comment(src, m.start())
                block = src[m.start() : m.start() + 4000]
                funcs = [fm.group(2) for fm in _RE_UFUNCTION.finditer(block)]
                props = [(pm.group(2), pm.group(3)) for pm in _RE_UPROPERTY.finditer(block)]
                kind = "struct" if ckind == "struct" else "class"
                parts = []
                if file_doc:
                    parts.append(file_doc)
                if comment and comment != file_doc:
                    parts.append(comment)
                parts.append(f"{kind} {name}")
                if parent:
                    parts.append(f"继承自 {parent}")
                if funcs:
                    parts.append("UFUNCTION: " + ", ".join(dict.fromkeys(funcs)))
                if props:
                    parts.append("UPROPERTY: " + ", ".join(f"{t} {n}" for t, n in props))
                symbols.append(
                    {
                        "id": f"{rel}:{name}",
                        "kind": kind,
                        "name": name,
                        "parent": parent or "",
                        "file": rel,
                        "text": "\n".join(parts),
                    }
                )
            for em in _RE_ENUM.finditer(src):
                name = em.group(1)
                if name in seen:
                    continue
                seen.add(name)
                comment = _leading_comment(src, em.start())
                # 把枚举值也纳入文本 (含 UMETA DisplayName 里的中文)
                tail = src[em.start() : em.start() + 500]
                body = tail[tail.find("{") : tail.find("}") + 1] if "{" in tail else ""
                text = " ".join(p for p in [file_doc, comment, f"enum class {name}", body] if p)
                symbols.append(
                    {
                        "id": f"{rel}:{name}",
                        "kind": "enum",
                        "name": name,
                        "parent": "",
                        "file": rel,
                        "text": text,
                    }
                )
    return symbols


class ProjectIndex:
    """工程符号索引。.search(query, k) 复用 LexicalIndex 的 BM25。"""

    def __init__(self, root: str = SAMPLE_PROJECT) -> None:
        self.root = root
        self.symbols = extract_symbols(root)
        # LexicalIndex 期望 chunk 有 title/file/text; 把符号名当 title。
        self.chunks = [
            {"id": s["id"], "title": s["name"], "file": s["file"], "text": s["text"]}
            for s in self.symbols
        ]
        self._lex = LexicalIndex(self.chunks) if self.chunks else None

    def search(self, query: str, k: int = 5) -> list[dict]:
        if not self._lex:
            return []
        return self._lex.search(query, k=k)


def build_project_index(root: str = SAMPLE_PROJECT) -> ProjectIndex:
    idx = ProjectIndex(root)
    if not idx.symbols:
        raise RuntimeError(f"工程里没抽到符号: {root}")
    return idx


# ---------------------------------------------------------------------------
# 离线自检 (无需 key/网络): python3 -m cindra.project_index
# ---------------------------------------------------------------------------

# (query, 期望命中的符号名)
_SELFCHECK = [
    ("生命值 受伤 死亡 组件", "UCindraHealthComponent"),
    ("玩家角色 character 移动 输入", "ACindraCharacter"),
    ("游戏规则 gamemode 胜负", "ACindraGameMode"),
    ("物品 道具 数据 结构体", "FCindraItemData"),
    ("稀有度 枚举 rarity", "ECindraItemRarity"),
]


def _selfcheck() -> int:
    idx = ProjectIndex()
    kinds: dict[str, int] = {}
    for s in idx.symbols:
        kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
    print(
        f"符号: {len(idx.symbols)} 个 "
        f"({', '.join(f'{k}×{v}' for k, v in kinds.items())}), 来自 "
        f"{len({s['file'] for s in idx.symbols})} 个文件"
    )
    for s in idx.symbols:
        par = f" : {s['parent']}" if s["parent"] else ""
        print(f"  - [{s['kind']}] {s['name']}{par}  ({s['file']})")
    print()
    passed = 0
    for query, expect in _SELFCHECK:
        hits = idx.search(query, k=3)
        top = hits[0] if hits else None
        ok = bool(top) and top["title"] == expect
        passed += ok
        mark = "✅" if ok else "❌"
        got = f"{top['title']} ({top['score']})" if top else "(无结果)"
        print(f"  {mark} {query!r}\n        期望 {expect} | 命中 {got}")
    print(f"\n检索质量: {passed}/{len(_SELFCHECK)} top-1 命中")
    return 0 if passed == len(_SELFCHECK) else 1


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
