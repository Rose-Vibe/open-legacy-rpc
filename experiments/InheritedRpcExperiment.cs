using UnityEngine;

/// Tests RPC encoding for methods on an inherited MonoBehaviour class.
/// InheritedRpcDerived extends InheritedRpcBase.
/// - BaseRpc is defined on InheritedRpcBase (position 0 in hierarchy -> tag 0)
/// - DerivedRpc is defined on InheritedRpcDerived (position 1 -> tag 4)
/// Captures will reveal whether the tag computation follows this rule.
public class InheritedRpcExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;

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
        if (ctx.InheritedRpcNetworkView == null)
        {
            ctx.Log("ERROR: InheritedRpcNetworkView not found in scene");
            return;
        }
        ctx.Log("InheritedRpc NetworkView viewID=" + ctx.InheritedRpcNetworkView.viewID);
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (ctx.InheritedRpcNetworkView == null) return;
        if (sendPhase > 3) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            switch (sendPhase)
            {
                case 0:
                    ctx.Log("Phase 0: Sending BaseRpc(100) - base class RPC, expect tag=0");
                    ctx.InheritedRpcNetworkView.RPC("BaseRpc", RPCMode.Server, 100);
                    break;
                case 1:
                    ctx.Log("Phase 1: Sending DerivedRpc(200) - derived class RPC, expect tag=4");
                    ctx.InheritedRpcNetworkView.RPC("DerivedRpc", RPCMode.Server, 200);
                    break;
                case 2:
                    ctx.Log("Phase 2: Sending BaseRpc(300) again (subsequent use)");
                    ctx.InheritedRpcNetworkView.RPC("BaseRpc", RPCMode.Server, 300);
                    break;
                case 3:
                    ctx.Log("EXPERIMENT_DONE");
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            sendPhase++;
        }
    }

    public void Shutdown() { }
}
