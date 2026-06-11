# Level 是什么

Level(关卡)是一组 Actor 的容器,对应一个 `.umap` 资产。它就是你在编辑器里
摆放物体的那个场景。一个 Level 可以是整张地图,也可以是被组合进更大世界的一块。

# World 是什么

World(`UWorld`)是运行时持有所有 Level 和 Actor 的顶层容器。游戏运行时,
存在一个 World,里面有一个 Persistent Level(持久关卡)和若干 Streaming Level
(流式加载的子关卡)。`GetWorld()` 是 C++ 里访问当前世界的常用入口,spawn
Actor、做射线检测(line trace)都需要 World。

# Sublevel 和 Level Streaming 是什么

大世界不会一次性全加载。Level Streaming 让你把世界切成多个 Sublevel,按需
**动态加载/卸载**:玩家走近某区域才加载那块关卡,走远了卸载,节省内存和性能。
开放世界(World Partition)是这套机制的自动化版本。

# Persistent Level 是什么

Persistent Level 是 World 里始终存在的主关卡,负责持有和管理那些会被流式
加载进来的 Sublevel。通常把全局的、一直要在的东西(如关卡蓝图的总控逻辑)
放在持久关卡。
