#include "CindraEditorPanel.h"

#include "Framework/Docking/TabManager.h"
#include "Containers/Ticker.h"
#include "Interfaces/IPluginManager.h"
#include "LevelEditor.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/PlatformMisc.h"
#include "ToolMenus.h"
#include "Widgets/Docking/SDockTab.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Input/SMultiLineEditableTextBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SSeparator.h"
#include "Widgets/Text/STextBlock.h"

#define LOCTEXT_NAMESPACE "FCindraEditorPanelModule"

DEFINE_LOG_CATEGORY_STATIC(LogCindraEditorPanel, Log, All);

namespace
{
static const FName CindraTabName(TEXT("CindraEditorPanel"));

static FString ReadEnvironmentVar(const FString& Name)
{
    return FPlatformMisc::GetEnvironmentVariable(*Name);
}

static FString DefaultCindraRoot()
{
    return FPaths::ConvertRelativePathToFull(FPaths::ProjectDir() / TEXT("..") / TEXT("..") / TEXT("..") / TEXT("cindra"));
}

static FString CindraProjectRoot()
{
    const FString Env = ReadEnvironmentVar(TEXT("CINDRA_PROJECT_ROOT"));
    return Env.IsEmpty() ? DefaultCindraRoot() : Env;
}

static FString CindraPythonExe()
{
    const FString Env = ReadEnvironmentVar(TEXT("CINDRA_PYTHON_EXE"));
    return Env.IsEmpty() ? FPaths::Combine(CindraProjectRoot(), TEXT(".venv"), TEXT("Scripts"), TEXT("python.exe")) : Env;
}

static FString CindraUEPythonPath()
{
    const FString Env = ReadEnvironmentVar(TEXT("CINDRA_UE_PYTHONPATH"));
    if (!Env.IsEmpty())
    {
        return Env;
    }
    const FString EngineDir = FPaths::ConvertRelativePathToFull(FPaths::EngineDir());
    return FPaths::Combine(EngineDir, TEXT("Plugins"), TEXT("Experimental"), TEXT("PythonScriptPlugin"), TEXT("Content"), TEXT("Python"));
}

static FString MaskKey(const FString& Key)
{
    if (Key.IsEmpty())
    {
        return TEXT("missing");
    }
    return FString::Printf(TEXT("present (%d chars)"), Key.Len());
}

static FString ReadUserEnvironmentVar(const FString& Name)
{
    FString Value = FPlatformMisc::GetEnvironmentVariable(*Name);
    if (!Value.IsEmpty())
    {
        return Value;
    }

    FString StdOut;
    FString StdErr;
    int32 ReturnCode = -1;
    const FString Args = FString::Printf(
        TEXT("-NoProfile -Command \"[Environment]::GetEnvironmentVariable('%s','User')\""),
        *Name);
    FPlatformProcess::ExecProcess(TEXT("powershell.exe"), *Args, &ReturnCode, &StdOut, &StdErr);
    return StdOut.TrimStartAndEnd();
}
}

void FCindraEditorPanelModule::StartupModule()
{
    UE_LOG(LogCindraEditorPanel, Display, TEXT("CindraEditorPanel startup."));

    FGlobalTabmanager::Get()->RegisterNomadTabSpawner(
        CindraTabName,
        FOnSpawnTab::CreateRaw(this, &FCindraEditorPanelModule::SpawnCindraTab))
        .SetDisplayName(LOCTEXT("CindraTabTitle", "Cindra"))
        .SetTooltipText(LOCTEXT("CindraTabTooltip", "AI scene, docs, code, and blueprint assistant."))
        .SetMenuType(ETabSpawnerMenuType::Enabled);

    UToolMenus::RegisterStartupCallback(
        FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FCindraEditorPanelModule::RegisterMenus));

    FTSTicker::GetCoreTicker().AddTicker(
        FTickerDelegate::CreateRaw(this, &FCindraEditorPanelModule::OpenCindraTabDeferred),
        5.0f);
}

