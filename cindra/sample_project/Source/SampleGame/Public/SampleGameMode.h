// SampleGameMode.h —— 游戏规则 (server-only)。约定: GameMode 定规则,
// 不存共享状态; 默认 Pawn/Controller 通过构造函数指定。
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "SampleGameMode.generated.h"

UCLASS()
class SAMPLEGAME_API ACindraGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	ACindraGameMode();

	// 一名玩家死亡时由角色回调通知, GameMode 决定是否结束本局 (权威逻辑)。
	UFUNCTION(BlueprintCallable, Category="Rules")
	void NotifyPlayerDied(AController* DeadPlayer);

protected:
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category="Rules")
	int32 ScoreToWin = 10;
};
