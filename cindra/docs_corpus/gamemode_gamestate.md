# GameMode 是什么

GameMode 是 `AGameModeBase`(或老的 `AGameMode`),定义一局游戏的**规则**:
用哪个默认 Pawn、用哪个 PlayerController、玩家怎么进场、胜负条件、重生逻辑。

关键:**GameMode 只存在于服务器**(server-only)。客户端没有 GameMode 实例。
所以任何"权威规则"判定都应放在 GameMode 里,客户端无法篡改。

常配置的属性:`DefaultPawnClass`、`PlayerControllerClass`、`GameStateClass`、
`HUDClass`。可在 Project Settings → Maps & Modes 设全局默认,也可每张关卡覆盖。

# GameState 是什么

GameState 是 `AGameStateBase`,保存"整局游戏对所有人可见的状态",并且会
**复制(replicate)到所有客户端**。比如:当前比分、剩余时间、已连接的玩家列表、
比赛阶段(准备中/进行中/结束)。

GameMode(只在服务器)做决策,GameState(同步到所有人)负责把结果广播出去。
想让客户端知道的全局信息放 GameState,不要放 GameMode。

# GameMode 和 GameState 的区别

- GameMode:规则与决策,**仅服务器**,客户端访问不到。
- GameState:全局共享状态,**复制到所有客户端**,大家都能读。

类比:GameMode 是裁判(只有一个,在服务器),GameState 是记分牌(所有人都看得见)。

# PlayerState 是什么

PlayerState 是 `APlayerState`,保存"单个玩家"的状态(分数、名字、队伍),
每个玩家一份,并复制给所有人。和 GameState 的区别:GameState 是整局共享的,
PlayerState 是每玩家一份的。
