using UnityEngine;

/// Tests sending RPCs on dynamically allocated ViewIDs (not scene-baked).
/// Allocated viewIDs use large numbers (player_index << 32 + offset).
/// This tests whether the 48-bit viewId encoding handles these correctly.
public class AllocatedViewRpcExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;
    NetworkViewID allocatedId;
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
        allocatedId = Network.AllocateViewID();
        ctx.Log("Allocated ViewID: " + allocatedId);

        var go = new GameObject("AllocatedViewObj");
        var secondRpc = go.AddComponent<SecondRpcBehaviour>();
        allocatedView = go.AddComponent<NetworkView>();
        allocatedView.viewID = allocatedId;
        allocatedView.stateSynchronization = NetworkStateSynchronization.Off;
        allocatedView.observed = secondRpc;
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (allocatedView == null) return;
        if (sendPhase > 2) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            switch (sendPhase)
            {
                case 0:
                    ctx.Log("Phase 0: Sending ReceiveSerializeEvent on allocated viewId=" + allocatedId);
                    allocatedView.RPC("ReceiveSerializeEvent", RPCMode.Server,
                        new byte[] { 0xDE, 0xAD, 0xBE, 0xEF });
                    break;
                case 1:
                    ctx.Log("Phase 1: Sending ReceiveSerializeEvent on allocated viewId (subsequent)");
                    allocatedView.RPC("ReceiveSerializeEvent", RPCMode.Server,
                        new byte[] { 0xCA, 0xFE });
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
