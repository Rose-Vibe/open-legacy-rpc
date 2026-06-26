using UnityEngine;

public class SyncInt : MonoBehaviour
{
    public int value;
    void OnSerializeNetworkView(BitStream stream, NetworkMessageInfo info)
    {
        stream.Serialize(ref value);
    }
}

public class SyncFloat : MonoBehaviour
{
    public float value;
    void OnSerializeNetworkView(BitStream stream, NetworkMessageInfo info)
    {
        stream.Serialize(ref value);
    }
}

public class SyncVector3 : MonoBehaviour
{
    public Vector3 value;
    void OnSerializeNetworkView(BitStream stream, NetworkMessageInfo info)
    {
        stream.Serialize(ref value);
    }
}

public class MultiViewExperiment : IExperiment
{
    ExperimentContext ctx;
    int tickCount;
    bool clientConnected;

    NetworkView view0; // ReliableDeltaCompressed, int
    NetworkView view1; // Unreliable, float
    NetworkView view2; // Unreliable, Vector3

    SyncInt syncInt;
    SyncFloat syncFloat;
    SyncVector3 syncVec;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }

    public void OnServerReady()
    {
        ctx.Log("Server ready, creating 3 NetworkViews...");

        // View 0: ReliableDeltaCompressed (int)
        var go0 = new GameObject("View0_RDC");
        syncInt = go0.AddComponent<SyncInt>();
        view0 = go0.AddComponent<NetworkView>();
        view0.viewID = Network.AllocateViewID();
        view0.observed = syncInt;
        view0.stateSynchronization = NetworkStateSynchronization.ReliableDeltaCompressed;
        ctx.Log("View0 (RDC/int): viewID=" + view0.viewID);

        // View 1: Unreliable (float)
        var go1 = new GameObject("View1_Unreliable");
        syncFloat = go1.AddComponent<SyncFloat>();
        view1 = go1.AddComponent<NetworkView>();
        view1.viewID = Network.AllocateViewID();
        view1.observed = syncFloat;
        view1.stateSynchronization = NetworkStateSynchronization.Unreliable;
        ctx.Log("View1 (Unreliable/float): viewID=" + view1.viewID);

        // View 2: Unreliable (Vector3)
        var go2 = new GameObject("View2_Unreliable");
        syncVec = go2.AddComponent<SyncVector3>();
        view2 = go2.AddComponent<NetworkView>();
        view2.viewID = Network.AllocateViewID();
        view2.observed = syncVec;
        view2.stateSynchronization = NetworkStateSynchronization.Unreliable;
        ctx.Log("View2 (Unreliable/Vector3): viewID=" + view2.viewID);
    }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
        clientConnected = true;
    }

    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected");
        clientConnected = true;
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Server) return;
        if (!clientConnected) return;

        tickCount++;

        // Update values at different rates
        if (tickCount == 30)
        {
            syncInt.value = 42;
            ctx.Log("Set view0 int=42");
        }
        else if (tickCount == 60)
        {
            syncFloat.value = 3.14f;
            ctx.Log("Set view1 float=3.14");
        }
        else if (tickCount == 90)
        {
            syncVec.value = new Vector3(1, 2, 3);
            ctx.Log("Set view2 Vector3=(1,2,3)");
        }
        else if (tickCount == 120)
        {
            syncInt.value = 99;
            syncFloat.value = -1.5f;
            syncVec.value = new Vector3(10, 20, 30);
            ctx.Log("Updated all views: int=99, float=-1.5, vec=(10,20,30)");
        }
        else if (tickCount == 200)
        {
            ctx.Log("EXPERIMENT_DONE");
        }
    }

    public void Shutdown() { }
}
