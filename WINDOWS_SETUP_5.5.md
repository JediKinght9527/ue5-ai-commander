# Cindra 在 Windows + UE 5.5 上跑通真闭环 —— 详细操作步骤

> 目标: 从拿到 `cindra_win.zip`, 到在 UE5 视口里"打一句中文 → 真的生成场景"。
> 每一步都可逐条照抄。**顺序很重要, 别跳步。** 撞坑了第 6 节有对照表。

---

## 前置检查 (确认你有这些)

- [ ] Windows 电脑, 装了 **UE 5.5** (Epic Games Launcher 里能看到版本号)
- [ ] 装了 **Python 3** (命令行敲 `python --version` 有输出; 没有就去 python.org 装, 勾 "Add to PATH")
- [ ] `cindra_win.zip` 已经拷到这台 Windows
- [ ] (真闭环那步才需要) 一个 **ANTHROPIC_API_KEY** (sk-ant-... 开头)

> 注: 前 5 节诊断**不需要 API key**, 先把管道打通再说。

---

## 第 1 节. 解压代码

1. 右键 `cindra_win.zip` → **全部解压**, 解压到比如 `C:\cindra`。
2. 解压后确认目录里能看到 `cindra\` 文件夹 (里面有 `cli.py`、`ue_helper.py` 等) 和 `check_ue.py`、`requirements.txt`。

> 记住这个路径 (例: `C:\cindra`), 下面命令都在这个目录里跑。

---

## 第 2 节. UE5 里开 Python 远程执行 (一次性, 做完重启编辑器)

1. 打开 **UE 5.5 编辑器** (随便开/新建一个关卡, 空关卡也行)。
2. 顶部菜单 **Edit → Plugins**:
   - 搜索框输入 `Python`
   - 勾上 **Python Editor Script Plugin**
   - 它会提示重启, 先别急, 把下一步也设了再一起重启。
3. 顶部菜单 **Edit → Project Settings**, 左侧找到 **Plugins → Python**:
   - 勾上 **Enable Remote Execution**
   - **Multicast Group Endpoint** 保持默认 `239.0.0.1:6766` (不要改)
4. **完全关闭并重启 UE5 编辑器**, 重新打开你那个关卡。

> ⚠️ 5.5 注意: 重启后确保**视口是可见的** (别把 Viewport 标签藏到别的标签后面)。
> 5.5 有个已知 bug: 没有可见视口时 spawn 会触发崩溃。正常打开关卡就没事。

---

## 第 3 节. 配 Python 环境 (每开一个新的 PowerShell 窗口都要重设, 见末尾"一劳永逸")

1. 按 **Win 键**, 搜 `PowerShell`, 打开 **Windows PowerShell**。
2. 进入代码目录 (按你的实际路径改):
   ```powershell
   cd C:\cindra
   ```
3. 让 Python 能找到引擎自带的 `remote_execution.py` 模块。**这是 5.5 的路径** (引擎装在默认位置时):
   ```powershell
   $env:PYTHONPATH = "C:\Program Files\Epic Games\UE_5.5\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python"
   ```
   > 如果你的 UE 装在别的盘 (比如 D 盘), 把前面 `C:\Program Files\Epic Games` 换成你的实际安装位置。
   > 不确定路径? 在文件资源管理器里搜 `remote_execution.py`, 它所在的文件夹就是这个值。
4. 装依赖:
   ```powershell
   python -m pip install -r requirements.txt
   ```

---

## 第 4 节. 跑诊断脚本 (不需要 API key —— 一定先跑这个!)

确保 **UE5 编辑器开着、关卡加载了、视口可见**, 然后在刚才那个 PowerShell 窗口:

```powershell
python check_ue.py
```

这个脚本把"Python ↔ UE 引擎"这条管道切成 **5 个台阶**, 撞在哪一阶立刻知道病因:

| 台阶 | 在验证什么 | 失败通常是 |
|---|---|---|
| [1] import remote_execution | PYTHONPATH 对不对 | 第 3 节第 3 步路径写错 |
| [2] 发现 UE 节点 | 编辑器开着? 远程执行开了? | 第 2 节没设好 / 防火墙拦 UDP |
| [3] 远程执行 1+1 | 管道双向通不通 | 重启编辑器再试 |
| [4] 注入 cnd_*() helper | ue_helper 源码在引擎里能跑吗 | **要贴 Output Log 给我** |
| [5] 真调 cnd_list/cnd_spawn | unreal API 真能 spawn 吗 | **要贴 Output Log 给我** |

**结果怎么处理:**

- ✅ **全过 (打印 🎉 全部 5 阶通过)** → 它已经在视口里放了一个 cube。直接进第 5 节。
- ❌ **卡在台阶 1/2/3** → 脚本会打印"怎么修", 照着做 (基本是环境配置问题), 然后重跑。
- ❌ **卡在台阶 4 或 5** → 这是要我改代码的地方。去 UE 编辑器 **Window → Output Log**, 找到那段红色的 Python 报错 (traceback), **整段原样复制贴给我**, 我改 `ue_helper.py` 发你新版。

---

## 第 5 节. 跑真闭环 (需要 API key)

诊断全过后, 在**同一个 PowerShell 窗口** (PYTHONPATH 还在):

1. 设 API key:
   ```powershell
   $env:ANTHROPIC_API_KEY = "sk-ant-你的key"
   ```
2. 中文别乱码, 切 UTF-8:
   ```powershell
   chcp 65001
   ```
3. 打第一句 —— 单次执行:
   ```powershell
   python -m cindra.cli --backend ue --once "生成5个cube排成一排, 中间放个球当主角"
   ```
4. **切回 UE5 视口看** —— Actor 应该真的出现了。这就是 Cindra 从 mock 变成真能用的分界点。
5. 想连续下指令, 用交互模式:
   ```powershell
   python -m cindra.cli --backend ue
   ```
   - 里面可以连续打中文指令
   - `/scene` 看当前场景
   - `/quit` 退出
6. **Ctrl+Z** 在编辑器里能撤销 (每步都包了 transaction)。
   > 如果发现撤销历史有条目但 Ctrl+Z 不真撤销 —— 告诉我, 我给 ue_helper 加 `actor.modify()`。

---

## 另外三个功能 (不依赖 UE 连接, 有 API key 就能跑)

这三个在 Mac 上就验证过了, Windows 上同样跑:

```powershell
python -m cindra.cli --mode docs --once "Actor 和 Pawn 区别"
python -m cindra.cli --mode code --once "给角色加冲刺技能"
python -m cindra.cli --mode blueprint --once "BeginPlay 时打印 hello"
```

---

## 第 6 节. 撞坑对照表

| 现象 | 原因 / 怎么修 |
|---|---|
| 台阶 1 报 `No module named remote_execution` | 第 3 节第 3 步 PYTHONPATH 路径不对; 搜 `remote_execution.py` 确认实际位置 |
| 台阶 2 "没发现 UE 节点" | ①编辑器没开 ②没勾 Enable Remote Execution / 没重启 ③防火墙拦了 UDP 多播 (临时关防火墙试) |
| 台阶 3 失败 | 重启编辑器; 确认没有别的程序占用连接 |
| 台阶 4/5 报 unreal API 错 | **去 Output Log 抓 Python traceback 贴给我**, 我按你的 5.5 改 ue_helper.py |
| spawn 时编辑器崩溃 | 第 2 节那个 5.5 视口 bug —— 确保有一个可见视口再跑 |
| 中文乱码 | `chcp 65001` 切 UTF-8 |
| `python` 命令找不到 | Python 没装或没加 PATH; 重装勾 "Add Python to PATH" |

---

## 附: 一劳永逸 (不想每次重设 PYTHONPATH)

每开一个新 PowerShell 都要重设 `$env:PYTHONPATH` 很烦。想永久设:

1. Win 键搜 "环境变量" → **编辑系统环境变量** → **环境变量** 按钮
2. 在"用户变量"里 **新建**:
   - 变量名: `PYTHONPATH`
   - 变量值: `C:\Program Files\Epic Games\UE_5.5\Engine\Plugins\Experimental\PythonScriptPlugin\Content\Python`
3. 确定, 之后新开的终端就自动带上了 (旧终端要重开)。

API key 同理可以设成用户变量 `ANTHROPIC_API_KEY`, 就不用每次 `$env:` 了。
