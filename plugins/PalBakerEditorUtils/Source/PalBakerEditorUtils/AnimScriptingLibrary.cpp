#include "AnimScriptingLibrary.h"
#include "Animation/AnimBlueprint.h"
#include "AnimGraphNode_Root.h"
#include "AnimGraphNode_LocalToComponentSpace.h"
#include "AnimGraphNode_ComponentToLocalSpace.h"
#include "AnimGraphNode_ModifyBone.h"
#include "AnimGraphNode_SpringBone.h"
#include "AnimGraphNode_LinkedInputPose.h"
#include "AnimGraphNode_ModifyCurve.h"
#include "AnimGraphNode_CopyBone.h"
#include "AnimNodes/AnimNode_ModifyCurve.h"
#include "UObject/UnrealType.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "AnimGraphNode_LookAt.h"
#include "Animation/Skeleton.h"
#include "Engine/SkeletalMeshSocket.h"
#include "Animation/BlendProfile.h"

#include "MaterialEditingLibrary.h"
#include "EdGraph/EdGraph.h"
#include "Materials/MaterialExpression.h"





static void ApplyAlphaScaleBiasClamp(FInputScaleBiasClamp& Clamp, const TSharedPtr<FJsonObject>& ClampObj)
{
    if (!ClampObj.IsValid()) return;
    if (ClampObj->HasField(TEXT("b_map_range"))) Clamp.bMapRange = ClampObj->GetBoolField(TEXT("b_map_range"));
    if (ClampObj->HasField(TEXT("b_clamp_result"))) Clamp.bClampResult = ClampObj->GetBoolField(TEXT("b_clamp_result"));
    if (ClampObj->HasField(TEXT("b_interp_result"))) Clamp.bInterpResult = ClampObj->GetBoolField(TEXT("b_interp_result"));
    if (ClampObj->HasField(TEXT("scale"))) Clamp.Scale = ClampObj->GetNumberField(TEXT("scale"));
    if (ClampObj->HasField(TEXT("bias"))) Clamp.Bias = ClampObj->GetNumberField(TEXT("bias"));
    if (ClampObj->HasField(TEXT("clamp_min"))) Clamp.ClampMin = ClampObj->GetNumberField(TEXT("clamp_min"));
    if (ClampObj->HasField(TEXT("clamp_max"))) Clamp.ClampMax = ClampObj->GetNumberField(TEXT("clamp_max"));
    if (ClampObj->HasField(TEXT("interp_speed_increasing"))) Clamp.InterpSpeedIncreasing = ClampObj->GetNumberField(TEXT("interp_speed_increasing"));
    if (ClampObj->HasField(TEXT("interp_speed_decreasing"))) Clamp.InterpSpeedDecreasing = ClampObj->GetNumberField(TEXT("interp_speed_decreasing"));

    const TSharedPtr<FJsonObject>* InRangeObj;
    if (ClampObj->TryGetObjectField(TEXT("in_range"), InRangeObj)) {
        Clamp.InRange.Min = (*InRangeObj)->GetNumberField(TEXT("min"));
        Clamp.InRange.Max = (*InRangeObj)->GetNumberField(TEXT("max"));
    }
    const TSharedPtr<FJsonObject>* OutRangeObj;
    if (ClampObj->TryGetObjectField(TEXT("out_range"), OutRangeObj)) {
        Clamp.OutRange.Min = (*OutRangeObj)->GetNumberField(TEXT("min"));
        Clamp.OutRange.Max = (*OutRangeObj)->GetNumberField(TEXT("max"));
    }
}

bool UAnimScriptingLibrary::ConnectWorldPositionOffset(UMaterialExpression* FromExpression, const FString& FromOutputName)
{
    if (!FromExpression) return false;
    return UMaterialEditingLibrary::ConnectMaterialProperty(FromExpression, FromOutputName, EMaterialProperty::MP_WorldPositionOffset);
}

