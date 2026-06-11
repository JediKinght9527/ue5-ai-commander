// SampleCharacter.h —— 玩家角色。示例工程的命名约定:
// C++ 类前缀 A/U/F, 项目类再加 "Cindra" 业务前缀; 组件成员用 *Component 结尾;
// 可调数值用 UPROPERTY(EditAnywhere) 暴露给设计师。
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "SampleCharacter.generated.h"

class UCindraHealthComponent;
class UCameraComponent;
class USpringArmComponent;
class UInputAction;
class UInputMappingContext;
struct FInputActionValue;

UCLASS()
class SAMPLEGAME_API ACindraCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	ACindraCharacter();

protected:
	virtual void BeginPlay() override;
	virtual void SetupPlayerInputComponent(class UInputComponent* PlayerInputComponent) override;

	// ---- 组件 (组合优于继承) ----
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Components")
	UCindraHealthComponent* HealthComponent;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Camera")
	USpringArmComponent* SpringArmComponent;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Camera")
	UCameraComponent* CameraComponent;

	// ---- Enhanced Input ----
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Input")
	UInputMappingContext* DefaultMappingContext;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Input")
	UInputAction* MoveAction;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Input")
	UInputAction* JumpAction;

	void Move(const FInputActionValue& Value);

	// ---- 可调数值 ----
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Movement")
	float WalkSpeed = 600.f;

private:
	UFUNCTION()
	void HandleDeath();
};
