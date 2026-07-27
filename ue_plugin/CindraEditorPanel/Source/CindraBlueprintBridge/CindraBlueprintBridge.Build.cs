using UnrealBuildTool;

public class CindraBlueprintBridge : ModuleRules
{
    public CindraBlueprintBridge(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;
        PrivateDependencyModuleNames.AddRange(new string[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "UnrealEd",
            "BlueprintGraph",
            "KismetCompiler",
            "Kismet",
            "AssetTools",
            "Json",
            "JsonUtilities"
        });
    }
}
