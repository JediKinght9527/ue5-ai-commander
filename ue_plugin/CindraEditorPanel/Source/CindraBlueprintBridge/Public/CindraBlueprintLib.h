// CindraBlueprintLib —— Python 可调的蓝图图操作函数库。
//
// 设计约定 (与 cindra/blueprint_model.py 的 mock 一一对应):
// - 全部返回 JSON FString, 形状与 mock bp_*() 完全一致 —— agent/工具层双后端无感。
// - 节点 id (如 "PrintString_2") 由 cindra 侧生成, 存在 K2Node 的 NodeComment
//   里做 round-trip; bp_list 用它回报, agent 引用的 id 永远稳定。
// - 节点类型表固定为 mock 的 8 种模板 (Event_BeginPlay/Event_Tick/Branch/
//   Sequence/PrintString/Delay/Greater_FloatFloat/Add_FloatFloat)。扩库必须
//   mock 模板 + 这里的映射表同步改, 保持校验对称。
// - 引脚名对外用 mock 命名 (exec/then/True/False/...), 内部翻译成 K2 真名。
// - 所有改动包 FScopedTransaction; 连接用 Schema->TryCreateConnection,
//   失败回传 schema 原生错误文本。

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "CindraBlueprintLib.generated.h"

class UBlueprint;
class UEdGraph;
class UEdGraphNode;
class UEdGraphPin;

UCLASS()
class CINDRABLUEPRINTBRIDGE_API UCindraBlueprintLib : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    /** 新建 Blueprint 资产 (ParentClass: Actor/Pawn/Character)。 */
    UFUNCTION(BlueprintCallable, Category = "Cindra")
    static FString CndBpCreate(const FString& AssetPath, const FString& ParentClass);

    /** 打开已有 Blueprint 并设为当前操作目标。 */
    UFUNCTION(BlueprintCallable, Category = "Cindra")
    static FString CndBpOpen(const FString& AssetPath);

    /** 加节点。NodeType 为 mock 模板名; CindraId 为 cindra 侧生成的稳定 id。 */
    UFUNCTION(BlueprintCallable, Category = "Cindra")
    static FString CndBpAddNode(const FString& AssetPath, const FString& NodeType,
                                const FString& CindraId);

    /** 加成员变量。VarType: bool/int/float/string/object。 */
    UFUNCTION(BlueprintCallable, Category = "Cindra")
    static FString CndBpAddVariable(const FString& AssetPath, const FString& VarName,
                                    const FString& VarType, const FString& DefaultValue);

    /** 连线 (mock 引脚名)。失败返回 schema 原生错误。 */
    UFUNCTION(BlueprintCallable, Category = "Cindra")
    static FString CndBpConnect(const FString& AssetPath,
                                const FString& FromNode, const FString& FromPin,
                                const FString& ToNode, const FString& ToPin);

    /** 删节点 (按 CindraId)。 */
    UFUNCTION(BlueprintCallable, Category = "Cindra")
    static FString CndBpDeleteNode(const FString& AssetPath, const FString& CindraId);

    /** 读回图结构 (nodes/links/variables), 形状同 mock bp_list。 */
    UFUNCTION(BlueprintCallable, Category = "Cindra")
    static FString CndBpList(const FString& AssetPath);

    /** 清空事件图里 Cindra 建的节点。 */
    UFUNCTION(BlueprintCallable, Category = "Cindra")
    static FString CndBpClear(const FString& AssetPath);

    /** 编译并回报错误/警告。 */
    UFUNCTION(BlueprintCallable, Category = "Cindra")
    static FString CndBpCompile(const FString& AssetPath);

private:
    static UBlueprint* LoadBP(const FString& AssetPath, FString& OutError);
    static UEdGraph* EventGraph(UBlueprint* BP);
    static UEdGraphNode* FindByCindraId(UEdGraph* Graph, const FString& CindraId);
    static UEdGraphPin* ResolvePin(UEdGraphNode* Node, const FString& NodeType,
                                   const FString& MockPin, bool bAsOutput);
    static FString Err(const FString& Message);
};
