# UPROPERTY 是什么

`UPROPERTY()` 是加在 C++ 成员变量上的宏,把这个变量注册进 UE 的反射系统。
不加它,引擎"看不见"这个变量。加了之后能获得:

- **垃圾回收**:指向 UObject 的指针被 UPROPERTY 标记后,GC 才会追踪它,
  防止对象被误回收或产生悬空指针。
- **编辑器暴露**:`EditAnywhere` / `VisibleAnywhere` 让变量出现在细节面板。
- **Blueprint 暴露**:`BlueprintReadWrite` / `BlueprintReadOnly`。
- **序列化**:存盘/读盘、关卡保存。
- **网络复制**:`Replicated` / `ReplicatedUsing`。

常用说明符:`EditAnywhere, BlueprintReadWrite, Category="Stats"`。

# UFUNCTION 是什么

`UFUNCTION()` 是加在 C++ 函数上的宏,把函数注册进反射系统。常见用途:

- `BlueprintCallable`:Blueprint 里能调用这个函数。
- `BlueprintPure`:无副作用的纯函数,Blueprint 里显示为无执行引脚的节点。
- `BlueprintImplementableEvent`:C++ 声明、Blueprint 实现。
- `BlueprintNativeEvent`:C++ 提供默认实现,Blueprint 可覆盖。
- `Server` / `Client` / `NetMulticast`:网络 RPC。
- `CallInEditor`:在细节面板生成一个可点的按钮。

# 反射系统为什么重要

UPROPERTY/UFUNCTION/UCLASS 这套宏是 UE "魔法"的根基:垃圾回收、序列化、
网络复制、Blueprint 互通、编辑器集成全都依赖反射。忘记给 UObject 指针加
UPROPERTY 是新手最常见的崩溃来源——对象被 GC 回收后指针悬空。