void FCindraEditorPanelModule::ShutdownModule()
{
    UToolMenus::UnRegisterStartupCallback(this);
    UToolMenus::UnregisterOwner(this);
    FGlobalTabmanager::Get()->UnregisterNomadTabSpawner(CindraTabName);
}

void FCindraEditorPanelModule::RegisterMenus()
{
    FToolMenuOwnerScoped OwnerScoped(this);
    const FToolMenuEntry Entry = FToolMenuEntry::InitMenuEntry(
        "OpenCindraPanel",
        LOCTEXT("OpenCindraPanel", "Cindra"),
        LOCTEXT("OpenCindraPanelTooltip", "Open the Cindra AI editor panel."),
        FSlateIcon(),
        FUIAction(FExecuteAction::CreateRaw(this, &FCindraEditorPanelModule::OpenCindraTab)));

    const FToolMenuEntry ToolbarEntry = FToolMenuEntry::InitToolBarButton(
        "OpenCindraPanelToolbar",
        FUIAction(FExecuteAction::CreateRaw(this, &FCindraEditorPanelModule::OpenCindraTab)),
        LOCTEXT("OpenCindraPanelToolbar", "Cindra"),
        LOCTEXT("OpenCindraPanelToolbarTooltip", "Open the Cindra AI editor panel."),
        FSlateIcon());

    if (UToolMenu* Toolbar = UToolMenus::Get()->ExtendMenu("LevelEditor.LevelEditorToolBar.User"))
    {
        FToolMenuSection& Section = Toolbar->FindOrAddSection("Cindra");
        Section.AddEntry(ToolbarEntry);
    }

    if (UToolMenu* Toolbar = UToolMenus::Get()->ExtendMenu("LevelEditor.LevelEditorToolBar.PlayToolBar"))
    {
        FToolMenuSection& Section = Toolbar->FindOrAddSection("Cindra");
        Section.AddEntry(ToolbarEntry);
    }

    if (UToolMenu* MainToolbar = UToolMenus::Get()->ExtendMenu("LevelEditor.LevelEditorToolBar"))
    {
        FToolMenuSection& Section = MainToolbar->FindOrAddSection("Cindra");
        Section.AddEntry(ToolbarEntry);
    }

    if (UToolMenu* WindowMenu = UToolMenus::Get()->ExtendMenu("LevelEditor.MainMenu.Window"))
    {
        FToolMenuSection& Section = WindowMenu->FindOrAddSection("WindowLayout");
        Section.AddEntry(Entry);
    }
    if (UToolMenu* ToolsMenu = UToolMenus::Get()->ExtendMenu("LevelEditor.MainMenu.Tools"))
    {
        FToolMenuSection& Section = ToolsMenu->FindOrAddSection("Cindra");
        Section.AddEntry(Entry);
    }
}

void FCindraEditorPanelModule::OpenCindraTab()
{
    UE_LOG(LogCindraEditorPanel, Display, TEXT("Opening Cindra tab."));
    FGlobalTabmanager::Get()->TryInvokeTab(CindraTabName);
}

bool FCindraEditorPanelModule::OpenCindraTabDeferred(float DeltaTime)
{
    ++OpenAttempts;
    OpenCindraTab();
    return OpenAttempts < 6;
}

