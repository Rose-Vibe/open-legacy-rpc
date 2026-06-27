using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

public static class BuildScript
{
    public static void BuildLinuxPlayer()
    {
        var scenes = EditorBuildSettings.scenes
            .Where(s => s.enabled)
            .Select(s => s.path)
            .ToArray();

        if (scenes.Length == 0)
        {
            Debug.LogError("No scenes in build settings — adding all scenes in Assets/");
            scenes = System.IO.Directory.GetFiles("Assets", "*.unity", System.IO.SearchOption.AllDirectories);
        }

        var opts = new BuildPlayerOptions
        {
            scenes           = scenes,
            locationPathName = "Builds/Linux/Player.x86_64",
            target           = BuildTarget.StandaloneLinux64,
            options          = BuildOptions.EnableHeadlessMode,
        };

        BuildReport report = BuildPipeline.BuildPlayer(opts);
        BuildSummary summary = report.summary;

        Debug.Log(string.Format("Build {0}: {1} bytes, {2} errors, output {3}",
            summary.result, summary.totalSize, summary.totalErrors, summary.outputPath));

        EditorApplication.Exit(summary.result == BuildResult.Succeeded ? 0 : 1);
    }
}
