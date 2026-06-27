using UnityEngine;

/// Compares user_rpc_constant between scene-baked and allocated views
/// of the SAME class (SecondRpcBehaviour).
/// Scene-baked SecondRpc is at SceneID 2 (expected constant 0x0004).
/// Allocated SecondRpc should reveal if constant is view-type-derived.
public class SceneVsAllocConstantExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;

    NetworkView allocatedView;

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

        if (ctx.SecondRpcNetworkView == null)
        {
            ctx.Log("ERROR: SecondRpcNetworkView not found in scene");
            return;
        }
        ctx.Log("Scene-baked SecondRpc viewID=" + ctx.SecondRpcNetworkView.viewID);

        // Allocate a new view with the same class
        var allocId = Network.AllocateViewID();
        var go = new GameObject("AllocSecondRpc");
        var rpc = go.AddComponent<SecondRpcBehaviour>();
        var nv = go.AddComponent<NetworkView>();
        nv.viewID = allocId;
        nv.stateSynchronization = NetworkStateSynchronization.Off;
        nv.observed = rpc;
        allocatedView = nv;
        ctx.Log("Allocated SecondRpc viewID=" + allocId);
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (ctx.SecondRpcNetworkView == null) return;
        if (allocatedView == null) return;
        if (sendPhase > 2) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            switch (sendPhase)
            {
                case 0:
                    ctx.Log("Phase 0: RPC on SCENE-BAKED SecondRpc (SceneID 2)");
                    ctx.SecondRpcNetworkView.RPC("ReceiveSerializeEvent", RPCMode.Server,
                        new byte[] { 0xCC });
                    break;
                case 1:
                    ctx.Log("Phase 1: RPC on ALLOCATED SecondRpc");
                    allocatedView.RPC("ReceiveSerializeEvent", RPCMode.Server,
                        new byte[] { 0xDD });
                    break;
                case 2:
                    ctx.Log("EXPERIMENT_DONE");
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            sendPhase++;
        }
    }

    public void Shutdown() { }
}
