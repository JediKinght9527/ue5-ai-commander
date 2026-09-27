"""docs_index —— CindraDocs 的检索后端 (RAG 的 R)。

复刻 transport.py 的双后端思路, 把"检索"做成可替换的 index:

  LexicalIndex    BM25-lite 关键词检索 —— 纯标准库, 离线, 确定性 (Mac 验证用, 默认)
  EmbeddingIndex  向量检索 —— 惰性导入 embedding 依赖, 生产质量 (有 key 的机器)

两者都暴露 .search(query, k) -> [{title, file, score, text}], 上层 docs_tools
不关心底下是关键词还是向量。

corpus 切块: docs_corpus/*.md 按 markdown 标题 (# / ##) 切成块, 每块带它的
标题和来源文件, 便于 agent 回答时标注引用 [来源: 文件#标题]。
"""
from __future__ import annotations

import math
import os
import re
from collections import Counter

# corpus 默认目录: 与本文件同级的 docs_corpus/
CORPUS_DIR = os.path.join(os.path.dirname(__file__), "docs_corpus")


# ---------------------------------------------------------------------------
# 切块
# ---------------------------------------------------------------------------

def chunk_corpus(corpus_dir: str = CORPUS_DIR) -> list[dict]:
    """把 corpus 目录下的 .md 按标题切块。

    规则: 每遇到一个 `#`/`##` 开头的标题, 开一个新块, 标题行做 title,
    其后正文做 text, 直到下一个标题。返回 [{id, title, file, text}]。
    """
    chunks: list[dict] = []
    if not os.path.isdir(corpus_dir):
        return chunks
    for fname in sorted(os.listdir(corpus_dir)):
        if not fname.endswith(".md"):
            continue
        chunks.extend(_chunk_file(os.path.join(corpus_dir, fname), fname, len(chunks)))
    return chunks


def _chunk_file(path: str, fname: str, id_offset: int) -> list[dict]:
    """把一个 .md 按 `#`/`##`/`###` 标题切块。

    原来是 chunk_corpus 里的内嵌闭包 flush()，捕获 title/buf/fname 三个循环
    变量 —— 当前用法没触发 bug（flush 只在同一次迭代内调用），但闭包跟着循环
    变量走是典型的踩雷姿势，拆成独立函数后每个文件的解析状态自成一体。
    """
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    out: list[dict] = []
    title: str | None = None
    buf: list[str] = []

    def emit() -> None:
        if title is None:
            return
        out.append({
            "id": f"{fname}#{id_offset + len(out)}",
            "title": title,
            "file": fname,
            "text": "\n".join(buf).strip(),
        })

    for line in lines:
        m = re.match(r"^#{1,3}\s+(.*)$", line)
        if m:
            emit()
            title = m.group(1).strip()
            buf = []
        else:
            buf.append(line)
    emit()
    return out


# ---------------------------------------------------------------------------
# 分词 (中英混排)
# ---------------------------------------------------------------------------

# 中文虚词/疑问词停用词。过滤掉它们, 避免 "UPROPERTY 是干什么的" 里的
# 是/干/什/么 这类高频无信息词把 "...是什么" 标题的短块顶上来。
# 保留 区别/优化 这类承载语义的词。
_STOP_CJK = set("的了是在和与也都很到有个这那它你我他她们吗呢吧把被让从对于"
                "及其之或而但即就还又再请用做为以可会能要会"
                "什么干怎样啥哪谁")
_STOP_BIGRAM = {"什么", "怎么", "是什", "是干", "干什", "么的", "为什", "什么的",
                "是否", "有没", "没有", "可以", "如何"}


def tokenize(text: str) -> list[str]:
    """把中英混排文本切成检索词。

    - ASCII 词 (Actor, BeginPlay, UPROPERTY) 整体保留, 小写。
    - CJK 单字成词, 并加相邻二元组 (区别 -> 区,别,区别), 提升中文短语匹配。
    - 过滤中文虚词/疑问词单字与纯虚词二元组 (停用词)。
    """
    text = text.lower()
    tokens: list[str] = []
    # 英文/数字词
    tokens.extend(re.findall(r"[a-z0-9_]+", text))
    # 中文: 单字 (去停用词) + 二元组 (去纯虚词组合)
    cjk = re.findall(r"[一-鿿]", text)
    tokens.extend(ch for ch in cjk if ch not in _STOP_CJK)
    for a, b in zip(cjk, cjk[1:], strict=False):
        bigram = a + b
        if bigram in _STOP_BIGRAM:
            continue
        tokens.append(bigram)
    return tokens


# ---------------------------------------------------------------------------
# LexicalIndex —— BM25-lite (默认, 零依赖, 离线, 确定性)
# ---------------------------------------------------------------------------

