using UnityEngine;

// Phase 1a smoke test (method_tag investigation): is a [RPC]-bearing class
// defined purely in experiments/*.cs (compiled into Experiments.dll via
// mcs, never part of Assembly-CSharp.dll) still discovered by Unity's
// reflection-based RPC dispatch when AddComponent'd at runtime? Reuses
// the scene-baked PrimaryNetworkView (same viewID on both peers already)
// rather than a freshly Network.AllocateViewID()'d one, to isolate
// "does reflection find this method" from "is this viewID synced".
public class RuntimeRpcBehaviour : MonoBehaviour
{
    [RPC]
    void RPC_SmokeTest(int value, NetworkMessageInfo info)
    {
        Debug.Log("[RPC] RuntimeRpcBehaviour.RPC_SmokeTest(" + value + ") from " + info.sender);
    }
}

public class RuntimeRpcSmokeExperiment : IExperiment
{
    ExperimentContext ctx;
    bool connected;
    bool sent;

    public void Setup(ExperimentContext ctx)
    {
        this.ctx = ctx;
        // Unity validates locally, on the SENDER, that the RPC method name
        // exists on NetworkView.observed before it will put anything on the
        // wire (confirmed via a first attempt that only swapped observed on
        // the server: the client logged "RPC call failed because the
        // function 'RPC_SmokeTest' does not exist in the any script
        // attached to 'Loader'" and zero RPC bytes appeared in the pcap).
        // So both peers need observed swapped, not just the receiver.
        var behaviour = ctx.PrimaryNetworkView.gameObject.AddComponent<RuntimeRpcBehaviour>();
        ctx.PrimaryNetworkView.observed = behaviour;
    }

    public void OnServerReady()
    {
        ctx.Log("Server ready");
    }

    public void OnPlayerConnected(NetworkPlayer player) { ctx.Log("Player connected"); }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected, will send RPC_SmokeTest");
        connected = true;
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (!connected || sent) return;

        ctx.Log("Sending RPC_SmokeTest(42)");
        ctx.PrimaryNetworkView.RPC("RPC_SmokeTest", RPCMode.Server, 42);
        sent = true;
        ctx.Log("EXPERIMENT_DONE");
    }

    public void Shutdown() { }
}
