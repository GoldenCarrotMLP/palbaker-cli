#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "IKRetargetScriptingLibrary.generated.h"

class UIKRigDefinition;
class UIKRetargeter;
class USkeletalMesh;

/**
 * Python access to IK Rig / IK Retargeter editing. UE 5.1 has the controllers in C++
 * (UIKRigController, UIKRetargeterController) but exposes none of it to scripting.
 * Every function returns a human-readable report so scripts can log what actually happened.
 */
UCLASS()
class PALBAKEREDITORUTILS_API UIKRetargetScriptingLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:

    /** Creates (or loads, if it already exists) an IK Rig asset for the mesh. Its factory needs the mesh set, which Python can't do in 5.1. */
    UFUNCTION(BlueprintCallable, Category = "PalBaker|Retarget")
    static UIKRigDefinition* CreateIKRigAsset(const FString& PackagePath, const FString& AssetName, USkeletalMesh* SkeletalMesh);

    /** Creates (or loads, if it already exists) an IK Retargeter asset. Its factory needs the source rig set, which Python can't do in 5.1. */
    UFUNCTION(BlueprintCallable, Category = "PalBaker|Retarget")
    static UIKRetargeter* CreateIKRetargeterAsset(const FString& PackagePath, const FString& AssetName, UIKRigDefinition* SourceIKRig);

    /** Sets the preview mesh and retarget root, replaces all retarget chains with the given ones (parallel arrays). */
    UFUNCTION(BlueprintCallable, Category = "PalBaker|Retarget")
    static FString SetupIKRig(UIKRigDefinition* IKRig, USkeletalMesh* PreviewMesh, FName RetargetRoot,
        const TArray<FName>& ChainNames, const TArray<FName>& StartBones, const TArray<FName>& EndBones);

    /** "root=<bone>; <chain>: <start> -> <end>; ..." as stored on the asset. */
    UFUNCTION(BlueprintCallable, Category = "PalBaker|Retarget")
    static FString DescribeIKRig(UIKRigDefinition* IKRig);

    /** Assigns source/target IK Rigs and preview meshes, then auto-maps chains by name. */
    UFUNCTION(BlueprintCallable, Category = "PalBaker|Retarget")
    static FString SetupIKRetargeter(UIKRetargeter* Retargeter, UIKRigDefinition* SourceIKRig, UIKRigDefinition* TargetIKRig,
        USkeletalMesh* SourcePreviewMesh, USkeletalMesh* TargetPreviewMesh);

    /** "<target chain> <- <source chain> [FK on/off, rotation mode, IK on/off]; ..." */
    UFUNCTION(BlueprintCallable, Category = "PalBaker|Retarget")
    static FString DescribeIKRetargeter(UIKRetargeter* Retargeter);

    /** Per target chain FK/IK switches. RotationMode: 0 Interpolated, 1 OneToOne, 2 OneToOneReversed, 3 None. */
    UFUNCTION(BlueprintCallable, Category = "PalBaker|Retarget")
    static bool SetRetargetChainSettings(UIKRetargeter* Retargeter, FName TargetChain, bool bEnableFK, uint8 RotationMode, bool bEnableIK);

    /** Rotation offset of one bone in the current retarget pose (source or target side). */
    UFUNCTION(BlueprintCallable, Category = "PalBaker|Retarget")
    static bool SetRetargetPoseRotationOffset(UIKRetargeter* Retargeter, FName BoneName, FRotator RotationOffset, bool bSourceSide);
};
