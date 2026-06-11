# CindraAssets —— 接 Tripo3D 文字生成 3D 模型 (方案 A: REST API 直连)

> 目标: 让 Cindra 能"打一句中文 → Tripo 生成真实 3D 模型 → 自动导入 UE5 → 在视口里 spawn"。
> 这补上了 CindraChat 只能放基础形状 (cube/sphere) 的最大短板, 也是 Ludus 演示里没有的能力。
>
> 状态: **方案已定 (REST API 直连), 代码闭环等上机 (Windows + UE5.5 + Tripo key) 一起做完整。**
> 本文档把两端真实接口查实记清, 上机时照此实现, 不在"API 怎么调"上卡壳。

---

## 架构: 完全复用现有 cnd_* / mock-real 双后端骨架

新增一个 `--mode assets` (工作名 **CindraAssets**), agent loop / CLI 派发 / 双后端
和现有四大功能同构。整条链路两段:

```
[第一段: 生成模型文件]  agent → tripo_tools → Tripo REST API → 下载 .glb 到本地
[第二段: 导入并放置]    agent → asset_tools → transport(ue) → cnd_import_mesh() → cnd_spawn_mesh()
```

- **第一段在 Mac 上就能验证** (只要有 Tripo key + 联网), 不依赖 UE。
- **第二段依赖 UE**, 用和 ue_helper.py 一样的 Remote Execution 注入新 helper。

---

## 第一段: Tripo3D REST API (查实)

Tripo API 是**异步**的: 提交任务拿 task_id → 轮询状态 → success 后从 `data.output.model` 拿 GLB 下载 URL。

- **Base**: `https://api.tripo3d.ai/v2/openapi`
- **认证**: Header `Authorization: Bearer tsk_***` (key 以 `tsk_` 开头, 注意不是 sk-ant)
- **输出格式**: GLB / GLTF / FBX / OBJ 都支持; 默认拿 **GLB** (含 PBR 贴图, 最适合直接导入)
- ⚠️ **下载 URL 有时效 (约 24h), 生成完立刻下载。**

### 创建任务
```
POST /task
body: { "type": "text_to_model", "prompt": "中文或英文描述" }
→ 返回 data.task_id
```

### 轮询 + 下载 (REST 版, 不引第三方 SDK, 和项目"纯标准库优先"一致)
```python
import requests, time

BASE = "https://api.tripo3d.ai/v2/openapi"
HEAD = {"Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"}

# 1) 建任务
r = requests.post(f"{BASE}/task", headers=HEAD,
                  json={"type": "text_to_model", "prompt": prompt})
task_id = r.json()["data"]["task_id"]

# 2) 轮询
while True:
    d = requests.get(f"{BASE}/task/{task_id}", headers=HEAD).json()["data"]
    if d["status"] == "success":
        model_url = d["output"]["model"]        # GLB; PBR 版在 output.pbr_model
        break
    if d["status"] in ("failed", "cancelled", "unknown"):
        raise RuntimeError(f"Tripo 任务失败: {d['status']}")
    time.sleep(2)

# 3) 下载
glb = requests.get(model_url).content
open("model.glb", "wb").write(glb)
```

> 也有官方 SDK (`pip install tripo3d`, `TripoClient().text_to_model(...)`) 更省事,
> 但 REST 版无额外依赖、可控、和项目风格一致。**默认用 REST。**

### mock 后端 (Mac 无 key / 离线时验证逻辑)
`tripo_transport.py` 双后端: real 打真 API; mock 不联网, 直接返回一个本地占位
`.glb` 路径 (放一个小的 placeholder.glb 在仓库里), 让第二段链路能在 Mac 上空跑验证。

---

## 第二段: 把 GLB 导入 UE5.5 并 spawn (查实 —— 这里有坑)

### 关键事实: GLB 必须走 Interchange, 不能用老的 AssetImportTask
- UE5.1+ 起, 老的 `AssetImportTask` 只对 **FBX** 可靠; **GLB/GLTF 必须用 Interchange 框架**。
- 需确认编辑器启用了 **glTF Interchange importer** 插件 (5.5 默认带, 检查一下)。

### cnd_import_mesh() 草案 (上机时按真实报错微调, 同 ue_helper 的打法)
```python
def cnd_import_mesh(glb_path, dest="/Game/CindraAssets", name=None):
    src = unreal.InterchangeManager.create_source_data(glb_path)
    params = unreal.ImportAssetParameters()
    params.is_automated = True
    mng = unreal.InterchangeManager.get_interchange_manager_scripted()
    # import_asset(dest_path, source_data, params) → 资产进 Content Browser
    # 返回/查到生成的 StaticMesh 资产路径, 供下一步 spawn
    ...
```

### cnd_spawn_mesh(): 导入后在场景放出来
导入得到 StaticMesh 资产后, 复用现有 spawn 思路 (spawn StaticMeshActor →
`static_mesh_component.set_static_mesh(load_asset(资产路径))`), 这部分和已验证的
ue_helper.cnd_spawn 一模一样, 风险低。

### 已知坑 (查证记录, 上机对照)
1. **Interchange 在 commandlet/headless 里可能崩** —— 我们走的是编辑器内 Remote
   Execution (有 GUI), 不是 commandlet, 应该没事。若崩, 看 Output Log。
2. **GLB 贴图丢失** —— 有报告 GLB 导入后只有几何体、贴图变成默认材质。若出现,
   优先用 `output.pbr_model` (PBR 版), 或导入后手动连材质。先接受"先有形状"。
3. **AI 生成网格面数高** —— Tripo 自己强调生成是"起跑线不是终点", 正式资产需
   减面/重拓扑。**做 demo 阶段先不管**, 能 spawn 出真实模型已经够震撼。

---

## 上机实现顺序 (Windows + UE5.5)

1. 先确认现有真闭环跑通 (`check_ue.py` 5 阶全过) —— 这是基础。
2. 实现 `tripo_tools.py` + REST 调用, **先单独验证**: 一句 prompt 能下到 model.glb。
3. 把 `cnd_import_mesh` / `cnd_spawn_mesh` 加进 ue_helper (或新建 asset_helper),
   先手动 `check` 式验证: 拿第 2 步下好的 glb, 注入 helper, 看能否导入 + spawn。
4. 串成 `--mode assets` 的 agent loop, 端到端打一句中文 → 视口出现真实模型。
5. 卡在 UE 导入 → 贴 Output Log 的 Python traceback 给 Claude 改 helper。

---

## 需要你准备
- **Tripo API key** (在 platform.tripo3d.ai 注册拿, `tsk_` 开头) —— 注意计费, 每次生成消耗额度。
- 确认 UE5.5 的 **glTF Interchange importer** 插件已启用 (Edit → Plugins 搜 glTF / Interchange)。
