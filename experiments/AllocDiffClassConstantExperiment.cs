using UnityEngine;

/// Allocates views with 2 different MonoBehaviour classes to test whether
/// user_rpc_constant varies per class for allocated views.
/// Also sends an RPC on Loader's scene-baked view for comparison.
/// Classes: SecondRpcBehaviour (allocated), InheritedRpcDerived (allocated),
///          Loader (scene-baked only - can't instantiate dynamically)
public class AllocDiffClassConstantExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;

    NetworkView viewSecond;
    NetworkView viewInherited;

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

        // View 1: SecondRpcBehaviour
        var id1 = Network.AllocateViewID();
        {
            var go = new GameObject("AllocSecondRpc");
            var rpc = go.AddComponent<SecondRpcBehaviour>();
            var nv = go.AddComponent<NetworkView>();
            nv.viewID = id1;
            nv.stateSynchronization = NetworkStateSynchronization.Off;
            nv.observed = rpc;
            viewSecond = nv;
            ctx.Log("SecondRpcBehaviour allocated: " + id1);
        }

        // View 2: InheritedRpcDerived
        var id2 = Network.AllocateViewID();
        {
            var go = new GameObject("AllocInheritedRpc");
            var rpc = go.AddComponent<InheritedRpcDerived>();
            var nv = go.AddComponent<NetworkView>();
            nv.viewID = id2;
            nv.stateSynchronization = NetworkStateSynchronization.Off;
            nv.observed = rpc;
            viewInherited = nv;
            ctx.Log("InheritedRpcDerived allocated: " + id2);
        }
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (viewSecond == null) return;
        if (sendPhase > 3) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            switch (sendPhase)
            {
                case 0:
                    ctx.Log("Phase 0: RPC on allocated SecondRpcBehaviour (AllocatedID)");
                    viewSecond.RPC("ReceiveSerializeEvent", RPCMode.Server,
                        new byte[] { 0xBB });
                    break;
                case 1:
                    ctx.Log("Phase 1: RPC on allocated InheritedRpcDerived (AllocatedID)");
                    viewInherited.RPC("BaseRpc", RPCMode.Server, 99);
                    break;
                case 2:
                    ctx.Log("Phase 2: RPC on scene-baked Loader (SceneID 1) for comparison");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 77);
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
