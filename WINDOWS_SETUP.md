# 在 Windows + UE5 上跑通 Cindra 真闭环

> 目标: 让你敲几条命令, 就能"打一句中文 → UE5 视口里真的生成场景"。
> 顺序很重要, 别跳步。撞坑了先跑诊断脚本 `check_ue.py`, 它会告诉你卡在哪。

## 一次性准备 (只做一次)

### 1. UE5 开启 Python Remote Execution
- 编辑器: **Edit → Plugins**, 搜 **Python**, 启用 **Python Editor Script Plugin**, 重启。
- **Edit → Project Settings → Plugins → Python**:
  - 勾 **Enable Remote Execution**
  - Multicast Group Endpoint 保持默认 `239.0.0.1:6766`
- 重启编辑器。

### 2. 让本机 Python 能 import remote_execution
引擎自带这个模块, 路径类似 (版本号按你的改):
```
C:\Program Files\Epic Games\UE_5.4\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python
```
PowerShell 里 (每个新终端都要设, 或加进系统环境变量):
```powershell
$env:PYTHONPATH = "C:\Program Files\Epic Games\UE_5.4\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python"
```

### 3. 装依赖
```powershell
cd <你放 cindra 的目录>
python -m pip install -r requirements.txt
```

## 每次跑之前

1. **打开 UE5 编辑器**, 随便开一个关卡 (空关卡也行)。
2. 终端设好 `PYTHONPATH` (见上) 和 API key:
   ```powershell
   $env:ANTHROPIC_API_KEY = "sk-ant-..."
   ```

## 第一步: 先跑诊断 (不需要 API key)

**强烈建议第一次先跑这个**, 它把"管道通不通"切成 5 阶, 撞哪一阶立刻知道病因:
```powershell
python check_ue.py
```
- 全过 → 它会在视口里放一个 cube, 并打印下一条命令。
- 卡在某一阶 → 照它打印的"怎么修"做; 若是台阶 4/5 的 unreal API 报错,
  把引擎 **Output Log** 里的 Python 报错贴给我, 我改 `ue_helper.py`。

## 第二步: 跑真闭环

```powershell
# 单次执行
python -m cindra.cli --backend ue --once "生成5个cube排成一排, 中间放个球当主角"

# 交互模式 (可连续下指令, /scene 看场景, /quit 退出)
python -m cindra.cli --backend ue
```
打完一句, 切回 UE 视口 —— Actor 应该真的出现了。Ctrl+Z 能撤销 (每步包了 transaction)。

## 其它三个功能 (不依赖 UE 连接, 有 key 即可)
```powershell
python -m cindra.cli --mode docs --once "Actor 和 Pawn 区别"
python -m cindra.cli --mode code --once "给角色加冲刺技能"
python -m cindra.cli --mode blueprint --once "BeginPlay 时打印 hello"
```

## 撞坑了怎么办
- **几乎所有"连不上/没反应"**: 先 `python check_ue.py`, 按它说的修。
- **台阶 4/5 报 unreal API 错**: 贴 Output Log 的 Python traceback 给我。
  `ue_helper.py` 的真 UE API 调用没在真引擎验证过, 第一次跑可能要按你的 UE 版本微调。
- **中文乱码**: 终端用 UTF-8 (`chcp 65001`)。
