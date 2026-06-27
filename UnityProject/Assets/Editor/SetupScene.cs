using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

public static class SetupScene
{
    public static void CreateMainScene()
    {
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

        var go = new GameObject("Loader");
        go.AddComponent<Loader>();
        var nv = go.AddComponent<NetworkView>();
        nv.stateSynchronization = NetworkStateSynchronization.Off;
        nv.observed = go.GetComponent<Loader>();

        var go2 = new GameObject("SecondRpc");
        go2.AddComponent<SecondRpcBehaviour>();
        var nv2 = go2.AddComponent<NetworkView>();
        nv2.stateSynchronization = NetworkStateSynchronization.Off;
        nv2.observed = go2.GetComponent<SecondRpcBehaviour>();

        var go3 = new GameObject("InheritedRpc");
        go3.AddComponent<InheritedRpcDerived>();
        var nv3 = go3.AddComponent<NetworkView>();
        nv3.stateSynchronization = NetworkStateSynchronization.Off;
        nv3.observed = go3.GetComponent<InheritedRpcDerived>();

        var scenePath = "Assets/Scenes/Main.unity";
        System.IO.Directory.CreateDirectory("Assets/Scenes");
        EditorSceneManager.SaveScene(scene, scenePath);

        var buildScenes = new EditorBuildSettingsScene[]
        {
            new EditorBuildSettingsScene(scenePath, true)
        };
        EditorBuildSettings.scenes = buildScenes;

        Debug.Log("[SetupScene] Created Main.unity with Loader + SecondRpc + InheritedRpc NetworkViews");
    }
}
