# Actor 是什么

Actor 是 UE 里所有能放进关卡(Level)的对象的基类 `AActor`。任何能在世界里
拥有位置、被放置、被生成(spawn)或销毁(destroy)的东西都是 Actor:静态网格、
光源、相机、触发器、玩家角色都是 Actor 的子类。

Actor 本身不一定有位置组件,但通常带一个 RootComponent 决定它的变换(Transform)。
Actor 通过组合 Component 来获得能力——网格、碰撞、移动等都是组件挂在 Actor 上。
常用生命周期函数:`BeginPlay`(进入游戏时)、`Tick`(每帧)、`EndPlay`(结束时)。

# Pawn 是什么

Pawn 是 `APawn`,继承自 Actor,代表"可以被 Controller 控制(possess)"的 Actor。
玩家或 AI 通过 Controller 占有(possess)一个 Pawn 来操纵它。Pawn 是"能被驾驶
的载体"的抽象:可以是人形角色,也可以是一辆车、一架飞机,甚至一个漂浮的相机。

Pawn 提供了接收输入和被 AIController/PlayerController 控制的基础设施,但它本身
没有内置的行走移动逻辑。

# Actor 和 Pawn 的区别

核心区别:**所有 Pawn 都是 Actor,但不是所有 Actor 都是 Pawn**。

- Actor:能放进世界的任意对象,不一定能被控制。
- Pawn:Actor 的子类,额外具备"被 Controller 占有并接收输入"的能力。

什么时候用哪个:静态布景、道具、光源用 Actor;玩家或 AI 要操纵的实体用 Pawn
(或它的子类 Character)。

# Character 是什么

Character 是 `ACharacter`,继承自 Pawn,是专门为"人形、会走路的角色"准备的。
它自带:

- `CharacterMovementComponent`:处理走、跑、跳、游泳、下落、网络同步移动。
- `CapsuleComponent`:胶囊碰撞体,适合直立人形。
- `SkeletalMeshComponent`:骨骼网格,播放角色动画。

所以做"主角"时一般直接继承 Character,而不是从裸 Pawn 自己写移动。只有当你
的可控对象不是人形(如载具)时,才考虑直接用 Pawn。
