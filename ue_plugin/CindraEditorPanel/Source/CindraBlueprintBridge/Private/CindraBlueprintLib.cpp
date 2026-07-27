#include "CindraBlueprintLib.h"

#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraphSchema_K2.h"
#include "Engine/Blueprint.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Character.h"
#include "GameFramework/Pawn.h"
#include "K2Node_CallFunction.h"
#include "K2Node_Event.h"
#include "K2Node_ExecutionSequence.h"
#include "K2Node_IfThenElse.h"
#include "Kismet/KismetMathLibrary.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/CompilerResultsLog.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/PackageName.h"
#include "ScopedTransaction.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UObject/Package.h"

#define LOCTEXT_NAMESPACE "CindraBlueprintLib"

// ---------------------------------------------------------------------------
// JSON 帮助
// ---------------------------------------------------------------------------

static FString CndJson(const TSharedRef<FJsonObject>& Obj)
{
    FString Out;
    const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer =
        TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
    FJsonSerializer::Serialize(Obj, Writer);
    return Out;
}

FString UCindraBlueprintLib::Err(const FString& Message)
{
    TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetBoolField(TEXT("ok"), false);
    Obj->SetStringField(TEXT("error"), Message);
    return CndJson(Obj);
}

// ---------------------------------------------------------------------------
// 节点类型映射表: mock 模板名 -> K2 节点。与 blueprint_model._NODE_TEMPLATES
// 一一对应, 扩库必须两边同步。
// ---------------------------------------------------------------------------

struct FCndNodeSpec
{
    enum class EKind { Event, Branch, Sequence, CallFunction };
    EKind Kind = EKind::CallFunction;
    FName EventName;          // Event 节点: AActor 里的事件函数名
    UClass* FuncClass = nullptr;
    FName FuncName;           // CallFunction 节点: 目标函数
};

static bool CndNodeSpecFor(const FString& NodeType, FCndNodeSpec& Out)
{
    if (NodeType == TEXT("Event_BeginPlay"))
    {
        Out.Kind = FCndNodeSpec::EKind::Event;
        Out.EventName = FName(TEXT("ReceiveBeginPlay"));
        return true;
    }
    if (NodeType == TEXT("Event_Tick"))
    {
        Out.Kind = FCndNodeSpec::EKind::Event;
        Out.EventName = FName(TEXT("ReceiveTick"));
        return true;
    }
    if (NodeType == TEXT("Branch"))
    {
        Out.Kind = FCndNodeSpec::EKind::Branch;
        return true;
    }
    if (NodeType == TEXT("Sequence"))
    {
        Out.Kind = FCndNodeSpec::EKind::Sequence;
        return true;
    }
    if (NodeType == TEXT("PrintString"))
    {
        Out.Kind = FCndNodeSpec::EKind::CallFunction;
        Out.FuncClass = UKismetSystemLibrary::StaticClass();
        Out.FuncName = GET_FUNCTION_NAME_CHECKED(UKismetSystemLibrary, PrintString);
        return true;
    }
    if (NodeType == TEXT("Delay"))
    {
        Out.Kind = FCndNodeSpec::EKind::CallFunction;
        Out.FuncClass = UKismetSystemLibrary::StaticClass();
        Out.FuncName = GET_FUNCTION_NAME_CHECKED(UKismetSystemLibrary, Delay);
        return true;
    }
    if (NodeType == TEXT("Greater_FloatFloat"))
    {
        Out.Kind = FCndNodeSpec::EKind::CallFunction;
        Out.FuncClass = UKismetMathLibrary::StaticClass();
        Out.FuncName = FName(TEXT("Greater_DoubleDouble"));
        return true;
    }
    if (NodeType == TEXT("Add_FloatFloat"))
    {
        Out.Kind = FCndNodeSpec::EKind::CallFunction;
        Out.FuncClass = UKismetMathLibrary::StaticClass();
        Out.FuncName = FName(TEXT("Add_DoubleDouble"));
        return true;
    }
    return false;
}

