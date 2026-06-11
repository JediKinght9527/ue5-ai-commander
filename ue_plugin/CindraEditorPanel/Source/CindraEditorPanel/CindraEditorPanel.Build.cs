using UnrealBuildTool;

public class CindraEditorPanel : ModuleRules
{
    public CindraEditorPanel(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;
        PrivateDependencyModuleNames.AddRange(new string[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "InputCore",
            "Slate",
            "SlateCore",
            "ToolMenus",
            "LevelEditor",
            "Projects"
        });
    }
}
