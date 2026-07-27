// CindraBlueprintBridge —— 蓝图真后端 C++ 桥模块。
// 把 UEdGraph/UK2Node 操作暴露成 Python 可调的 UFUNCTION (见 CindraBlueprintLib),
// cindra 的 UEBlueprintTransport 经 Remote Execution 调它们。

#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"

class FCindraBlueprintBridgeModule : public IModuleInterface
{
public:
    virtual void StartupModule() override;
    virtual void ShutdownModule() override;
};
