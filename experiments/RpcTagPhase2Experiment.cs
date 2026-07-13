using UnityEngine;

// Phase 2 (method_tag investigation): behavioral accept/reject test.
//
// Phase 1 confirmed the shared-derivation rule predicts observed tags with
// 11/11 accuracy across a self-Unity-to-Unity capture, where the real tag
// Unity itself chose was compared against the prediction. Phase 2 asks the
// complementary question: does a WRONG tag actually get rejected by Unity's
// dispatcher, or does Unity accept any 4-bit value and dispatch on the
// method identifier alone (making method_tag cosmetic)? This mirrors the
// original decisive RPC_Float test in
// docs/research/2026-07-12-method-tag-real-derivation.md.
//
// Two brand-new names (never seen by this Unity binary before):
//   RPC_Phase2Accept -- sent with tag=8, the rule's PREDICTED (correct) tag
//   RPC_Phase2Reject -- sent with tag=0, a DELIBERATELY WRONG tag (correct
//                       predicted tag is 4)
//
// The sender is a raw Python script (scripts/rpc-tag-phase2-server.py),
// not a real Unity peer, so the Phase 1a sender-side validation (Unity
// refusing to transmit RPCs not on NetworkView.observed) does not apply
// here -- only the CLIENT (receiver)'s dispatch behavior is under test.
//
// The new RPC methods are added to ctx.SecondRpcNetworkView (scene ID 2,
// routing constant 0x0004; see experiments/SceneVsAllocConstantExperiment.cs)
// rather than PrimaryNetworkView, so Loader's own RPC_Gamma stays available
// on PrimaryNetworkView for the ready-ping (as in scripts/tag-collision-
// server.py) without needing a second connect/observed dance.
public class Phase2TagBehaviour : MonoBehaviour
{
    [RPC]
    void RPC_Phase2Accept(int v, NetworkMessageInfo info)
    {
        Debug.Log("[RPC] RPC_Phase2Accept(" + v + ") from " + info.sender);
    }

    [RPC]
    void RPC_Phase2Reject(int v, NetworkMessageInfo info)
    {
        Debug.Log("[RPC] RPC_Phase2Reject(" + v + ") from " + info.sender);
    }
}

public class RpcTagPhase2Experiment : IExperiment
{
    ExperimentContext ctx;
    bool connected;
    bool sentPing;

    public void Setup(ExperimentContext ctx)
    {
        this.ctx = ctx;
        if (ctx.SecondRpcNetworkView == null)
        {
            ctx.Log("ERROR: SecondRpcNetworkView not found in scene");
            return;
        }
        var behaviour = ctx.SecondRpcNetworkView.gameObject.AddComponent<Phase2TagBehaviour>();
        ctx.SecondRpcNetworkView.observed = behaviour;
        ctx.Log("SecondRpc viewID=" + ctx.SecondRpcNetworkView.viewID);
    }

    public void OnServerReady() { ctx.Log("Server ready"); }
    public void OnPlayerConnected(NetworkPlayer player) { ctx.Log("Player connected"); }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected");
        connected = true;
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (!connected || sentPing) return;

        // Ready ping via Loader's own pre-existing RPC_Gamma (PrimaryNetworkView
        // still observed by Loader -- untouched by Setup() above).
        ctx.Log("Sending ready ping (RPC_Gamma)");
        ctx.PrimaryNetworkView.RPC("RPC_Gamma", RPCMode.Server, 1);
        sentPing = true;
    }

    public void Shutdown() { }
}