class LexicalIndex:
    """BM25 关键词检索。纯标准库, 不联网不需要 API key。"""

    K1 = 1.5
    B = 0.75

    def __init__(self, chunks: list[dict]) -> None:
        self.chunks = chunks
        self.doc_tokens = [tokenize(c["title"] + " " + c["text"]) for c in chunks]
        self.doc_len = [len(t) for t in self.doc_tokens]
        self.avg_len = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 0.0
        self.tf = [Counter(t) for t in self.doc_tokens]
        # 文档频率 -> idf
        df: Counter = Counter()
        for toks in self.doc_tokens:
            for term in set(toks):
                df[term] += 1
        n = len(chunks)
        self.idf = {
            term: math.log(1 + (n - d + 0.5) / (d + 0.5))
            for term, d in df.items()
        }

    def _score(self, doc_i: int, q_terms: list[str]) -> float:
        score = 0.0
        tf = self.tf[doc_i]
        dl = self.doc_len[doc_i]
        for term in q_terms:
            if term not in tf:
                continue
            idf = self.idf.get(term, 0.0)
            freq = tf[term]
            denom = freq + self.K1 * (1 - self.B + self.B * dl / (self.avg_len or 1))
            score += idf * (freq * (self.K1 + 1)) / denom
        return score

    def search(self, query: str, k: int = 4) -> list[dict]:
        q_terms = tokenize(query)
        scored = []
        for i, _c in enumerate(self.chunks):
            s = self._score(i, q_terms)
            if s > 0:
                scored.append((s, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for s, i in scored[:k]:
            c = self.chunks[i]
            out.append({"title": c["title"], "file": c["file"],
                        "score": round(s, 3), "text": c["text"]})
        return out


# ---------------------------------------------------------------------------
# EmbeddingIndex —— 向量检索 (惰性依赖, 生产质量)
# ---------------------------------------------------------------------------

class EmbeddingIndex:
    """向量检索后端。

    用一个 embedding 提供者把每个块向量化, query 时取余弦最相近的 k 个。
    依赖惰性导入: 没装 embedding 依赖 / 没有 key 的机器, import 本模块和用
    LexicalIndex 都不受影响 (照搬 transport.RemoteExecTransport 的惰性写法)。

    embed_fn: Callable[[list[str]], list[list[float]]]。不传则尝试用一个默认
    provider (留到接真 embedding 时实现); 当前默认 provider 缺失会明确报错,
    引导用户改用 lexical 后端。
    """

    def __init__(self, chunks: list[dict], embed_fn=None) -> None:
        self.chunks = chunks
        self.embed_fn = embed_fn or self._default_embed_fn()
        texts = [c["title"] + "\n" + c["text"] for c in chunks]
        self.vectors = self.embed_fn(texts)

    @staticmethod
    def _default_embed_fn():
        def _embed(_texts):
            raise RuntimeError(
                "EmbeddingIndex 需要一个 embedding 提供者。这台机器没配 embedding "
                "依赖/Key。请改用默认的 lexical 后端 (--index lexical), 或传入 "
                "embed_fn。lexical 在 Mac 上离线即可跑, 检索质量足够验证闭环。"
            )
        return _embed

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0

    def search(self, query: str, k: int = 4) -> list[dict]:
        qv = self.embed_fn([query])[0]
        scored = [(self._cosine(qv, v), i) for i, v in enumerate(self.vectors)]
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for s, i in scored[:k]:
            c = self.chunks[i]
            out.append({"title": c["title"], "file": c["file"],
                        "score": round(s, 3), "text": c["text"]})
        return out


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------

def build_index(kind: str = "lexical", corpus_dir: str = CORPUS_DIR,
                embed_fn=None):
    """按 kind 构建检索后端。kind: 'lexical' (默认) | 'embed'。"""
    chunks = chunk_corpus(corpus_dir)
    if not chunks:
        raise RuntimeError(f"corpus 为空: {corpus_dir}")
    if kind == "lexical":
        return LexicalIndex(chunks)
    if kind == "embed":
        return EmbeddingIndex(chunks, embed_fn=embed_fn)
    raise ValueError(f"未知 index 类型: {kind}")


# ---------------------------------------------------------------------------
# 离线自检 (无需 key/网络): python3 -m cindra.docs_index
# ---------------------------------------------------------------------------

# (query, 期望命中的文件) —— 检索质量回归
_SELFCHECK = [
    ("Actor 和 Pawn 有什么区别", "actor_pawn_character.md"),
    ("GameMode 和 GameState 区别", "gamemode_gamestate.md"),
    ("UPROPERTY 是干什么的", "uproperty_ufunction.md"),
    ("怎么优化 Tick 性能", "tick_and_performance.md"),
    ("垃圾回收 GC 悬空指针", "garbage_collection.md"),
    ("Enhanced Input 怎么绑定按键", "input_system.md"),
    ("delegate 委托 事件 解耦", "delegates_events.md"),
    ("level streaming 子关卡 流式加载", "level_and_world.md"),
    ("SceneComponent 和 ActorComponent 区别", "components.md"),
    ("blueprint 和 c++ 怎么选", "blueprint_vs_cpp.md"),
]


def _selfcheck() -> int:
    chunks = chunk_corpus()
    print(f"切块: {len(chunks)} 块, 来自 "
          f"{len({c['file'] for c in chunks})} 个文件")
    idx = LexicalIndex(chunks)
    passed = 0
    for query, expect_file in _SELFCHECK:
        hits = idx.search(query, k=3)
        top = hits[0] if hits else None
        ok = bool(top) and top["file"] == expect_file
        passed += ok
        mark = "✅" if ok else "❌"
        got = f"{top['file']}#{top['title']} ({top['score']})" if top else "(无结果)"
        print(f"  {mark} {query!r}\n        期望 {expect_file} | 命中 {got}")
    print(f"\n检索质量: {passed}/{len(_SELFCHECK)} top-1 命中")
    return 0 if passed == len(_SELFCHECK) else 1


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