TSharedRef<SDockTab> FCindraEditorPanelModule::SpawnCindraTab(const FSpawnTabArgs& Args)
{
    UE_LOG(LogCindraEditorPanel, Display, TEXT("Spawning Cindra tab."));
    return SNew(SDockTab)
        .TabRole(ETabRole::NomadTab)
        [
            SNew(SBorder)
            .Padding(10)
            [
                SNew(SVerticalBox)
                + SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 4)
                [
                    SNew(STextBlock)
                    .Text(LOCTEXT("CindraTitle", "Cindra UE Assistant"))
                    .Font(FCoreStyle::GetDefaultFontStyle("Bold", 20))
                ]
                + SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 10)
                [
                    SNew(STextBlock)
                    .AutoWrapText(true)
                    .Text(LOCTEXT("CindraSubtitle", "在编辑器里直接改当前关卡。Chat UE 会调用真 UE；Docs / Code / Blueprint 走离线助手。"))
                ]
                + SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 8)
                [
                    SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 6, 0)
                    [ SNew(SButton).Text(LOCTEXT("ModeChat", "Chat UE")).OnClicked_Lambda([this]() { ModeBox->SetText(FText::FromString(TEXT("chat"))); BackendBox->SetText(FText::FromString(TEXT("ue"))); return FReply::Handled(); }) ]
                    + SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 6, 0)
                    [ SNew(SButton).Text(LOCTEXT("ModeDocs", "Docs")).OnClicked_Lambda([this]() { ModeBox->SetText(FText::FromString(TEXT("docs"))); BackendBox->SetText(FText::FromString(TEXT("mock"))); return FReply::Handled(); }) ]
                    + SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 6, 0)
                    [ SNew(SButton).Text(LOCTEXT("ModeCode", "Code")).OnClicked_Lambda([this]() { ModeBox->SetText(FText::FromString(TEXT("code"))); BackendBox->SetText(FText::FromString(TEXT("mock"))); return FReply::Handled(); }) ]
                    + SHorizontalBox::Slot().AutoWidth()
                    [ SNew(SButton).Text(LOCTEXT("ModeBlueprint", "Blueprint")).OnClicked_Lambda([this]() { ModeBox->SetText(FText::FromString(TEXT("blueprint"))); BackendBox->SetText(FText::FromString(TEXT("mock"))); return FReply::Handled(); }) ]
                ]
                + SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 8)
                [
                    SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().FillWidth(0.18f).Padding(0, 0, 6, 0)
                    [ SAssignNew(ModeBox, SEditableTextBox).Text(FText::FromString(TEXT("chat"))).HintText(LOCTEXT("ModeHint", "mode")) ]
                    + SHorizontalBox::Slot().FillWidth(0.18f).Padding(0, 0, 6, 0)
                    [ SAssignNew(BackendBox, SEditableTextBox).Text(FText::FromString(TEXT("ue"))).HintText(LOCTEXT("BackendHint", "backend")) ]
                    + SHorizontalBox::Slot().FillWidth(0.18f).Padding(0, 0, 6, 0)
                    [ SAssignNew(ProviderBox, SEditableTextBox).Text(FText::FromString(TEXT("glm"))).HintText(LOCTEXT("ProviderHint", "provider")) ]
                    + SHorizontalBox::Slot().FillWidth(0.23f).Padding(0, 0, 6, 0)
                    [ SAssignNew(ModelBox, SEditableTextBox).Text(FText::FromString(TEXT("glm-5.1"))).HintText(LOCTEXT("ModelHint", "model")) ]
                    + SHorizontalBox::Slot().FillWidth(0.23f)
                    [ SAssignNew(KeyEnvBox, SEditableTextBox).Text(FText::FromString(TEXT("BIGMODEL_API_KEY"))).HintText(LOCTEXT("KeyEnvHint", "key env")) ]
                ]
                + SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 8)
                [
                    SAssignNew(ApiKeyBox, SEditableTextBox)
                    .HintText(LOCTEXT("ApiKeyHint", "Optional API key override for this panel session"))
                    .IsPassword(true)
                ]
                + SVerticalBox::Slot().FillHeight(0.28f).Padding(0, 0, 0, 8)
                [
                    SAssignNew(PromptBox, SMultiLineEditableTextBox)
                    .Text(FText::FromString(TEXT("生成一个小球")))
                    .HintText(LOCTEXT("PromptHint", "生成5个cube排成一排, 中间放个球当主角"))
                    .AutoWrapText(true)
                ]
                + SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 8)
                [
                    SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 6, 0)
                    [ SNew(SButton).Text(LOCTEXT("RunButton", "Run")).OnClicked_Lambda([this]() { RunPrompt(PromptBox.IsValid() ? PromptBox->GetText().ToString() : FString()); return FReply::Handled(); }) ]
                    + SHorizontalBox::Slot().AutoWidth().Padding(0, 0, 6, 0)
                    [ SNew(SButton).Text(LOCTEXT("SceneButton", "Read Scene")).OnClicked_Lambda([this]() { const FString OldMode = ModeBox->GetText().ToString(); const FString OldBackend = BackendBox->GetText().ToString(); ModeBox->SetText(FText::FromString(TEXT("chat"))); BackendBox->SetText(FText::FromString(TEXT("ue"))); RunPrompt(TEXT("场景里现在有什么? 请列出来")); ModeBox->SetText(FText::FromString(OldMode)); BackendBox->SetText(FText::FromString(OldBackend)); return FReply::Handled(); }) ]
                    + SHorizontalBox::Slot().AutoWidth()
                    [ SNew(SButton).Text(LOCTEXT("ClearLogButton", "Clear Log")).OnClicked_Lambda([this]() { if (LogBox.IsValid()) { LogBox->SetText(FText::GetEmpty()); } return FReply::Handled(); }) ]
                ]
                + SVerticalBox::Slot().AutoHeight().Padding(0, 0, 0, 8)
                [ SNew(SSeparator) ]
                + SVerticalBox::Slot().FillHeight(0.72f)
                [
                    SAssignNew(LogBox, SMultiLineEditableTextBox)
                    .IsReadOnly(true)
                    .AutoWrapText(true)
                    .HintText(LOCTEXT("LogHint", "Model text, tool calls, stdout, stderr, and exit code appear here."))
                ]
            ]
        ];
}

