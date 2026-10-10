#include "IKRetargetScriptingLibrary.h"

#include "IKRigDefinition.h"
#include "RigEditor/IKRigController.h"
#include "Retargeter/IKRetargeter.h"
#include "Retargeter/IKRetargetSettings.h"
#include "RetargetEditor/IKRetargeterController.h"
#include "Engine/SkeletalMesh.h"
#include "UObject/UnrealType.h"
#include "AssetToolsModule.h"
#include "Factories/Factory.h"

namespace
{
    // UIKRetargeter's target rig / preview meshes are private UPROPERTYs the 5.1 controller has no setter for.
    bool SetSoftObjectProperty(UObject* Owner, const FName PropertyName, UObject* Value)
    {
        FSoftObjectProperty* Prop = FindFProperty<FSoftObjectProperty>(Owner->GetClass(), PropertyName);
        if (!Prop)
        {
            return false;
        }
        Prop->SetObjectPropertyValue(Prop->ContainerPtrToValuePtr<void>(Owner), Value);
        return true;
    }

    const TCHAR* RotationModeName(ERetargetRotationMode Mode)
    {
        switch (Mode)
        {
        case ERetargetRotationMode::Interpolated: return TEXT("Interpolated");
        case ERetargetRotationMode::OneToOne: return TEXT("OneToOne");
        case ERetargetRotationMode::OneToOneReversed: return TEXT("OneToOneReversed");
        default: return TEXT("None");
        }
    }
}

namespace
{
    // Load the asset if it exists, otherwise create it with an editor factory whose required input
    // (a non-editable UPROPERTY TWeakObjectPtr) is filled in through reflection.
    template <typename AssetType>
    AssetType* LoadOrCreateWithFactory(const FString& PackagePath, const FString& AssetName, const TCHAR* FactoryClassPath,
        const FName FactoryInputProperty, UObject* FactoryInput)
    {
        const FString ObjectPath = FString::Printf(TEXT("%s/%s.%s"), *PackagePath, *AssetName, *AssetName);
        if (AssetType* Existing = LoadObject<AssetType>(nullptr, *ObjectPath, nullptr, LOAD_NoWarn | LOAD_Quiet))
        {
            return Existing;
        }
        UClass* FactoryClass = FindObject<UClass>(nullptr, FactoryClassPath);
        if (!FactoryClass || !FactoryInput)
        {
            return nullptr;
        }
        UFactory* Factory = NewObject<UFactory>(GetTransientPackage(), FactoryClass);
        FWeakObjectProperty* Prop = FindFProperty<FWeakObjectProperty>(FactoryClass, FactoryInputProperty);
        if (!Prop)
        {
            return nullptr;
        }
        Prop->SetObjectPropertyValue(Prop->ContainerPtrToValuePtr<void>(Factory), FactoryInput);
        IAssetTools& AssetTools = FModuleManager::LoadModuleChecked<FAssetToolsModule>("AssetTools").Get();
        return Cast<AssetType>(AssetTools.CreateAsset(AssetName, PackagePath, AssetType::StaticClass(), Factory));
    }
}

UIKRigDefinition* UIKRetargetScriptingLibrary::CreateIKRigAsset(const FString& PackagePath, const FString& AssetName,
    USkeletalMesh* SkeletalMesh)
{
    return LoadOrCreateWithFactory<UIKRigDefinition>(PackagePath, AssetName,
        TEXT("/Script/IKRigEditor.IKRigDefinitionFactory"), TEXT("SkeletalMesh"), SkeletalMesh);
}

UIKRetargeter* UIKRetargetScriptingLibrary::CreateIKRetargeterAsset(const FString& PackagePath, const FString& AssetName,
    UIKRigDefinition* SourceIKRig)
{
    return LoadOrCreateWithFactory<UIKRetargeter>(PackagePath, AssetName,
        TEXT("/Script/IKRigEditor.IKRetargetFactory"), TEXT("SourceIKRig"), SourceIKRig);
}

FString UIKRetargetScriptingLibrary::SetupIKRig(UIKRigDefinition* IKRig, USkeletalMesh* PreviewMesh, FName RetargetRoot,
    const TArray<FName>& ChainNames, const TArray<FName>& StartBones, const TArray<FName>& EndBones)
{
    if (!IKRig || !PreviewMesh)
    {
        return TEXT("ERROR: IKRig or PreviewMesh is null");
    }
    if (ChainNames.Num() != StartBones.Num() || ChainNames.Num() != EndBones.Num())
    {
        return TEXT("ERROR: ChainNames, StartBones and EndBones must have the same length");
    }

    UIKRigController* Controller = UIKRigController::GetIKRigController(IKRig);
    TArray<FString> Report;

    if (!Controller->SetSkeletalMesh(PreviewMesh))
    {
        return FString::Printf(TEXT("ERROR: SetSkeletalMesh(%s) failed"), *PreviewMesh->GetName());
    }

    TArray<FName> Existing;
    for (const FBoneChain& Chain : IKRig->GetRetargetChains())
    {
        Existing.Add(Chain.ChainName);
    }
    for (const FName& Name : Existing)
    {
        Controller->RemoveRetargetChain(Name);
    }

    Controller->SetRetargetRoot(RetargetRoot);
    Report.Add(FString::Printf(TEXT("root=%s"), *Controller->GetRetargetRoot().ToString()));

    for (int32 i = 0; i < ChainNames.Num(); ++i)
    {
        const FName Added = Controller->AddRetargetChain(FBoneChain(ChainNames[i], StartBones[i], EndBones[i]));
        const bool bOk = Added != NAME_None
            && Controller->GetRetargetChainStartBone(Added) == StartBones[i]
            && Controller->GetRetargetChainEndBone(Added) == EndBones[i];
        Report.Add(FString::Printf(TEXT("%s%s: %s -> %s"), bOk ? TEXT("") : TEXT("FAILED "),
            *Added.ToString(), *StartBones[i].ToString(), *EndBones[i].ToString()));
    }

    IKRig->MarkPackageDirty();
    return FString::Join(Report, TEXT("; "));
}

