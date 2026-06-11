// HealthComponent.h —— 可复用的生命值组件 (示例工程的护城河式约定:
// 把"受伤/死亡"封装成组件, 用 Dynamic Multicast 委托对外广播, 供 UI/音效/计分解耦订阅)。
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "HealthComponent.generated.h"

// 血量变化时广播: 当前值, 最大值, 变化量 (负为受伤)。
DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FOnHealthChanged, float, NewHealth, float, MaxHealth, float, Delta);
// 死亡时广播。
DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnDeath);

UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class SAMPLEGAME_API UCindraHealthComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UCindraHealthComponent();

	// 施加伤害 (Amount 为正)。返回是否致死。仅服务器权威调用。
	UFUNCTION(BlueprintCallable, Category="Health")
	bool ApplyDamage(float Amount);

	// 治疗 (Amount 为正), 不超过最大值。
	UFUNCTION(BlueprintCallable, Category="Health")
	void Heal(float Amount);

	UFUNCTION(BlueprintPure, Category="Health")
	float GetHealthPercent() const;

	UFUNCTION(BlueprintPure, Category="Health")
	bool IsDead() const { return CurrentHealth <= 0.f; }

	UPROPERTY(BlueprintAssignable, Category="Health")
	FOnHealthChanged OnHealthChanged;

	UPROPERTY(BlueprintAssignable, Category="Health")
	FOnDeath OnDeath;

protected:
	virtual void BeginPlay() override;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Health")
	float MaxHealth = 100.f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Health")
	float CurrentHealth = 100.f;
};