// mock 引脚名 -> K2 真引脚名 (按节点类型翻译, 找不到映射就按原名找)
static FName CndRealPinName(const FString& NodeType, const FString& MockPin)
{
    if (MockPin == TEXT("exec"))  return UEdGraphSchema_K2::PN_Execute;
    if (MockPin == TEXT("then"))  return UEdGraphSchema_K2::PN_Then;
    if (NodeType == TEXT("Branch"))
    {
        if (MockPin == TEXT("True"))  return UEdGraphSchema_K2::PN_Then;
        if (MockPin == TEXT("False")) return UEdGraphSchema_K2::PN_Else;
    }
    if (NodeType == TEXT("Sequence"))
    {
        if (MockPin == TEXT("Then0")) return FName(TEXT("then_0"));
        if (MockPin == TEXT("Then1")) return FName(TEXT("then_1"));
    }
    if (NodeType == TEXT("Delay") && MockPin == TEXT("Completed"))
    {
        return UEdGraphSchema_K2::PN_Then;
    }
    if (NodeType == TEXT("Event_Tick") && MockPin == TEXT("DeltaSeconds"))
    {
        return FName(TEXT("DeltaSeconds"));
    }
    return FName(*MockPin);
}

// ---------------------------------------------------------------------------
// 内部工具
// ---------------------------------------------------------------------------

UBlueprint* UCindraBlueprintLib::LoadBP(const FString& AssetPath, FString& OutError)
{
    UBlueprint* BP = LoadObject<UBlueprint>(nullptr, *AssetPath);
    if (!BP)
    {
        OutError = FString::Printf(TEXT("blueprint not found: %s"), *AssetPath);
    }
    return BP;
}

UEdGraph* UCindraBlueprintLib::EventGraph(UBlueprint* BP)
{
    return (BP && BP->UbergraphPages.Num() > 0) ? BP->UbergraphPages[0] : nullptr;
}

UEdGraphNode* UCindraBlueprintLib::FindByCindraId(UEdGraph* Graph, const FString& CindraId)
{
    if (!Graph)
    {
        return nullptr;
    }
    for (UEdGraphNode* Node : Graph->Nodes)
    {
        if (Node && Node->NodeComment == CindraId)
        {
            return Node;
        }
    }
    return nullptr;
}

UEdGraphPin* UCindraBlueprintLib::ResolvePin(UEdGraphNode* Node, const FString& NodeType,
                                             const FString& MockPin, bool bAsOutput)
{
    const FName Real = CndRealPinName(NodeType, MockPin);
    const EEdGraphPinDirection Dir = bAsOutput ? EGPD_Output : EGPD_Input;
    for (UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin && Pin->PinName == Real && Pin->Direction == Dir)
        {
            return Pin;
        }
    }
    // 方向不限再找一次 (agent 可能拿 output 名当 input 传, 让 schema 报错更准)
    for (UEdGraphPin* Pin : Node->Pins)
    {
        if (Pin && Pin->PinName == Real)
        {
            return Pin;
        }
    }
    return nullptr;
}

static FString CndNodeTypeOf(UEdGraphNode* Node)
{
    if (const UK2Node_Event* Ev = Cast<UK2Node_Event>(Node))
    {
        const FName Ref = Ev->EventReference.GetMemberName();
        if (Ref == FName(TEXT("ReceiveBeginPlay"))) return TEXT("Event_BeginPlay");
        if (Ref == FName(TEXT("ReceiveTick")))      return TEXT("Event_Tick");
        return FString::Printf(TEXT("Event_%s"), *Ref.ToString());
    }
    if (Cast<UK2Node_IfThenElse>(Node))       return TEXT("Branch");
    if (Cast<UK2Node_ExecutionSequence>(Node)) return TEXT("Sequence");
    if (const UK2Node_CallFunction* Call = Cast<UK2Node_CallFunction>(Node))
    {
        const FName Fn = Call->FunctionReference.GetMemberName();
        if (Fn == FName(TEXT("PrintString")))          return TEXT("PrintString");
        if (Fn == FName(TEXT("Delay")))                return TEXT("Delay");
        if (Fn == FName(TEXT("Greater_DoubleDouble"))) return TEXT("Greater_FloatFloat");
        if (Fn == FName(TEXT("Add_DoubleDouble")))     return TEXT("Add_FloatFloat");
        return Fn.ToString();
    }
    return Node ? Node->GetClass()->GetName() : TEXT("?");
}

// ---------------------------------------------------------------------------
// 公开 API
// ---------------------------------------------------------------------------

