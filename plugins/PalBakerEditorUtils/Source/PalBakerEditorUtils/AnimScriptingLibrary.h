#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "AnimScriptingLibrary.generated.h"

class UAnimBlueprint;
class USkeleton;

UCLASS()
class PALBAKEREDITORUTILS_API UAnimScriptingLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintCallable, Category = "PalBaker")
    static bool ApplyPalBakerRigging(UAnimBlueprint* AnimBP, const FString& JsonPath);

    UFUNCTION(BlueprintCallable, Category = "PalBaker")
    static FString InjectVirtualBonesAndSlots(USkeleton* TargetSkeleton, const TArray<FString>& VBSources, const TArray<FString>& VBTargets, const TArray<FString>& SlotNames, const TArray<FString>& SlotGroups);

    // --- ADD THE NEW FUNCTION EXPORT BELOW ---
    UFUNCTION(BlueprintCallable, Category = "PalBaker")
    static FString InjectSockets(USkeleton* TargetSkeleton, const TArray<FString>& SocketNames, const TArray<FString>& BoneNames, const TArray<FVector>& RelativeLocations, const TArray<FRotator>& RelativeRotations, const TArray<FVector>& RelativeScales);
};