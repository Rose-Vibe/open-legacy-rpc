# Building with Headless Unity (2018.1.6f1)

How to drive the Unity editor non-interactively to build a player. Assumes the editor is installed and licensed (see *Installing Unity 2018.1.6f1 Headless on Linux*).

## The core invocation

```bash
xvfb-run -a ~/unity-2018.1.6f1/Editor/Unity \
  -batchmode -nographics \
  -projectPath /home/server-mint/unity-legacy-networking-reversed/UnityProject \
  -executeMethod BuildScript.BuildLinuxPlayer \
  -accept-apiupdate \
  -quit \
  -logFile -
```

Flag by flag:

- `-batchmode` — no GUI, no interactive dialogs.
- `-nographics` — no graphics device. Fine for building.
- `xvfb-run -a` — supplies the X connection the 2018 editor's Qt still wants even with `-nographics`. **Required** on Linux.
- `-projectPath` — the Unity project to open.
- `-executeMethod` — the static C# method that performs the build (below). Batchmode requires a build script.
- `-accept-apiupdate` — auto-accept API-updater prompts; prevents a hang.
- `-quit` — exit when the method returns.
- `-logFile -` — stream the full editor log to stdout.

## The build script (mandatory)

Place a C# file under `Assets/Editor/` in the Unity project:

```csharp
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

        var opts = new BuildPlayerOptions
        {
            scenes           = scenes,
            locationPathName = "Builds/Linux/Player.x86_64",
            target           = BuildTarget.StandaloneLinux64,
            options          = BuildOptions.EnableHeadlessMode,
        };

        BuildReport report = BuildPipeline.BuildPlayer(opts);
        BuildSummary summary = report.summary;

        Debug.Log($"Build {summary.result}: {summary.totalSize} bytes, " +
                  $"{summary.totalErrors} errors, output {summary.outputPath}");

        EditorApplication.Exit(summary.result == BuildResult.Succeeded ? 0 : 1);
    }
}
```

Notes:

- `BuildOptions.EnableHeadlessMode` is the 2018-era way to produce a headless player. `StandaloneBuildSubtarget.Server` does not exist in 2018.
- `EditorApplication.Exit(code)` gives the process a meaningful exit code.

## Detecting success

1. **Exit code** — `0` = success with the pattern above.
2. **Log scan** — grep for `error CS` / `Build Failed`.
3. **Artifact check** — confirm the output file exists and is non-empty.

## Running the built player (headless)

```bash
./Builds/Linux/Player.x86_64 -batchmode -nographics -logFile -
```

No xvfb needed for the built player.

## Gotchas

- **License must be active first.** An unlicensed editor exits early.
- **One instance per project.** Unity locks the project directory.
- **Batchmode hang on exit.** Wrap in `timeout` if needed (e.g. `timeout 1800 xvfb-run ...`).
- **First build is slow.** The editor imports all assets on first open. Keep `Library/` warm.
- **RakNet IP limit.** See `docs/notes/raknet-ip-limit-crash.md` — run the built player inside a network namespace.
