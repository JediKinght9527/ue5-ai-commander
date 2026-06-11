# Blueprint 是什么

Blueprint 是 UE 的可视化脚本系统:用连线的节点图代替写代码。它本质上是建立在
C++ 反射系统之上的一层——Blueprint 能调用任何标记了 `UFUNCTION(BlueprintCallable)`
的 C++ 函数,访问任何 `UPROPERTY(BlueprintReadWrite)` 的变量。

优点:迭代快、不用编译 C++、设计师友好、可视化数据流。
缺点:运行时比 C++ 慢(虚拟机解释执行)、大型逻辑图难维护、版本控制(diff/merge)
困难(二进制资产)。

# C++ 在 UE 里的角色

C++ 是 UE 的底层语言,提供最高性能和完整引擎访问。适合:性能敏感的核心系统、
复杂算法、需要单元测试的逻辑、需要良好版本控制的代码。

UE 的 C++ 不是裸 C++:有 `UCLASS`/`UPROPERTY`/`UFUNCTION` 宏接入反射系统、
垃圾回收、序列化和 Blueprint 暴露。

# Blueprint 和 C++ 怎么选 / 怎么配合

最佳实践是**混合**:用 C++ 写基类和核心系统(性能、可测试、护城河逻辑),
把需要让设计师调整的部分用 `UPROPERTY(EditAnywhere)` 和
`UFUNCTION(BlueprintCallable)` 暴露出去,再用 Blueprint 子类做快速迭代和组装。

经验法则:
- 算法、性能热点、网络权威逻辑 → C++。
- 关卡脚本、UI 交互、快速原型、设计师要反复调的数值 → Blueprint。
- 在 C++ 定义"能做什么",在 Blueprint 决定"具体怎么用"。
