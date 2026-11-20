#include "CompileScriptingLibrary.h"

#include "ShaderCompiler.h"
#include "AssetCompilingManager.h"
#include "RenderingThread.h"

int32 UCompileScriptingLibrary::FinishAllCompilation()
{
    int32 PendingShaderJobs = 0;

    if (GShaderCompilingManager)
    {
        PendingShaderJobs = GShaderCompilingManager->GetNumRemainingJobs();
    }

    // Textures and meshes compile asynchronously too, and finishing them can queue more shader work,
    // so drain the asset compilers first and the shader compiler last.
    FAssetCompilingManager::Get().FinishAllCompilation();

    if (GShaderCompilingManager)
    {
        // Waits for the workers and assigns the finished shader maps to their materials.
        GShaderCompilingManager->FinishAllCompilation();
    }

    FlushRenderingCommands();

    return PendingShaderJobs;
}
