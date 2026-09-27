"""asset_index —— 工程资产检索 (真资产世界搭建的入口)。

告别"只会摆 cube": 把工程里真实的 mesh/材质/蓝图/PCG 图索引起来,
agent 用自然语言找资产 ("木箱子" -> /Game/Props/SM_Crate_A), 再 spawn_asset。

manifest 来源 (与 mock/real 双后端同构):
  mock  cindra/mock_assets/manifest.json (内置 ~60 条仿真条目, 离线可测)
  real  cnd_list_assets 在 UE 侧枚举 AssetRegistry 并写盘
        <Project>/Saved/Cindra/asset_manifest.json —— 大 manifest 不走
        remote-exec 输出 (硬规则), cindra 侧读文件。

检索复用 docs_index.LexicalIndex (BM25, 离线确定性): 资产名按
CamelCase/下划线拆词 (SM_Crate_A -> "sm crate a"), 连同 class/tags/路径段
一起进索引。几千条量级构建 <1s, 每次进程内直接重建, 不做磁盘缓存。

自检: python3 -m cindra.asset_index (8/8 top-1 回归)
"""

from __future__ import annotations

import json
import os
import re

from .docs_index import LexicalIndex

MOCK_MANIFEST = os.path.join(os.path.dirname(__file__), "mock_assets", "manifest.json")

# 工具层的 class_filter 值 -> manifest 里的资产 class
_CLASS_FILTERS = {
    "static_mesh": {"StaticMesh"},
    "material": {"Material", "MaterialInstanceConstant"},
    "blueprint": {"Blueprint"},
    "pcg_graph": {"PCGGraph"},
    "niagara": {"NiagaraSystem"},
}


def _split_words(name: str) -> str:
    """SM_Crate_A / PCGForestScatter -> 'sm crate a' / 'pcg forest scatter'。"""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    s = re.sub(r"[_\-/.]", " ", s)
    return " ".join(w for w in s.lower().split() if w)


class AssetIndex:
    """资产清单 -> BM25 索引。search 返回带完整 path/class 的条目。"""

    def __init__(self, manifest_path: str = MOCK_MANIFEST) -> None:
        self.manifest_path = manifest_path
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assets: list[dict] = data.get("assets", [])
        self.by_path = {a["path"]: a for a in self.assets}
        chunks = []
        for a in self.assets:
            text = " ".join(
                [
                    _split_words(a["name"]),
                    _split_words(a.get("class", "")),
                    " ".join(a.get("tags", [])),
                    _split_words(a["path"]),
                ]
            )
            chunks.append({"id": a["path"], "title": a["name"], "file": a["path"], "text": text})
        self._index = LexicalIndex(chunks) if chunks else None

    def search(self, query: str, k: int = 8, class_filter: str | None = None) -> list[dict]:
        if self._index is None:
            return []
        wanted = _CLASS_FILTERS.get(class_filter or "")
        hits = self._index.search(query, k=k * 4 if wanted else k)
        out = []
        for h in hits:
            a = self.by_path.get(h["file"])
            if a is None:
                continue
            if wanted and a.get("class") not in wanted:
                continue
            out.append(
                {
                    "path": a["path"],
                    "name": a["name"],
                    "class": a.get("class", ""),
                    "tags": a.get("tags", []),
                    "score": h["score"],
                }
            )
            if len(out) >= k:
                break
        return out

    def has(self, path: str) -> bool:
        return path in self.by_path


def load_asset_index(manifest_path: str | None = None) -> AssetIndex:
    """manifest_path 不给则用 mock 内置清单 (真后端由 CLI 在刷新后传真路径)。"""
    return AssetIndex(manifest_path or MOCK_MANIFEST)


# (query, class_filter, 期望 top-1 path) —— 检索质量回归
_SELFCHECK = [
    ("wooden crate 木箱", None, "/Game/Props/SM_Crate_A.SM_Crate_A"),
    ("rusty metal material", "material", "/Game/Materials/M_Rusty_Metal.M_Rusty_Metal"),
    ("large rock 大石头", None, "/Game/Environment/SM_Rock_Large.SM_Rock_Large"),
    ("dead spooky tree", None, "/Game/Environment/SM_Tree_Dead.SM_Tree_Dead"),
    ("campfire", None, "/Game/Props/SM_Campfire.SM_Campfire"),
    (
        "flickering horror lamp",
        "blueprint",
        "/Game/Blueprints/BP_Flickering_Lamp.BP_Flickering_Lamp",
    ),
    ("forest scatter pcg", "pcg_graph", "/Game/PCG/PCG_Forest_Scatter.PCG_Forest_Scatter"),
    ("stone wall", "static_mesh", "/Game/Architecture/SM_Wall_Stone_4m.SM_Wall_Stone_4m"),
]


def _selfcheck() -> int:
    idx = load_asset_index()
    print(f"资产清单: {len(idx.assets)} 条 ({idx.manifest_path})")
    passed = 0
    for query, cf, expect in _SELFCHECK:
        hits = idx.search(query, k=3, class_filter=cf)
        top = hits[0] if hits else None
        ok = bool(top) and top["path"] == expect
        passed += ok
        mark = "✅" if ok else "❌"
        got = f"{top['path']} ({top['score']})" if top else "(无结果)"
        print(f"  {mark} {query!r} filter={cf}\n        期望 {expect}\n        命中 {got}")
    print(f"\n资产检索: {passed}/{len(_SELFCHECK)} top-1 命中")
    return 0 if passed == len(_SELFCHECK) else 1


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