FString UCindraBlueprintLib::CndBpCreate(const FString& AssetPath, const FString& ParentClass)
{
    check(IsInGameThread());
    UClass* Parent = AActor::StaticClass();
    if (ParentClass == TEXT("Pawn"))      Parent = APawn::StaticClass();
    if (ParentClass == TEXT("Character")) Parent = ACharacter::StaticClass();

    if (LoadObject<UBlueprint>(nullptr, *AssetPath))
    {
        return Err(FString::Printf(TEXT("blueprint exists: %s"), *AssetPath));
    }
    const FString PackagePath = FPackageName::ObjectPathToPackageName(AssetPath);
    const FString AssetName = FPackageName::GetShortName(PackagePath);
    UPackage* Package = CreatePackage(*PackagePath);
    if (!Package)
    {
        return Err(TEXT("CreatePackage failed"));
    }

    const FScopedTransaction Tx(LOCTEXT("CndBpCreate", "Cindra Create Blueprint"));
    UBlueprint* BP = FKismetEditorUtilities::CreateBlueprint(
        Parent, Package, FName(*AssetName), BPTYPE_Normal,
        UBlueprint::StaticClass(), UBlueprintGeneratedClass::StaticClass());
    if (!BP)
    {
        return Err(TEXT("CreateBlueprint failed"));
    }
    FBlueprintEditorUtils::MarkBlueprintAsModified(BP);

    TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetBoolField(TEXT("ok"), true);
    Obj->SetStringField(TEXT("action"), TEXT("create"));
    Obj->SetStringField(TEXT("path"), AssetPath);
    Obj->SetStringField(TEXT("parent"), Parent->GetName());
    return CndJson(Obj);
}

FString UCindraBlueprintLib::CndBpOpen(const FString& AssetPath)
{
    FString Error;
    UBlueprint* BP = LoadBP(AssetPath, Error);
    if (!BP)
    {
        return Err(Error);
    }
    TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetBoolField(TEXT("ok"), true);
    Obj->SetStringField(TEXT("action"), TEXT("open"));
    Obj->SetStringField(TEXT("path"), AssetPath);
    Obj->SetNumberField(TEXT("nodes"),
                        EventGraph(BP) ? EventGraph(BP)->Nodes.Num() : 0);
    return CndJson(Obj);
}