void FCindraEditorPanelModule::RunPrompt(const FString& Prompt)
{
    UE_LOG(LogCindraEditorPanel, Display, TEXT("RunPrompt clicked. Prompt length=%d"), Prompt.Len());
    if (bRunInProgress)
    {
        AppendLog(TEXT("已有任务在运行，等它结束后再点 Run。"));
        return;
    }
    if (Prompt.TrimStartAndEnd().IsEmpty())
    {
        AppendLog(TEXT("请输入指令。"));
        return;
    }

    AppendLog(TEXT("---"));
    AppendLog(FString::Printf(TEXT("Prompt: %s"), *Prompt));

    FString StdOut;
    FString StdErr;
    const FString Args = PreparePythonArgs(Prompt);
    AppendLog(FString::Printf(TEXT("PromptFile: %s"), *LastPromptPath));
    AppendLog(FString::Printf(TEXT("OutputFile: %s"), *LastLogPath));
    FString Command = FString::Printf(
        TEXT("/C \"\"%s\" %s > \"%s\" 2>&1\""),
        *CindraPythonExe(), *Args, *LastLogPath);
    ActiveProcessHandle = FPlatformProcess::CreateProc(
        TEXT("C:\\Windows\\System32\\cmd.exe"),
        *Command,
        false, true, true,
        nullptr,
        0,
        *CindraProjectRoot(),
        nullptr);
    if (!ActiveProcessHandle.IsValid())
    {
        AppendLog(TEXT("ERROR: 无法启动 Python 子进程。"));
        return;
    }
    bRunInProgress = true;
    AppendLog(TEXT("Running async..."));
    FTSTicker::GetCoreTicker().AddTicker(
        FTickerDelegate::CreateRaw(this, &FCindraEditorPanelModule::PollRunProcess),
        0.5f);
}

bool FCindraEditorPanelModule::PollRunProcess(float DeltaTime)
{
    if (!bRunInProgress)
    {
        return false;
    }
    if (FPlatformProcess::IsProcRunning(ActiveProcessHandle))
    {
        return true;
    }

    int32 ReturnCode = -1;
    FPlatformProcess::GetProcReturnCode(ActiveProcessHandle, &ReturnCode);
    FPlatformProcess::CloseProc(ActiveProcessHandle);
    bRunInProgress = false;

    FString FileOutput;
    if (FFileHelper::LoadFileToString(FileOutput, *LastLogPath) && !FileOutput.IsEmpty())
    {
        AppendLog(FileOutput.TrimStartAndEnd());
    }
    else
    {
        AppendLog(TEXT("Output file missing or empty."));
    }
    AppendLog(FString::Printf(TEXT("Exit: %d"), ReturnCode));
    return false;
}

