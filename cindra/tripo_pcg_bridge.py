"""tripo_pcg_bridge —— Tripo3D 文字生成 3D 模型 → PCG spawn 整链。

这个文件把 CindraAssets (Tripo3D) 和 CindraPCG (PCG spawn) 串成一整条链路:
  1. agent 描述想要什么 3D 资产 (中文/英文 prompt)
  2. Tripo REST API 生成 .glb 模型文件
  3. GLB 导入 UE5 (走 Interchange 框架)
  4. PCG 图的 static_mesh_spawner 节点指向这个资产
  5. run_pcg_graph → 场景里每个 spawn 点都是这个真实 3D 模型

这是 Ludus 完全做不到的事情: PCG 大量生成的不只是 cube/sphere,
而是 AI 实时创造的独特 3D 模型。

mock 端 (本文件): 模拟 Tripo 调用 (占位 glb) + 模拟 Interchange 导入 + 把 mesh_path
写到 PCG 节点参数里。Mac 上可完整验证链路逻辑。

真 UE 端: 替换 Tripo 调用为真 REST API, 替换导入为 InterchangeManager,
其余不变。

自检: python3 -m cindra.tripo_pcg_bridge
"""

from __future__ import annotations

import json
import os
import time

# ═══════════════════════════════════════════════════════════════
# Tripo3D 客户端 (mock + real 双后端)
# ═══════════════════════════════════════════════════════════════


class TripoClient:
    """Tripo3D 客户端基类。"""

    def text_to_model(self, prompt: str, output_path: str, model_format: str = "glb") -> dict:
        raise NotImplementedError


class MockTripoClient(TripoClient):
    """mock 后端: 不联网, 本地生成一个极简有效的 GLB 占位文件。

    最小可验证的 GLB: 有一个 triangle 的二进制数据 (12B header + JSON chunk +
    三角形 binary buffer)。能让后续链路跑通而不卡在"没有模型文件"上。
    """

    # 最小 glb 二进制: 一个 triangle 的 box (Mock 用, 不是真实美工模型)
    PLACEHOLDER_GLB = (
        b"glTF\x02\x00\x00\x00\xb4\x00\x00\x00\x84\x00\x00\x00"
        b'JSON{"asset":{"version":"2.0"},"scenes":[{"nodes":[0]}],'
        b'"nodes":[{"mesh":0}],"meshes":[{"primitives":[{"attributes":'
        b'{"POSITION":1},"indices":0}]}],"accessors":['
        b'{"bufferView":0,"componentType":5123,"count":3,"type":"SCALAR"},'
        b'{"bufferView":1,"componentType":5126,"count":3,"type":"VEC3"}],'
        b'"bufferViews":[{"buffer":0,"byteOffset":0,"byteLength":6},'
        b'{"buffer":0,"byteOffset":8,"byteLength":36}],'
        b'"buffers":[{"byteLength":44}]}\x00\x00\x00\x00'
        b"BIN\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x01\x00\x02\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x80\x3f\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x80\x3f\x00\x00\x00\x00"
    )

    def text_to_model(self, prompt: str, output_path: str, model_format: str = "glb") -> dict:
        """mock 生成: 写一个占位 GLB 文件。"""
        path = (
            output_path
            if output_path.endswith(f".{model_format}")
            else f"{output_path}.{model_format}"
        )
        with open(path, "wb") as f:
            f.write(self.PLACEHOLDER_GLB)
        return {
            "ok": True,
            "action": "tripo_generate",
            "prompt": prompt,
            "model_path": path,
            "format": model_format,
            "size_bytes": os.path.getsize(path),
            "note": "mock 占位模型 (Mac 离线验证用)。真 UE 上替换为 Tripo REST API 生成的真实模型。",
        }


