using UnityEngine;

/// Allocates multiple NetworkViews with the same class (SecondRpcBehaviour)
/// to test whether user_rpc_constant varies by AllocatedID or stays the same.
/// Allocates IDs 50,51,52 consecutively, then skips one and uses 54.
public class MultiAllocConstantExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;

    NetworkView[] views;
    NetworkViewID[] ids;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }
    public void OnServerReady() { ctx.Log("Server ready"); }
    public void OnPlayerDisconnected(NetworkPlayer player) { }
    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
    }

    public void OnClientConnected()
    {
        ctx.Log("Client connected");

        ids = new NetworkViewID[4];
        views = new NetworkView[4];

        // Allocate 4 consecutive IDs (50, 51, 52, 53)
        for (int i = 0; i < 4; i++)
            ids[i] = Network.AllocateViewID();

        // Use IDs 0,1,2 (50,51,52) and skip ID 3 (53), allocate one more (54)
        var extraId = Network.AllocateViewID();

        for (int i = 0; i < 3; i++)
        {
            var go = new GameObject("AllocView_" + i);
            var rpc = go.AddComponent<SecondRpcBehaviour>();
            var nv = go.AddComponent<NetworkView>();
            nv.viewID = ids[i];
            nv.stateSynchronization = NetworkStateSynchronization.Off;
            nv.observed = rpc;
            views[i] = nv;
            ctx.Log("Created view " + i + " with AllocatedID=" + ids[i]);
        }

        // View 3 uses the 5th allocated ID (skipping the 4th)
        {
            var go = new GameObject("AllocView_skipped");
            var rpc = go.AddComponent<SecondRpcBehaviour>();
            var nv = go.AddComponent<NetworkView>();
            nv.viewID = extraId;
            nv.stateSynchronization = NetworkStateSynchronization.Off;
            nv.observed = rpc;
            views[3] = nv;
            ctx.Log("Created view 3 (skipped) with AllocatedID=" + extraId);
        }
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (views == null) return;
        if (sendPhase > 4) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            if (sendPhase < 4)
            {
                ctx.Log("Phase " + sendPhase + ": Sending RPC on view " + sendPhase +
                        " (AllocatedID=" + views[sendPhase].viewID + ")");
                views[sendPhase].RPC("ReceiveSerializeEvent", RPCMode.Server,
                    new byte[] { (byte)(0xA0 + sendPhase) });
            }
            else
            {
                ctx.Log("EXPERIMENT_DONE");
            }
            lastSend = Time.realtimeSinceStartup;
            sendPhase++;
        }
    }

    public void Shutdown() { }
}
