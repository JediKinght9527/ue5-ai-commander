# Enhanced Input 是什么

Enhanced Input 是 UE5 推荐的输入系统,取代了老的 Project Settings 里的
Action/Axis Mappings。它更灵活:支持运行时重映射、修饰键、触发条件、上下文
切换。核心概念:

- **Input Action (IA)**:一个抽象动作,如"跳跃""移动""开火"。有值类型
  (bool / Axis1D / Axis2D / Axis3D)。
- **Input Mapping Context (IMC)**:把物理按键/摇杆绑定到 Input Action 的一张
  映射表。可以按情境切换(如步行时一套、开车时另一套),并有优先级。
- **Modifiers**:对输入值做变换(取反、死区、缩放、Swizzle 调整轴顺序)。
- **Triggers**:决定动作何时触发(按下、长按、双击、释放)。

# 怎么接收输入

在 Pawn/Character 的 `SetupPlayerInputComponent` 里,把
`UEnhancedInputComponent` 的 `BindAction` 绑到你的 Input Action 上,指定触发
事件类型(`ETriggerEvent::Triggered` / `Started` / `Completed`)和回调函数。
进游戏时,通过 `UEnhancedInputLocalPlayerSubsystem` 给玩家添加 Mapping Context。

# 老输入系统和新系统的区别

老系统(Input Mappings)简单但僵硬:绑定写死在项目设置里,难以运行时改键、
难以做情境切换。Enhanced Input 用资产(IA/IMC)管理,支持运行时增删上下文、
修饰键和触发器,是 UE5 新项目的默认推荐。