FString UCindraBlueprintLib::CndBpAddNode(const FString& AssetPath, const FString& NodeType,
                                          const FString& CindraId)
{
    check(IsInGameThread());
    FString Error;
    UBlueprint* BP = LoadBP(AssetPath, Error);
    if (!BP)
    {
        return Err(Error);
    }
    UEdGraph* Graph = EventGraph(BP);
    if (!Graph)
    {
        return Err(TEXT("no event graph"));
    }
    FCndNodeSpec Spec;
    if (!CndNodeSpecFor(NodeType, Spec))
    {
        return Err(FString::Printf(TEXT("unknown node type: %s"), *NodeType));
    }
    if (FindByCindraId(Graph, CindraId))
    {
        return Err(FString::Printf(TEXT("node id exists: %s"), *CindraId));
    }

    const FScopedTransaction Tx(LOCTEXT("CndBpAddNode", "Cindra Add Node"));
    Graph->Modify();

    // 网格摆位: 按现有节点数排, 避免全叠在原点
    const int32 N = Graph->Nodes.Num();
    const int32 PosX = 200 + (N % 5) * 350;
    const int32 PosY = 100 + (N / 5) * 250;

    UEdGraphNode* NewNode = nullptr;
    switch (Spec.Kind)
    {
    case FCndNodeSpec::EKind::Event:
    {
        // 同名事件已存在则复用 (BeginPlay 只能有一个)
        for (UEdGraphNode* Node : Graph->Nodes)
        {
            UK2Node_Event* Ev = Cast<UK2Node_Event>(Node);
            if (Ev && Ev->EventReference.GetMemberName() == Spec.EventName)
            {
                Ev->NodeComment = CindraId;
                Ev->bCommentBubbleVisible = false;
                NewNode = Ev;
                break;
            }
        }
        if (!NewNode)
        {
            FGraphNodeCreator<UK2Node_Event> Creator(*Graph);
            UK2Node_Event* Ev = Creator.CreateNode();
            Ev->EventReference.SetExternalMember(Spec.EventName, AActor::StaticClass());
            Ev->bOverrideFunction = true;
            Ev->NodePosX = PosX;
            Ev->NodePosY = PosY;
            Creator.Finalize();
            NewNode = Ev;
        }
        break;
    }
    case FCndNodeSpec::EKind::Branch:
    {
        FGraphNodeCreator<UK2Node_IfThenElse> Creator(*Graph);
        UK2Node_IfThenElse* Node = Creator.CreateNode();
        Node->NodePosX = PosX;
        Node->NodePosY = PosY;
        Creator.Finalize();
        NewNode = Node;
        break;
    }
    case FCndNodeSpec::EKind::Sequence:
    {
        FGraphNodeCreator<UK2Node_ExecutionSequence> Creator(*Graph);
        UK2Node_ExecutionSequence* Node = Creator.CreateNode();
        Node->NodePosX = PosX;
        Node->NodePosY = PosY;
        Creator.Finalize();
        NewNode = Node;
        break;
    }
    case FCndNodeSpec::EKind::CallFunction:
    {
        FGraphNodeCreator<UK2Node_CallFunction> Creator(*Graph);
        UK2Node_CallFunction* Node = Creator.CreateNode();
        Node->FunctionReference.SetExternalMember(Spec.FuncName, Spec.FuncClass);
        Node->NodePosX = PosX;
        Node->NodePosY = PosY;
        Creator.Finalize();
        NewNode = Node;
        break;
    }
    }

    if (!NewNode)
    {
        return Err(TEXT("node creation failed"));
    }
    NewNode->NodeComment = CindraId;
    NewNode->bCommentBubbleVisible = false;
    FBlueprintEditorUtils::MarkBlueprintAsModified(BP);

    TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetBoolField(TEXT("ok"), true);
    Obj->SetStringField(TEXT("action"), TEXT("add_node"));
    Obj->SetStringField(TEXT("id"), CindraId);
    Obj->SetStringField(TEXT("type"), NodeType);
    TArray<TSharedPtr<FJsonValue>> Pins;
    for (const UEdGraphPin* Pin : NewNode->Pins)
    {
        if (Pin && !Pin->bHidden)
        {
            Pins.Add(MakeShared<FJsonValueString>(Pin->PinName.ToString()));
        }
    }
    Obj->SetArrayField(TEXT("pins"), Pins);
    return CndJson(Obj);
}

FString UCindraBlueprintLib::CndBpAddVariable(const FString& AssetPath, const FString& VarName,
                                              const FString& VarType, const FString& DefaultValue)
{
    check(IsInGameThread());
    FString Error;
    UBlueprint* BP = LoadBP(AssetPath, Error);
    if (!BP)
    {
        return Err(Error);
    }
    FEdGraphPinType PinType;
    PinType.PinCategory = UEdGraphSchema_K2::PC_Double;
    if (VarType == TEXT("bool"))   PinType.PinCategory = UEdGraphSchema_K2::PC_Boolean;
    if (VarType == TEXT("int"))    PinType.PinCategory = UEdGraphSchema_K2::PC_Int;
    if (VarType == TEXT("string")) PinType.PinCategory = UEdGraphSchema_K2::PC_String;
    if (VarType == TEXT("object"))
    {
        PinType.PinCategory = UEdGraphSchema_K2::PC_Object;
        PinType.PinSubCategoryObject = UObject::StaticClass();
    }

    const FScopedTransaction Tx(LOCTEXT("CndBpAddVar", "Cindra Add Variable"));
    if (!FBlueprintEditorUtils::AddMemberVariable(BP, FName(*VarName), PinType, DefaultValue))
    {
        return Err(FString::Printf(TEXT("variable exists or invalid: %s"), *VarName));
    }
    TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetBoolField(TEXT("ok"), true);
    Obj->SetStringField(TEXT("action"), TEXT("add_variable"));
    Obj->SetStringField(TEXT("name"), VarName);
    Obj->SetStringField(TEXT("type"), VarType);
    return CndJson(Obj);
}

