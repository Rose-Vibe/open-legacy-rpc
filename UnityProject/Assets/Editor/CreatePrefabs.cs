using UnityEditor;
using UnityEngine;

public static class CreatePrefabs
{
    public static void CreateTestPrefab()
    {
        System.IO.Directory.CreateDirectory("Assets/Resources");

        var go = new GameObject("NetworkPrefab");
        var nv = go.AddComponent<NetworkView>();
        nv.stateSynchronization = NetworkStateSynchronization.Off;

#pragma warning disable 0618
        PrefabUtility.CreatePrefab("Assets/Resources/NetworkPrefab.prefab", go);
#pragma warning restore 0618

        Object.DestroyImmediate(go);

        var go2 = new GameObject("NetworkPrefab2");
        var nv2 = go2.AddComponent<NetworkView>();
        nv2.stateSynchronization = NetworkStateSynchronization.Off;

#pragma warning disable 0618
        PrefabUtility.CreatePrefab("Assets/Resources/NetworkPrefab2.prefab", go2);
#pragma warning restore 0618

        Object.DestroyImmediate(go2);

        AssetDatabase.SaveAssets();
        Debug.Log("[CreatePrefabs] Created NetworkPrefab and NetworkPrefab2 in Resources");
    }
}
