# Windows UE5.7 安装与配置指南

## 前置要求

- Windows 10/11 (64-bit)
- Unreal Engine 5.7 (Epic Games Launcher 安装)
- Python 3.11+ (系统 PATH 里)
- Git

## 1. 克隆仓库

```powershell
git clone https://github.com/yourname/cindra.git
cd cindra
pip install -e ".[dev]"
```

## 2. UE5 Python Remote Execution

1. 打开 UE5 编辑器 → Edit → Project Settings
2. 搜索 "Python" → Python Script Plugin
3. 勾选 **Enable Remote Execution**
4. 重启编辑器

验证:
```powershell
$env:PYTHONPATH = "C:\Program Files\Epic Games\UE_5.7\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python"
python check_ue.py
```
台阶 1-3 全过即可继续。

## 3. 编译 CindraEditorPanel 插件

插件目录: `ue_plugin/CindraEditorPanel/`

### 方法 A: 拖入项目 (推荐)

1. 把 `ue_plugin/CindraEditorPanel/` 整个复制到你的 UE 项目的 `Plugins/` 目录
2. 右键 `.uproject` → **Generate Visual Studio project files**
3. 用 Visual Studio 2022 打开 `.sln`, 选 `Development Editor | Win64`, Build
4. 重新打开 UE 编辑器 → Edit → Plugins → 搜索 "Cindra" → 勾选启用 → 重启

### 方法 B: 引擎插件

把插件复制到:
```
C:\Program Files\Epic Games\UE_5.7\Engine\Plugins\Editor\CindraEditorPanel\
```
然后同上 Generate + Build。

### 验证插件

```powershell
python check_ue.py
```
台阶 9 (蓝图桥) 应显示 ✅。

## 4. Movie Render Queue (运镜模式)

1. Edit → Plugins → 搜索 "Movie Render Queue" → 勾选 → 重启
2. `python check_ue.py` 台阶 8b 应显示 ✅

## 5. 配置 API Key

```powershell
# Anthropic (默认)
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# 或 DeepSeek
$env:CINDRA_MODEL_PROVIDER = "deepseek"
$env:DEEPSEEK_API_KEY = "sk-..."
```

永久设置: 系统属性 → 环境变量 → 新建用户变量。

## 6. 快速验证全链路

```powershell
# 场景搭建 (chat 模式)
python -m cindra.cli --backend ue --once "用木箱和石头搭一个营地, 加恐怖氛围灯光, 看一眼"

# 运镜 (cine 模式)
python -m cindra.cli --mode cine --backend ue --once "给场景来个8秒环绕镜头并渲染故事板"

# 蓝图 (blueprint 模式)
python -m cindra.cli --mode blueprint --backend ue --once "建一个 Actor 蓝图, BeginPlay 时打印 Hello"
```

## 7. 常见问题

**台阶 2 失败 (找不到 UE 节点)**
- 确认编辑器正在运行且已加载关卡
- 防火墙: 允许 UDP 239.0.0.1:6766 (多播)
- 有时需要在编辑器里点一下 Output Log 窗口激活 Python

**台阶 4 失败 (helper 注入报错)**
- 看 UE Output Log 里的 Python 错误
- 常见: `unreal.EditorActorSubsystem` API 在 5.7 有小改动
- 把报错贴到 issue 或直接改 `cindra/ue_helpers/scene.py`

**台阶 9 失败 (蓝图桥)**
- 确认插件已编译且在 Plugins 面板里勾选
- 确认 Build 时没有 C++ 错误 (看 VS Output)
- `UCindraBlueprintLib` 需要 `BlueprintGraph` 模块, 确认 Build.cs 里有

**MRQ 渲染超时**
- 确认关卡已保存 (Ctrl+S)
- 确认 viewport 可见 (最小化会导致 PIE executor 挂起)
- 渲染目录: `<Project>/Saved/Cindra/renders/<sequence>/`

**资产枚举 (台阶 7) 返回 0 条**
- 项目里确实没有资产? 先导入几个 mesh
- 或指定 roots: `cnd_list_assets(roots=['/Game'])`
