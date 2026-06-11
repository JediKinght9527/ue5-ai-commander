# Component 是什么

Component 是挂在 Actor 上、提供具体能力的可复用部件,基类 `UActorComponent`。
Actor 通过**组合**多个 Component 获得功能,而不是靠庞大的继承树。这是 UE 的
"组合优于继承"设计。

常见类型:
- `UStaticMeshComponent`:渲染静态网格。
- `USkeletalMeshComponent`:骨骼网格 + 动画。
- `UCameraComponent`:相机视角。
- `UCharacterMovementComponent`:角色移动逻辑。
- 自定义 `UActorComponent`:把可复用逻辑(如生命值系统、拾取系统)封装成组件,
  挂到任意 Actor 上复用。

# SceneComponent 和 ActorComponent 的区别

- `UActorComponent`:最基础的组件,**没有变换(没有位置)**。适合纯逻辑组件
  (如一个管理库存的组件)。
- `USceneComponent`:继承自 ActorComponent,**有 Transform(位置/旋转/缩放)**,
  能附加成父子层级。需要在世界里有空间位置的组件用它。
- `UPrimitiveComponent`:继承自 SceneComponent,**能渲染和参与碰撞**(网格、
  碰撞体都属于这类)。

# RootComponent 是什么

Actor 的 RootComponent 是它的根 SceneComponent,决定整个 Actor 的位置。
其它 SceneComponent 附加到它下面形成层级,移动根组件会带动所有子组件。