FString FCindraEditorPanelModule::PreparePythonArgs(const FString& Prompt)
{
    const FString Mode = ModeBox.IsValid() ? ModeBox->GetText().ToString() : TEXT("chat");
    const FString Backend = BackendBox.IsValid() ? BackendBox->GetText().ToString() : TEXT("ue");
    const FString Provider = ProviderBox.IsValid() ? ProviderBox->GetText().ToString() : TEXT("glm");
    const FString Model = ModelBox.IsValid() ? ModelBox->GetText().ToString() : TEXT("glm-5.1");
    const FString KeyEnv = KeyEnvBox.IsValid() ? KeyEnvBox->GetText().ToString() : TEXT("BIGMODEL_API_KEY");
    FString ApiKey = ApiKeyBox.IsValid() ? ApiKeyBox->GetText().ToString() : FString();
    if (ApiKey.IsEmpty())
    {
        ApiKey = ReadUserEnvironmentVar(KeyEnv);
    }

    if (!ApiKey.IsEmpty())
    {
        FPlatformMisc::SetEnvironmentVar(*KeyEnv, *ApiKey);
    }
    if (Provider == TEXT("glm") && KeyEnv != TEXT("BIGMODEL_API_KEY") && !ApiKey.IsEmpty())
    {
        FPlatformMisc::SetEnvironmentVar(TEXT("BIGMODEL_API_KEY"), *ApiKey);
    }
    FPlatformMisc::SetEnvironmentVar(TEXT("PYTHONPATH"), *CindraUEPythonPath());
    FPlatformMisc::SetEnvironmentVar(TEXT("PYTHONIOENCODING"), TEXT("utf-8"));
    FPlatformMisc::SetEnvironmentVar(TEXT("PYTHONUTF8"), TEXT("1"));
    FPlatformMisc::SetEnvironmentVar(TEXT("CINDRA_MODEL_PROVIDER"), *Provider);
    FPlatformMisc::SetEnvironmentVar(TEXT("CINDRA_MODEL"), *Model);

    const FString TempDir = FPaths::ConvertRelativePathToFull(
        FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Cindra")));
    IFileManager::Get().MakeDirectory(*TempDir, true);
    const FString Stamp = FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S_%s"));
    LastPromptPath = FPaths::Combine(TempDir, FString::Printf(TEXT("prompt_%s.txt"), *Stamp));
    LastLogPath = FPaths::Combine(TempDir, FString::Printf(TEXT("run_%s.out.txt"), *Stamp));
    FFileHelper::SaveStringToFile(Prompt, *LastPromptPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);

    AppendLog(FString::Printf(
        TEXT("Cindra panel mode=%s backend=%s provider=%s model=%s keyEnv=%s key=%s"),
        *Mode, *Backend, *Provider, *Model, *KeyEnv, *MaskKey(ApiKey)));
    if (ApiKey.IsEmpty())
    {
        AppendLog(FString::Printf(TEXT("ERROR: Missing API key env var: %s"), *KeyEnv));
    }

    return FString::Printf(
        TEXT("-m cindra.cli --mode \"%s\" --backend \"%s\" --once-file \"%s\""),
        *Mode, *Backend, *LastPromptPath);
}

void FCindraEditorPanelModule::AppendLog(const FString& Line)
{
    if (!LogBox.IsValid())
    {
        return;
    }
    const FString Current = LogBox->GetText().ToString();
    const FString Next = Current.IsEmpty() ? Line : Current + TEXT("\n") + Line;
    LogBox->SetText(FText::FromString(Next));
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FCindraEditorPanelModule, CindraEditorPanel)
