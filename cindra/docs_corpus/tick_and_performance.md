# Tick 是什么

Tick 是 Actor/Component 每帧被调用的函数 `Tick(float DeltaTime)`。`DeltaTime`
是距上一帧的秒数,用它做帧率无关的运动(`Location += Speed * DeltaTime`)。

Tick 默认对很多类是开启的,但**每帧执行的东西多了就是性能杀手**。

# 怎么优化 Tick

- 不需要每帧跑的逻辑就**关掉 Tick**:`PrimaryActorTick.bCanEverTick = false`。
- 用**定时器** `FTimerManager::SetTimer` 代替 Tick 做周期性逻辑(如每 0.5 秒)。
- 用**事件驱动**(委托/回调)代替轮询(在 Tick 里反复检查条件)。
- 降低 Tick 频率:`PrimaryActorTick.TickInterval = 0.2f`。
- 远处或不可见的 Actor 可禁用 Tick。

经验法则:先问"这真的需要每帧做吗?"——大多数逻辑可以事件驱动或定时器化。

# 帧率无关 (DeltaTime) 为什么重要

如果直接 `Location += Speed`,高帧率机器上物体会跑得更快,不同设备表现不一致。
乘上 `DeltaTime` 后,无论 30fps 还是 144fps,每秒移动距离相同。所有基于时间的
运动、插值、计时都应使用 DeltaTime。
