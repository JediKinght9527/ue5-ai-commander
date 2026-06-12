#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleManager.h"

class FCindraEditorPanelModule final : public IModuleInterface
{
public:
    virtual void StartupModule() override;
    virtual void ShutdownModule() override;

private:
    void RegisterMenus();
    bool OpenCindraTabDeferred(float DeltaTime);
    void OpenCindraTab();
    TSharedRef<class SDockTab> SpawnCindraTab(const class FSpawnTabArgs& Args);
    void RunPrompt(const FString& Prompt);
    FString PreparePythonArgs(const FString& Prompt);
    bool PollRunProcess(float DeltaTime);
    void AppendLog(const FString& Line);

    mutable FString LastLogPath;
    mutable FString LastPromptPath;
    struct FProcHandle ActiveProcessHandle;
    bool bRunInProgress = false;
    int32 OpenAttempts = 0;
    TSharedPtr<class SMultiLineEditableTextBox> PromptBox;
    TSharedPtr<class SMultiLineEditableTextBox> LogBox;
    TSharedPtr<class SEditableTextBox> ModeBox;
    TSharedPtr<class SEditableTextBox> BackendBox;
    TSharedPtr<class SEditableTextBox> ProviderBox;
    TSharedPtr<class SEditableTextBox> ModelBox;
    TSharedPtr<class SEditableTextBox> KeyEnvBox;
    TSharedPtr<class SEditableTextBox> RunnerBox;
    TSharedPtr<class SEditableTextBox> ApiKeyBox;
};