class RealTripoClient(TripoClient):
    """真实 Tripo REST API 客户端。"""

    def __init__(self, api_key: str, base_url: str = "https://api.tripo3d.ai/v2/openapi"):
        self.api_key = api_key
        self.base_url = base_url

    def text_to_model(self, prompt: str, output_path: str, model_format: str = "glb") -> dict:
        """调 Tripo REST API, 异步任务 → 轮询 → 下载 GLB。"""
        import urllib.error
        import urllib.request

        base = self.base_url
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        # 1) 创建任务
        req = urllib.request.Request(
            f"{base}/task",
            data=json.dumps({"type": "text_to_model", "prompt": prompt}).encode(),
            headers=headers,
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            task = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return {"ok": False, "error": f"Tripo HTTP {e.code}: {e.read().decode()[:200]}"}
        except Exception as e:
            return {"ok": False, "error": f"Tripo 请求失败: {e}"}

        task_id = task.get("data", {}).get("task_id")
        if not task_id:
            return {"ok": False, "error": f"Tripo 创建任务失败: {task}"}

        # 2) 轮询 (最多 120s)
        deadline = time.time() + 120
        while time.time() < deadline:
            r2 = urllib.request.Request(f"{base}/task/{task_id}", headers=headers)
            try:
                resp = urllib.request.urlopen(r2, timeout=15)
                d = json.loads(resp.read()).get("data", {})
            except Exception:
                time.sleep(2)
                continue
            status = d.get("status")
            if status == "success":
                model_url = d.get("output", {}).get("model")
                if not model_url:
                    return {"ok": False, "error": "Tripo 成功但无 model URL"}
                break
            if status in ("failed", "cancelled", "unknown"):
                return {"ok": False, "error": f"Tripo 任务 {status}"}
            time.sleep(2)
        else:
            return {"ok": False, "error": "Tripo 轮询超时"}

        # 3) 下载
        from urllib.request import urlopen as _urlopen

        try:
            data = _urlopen(model_url, timeout=60).read()
        except Exception as e:
            return {"ok": False, "error": f"下载模型文件失败: {e}"}

        path = (
            output_path
            if output_path.endswith(f".{model_format}")
            else f"{output_path}.{model_format}"
        )
        with open(path, "wb") as f:
            f.write(data)
        return {
            "ok": True,
            "action": "tripo_generate",
            "prompt": prompt,
            "model_path": path,
            "format": model_format,
            "size_bytes": len(data),
            "task_id": task_id,
        }


# ═══════════════════════════════════════════════════════════════
# GLB → UE5 资产导入
# ═══════════════════════════════════════════════════════════════


class AssetImporter:
    """GLB 导入器基类。"""

    def import_glb(
        self,
        glb_path: str,
        dest_folder: str = "/Game/CindraAssets/PCG",
        asset_name: str | None = None,
    ) -> dict:
        raise NotImplementedError


class MockAssetImport(AssetImporter):
    """mock 后端: 不真的导入, 只返回一个预期的 UE 资产路径。"""

    def import_glb(
        self,
        glb_path: str,
        dest_folder: str = "/Game/CindraAssets/PCG",
        asset_name: str | None = None,
    ) -> dict:
        basename = asset_name or os.path.splitext(os.path.basename(glb_path))[0]
        # UE 资产路径格式
        ue_path = f"{dest_folder}/{basename}.{basename}"
        return {
            "ok": True,
            "action": "import_glb",
            "asset_path": ue_path,
            "note": "mock: 真 UE 上走 InterchangeManager.create_source_data + ImportAssetParameters",
        }


class UEAssetImport(AssetImporter):
    """真 UE 后端: 走 Interchange 框架导入 GLB。

    依赖: UE 5.7 编辑器 + glTF Interchange importer 插件已启用。
    """

    def import_glb(
        self,
        glb_path: str,
        dest_folder: str = "/Game/CindraAssets/PCG",
        asset_name: str | None = None,
    ) -> dict:
        try:
            import unreal

            basename = asset_name or os.path.splitext(os.path.basename(glb_path))[0]
            src = unreal.InterchangeManager.create_source_data(glb_path)
            params = unreal.ImportAssetParameters()
            params.is_automated = True
            params.asset_name = basename
            params.destination_path = dest_folder
            mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
            result = mgr.import_asset(dest_folder, src, params)
            asset_path = f"{dest_folder}/{basename}"
            return {
                "ok": True,
                "action": "import_glb",
                "asset_path": asset_path,
                "result": str(result),
            }
        except Exception as e:
            return {"ok": False, "error": f"GLB 导入失败: {e}. 检查: glTF Interchange 插件已启用?"}


# ═══════════════════════════════════════════════════════════════
# 主流程: Tripo 生成 → 导入 → 更新 PCG spawner
# ═══════════════════════════════════════════════════════════════


def generate_and_bind(
    tripo_client: TripoClient,
    importer: AssetImporter,
    pcg_graph,
    spawner_node_id: str,
    prompt: str,
    model_name: str | None = None,
    output_dir: str = "/tmp/cindra_tripo",
    ue_dest: str = "/Game/CindraAssets/PCG",
) -> dict:
    """端到端: 文字描述 → Tripo 生成 GLB → 导入 UE → 更新 PCG spawner 节点。

    这是用户说"在这里生成一座哥特式教堂"的完整对应:
    CindraChat 放建筑底座 → CindraPCG 在底座周围 scatter → Tripo 生成
    哥特式教堂模型 → spawner 节点用这个模型而不是 cube。

    参数:
      tripo_client: MockTripoClient 或 RealTripoClient
      importer:     MockAssetImport 或 UEAssetImport
      pcg_graph:    PCGGraph 实例
      spawner_node_id: 要更新 mesh_path 的 static_mesh_spawner 节点 id
      prompt:       Tripo 文字描述
      model_name:   模型名字 (作文件名和资产名)
      output_dir:   下载 glb 的本地目录
      ue_dest:      UE Content Browser 导入路径

    mock 端可整链验证 (不联网、没有 UE), 真 UE 端替换 tripo_client 和 importer 即可。
    """
    os.makedirs(output_dir, exist_ok=True)
    name = model_name or prompt.replace(" ", "_")[:40].replace("/", "_")

    # 第一步: Tripo 生成 GLB
    glb_path = os.path.join(output_dir, f"{name}")
    gen_result = tripo_client.text_to_model(prompt, glb_path)
    if not gen_result.get("ok"):
        return {
            "ok": False,
            "error": f"Tripo 生成失败: {gen_result.get('error')}",
            "step": "generate",
        }

    # 第二步: 导入 UE (mock 只是返回预期路径)
    imp_result = importer.import_glb(gen_result["model_path"], ue_dest, name)
    if not imp_result.get("ok"):
        return {
            "ok": False,
            "error": f"资产导入失败: {imp_result.get('error')}",
            "step": "import",
            "glb_path": gen_result["model_path"],
        }

    # 第三步: 更新 PCG spawner 节点的 mesh_path
    asset_path = imp_result["asset_path"]
    set_result = pcg_graph.set_param(spawner_node_id, "mesh_path", asset_path)
    if not set_result.get("ok"):
        return {
            "ok": False,
            "error": f"更新 PCG 节点失败: {set_result.get('error')}",
            "step": "bind",
            "asset_path": asset_path,
        }

    return {
        "ok": True,
        "action": "tripo_pcg_bind",
        "model_prompt": prompt,
        "glb_path": gen_result["model_path"],
        "asset_path": asset_path,
        "spawner_node": spawner_node_id,
        "ready_to_execute": True,
    }


# ═══════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════


def _selfcheck() -> int:
    """离线自检: 用 mock 后端跑通 Tripo→PCG 整链。"""
    import tempfile

    from .pcg_model import PCGGraph

    tmpdir = tempfile.mkdtemp(prefix="cindra_tripo_test_")

    # 1) 建一张简单的 PCG 图 (只有 sampler → spawner)
    g = PCGGraph()
    g.add_node(
        "volume_input", "area", {"shape": "box", "location": [0, 0, 0], "extent": [2000, 2000, 500]}
    )
    g.add_node("volume_sampler", "sampler", {"points_per_cubic_meter": 0.02, "seed": 42})
    g.add_node(
        "static_mesh_spawner",
        "buildings",
        {"mesh_path": "/Engine/BasicShapes/Cube.Cube", "density_threshold": 0.0},
    )
    g.connect("area", "volume", "sampler", "source")
    g.connect("sampler", "points", "buildings", "points")

    # 2) 先跑一次 (用默认 cube) 确认图正常
    r0 = g.execute()
    assert r0["ok"] and r0["outputs"][-1]["stats"]["count"] > 0, f"PCG 图执行失败: {r0}"
    before_count = r0["outputs"][-1]["stats"]["count"]
    print(f"✅ PCG 图正常: {before_count} 个 spawn 点 (默认 cube)")

    # 3) Tripo 生成 → 导入 → 更新 spawner
    tripo = MockTripoClient()
    imp = MockAssetImport()
    result = generate_and_bind(
        tripo,
        imp,
        g,
        "buildings",
        prompt="一座哥特式大教堂, 尖顶, 飞扶壁",
        model_name="Gothic_Cathedral",
        output_dir=tmpdir,
    )
    assert result["ok"], f"Tripo→PCG 桥接失败: {result}"
    print(f"✅ Tripo 生成: {result['model_prompt']} → {result['glb_path']}")
    print(f"✅ 资产导入: GLB → {result['asset_path']}")

    # 4) 验证 spawner 节点参数已更新
    node = g.nodes["buildings"]
    assert node["params"]["mesh_path"] == result["asset_path"], (
        f"mesh_path 未更新: {node['params']['mesh_path']}"
    )
    print(f"✅ PCG spawner mesh_path 已更新: {node['params']['mesh_path']}")

    # 5) 再执行 → 点还是那么多, 但 mesh 变了
    r1 = g.execute()
    assert r1["ok"] and r1["outputs"][-1]["stats"]["count"] == before_count, (
        f"更新 mesh 后执行失败: {r1}"
    )
    print(f"✅ 更新 mesh 后再执行: {before_count} 个 spawn 点 (mesh={result['asset_path']})")

    # 6) 验证 glb 文件确实存在且非空
    assert os.path.exists(result["glb_path"]) and os.path.getsize(result["glb_path"]) > 0, (
        f"GLB 文件不存在: {result['glb_path']}"
    )
    print(f"✅ GLB 文件已落地: {os.path.getsize(result['glb_path'])} bytes")

    # 清理
    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)

    print("\nTripo→PCG 桥接自检 6/6 通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selfcheck())