FString UCindraBlueprintLib::CndBpConnect(const FString& AssetPath,
                                          const FString& FromNode, const FString& FromPin,
                                          const FString& ToNode, const FString& ToPin)
{
    check(IsInGameThread());
    FString Error;
    UBlueprint* BP = LoadBP(AssetPath, Error);
    if (!BP)
    {
        return Err(Error);
    }
    UEdGraph* Graph = EventGraph(BP);
    UEdGraphNode* Src = FindByCindraId(Graph, FromNode);
    if (!Src)
    {
        return Err(FString::Printf(TEXT("node not found: %s"), *FromNode));
    }
    UEdGraphNode* Dst = FindByCindraId(Graph, ToNode);
    if (!Dst)
    {
        return Err(FString::Printf(TEXT("node not found: %s"), *ToNode));
    }
    UEdGraphPin* SrcPin = ResolvePin(Src, CndNodeTypeOf(Src), FromPin, /*bAsOutput=*/true);
    if (!SrcPin)
    {
        return Err(FString::Printf(TEXT("pin not found: %s.%s"), *FromNode, *FromPin));
    }
    UEdGraphPin* DstPin = ResolvePin(Dst, CndNodeTypeOf(Dst), ToPin, /*bAsOutput=*/false);
    if (!DstPin)
    {
        return Err(FString::Printf(TEXT("pin not found: %s.%s"), *ToNode, *ToPin));
    }

    const UEdGraphSchema* Schema = Graph->GetSchema();
    const FPinConnectionResponse Response = Schema->CanCreateConnection(SrcPin, DstPin);
    if (Response.Response == CONNECT_RESPONSE_DISALLOW)
    {
        return Err(Response.Message.ToString());
    }

    const FScopedTransaction Tx(LOCTEXT("CndBpConnect", "Cindra Connect Pins"));
    Graph->Modify();
    if (!Schema->TryCreateConnection(SrcPin, DstPin))
    {
        return Err(FString::Printf(TEXT("TryCreateConnection failed: %s"),
                                   *Response.Message.ToString()));
    }
    FBlueprintEditorUtils::MarkBlueprintAsModified(BP);

    TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetBoolField(TEXT("ok"), true);
    Obj->SetStringField(TEXT("action"), TEXT("connect"));
    Obj->SetStringField(TEXT("link"), FString::Printf(TEXT("%s.%s -> %s.%s"),
                        *FromNode, *FromPin, *ToNode, *ToPin));
    return CndJson(Obj);
}

FString UCindraBlueprintLib::CndBpDeleteNode(const FString& AssetPath, const FString& CindraId)
{
    check(IsInGameThread());
    FString Error;
    UBlueprint* BP = LoadBP(AssetPath, Error);
    if (!BP)
    {
        return Err(Error);
    }
    UEdGraph* Graph = EventGraph(BP);
    UEdGraphNode* Node = FindByCindraId(Graph, CindraId);
    if (!Node)
    {
        return Err(FString::Printf(TEXT("node not found: %s"), *CindraId));
    }
    int32 Removed = 0;
    for (const UEdGraphPin* Pin : Node->Pins)
    {
        Removed += Pin ? Pin->LinkedTo.Num() : 0;
    }
    const FScopedTransaction Tx(LOCTEXT("CndBpDelete", "Cindra Delete Node"));
    FBlueprintEditorUtils::RemoveNode(BP, Node, /*bDontRecompile=*/true);

    TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetBoolField(TEXT("ok"), true);
    Obj->SetStringField(TEXT("action"), TEXT("delete_node"));
    Obj->SetStringField(TEXT("id"), CindraId);
    Obj->SetNumberField(TEXT("removed_links"), Removed);
    return CndJson(Obj);
}