bool UAnimScriptingLibrary::ConnectMaterialPropertyCustom(UMaterialExpression* FromExpression, const FString& FromOutputName, const FString& PropertyName)
{
    if (!FromExpression) return false;

    EMaterialProperty TargetProp = EMaterialProperty::MP_MAX;

    if (PropertyName.Equals(TEXT("WorldPositionOffset"), ESearchCase::IgnoreCase) || PropertyName.Equals(TEXT("WPO"), ESearchCase::IgnoreCase))
    {
        TargetProp = EMaterialProperty::MP_WorldPositionOffset;
    }
    else if (PropertyName.Equals(TEXT("PixelDepthOffset"), ESearchCase::IgnoreCase) || PropertyName.Equals(TEXT("PDO"), ESearchCase::IgnoreCase))
    {
        TargetProp = EMaterialProperty::MP_PixelDepthOffset;
    }
    else if (PropertyName.Equals(TEXT("MaterialAttributes"), ESearchCase::IgnoreCase))
    {
        TargetProp = EMaterialProperty::MP_MaterialAttributes;
    }

    if (TargetProp != EMaterialProperty::MP_MAX)
    {
        return UMaterialEditingLibrary::ConnectMaterialProperty(FromExpression, FromOutputName, TargetProp);
    }

    return false;
}


