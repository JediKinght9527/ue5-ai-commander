# 垃圾回收 (GC) 在 UE 里怎么工作

UE 对继承自 `UObject` 的对象有自己的垃圾回收系统,**不是** C++ 的手动
`new`/`delete`,也不是智能指针引用计数。GC 会定期从"根集合(root set)"出发
做可达性分析:凡是被 `UPROPERTY` 指针链能追踪到的 UObject 就保留,追踪不到的
就被回收。

关键规则:**指向 UObject 的成员指针必须用 `UPROPERTY()` 标记**,GC 才知道它
还被引用。忘了标记,对象会在下次 GC 时被回收,你手里的裸指针变成悬空指针,
随后崩溃——这是新手最常见的 UE 崩溃原因。

# UObject 和普通 C++ 对象的区别

- `UObject` 子类(`UCLASS`):受反射、GC、序列化、Blueprint 管理。用
  `NewObject<>()` / `SpawnActor<>()` 创建,**不要手动 delete**,交给 GC。
- 普通 C++ 类 / 结构体:不在 GC 管理范围,按 C++ 规则管理生命周期
  (栈对象、智能指针等)。`USTRUCT` 是值类型,也不受 GC 单独管理。

# 怎么安全持有 UObject 引用

- 成员变量:用 `UPROPERTY()` 标记的裸指针(`UMyObj* Ptr`)。
- 不想阻止回收、只想"对象还在吗"弱引用:用 `TWeakObjectPtr`。
- 容器:`TArray<UMyObj*>` 配合 UPROPERTY 也会被 GC 追踪。

记住一句话:**让 GC 看见你的引用,或者用弱指针,别留裸指针赌它不被回收。**