FString UCindraBlueprintLib::CndBpList(const FString& AssetPath)
{
    FString Error;
    UBlueprint* BP = LoadBP(AssetPath, Error);
    if (!BP)
    {
        return Err(Error);
    }
    UEdGraph* Graph = EventGraph(BP);
    TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetBoolField(TEXT("ok"), true);
    Obj->SetStringField(TEXT("action"), TEXT("list"));

    TArray<TSharedPtr<FJsonValue>> Nodes;
    TArray<TSharedPtr<FJsonValue>> Links;
    if (Graph)
    {
        for (UEdGraphNode* Node : Graph->Nodes)
        {
            if (!Node || Node->NodeComment.IsEmpty())
            {
                continue;  // 只回报 Cindra 建的节点 (有 id 的)
            }
            TSharedRef<FJsonObject> N = MakeShared<FJsonObject>();
            N->SetStringField(TEXT("id"), Node->NodeComment);
            N->SetStringField(TEXT("type"), CndNodeTypeOf(Node));
            Nodes.Add(MakeShared<FJsonValueObject>(N));

            for (const UEdGraphPin* Pin : Node->Pins)
            {
                if (!Pin || Pin->Direction != EGPD_Output)
                {
                    continue;
                }
                for (const UEdGraphPin* Linked : Pin->LinkedTo)
                {
                    if (!Linked || !Linked->GetOwningNode() ||
                        Linked->GetOwningNode()->NodeComment.IsEmpty())
                    {
                        continue;
                    }
                    TSharedRef<FJsonObject> L = MakeShared<FJsonObject>();
                    L->SetStringField(TEXT("from_node"), Node->NodeComment);
                    L->SetStringField(TEXT("from_pin"), Pin->PinName.ToString());
                    L->SetStringField(TEXT("to_node"),
                                      Linked->GetOwningNode()->NodeComment);
                    L->SetStringField(TEXT("to_pin"), Linked->PinName.ToString());
                    Links.Add(MakeShared<FJsonValueObject>(L));
                }
            }
        }
    }
    Obj->SetArrayField(TEXT("nodes"), Nodes);
    Obj->SetArrayField(TEXT("links"), Links);

    TArray<TSharedPtr<FJsonValue>> Vars;
    for (const FBPVariableDescription& Var : BP->NewVariables)
    {
        TSharedRef<FJsonObject> V = MakeShared<FJsonObject>();
        V->SetStringField(TEXT("name"), Var.VarName.ToString());
        V->SetStringField(TEXT("type"), Var.VarType.PinCategory.ToString());
        Vars.Add(MakeShared<FJsonValueObject>(V));
    }
    Obj->SetArrayField(TEXT("variables"), Vars);
    return CndJson(Obj);
}

FString UCindraBlueprintLib::CndBpClear(const FString& AssetPath)
{
    check(IsInGameThread());
    FString Error;
    UBlueprint* BP = LoadBP(AssetPath, Error);
    if (!BP)
    {
        return Err(Error);
    }
    UEdGraph* Graph = EventGraph(BP);
    if (!Graph)
    {
        return Err(TEXT("no event graph"));
    }
    TArray<UEdGraphNode*> ToRemove;
    for (UEdGraphNode* Node : Graph->Nodes)
    {
        if (Node && !Node->NodeComment.IsEmpty())
        {
            ToRemove.Add(Node);
        }
    }
    const FScopedTransaction Tx(LOCTEXT("CndBpClear", "Cindra Clear Graph"));
    for (UEdGraphNode* Node : ToRemove)
    {
        FBlueprintEditorUtils::RemoveNode(BP, Node, /*bDontRecompile=*/true);
    }
    TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetBoolField(TEXT("ok"), true);
    Obj->SetStringField(TEXT("action"), TEXT("clear"));
    Obj->SetNumberField(TEXT("deleted"), ToRemove.Num());
    return CndJson(Obj);
}

FString UCindraBlueprintLib::CndBpCompile(const FString& AssetPath)
{
    check(IsInGameThread());
    FString Error;
    UBlueprint* BP = LoadBP(AssetPath, Error);
    if (!BP)
    {
        return Err(Error);
    }
    FCompilerResultsLog Results;
    FKismetEditorUtilities::CompileBlueprint(
        BP, EBlueprintCompileOptions::None, &Results);

    TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
    Obj->SetBoolField(TEXT("ok"), Results.NumErrors == 0);
    Obj->SetStringField(TEXT("action"), TEXT("compile"));
    Obj->SetNumberField(TEXT("errors"), Results.NumErrors);
    Obj->SetNumberField(TEXT("warnings"), Results.NumWarnings);
    TArray<TSharedPtr<FJsonValue>> Messages;
    for (const TSharedRef<FTokenizedMessage>& Msg : Results.Messages)
    {
        Messages.Add(MakeShared<FJsonValueString>(Msg->ToText().ToString()));
    }
    Obj->SetArrayField(TEXT("messages"), Messages);
    if (Results.NumErrors > 0)
    {
        Obj->SetStringField(TEXT("error"),
                            FString::Printf(TEXT("compile failed: %d errors"),
                                            Results.NumErrors));
    }
    return CndJson(Obj);
}

#undef LOCTEXT_NAMESPACE
