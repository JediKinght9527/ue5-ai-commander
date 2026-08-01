# 发布文案

下面是发帖用的标题和正文（四种平台，各自适配）。每份文案都从"一句话能干什么"切入，不放任何 AI 味套话。

---

## 1. Show HN（Hacker News）

**标题：** Show HN: ue5-ai-commander — Control Unreal Engine 5 with natural language, no UE required to try

**正文：**

```
I built an AI tool that edits Unreal Engine scenes, generates PCG forests,
builds Blueprint nodes, writes C++, and answers engine questions — all from
natural language.

The part I think HN might find novel: you don't need Unreal Engine to try it.
Every module has a deterministic in-memory mock. You can spawn a level, run
a PCG graph that scatters 141 trees, see an ASCII top-down map, and generate
a PNG screenshot — on any machine, zero setup beyond pip install.

git clone https://github.com/JediKinght9527/ue5-ai-commander.git
cd the-repo && pip install -r requirements.txt
python -m the-repo.demo  # generates an oak forest, no UE, no API key

It exposes 43 MCP tools across 9 domains — Claude Code/Cursor talk to it
directly. When you do have UE open on Windows with Python Remote Execution,
the same MCP tools drive the real engine. A snapshot-diff verifier catches
"tool says ok but nothing changed" failures (zero-token hard check, not LLM
vision). 103 offline assertions pass on every push.

Built this because UE 5.7's built-in AI assistant answers questions — it
doesn't do things. I wanted something that acts, looks at the result, and
fixes its own mistakes.

Happy to answer questions, especially about the mock-first architecture or
the PCG graph engine (19 node types, topological-sort executor, deterministic
seeded point-cloud math).
```

---

## 2. r/unrealengine (Reddit)

**标题：** I made an AI that actually builds stuff in UE5 — and you can test it without opening the editor

**正文：**

```
UE 5.7 ships with an AI assistant that's good at explaining how things work.
I wanted something different: an AI that does the work. Builds the scene.
Runs the PCG graph. Compiles the Blueprint. Then checks its own output and
fixes it when it's wrong.

So I built this over the last few weeks. It's called cindra (灰星).

What can it do:
- Scene editing: "put 10 trees in a circle, a rock in the middle"
- PCG: "scatter oak trees on flat ground only, skip the slopes" (19 node types)
- Blueprints: one-call T3D injection for common patterns (event→print, branch→dual-print)
- C++ generation: indexes your project first, then writes matching code
- UE RAG: searches a local knowledge base and cites sources
- Cinematics: orbit/dolly/crane/flyover with render-to-PNG review
- Lighting: 5 stylistic rigs (horror, golden hour, studio, night neon, overcast)
- PIE automation: launch → read log → fix bugs → repeat

The mock backend is what I'm most proud of. Every module has an in-memory
simulation. You can run the whole pipeline on your Mac without UE installed.
pip install, python -m cindra.demo, done — a 141-tree oak forest appears.

It works as an MCP server (43 tools, 9 domains) for Claude Code/Cursor.
On Windows with UE 5.7 and Remote Execution on, it drives the real engine.
Same code, same tools, just flip the transport.

Repo: https://github.com/JediKinght9527/ue5-ai-commander
103 self-checks pass on every commit (GitHub Actions).

Would love feedback, especially from anyone who's tried the other UE MCP
tools and knows what's missing.
```

---

## 3. Epic Dev Community 论坛

**标题：** cindra — AI 直接在编辑器里动手，不只回答问题

**正文：**

```
我知道 UE 5.7 自带了 AI 助手。会用的人不少。我走了另一条路。

我这个工具叫 cindra（灰星）。和官方助手的区别：

官方助手：问"PCG 怎么用"，它回答。
cindra：说"在 200x200m 地形上，只在平坦区域撒橡树"，它建 PCG 图、跑、长出 141 棵树，然后画一张俯视图给你看。

官方助手：问"BeginPlay 怎么接 PrintString"，它说步骤。
cindra：把 T3D 模板注入到蓝图里，节点和线全部建好，编译，报错的话自己修。

核心设计：
- mock 先行：所有模块有内存模拟，Mac 上无 UE 就能验证逻辑
- 验证闭环：每次操作前后拍 scene 快照 diff，工具返回 ok 但引擎没动的情况会被抓出来（零 token 硬校验）
- 双后端透明：mock 全绿 → 切 transport → 同一套代码在真引擎里跑

43 个 MCP 工具，Claude Code 里直接对话。

GitHub: https://github.com/JediKinght9527/ue5-ai-commander
60 秒上手: pip install 后 python -m cindra.demo 生成一片橡树林

想听真实反馈。如果你在 UE5 项目里试过 AI 辅助，觉得哪里还不够用，告诉我。
```

---

## 4. B 站 / 知乎（中文）

**标题：** 我做了个 AI 工具，一句话在 UE5 里生成场景 —— 不用装 UE 就能试

**正文：**

```
UE 5.7 内置 AI 助手，能回答问题，不能动手。

我做的这个可以动手。

说"在场景里放 10 棵树围成一圈"，它直接 spawn。
说"这块地形上只在平坦区域撒橡树，斜坡别长"，它建 PCG 图、跑，长出一片森林。
说"BeginPlay 时打印 hello"，它把蓝图节点和连线全部建好。

亮点：
1. 不用开 UE 就能试 —— 全部模块有 mock 后端，pip install 就跑
2. 操作验证 — 每次改完后前后拍快照，自动对账。工具说 ok 但引擎没动的情况会被抓出来
3. 43 个 MCP 工具，Claude Code / Cursor 直接对话
4. Tripo3D 桥接：文字描述 → 生成 3D 模型 → 导入 UE → PCG 在场景里批量放置

GitHub: https://github.com/JediKinght9527/ue5-ai-commander
安装：pip install -r requirements.txt
试一下：python -m cindra.demo （不用 UE，不用 key，3 行命令看到 141 棵橡树的森林）

做黑神话那个方向的朋友特别注意：PCG 这块在 UE 5.7 已经 production-ready 了，
cindra 直接帮你把自然语言翻译成 PCG 管线，不是教你怎么用 PCG。
```

---

# 发布策略

| 平台 | 什么时候发 | 为什么 |
|------|-----------|--------|
| Show HN | 工作日早上 7-9am PT | 美国白天, 容易被看到 |
| Reddit r/unrealengine | Show HN 后第二天 | 交叉引流, 已有人在 Show HN 评论中打开 |
| Epic 论坛 | 同一天 | 最直接的 UE 用户群体 |
| B站+知乎 | 美国帖子有回应后 | 中文内容反哺英文讨论 |