bool UAnimScriptingLibrary::ApplyPalBakerRigging(UAnimBlueprint* AnimBP, const FString& JsonPath)
{
    if (!AnimBP) return false;

    // 1. Load JSON Metadata
    FString JsonStr;
    if (!FFileHelper::LoadFileToString(JsonStr, *JsonPath)) return false;

    TSharedPtr<FJsonObject> JsonObj;
    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(JsonStr);
    if (!FJsonSerializer::Deserialize(Reader, JsonObj)) return false;

    // 2. Locate the AnimGraph
    UEdGraph* AnimGraph = nullptr;
    for (UEdGraph* Graph : AnimBP->FunctionGraphs) {
        if (Graph->GetFName() == TEXT("AnimGraph")) {
            AnimGraph = Graph;
            break;
        }
    }
    if (!AnimGraph) return false;

    // 3. Locate the Root Node and its Input Pin
    UAnimGraphNode_Root* RootNode = nullptr;
    for (UEdGraphNode* Node : AnimGraph->Nodes) {
        RootNode = Cast<UAnimGraphNode_Root>(Node);
        if (RootNode) break;
    }
    if (!RootNode) return false;

    UEdGraphPin* RootInputPin = RootNode->FindPin(TEXT("Result"));
    if (!RootInputPin) return false;

    UEdGraphPin* OriginalOutputPin = nullptr;
    int32 NodeX = RootNode->NodePosX - 400;
    int32 NodeY = RootNode->NodePosY;

    // If an existing blueprint, intercept the existing feed. 
    // If empty (newly generated), spawn an Input Pose node to drive the physics chain.
    if (RootInputPin->LinkedTo.Num() > 0) {
        OriginalOutputPin = RootInputPin->LinkedTo[0];
        RootInputPin->BreakAllPinLinks();
    } else {
        UAnimGraphNode_LinkedInputPose* InputNode = NewObject<UAnimGraphNode_LinkedInputPose>(AnimGraph);
        AnimGraph->AddNode(InputNode);
        InputNode->CreateNewGuid(); // FIX: Assign unique NodeGuid programmatically
        InputNode->AllocateDefaultPins();
        InputNode->Node.Name = FName(TEXT("InPose"));
        InputNode->NodePosX = NodeX - 400;
        InputNode->NodePosY = NodeY;
        
        OriginalOutputPin = InputNode->FindPin(TEXT("Pose"));
        if (!OriginalOutputPin) return false;
    }

    // --- Create Local to Component Space ---
    UAnimGraphNode_LocalToComponentSpace* L2C = NewObject<UAnimGraphNode_LocalToComponentSpace>(AnimGraph);
    AnimGraph->AddNode(L2C);
    L2C->CreateNewGuid(); // FIX: Assign unique NodeGuid programmatically
    L2C->AllocateDefaultPins();
    L2C->NodePosX = NodeX;
    L2C->NodePosY = NodeY;
    NodeX += 300;
    
    L2C->FindPin(TEXT("LocalPose"))->MakeLinkTo(OriginalOutputPin);
    UEdGraphPin* CurrentOutputPin = L2C->FindPin(TEXT("ComponentPose"));

    // --- Inject Offset Bones (ModifyBone) ---
    const TArray<TSharedPtr<FJsonValue>>* OffsetBones;
    if (JsonObj->TryGetArrayField(TEXT("offset_bones"), OffsetBones))
    {
        for (const auto& Val : *OffsetBones)
        {
            TSharedPtr<FJsonObject> BoneObj = Val->AsObject();
            
            UAnimGraphNode_ModifyBone* ModBone = NewObject<UAnimGraphNode_ModifyBone>(AnimGraph);
            AnimGraph->AddNode(ModBone);
            ModBone->CreateNewGuid(); // FIX: Assign unique NodeGuid programmatically
            ModBone->AllocateDefaultPins();
            ModBone->NodePosX = NodeX;
            ModBone->NodePosY = NodeY;
            NodeX += 300;

            ModBone->Node.BoneToModify.BoneName = FName(*BoneObj->GetStringField(TEXT("bone_name")));
            
            const TArray<TSharedPtr<FJsonValue>>* TransArr;
            if (BoneObj->TryGetArrayField(TEXT("translation"), TransArr)) {
                FVector TVal((*TransArr)[0]->AsNumber(), (*TransArr)[1]->AsNumber(), (*TransArr)[2]->AsNumber());
                ModBone->Node.Translation = TVal;
                if (UEdGraphPin* Pin = ModBone->FindPin(TEXT("Translation"))) {
                    Pin->DefaultValue = FString::Printf(TEXT("%f,%f,%f"), TVal.X, TVal.Y, TVal.Z);
                }
            }
            
            const TArray<TSharedPtr<FJsonValue>>* RotArr;
            if (BoneObj->TryGetArrayField(TEXT("rotation"), RotArr)) {
                FRotator RVal((*RotArr)[1]->AsNumber(), (*RotArr)[2]->AsNumber(), (*RotArr)[0]->AsNumber());
                ModBone->Node.Rotation = RVal;
                if (UEdGraphPin* Pin = ModBone->FindPin(TEXT("Rotation"))) {
                    Pin->DefaultValue = FString::Printf(TEXT("%f,%f,%f"), RVal.Pitch, RVal.Yaw, RVal.Roll);
                }
            }

            const TArray<TSharedPtr<FJsonValue>>* ScaleArr;
            if (BoneObj->TryGetArrayField(TEXT("scale"), ScaleArr)) {
                FVector SVal((*ScaleArr)[0]->AsNumber(), (*ScaleArr)[1]->AsNumber(), (*ScaleArr)[2]->AsNumber());
                ModBone->Node.Scale = SVal;
                if (UEdGraphPin* Pin = ModBone->FindPin(TEXT("Scale"))) {
                    Pin->DefaultValue = FString::Printf(TEXT("%f,%f,%f"), SVal.X, SVal.Y, SVal.Z);
                }
            }

            if (BoneObj->HasField(TEXT("translation_mode"))) {
                FString ModeStr = BoneObj->GetStringField(TEXT("translation_mode"));
                if (ModeStr == TEXT("BMM_Ignore")) ModBone->Node.TranslationMode = EBoneModificationMode::BMM_Ignore;
                else if (ModeStr == TEXT("BMM_Replace")) ModBone->Node.TranslationMode = EBoneModificationMode::BMM_Replace;
                else if (ModeStr == TEXT("BMM_Additive")) ModBone->Node.TranslationMode = EBoneModificationMode::BMM_Additive;
            } else {
                ModBone->Node.TranslationMode = EBoneModificationMode::BMM_Additive;
            }

            if (BoneObj->HasField(TEXT("rotation_mode"))) {
                FString ModeStr = BoneObj->GetStringField(TEXT("rotation_mode"));
                if (ModeStr == TEXT("BMM_Ignore")) ModBone->Node.RotationMode = EBoneModificationMode::BMM_Ignore;
                else if (ModeStr == TEXT("BMM_Replace")) ModBone->Node.RotationMode = EBoneModificationMode::BMM_Replace;
                else if (ModeStr == TEXT("BMM_Additive")) ModBone->Node.RotationMode = EBoneModificationMode::BMM_Additive;
            } else {
                ModBone->Node.RotationMode = EBoneModificationMode::BMM_Additive;
            }

            if (BoneObj->HasField(TEXT("scale_mode"))) {
                FString ModeStr = BoneObj->GetStringField(TEXT("scale_mode"));
                if (ModeStr == TEXT("BMM_Ignore")) ModBone->Node.ScaleMode = EBoneModificationMode::BMM_Ignore;
                else if (ModeStr == TEXT("BMM_Replace")) ModBone->Node.ScaleMode = EBoneModificationMode::BMM_Replace;
                else if (ModeStr == TEXT("BMM_Additive")) ModBone->Node.ScaleMode = EBoneModificationMode::BMM_Additive;
            } else {
                ModBone->Node.ScaleMode = EBoneModificationMode::BMM_Replace;
            }

            if (BoneObj->HasField(TEXT("translation_space"))) {
                FString SpaceStr = BoneObj->GetStringField(TEXT("translation_space"));
                if (SpaceStr == TEXT("BCS_ComponentSpace")) ModBone->Node.TranslationSpace = EBoneControlSpace::BCS_ComponentSpace;
                else if (SpaceStr == TEXT("BCS_BoneSpace")) ModBone->Node.TranslationSpace = EBoneControlSpace::BCS_BoneSpace;
                else if (SpaceStr == TEXT("BCS_ParentBoneSpace")) ModBone->Node.TranslationSpace = EBoneControlSpace::BCS_ParentBoneSpace;
            } else {
                ModBone->Node.TranslationSpace = EBoneControlSpace::BCS_ParentBoneSpace;
            }

            if (BoneObj->HasField(TEXT("rotation_space"))) {
                FString SpaceStr = BoneObj->GetStringField(TEXT("rotation_space"));
                if (SpaceStr == TEXT("BCS_ComponentSpace")) ModBone->Node.RotationSpace = EBoneControlSpace::BCS_ComponentSpace;
                else if (SpaceStr == TEXT("BCS_BoneSpace")) ModBone->Node.RotationSpace = EBoneControlSpace::BCS_BoneSpace;
                else if (SpaceStr == TEXT("BCS_ParentBoneSpace")) ModBone->Node.RotationSpace = EBoneControlSpace::BCS_ParentBoneSpace;
            } else {
                ModBone->Node.RotationSpace = EBoneControlSpace::BCS_ParentBoneSpace;
            }

            if (BoneObj->HasField(TEXT("scale_space"))) {
                FString SpaceStr = BoneObj->GetStringField(TEXT("scale_space"));
                if (SpaceStr == TEXT("BCS_ComponentSpace")) ModBone->Node.ScaleSpace = EBoneControlSpace::BCS_ComponentSpace;
                else if (SpaceStr == TEXT("BCS_BoneSpace")) ModBone->Node.ScaleSpace = EBoneControlSpace::BCS_BoneSpace;
                else if (SpaceStr == TEXT("BCS_ParentBoneSpace")) ModBone->Node.ScaleSpace = EBoneControlSpace::BCS_ParentBoneSpace;
            } else {
                ModBone->Node.ScaleSpace = EBoneControlSpace::BCS_BoneSpace;
            }

            const TSharedPtr<FJsonObject>* ModClampObj;
            if (BoneObj->TryGetObjectField(TEXT("alpha_scale_bias_clamp"), ModClampObj)) {
                ApplyAlphaScaleBiasClamp(ModBone->Node.AlphaScaleBiasClamp, *ModClampObj);
            }

            ModBone->FindPin(TEXT("ComponentPose"))->MakeLinkTo(CurrentOutputPin);
            CurrentOutputPin = ModBone->FindPin(TEXT("Pose"));
        }
    }

    // --- Inject Jiggle Bones (SpringBone) ---
    const TArray<TSharedPtr<FJsonValue>>* JiggleBones;
    if (JsonObj->TryGetArrayField(TEXT("jiggle_bones"), JiggleBones))
    {
        for (const auto& Val : *JiggleBones)
        {
            TSharedPtr<FJsonObject> BoneObj = Val->AsObject();
            
            UAnimGraphNode_SpringBone* SpringBone = NewObject<UAnimGraphNode_SpringBone>(AnimGraph);
            AnimGraph->AddNode(SpringBone);
            SpringBone->CreateNewGuid(); // FIX: Assign unique NodeGuid programmatically
            SpringBone->AllocateDefaultPins();
            SpringBone->NodePosX = NodeX;
            SpringBone->NodePosY = NodeY;
            NodeX += 300;

            SpringBone->Node.SpringBone.BoneName = FName(*BoneObj->GetStringField(TEXT("bone_name")));
            SpringBone->Node.SpringStiffness = BoneObj->GetNumberField(TEXT("spring_stiffness"));
            SpringBone->Node.SpringDamping = BoneObj->GetNumberField(TEXT("spring_damping"));
            SpringBone->Node.MaxDisplacement = BoneObj->GetNumberField(TEXT("max_displacement"));
            SpringBone->Node.ErrorResetThresh = BoneObj->GetNumberField(TEXT("error_reset_thresh"));
            SpringBone->Node.bLimitDisplacement = BoneObj->GetBoolField(TEXT("limit_displacement"));
            
            SpringBone->Node.bTranslateX = BoneObj->GetBoolField(TEXT("translate_x"));
            SpringBone->Node.bTranslateY = BoneObj->GetBoolField(TEXT("translate_y"));
            SpringBone->Node.bTranslateZ = BoneObj->GetBoolField(TEXT("translate_z"));
            SpringBone->Node.bRotateX = BoneObj->GetBoolField(TEXT("rotate_x"));
            SpringBone->Node.bRotateY = BoneObj->GetBoolField(TEXT("rotate_y"));
            SpringBone->Node.bRotateZ = BoneObj->GetBoolField(TEXT("rotate_z"));

            // Parse and apply the Alpha field to both the property and the exposed Pin
            if (BoneObj->HasField(TEXT("alpha"))) {
                float AlphaVal = BoneObj->GetNumberField(TEXT("alpha"));
                SpringBone->Node.Alpha = AlphaVal;
                
                UEdGraphPin* AlphaPin = SpringBone->FindPin(TEXT("Alpha"));
                if (AlphaPin) {
                    AlphaPin->DefaultValue = FString::Printf(TEXT("%f"), AlphaVal);
                }
            }

            const TSharedPtr<FJsonObject>* SpringClampObj;
            if (BoneObj->TryGetObjectField(TEXT("alpha_scale_bias_clamp"), SpringClampObj)) {
                ApplyAlphaScaleBiasClamp(SpringBone->Node.AlphaScaleBiasClamp, *SpringClampObj);
            }

            SpringBone->FindPin(TEXT("ComponentPose"))->MakeLinkTo(CurrentOutputPin);
            CurrentOutputPin = SpringBone->FindPin(TEXT("Pose"));
        }
    }

    
    // --- Inject LookAt Bones (Track To) ---
    const TArray<TSharedPtr<FJsonValue>>* LookAtBones;
    if (JsonObj->TryGetArrayField(TEXT("lookat_bones"), LookAtBones))
    {
        for (const auto& Val : *LookAtBones)
        {
            TSharedPtr<FJsonObject> BoneObj = Val->AsObject();
            if (!BoneObj.IsValid()) continue;

            UAnimGraphNode_LookAt* LookAtNode = NewObject<UAnimGraphNode_LookAt>(AnimGraph);
            AnimGraph->AddNode(LookAtNode);
            LookAtNode->CreateNewGuid();
            LookAtNode->AllocateDefaultPins();
            LookAtNode->NodePosX = NodeX;
            LookAtNode->NodePosY = NodeY;
            NodeX += 300;

            // Set up Core Properties
            LookAtNode->Node.BoneToModify.BoneName = FName(*BoneObj->GetStringField(TEXT("bone_name")));
            LookAtNode->Node.LookAtTarget.BoneReference.BoneName = FName(*BoneObj->GetStringField(TEXT("target_bone")));
            LookAtNode->Node.LookAtLocation = FVector::ZeroVector;
            
            if (BoneObj->HasField(TEXT("clamp"))) {
                LookAtNode->Node.LookAtClamp = BoneObj->GetNumberField(TEXT("clamp"));
            }
            if (BoneObj->HasField(TEXT("alpha"))) {
                LookAtNode->Node.Alpha = BoneObj->GetNumberField(TEXT("alpha"));
            }

            // Map Blender axes to Unreal
            const TSharedPtr<FJsonObject>* LookAtAxisObj;
            if (BoneObj->TryGetObjectField(TEXT("look_at_axis"), LookAtAxisObj)) {
                LookAtNode->Node.LookAt_Axis.Axis = FVector((*LookAtAxisObj)->GetNumberField(TEXT("X")), (*LookAtAxisObj)->GetNumberField(TEXT("Y")), (*LookAtAxisObj)->GetNumberField(TEXT("Z")));
                LookAtNode->Node.LookAt_Axis.bInLocalSpace = true;
            }

            const TSharedPtr<FJsonObject>* LookUpAxisObj;
            if (BoneObj->TryGetObjectField(TEXT("look_up_axis"), LookUpAxisObj)) {
                LookAtNode->Node.LookUp_Axis.Axis = FVector((*LookUpAxisObj)->GetNumberField(TEXT("X")), (*LookUpAxisObj)->GetNumberField(TEXT("Y")), (*LookUpAxisObj)->GetNumberField(TEXT("Z")));
                LookAtNode->Node.LookUp_Axis.bInLocalSpace = true;
            }

            // Wire it into the Graph
            LookAtNode->FindPin(TEXT("ComponentPose"))->MakeLinkTo(CurrentOutputPin);
            CurrentOutputPin = LookAtNode->FindPin(TEXT("Pose"));
        }
    }
    
    // --- Inject Copy Bones (CopyBone) ---
    const TArray<TSharedPtr<FJsonValue>>* CopyBones;
    if (JsonObj->TryGetArrayField(TEXT("copy_bones"), CopyBones))
    {
        for (const auto& Val : *CopyBones)
        {
            TSharedPtr<FJsonObject> BoneObj = Val->AsObject();
            if (!BoneObj.IsValid()) continue;

            UAnimGraphNode_CopyBone* CopyNode = NewObject<UAnimGraphNode_CopyBone>(AnimGraph);
            AnimGraph->AddNode(CopyNode);
            CopyNode->CreateNewGuid();
            CopyNode->NodePosX = NodeX;
            CopyNode->NodePosY = NodeY;
            NodeX += 300;

            const bool bCopyTrans = BoneObj->GetBoolField(TEXT("copy_translation"));
            const bool bCopyRot   = BoneObj->GetBoolField(TEXT("copy_rotation"));
            const bool bCopyScale = BoneObj->GetBoolField(TEXT("copy_scale"));

            float AlphaVal = 1.0f;
            if (BoneObj->HasField(TEXT("alpha")))
            {
                AlphaVal = BoneObj->GetNumberField(TEXT("alpha"));
            }

            // 1. Set the struct properties FIRST so pin generation inherits these values
            CopyNode->Node.SourceBone.BoneName = FName(*BoneObj->GetStringField(TEXT("source_bone")));
            CopyNode->Node.TargetBone.BoneName = FName(*BoneObj->GetStringField(TEXT("target_bone")));
            CopyNode->Node.bCopyTranslation = bCopyTrans;
            CopyNode->Node.bCopyRotation = bCopyRot;
            CopyNode->Node.bCopyScale = bCopyScale;

            if (BoneObj->HasField(TEXT("control_space"))) {
                FString SpaceStr = BoneObj->GetStringField(TEXT("control_space"));
                if (SpaceStr == TEXT("BCS_ComponentSpace")) CopyNode->Node.ControlSpace = EBoneControlSpace::BCS_ComponentSpace;
                else if (SpaceStr == TEXT("BCS_BoneSpace")) CopyNode->Node.ControlSpace = EBoneControlSpace::BCS_BoneSpace;
                else if (SpaceStr == TEXT("BCS_ParentBoneSpace")) CopyNode->Node.ControlSpace = EBoneControlSpace::BCS_ParentBoneSpace;
            } else {
                CopyNode->Node.ControlSpace = EBoneControlSpace::BCS_ComponentSpace;
            }

            CopyNode->Node.Alpha = AlphaVal;

            const TSharedPtr<FJsonObject>* CopyClampObj;
            if (BoneObj->TryGetObjectField(TEXT("alpha_scale_bias_clamp"), CopyClampObj)) {
                ApplyAlphaScaleBiasClamp(CopyNode->Node.AlphaScaleBiasClamp, *CopyClampObj);
            }

            // 2. Allocate default pins
            CopyNode->AllocateDefaultPins();

            // 3. Explicitly synchronize pin default values to prevent Unreal from resetting them to False
            if (UEdGraphPin* Pin = CopyNode->FindPin(TEXT("bCopyTranslation")))
            {
                Pin->DefaultValue = bCopyTrans ? TEXT("true") : TEXT("false");
            }
            if (UEdGraphPin* Pin = CopyNode->FindPin(TEXT("bCopyRotation")))
            {
                Pin->DefaultValue = bCopyRot ? TEXT("true") : TEXT("false");
            }
            if (UEdGraphPin* Pin = CopyNode->FindPin(TEXT("bCopyScale")))
            {
                Pin->DefaultValue = bCopyScale ? TEXT("true") : TEXT("false");
            }
            if (UEdGraphPin* AlphaPin = CopyNode->FindPin(TEXT("Alpha")))
            {
                AlphaPin->DefaultValue = FString::Printf(TEXT("%f"), AlphaVal);
            }

            CopyNode->FindPin(TEXT("ComponentPose"))->MakeLinkTo(CurrentOutputPin);
            CurrentOutputPin = CopyNode->FindPin(TEXT("Pose"));
        }
    }

    // --- Create Component to Local Space ---
    UAnimGraphNode_ComponentToLocalSpace* C2L = NewObject<UAnimGraphNode_ComponentToLocalSpace>(AnimGraph);
    AnimGraph->AddNode(C2L);
    C2L->CreateNewGuid(); // FIX: Assign unique NodeGuid programmatically
    C2L->AllocateDefaultPins();
    C2L->NodePosX = NodeX;
    C2L->NodePosY = NodeY;
    NodeX += 300;

    C2L->FindPin(TEXT("ComponentPose"))->MakeLinkTo(CurrentOutputPin);
    UEdGraphPin* FinalLocalPosePin = C2L->FindPin(TEXT("Pose"));

    // --- Inject Default Shape Keys (ModifyCurve Node) ---
    const TArray<TSharedPtr<FJsonValue>>* DefaultShapekeys;
    if (JsonObj->TryGetArrayField(TEXT("default_shapekeys"), DefaultShapekeys) && DefaultShapekeys->Num() > 0)
    {
        UAnimGraphNode_ModifyCurve* ModifyCurveNode = NewObject<UAnimGraphNode_ModifyCurve>(AnimGraph);
        AnimGraph->AddNode(ModifyCurveNode);
        ModifyCurveNode->CreateNewGuid();
        ModifyCurveNode->AllocateDefaultPins();
        ModifyCurveNode->NodePosX = NodeX;
        ModifyCurveNode->NodePosY = NodeY;
        NodeX += 300;

        // Access private UPROPERTY 'Node' via Unreal reflection to bypass C2248
        FStructProperty* NodeProp = CastField<FStructProperty>(ModifyCurveNode->GetClass()->FindPropertyByName(TEXT("Node")));
        if (NodeProp)
        {
            FAnimNode_ModifyCurve* NodePtr = NodeProp->ContainerPtrToValuePtr<FAnimNode_ModifyCurve>(ModifyCurveNode);
            if (NodePtr)
            {
                NodePtr->ApplyMode = EModifyCurveApplyMode::Blend;
                NodePtr->Alpha = 1.0f;

                for (const auto& Val : *DefaultShapekeys)
                {
                    FString CurveNameStr = Val->AsString();
                    if (!CurveNameStr.IsEmpty())
                    {
                        NodePtr->AddCurve(FName(*CurveNameStr), 1.0f);
                    }
                }
            }
        }

        ModifyCurveNode->ReconstructNode();
        // Enforce default values on pins if exposed
        for (const auto& Val : *DefaultShapekeys)
        {
            FString CurveNameStr = Val->AsString();
            if (UEdGraphPin* CurvePin = ModifyCurveNode->FindPin(CurveNameStr))
            {
                CurvePin->DefaultValue = TEXT("1.0");
            }
        }

        UEdGraphPin* ModifyCurveInPin = ModifyCurveNode->FindPin(TEXT("SourcePose"));
        if (!ModifyCurveInPin)
        {
            for (UEdGraphPin* Pin : ModifyCurveNode->Pins)
            {
                if (Pin->Direction == EGPD_Input && Pin->PinType.PinCategory == UEdGraphSchema_K2::PC_Struct)
                {
                    ModifyCurveInPin = Pin;
                    break;
                }
            }
        }

        UEdGraphPin* ModifyCurveOutPin = ModifyCurveNode->FindPin(TEXT("Pose"));
        if (!ModifyCurveOutPin)
        {
            for (UEdGraphPin* Pin : ModifyCurveNode->Pins)
            {
                if (Pin->Direction == EGPD_Output && Pin->PinType.PinCategory == UEdGraphSchema_K2::PC_Struct)
                {
                    ModifyCurveOutPin = Pin;
                    break;
                }
            }
        }

        if (ModifyCurveInPin && FinalLocalPosePin)
        {
            ModifyCurveInPin->MakeLinkTo(FinalLocalPosePin);
        }

        if (ModifyCurveOutPin)
        {
            FinalLocalPosePin = ModifyCurveOutPin;
        }
    }

    FinalLocalPosePin->MakeLinkTo(RootInputPin);

    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(AnimBP);
    FKismetEditorUtilities::CompileBlueprint(AnimBP);

    return true;
}
FString UAnimScriptingLibrary::InjectVirtualBonesAndSlots(USkeleton* TargetSkeleton, const TArray<FString>& VBSources, const TArray<FString>& VBTargets, const TArray<FString>& SlotNames, const TArray<FString>& SlotGroups)
{
    if (!TargetSkeleton) return TEXT("Target Skeleton is null.");
    TargetSkeleton->Modify();
    FString Report = TEXT("");

    // 1. Inject Virtual Bones
    for (int32 i = 0; i < VBSources.Num() && i < VBTargets.Num(); i++)
    {
        FName SourceName = FName(*VBSources[i]);
        FName TargetName = FName(*VBTargets[i]);

        bool bExists = false;
        for (const FVirtualBone& VB : TargetSkeleton->GetVirtualBones()) {
            if (VB.SourceBoneName == SourceName && VB.TargetBoneName == TargetName) {
                bExists = true; break;
            }
        }
        if (!bExists) {
            if (TargetSkeleton->AddNewVirtualBone(SourceName, TargetName)) {
                Report += FString::Printf(TEXT("  + Virtual Bone: %s -> %s\n"), *VBSources[i], *VBTargets[i]);
            } else {
                Report += FString::Printf(TEXT("  - FAILED Virtual Bone: %s -> %s (Missing bone in custom mesh)\n"), *VBSources[i], *VBTargets[i]);
            }
        }
    }

    // 2. Inject Anim Slot Groups
    for (int32 i = 0; i < SlotNames.Num() && i < SlotGroups.Num(); i++)
    {
        FName SlotName = FName(*SlotNames[i]);
        FName GroupName = FName(*SlotGroups[i]);
        
        bool bGroupExists = false;
        for (const FAnimSlotGroup& Group : TargetSkeleton->GetSlotGroups()) {
            if (Group.GroupName == GroupName) { bGroupExists = true; break; }
        }
        if (!bGroupExists) {
            TargetSkeleton->AddSlotGroupName(GroupName);
            Report += FString::Printf(TEXT("  + Slot Group: %s\n"), *SlotGroups[i]);
        }
        if (!TargetSkeleton->ContainsSlotName(SlotName)) {
            TargetSkeleton->SetSlotGroupName(SlotName, GroupName);
            Report += FString::Printf(TEXT("  + Anim Slot: %s\n"), *SlotNames[i]);
        }
    }
    
    return Report;
}

