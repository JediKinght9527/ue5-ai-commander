// ItemTypes.h —— 纯数据定义。约定: 值类型用 USTRUCT(BlueprintType),
// 枚举用 UENUM(BlueprintType) 并加 uint8 底层类型。
#pragma once

#include "CoreMinimal.h"
#include "ItemTypes.generated.h"

UENUM(BlueprintType)
enum class ECindraItemRarity : uint8
{
	Common     UMETA(DisplayName="普通"),
	Rare       UMETA(DisplayName="稀有"),
	Legendary  UMETA(DisplayName="传说"),
};

USTRUCT(BlueprintType)
struct SAMPLEGAME_API FCindraItemData
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Item")
	FName ItemId;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Item")
	FText DisplayName;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Item")
	ECindraItemRarity Rarity = ECindraItemRarity::Common;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Item", meta=(ClampMin="0"))
	int32 Value = 0;
};