FString UIKRetargetScriptingLibrary::DescribeIKRig(UIKRigDefinition* IKRig)
{
    if (!IKRig)
    {
        return TEXT("ERROR: IKRig is null");
    }
    TArray<FString> Report;
    Report.Add(FString::Printf(TEXT("root=%s"), *IKRig->GetRetargetRoot().ToString()));
    for (const FBoneChain& Chain : IKRig->GetRetargetChains())
    {
        Report.Add(FString::Printf(TEXT("%s: %s -> %s"), *Chain.ChainName.ToString(),
            *Chain.StartBone.BoneName.ToString(), *Chain.EndBone.BoneName.ToString()));
    }
    return FString::Join(Report, TEXT("; "));
}

FString UIKRetargetScriptingLibrary::SetupIKRetargeter(UIKRetargeter* Retargeter, UIKRigDefinition* SourceIKRig,
    UIKRigDefinition* TargetIKRig, USkeletalMesh* SourcePreviewMesh, USkeletalMesh* TargetPreviewMesh)
{
    if (!Retargeter || !SourceIKRig || !TargetIKRig)
    {
        return TEXT("ERROR: Retargeter, SourceIKRig or TargetIKRig is null");
    }
    UIKRetargeterController* Controller = UIKRetargeterController::GetController(Retargeter);

    Controller->SetSourceIKRig(SourceIKRig);
    if (!SetSoftObjectProperty(Retargeter, TEXT("TargetIKRigAsset"), TargetIKRig))
    {
        return TEXT("ERROR: UIKRetargeter has no TargetIKRigAsset property in this engine version");
    }
    if (SourcePreviewMesh)
    {
        SetSoftObjectProperty(Retargeter, TEXT("SourcePreviewMesh"), SourcePreviewMesh);
    }
    if (TargetPreviewMesh)
    {
        SetSoftObjectProperty(Retargeter, TEXT("TargetPreviewMesh"), TargetPreviewMesh);
    }
    Controller->OnIKRigChanged(ERetargetSourceOrTarget::Target);
    Controller->CleanChainMapping();
    Controller->AutoMapChains();
    Controller->CleanPoseLists();

    Retargeter->MarkPackageDirty();
    return DescribeIKRetargeter(Retargeter);
}

FString UIKRetargetScriptingLibrary::DescribeIKRetargeter(UIKRetargeter* Retargeter)
{
    if (!Retargeter)
    {
        return TEXT("ERROR: Retargeter is null");
    }
    UIKRetargeterController* Controller = UIKRetargeterController::GetController(Retargeter);
    const UIKRigDefinition* Source = Controller->GetIKRig(ERetargetSourceOrTarget::Source);
    const UIKRigDefinition* Target = Controller->GetIKRig(ERetargetSourceOrTarget::Target);

    TArray<FString> Report;
    Report.Add(FString::Printf(TEXT("source=%s target=%s"),
        Source ? *Source->GetName() : TEXT("<none>"), Target ? *Target->GetName() : TEXT("<none>")));
    for (const TObjectPtr<URetargetChainSettings>& Map : Retargeter->GetAllChainSettings())
    {
        if (!Map)
        {
            continue;
        }
        const FTargetChainSettings& S = Map->Settings;
        Report.Add(FString::Printf(TEXT("%s <- %s [FK %s %s, IK %s]"), *Map->TargetChain.ToString(),
            Map->SourceChain.IsNone() ? TEXT("<unmapped>") : *Map->SourceChain.ToString(),
            S.FK.EnableFK ? TEXT("on") : TEXT("off"), RotationModeName(S.FK.RotationMode),
            S.IK.EnableIK ? TEXT("on") : TEXT("off")));
    }
    return FString::Join(Report, TEXT("; "));
}

bool UIKRetargetScriptingLibrary::SetRetargetChainSettings(UIKRetargeter* Retargeter, FName TargetChain, bool bEnableFK,
    uint8 RotationMode, bool bEnableIK)
{
    if (!Retargeter || RotationMode > static_cast<uint8>(ERetargetRotationMode::None))
    {
        return false;
    }
    // UIKRetargeterController::GetChainMap is private in 5.1; the asset's chain list is public
    URetargetChainSettings* Map = nullptr;
    for (const TObjectPtr<URetargetChainSettings>& Candidate : Retargeter->GetAllChainSettings())
    {
        if (Candidate && Candidate->TargetChain == TargetChain)
        {
            Map = Candidate.Get();
            break;
        }
    }
    if (!Map)
    {
        return false;
    }
    Map->Modify();
    Map->Settings.FK.EnableFK = bEnableFK;
    Map->Settings.FK.RotationMode = static_cast<ERetargetRotationMode>(RotationMode);
    Map->Settings.IK.EnableIK = bEnableIK;
    Retargeter->MarkPackageDirty();
    return true;
}

bool UIKRetargetScriptingLibrary::SetRetargetPoseRotationOffset(UIKRetargeter* Retargeter, FName BoneName,
    FRotator RotationOffset, bool bSourceSide)
{
    if (!Retargeter)
    {
        return false;
    }
    const ERetargetSourceOrTarget Side = bSourceSide ? ERetargetSourceOrTarget::Source : ERetargetSourceOrTarget::Target;
    UIKRetargeterController::GetController(Retargeter)->SetRotationOffsetForRetargetPoseBone(BoneName, RotationOffset.Quaternion(), Side);
    Retargeter->MarkPackageDirty();
    return true;
}
