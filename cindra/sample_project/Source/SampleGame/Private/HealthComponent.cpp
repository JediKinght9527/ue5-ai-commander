// HealthComponent.cpp
#include "HealthComponent.h"

UCindraHealthComponent::UCindraHealthComponent()
{
	PrimaryComponentTick.bCanEverTick = false; // 事件驱动, 无需 Tick
}

void UCindraHealthComponent::BeginPlay()
{
	Super::BeginPlay();
	CurrentHealth = MaxHealth;
}

bool UCindraHealthComponent::ApplyDamage(float Amount)
{
	if (Amount <= 0.f || IsDead())
	{
		return false;
	}
	const float Old = CurrentHealth;
	CurrentHealth = FMath::Clamp(CurrentHealth - Amount, 0.f, MaxHealth);
	OnHealthChanged.Broadcast(CurrentHealth, MaxHealth, CurrentHealth - Old);
	if (IsDead())
	{
		OnDeath.Broadcast();
		return true;
	}
	return false;
}

void UCindraHealthComponent::Heal(float Amount)
{
	if (Amount <= 0.f || IsDead())
	{
		return;
	}
	const float Old = CurrentHealth;
	CurrentHealth = FMath::Clamp(CurrentHealth + Amount, 0.f, MaxHealth);
	OnHealthChanged.Broadcast(CurrentHealth, MaxHealth, CurrentHealth - Old);
}

float UCindraHealthComponent::GetHealthPercent() const
{
	return MaxHealth > 0.f ? CurrentHealth / MaxHealth : 0.f;
}
