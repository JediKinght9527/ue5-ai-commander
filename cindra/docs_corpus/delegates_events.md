# Delegate 是什么

Delegate(委托)是 UE 的类型安全函数指针/回调机制,用来实现事件驱动:
"当某事发生时,通知所有关心它的人",而不用被通知方每帧去轮询。这是替代 Tick
里反复检查条件的关键工具。

# Delegate 的几种类型

- **Single-cast** `DECLARE_DELEGATE`:只绑定一个回调。
- **Multicast** `DECLARE_MULTICAST_DELEGATE`:可绑定多个回调,广播时全部调用。
- **Dynamic Multicast** `DECLARE_DYNAMIC_MULTICAST_DELEGATE`:可序列化、可在
  Blueprint 里绑定的多播委托。**Blueprint 里能看到/绑定的事件**(如
  `OnClicked`、`OnComponentBeginOverlap`)都是 Dynamic Multicast。

带参数的版本在宏名后加 `_OneParam` / `_TwoParams` 等。

# Event Dispatcher 是什么

Event Dispatcher 是 Blueprint 里对 Dynamic Multicast Delegate 的叫法。在
Blueprint 中你创建一个 Event Dispatcher,在某处 Call 它(广播),其它 Blueprint
Bind 到它来响应。这就是 Blueprint 做"解耦事件通信"的标准方式。

# 什么时候用 Delegate 而不是直接调用

当"发出事件的一方"不应该知道"谁在监听"时,用 Delegate 解耦。例如:生命值
组件血量归零时广播 `OnDeath`,UI、音效、计分系统各自绑定响应,血量组件无需
认识它们。比硬编码互相调用更可维护。