FString UAnimScriptingLibrary::InjectSockets(USkeleton* TargetSkeleton, const TArray<FString>& SocketNames, const TArray<FString>& BoneNames, const TArray<FVector>& RelativeLocations, const TArray<FRotator>& RelativeRotations, const TArray<FVector>& RelativeScales)
{
    if (!TargetSkeleton) return TEXT("Target Skeleton is null.");
    TargetSkeleton->Modify();
    FString Report = TEXT("");
    
    for (int32 i = 0; i < SocketNames.Num(); i++)
    {
        FName SocketName = FName(*SocketNames[i]);
        FName BoneName = FName(*BoneNames[i]);
        
        bool bExists = false;
        for (USkeletalMeshSocket* Socket : TargetSkeleton->Sockets) {
            if (Socket && Socket->SocketName == SocketName) {
                bExists = true;
                break;
            }
        }
        
        if (!bExists) {
            USkeletalMeshSocket* NewSocket = NewObject<USkeletalMeshSocket>(TargetSkeleton);
            NewSocket->SocketName = SocketName;
            NewSocket->BoneName = BoneName;
            
            if (RelativeLocations.IsValidIndex(i)) NewSocket->RelativeLocation = RelativeLocations[i];
            if (RelativeRotations.IsValidIndex(i)) NewSocket->RelativeRotation = RelativeRotations[i];
            if (RelativeScales.IsValidIndex(i)) NewSocket->RelativeScale = RelativeScales[i];
            
            TargetSkeleton->Sockets.Add(NewSocket);
            Report += FString::Printf(TEXT("  + Socket: %s (Bone: %s)\n"), *SocketNames[i], *BoneNames[i]);
        }
    }
    return Report;
}