#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "CompileScriptingLibrary.generated.h"

/**
 * Python access to the editor's async compilers. UE 5.1 exposes no way to wait for shader
 * compilation from scripting, so a material instance whose static permutation changed (e.g. a
 * BlendMode override) can be drawn with its parent's shader map while its own is still compiling.
 * A translucent override on an opaque parent then trips the RHICoreShader.cpp uniform-buffer
 * assertion (TranslucentBasePass bound, OpaqueBasePass expected) on machines with a cold shader cache.
 */
UCLASS()
class PALBAKEREDITORUTILS_API UCompileScriptingLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:

    /**
     * Blocks until every pending shader job and async asset compile (textures, meshes) has finished
     * and its results are applied, then flushes the render thread. Returns the number of shader
     * jobs that were outstanding when called (0 means there was nothing to wait for).
     */
    UFUNCTION(BlueprintCallable, Category = "PalBaker|Compile")
    static int32 FinishAllCompilation();
};
