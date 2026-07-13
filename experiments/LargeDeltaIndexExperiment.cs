using UnityEngine;

/// Cross-binary method_index test at a large, non-uniform delta.
///
/// Extends CrossBinaryIndexExperiment's pattern (see that file) to all 13
/// real Loader [RPC] methods instead of just 4, each sent first-use then
/// subsequent-use. Intended to run against a peer built with
/// scripts/patch-assembly-shift-indices.cs's non-uniform filler recipe, so
/// each method has a different real static index delta from its peer's
/// (some methods shifted by only a few slots, others by 80+) — see
/// docs/plans/large-delta-cross-assembly-index-test.md.
public class LargeDeltaIndexExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;
    bool ready;

    static readonly string[] MethodOrder =
    {
        "RPC_Void", "RPC_Int", "RPC_Float", "RPC_String", "RPC_Vector3",
        "RPC_Quaternion", "RPC_Bytes", "RPC_IntFloatString",
        "RPC_NetworkPlayer", "RPC_NetworkViewID", "RPC_Alpha", "RPC_Beta",
        "RPC_Gamma",
    };

    public void Setup(ExperimentContext ctx)
    {
        this.ctx = ctx;
    }

    public void OnServerReady()
    {
        ctx.Log("Server ready, waiting for client");
    }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
        ready = true;
        lastSend = Time.realtimeSinceStartup;
    }

    public void OnPlayerDisconnected(NetworkPlayer player)
    {
        ctx.Log("Player disconnected: " + player);
    }

    public void OnClientConnected()
    {
        ctx.Log("Connected to server");
        ready = true;
        lastSend = Time.realtimeSinceStartup;
    }

    void SendUse(string method, int useNumber)
    {
        RPCMode target = ctx.Role == ExperimentRole.Server ? RPCMode.Others : RPCMode.Server;
        string prefix = ctx.Role == ExperimentRole.Server ? "S" : "C";
        ctx.Log(prefix + ": Sending " + method + " — use #" + useNumber);

        switch (method)
        {
            case "RPC_Void":
                ctx.PrimaryNetworkView.RPC(method, target, new object[0]);
                break;
            case "RPC_Int":
            case "RPC_Alpha":
            case "RPC_Beta":
            case "RPC_Gamma":
                ctx.PrimaryNetworkView.RPC(method, target, 1000 + useNumber);
                break;
            case "RPC_Float":
                ctx.PrimaryNetworkView.RPC(method, target, 3.14f + useNumber);
                break;
            case "RPC_String":
                ctx.PrimaryNetworkView.RPC(method, target, "use" + useNumber);
                break;
            case "RPC_Vector3":
                ctx.PrimaryNetworkView.RPC(method, target, new Vector3(useNumber, useNumber, useNumber));
                break;
            case "RPC_Quaternion":
                ctx.PrimaryNetworkView.RPC(method, target, Quaternion.identity);
                break;
            case "RPC_Bytes":
                ctx.PrimaryNetworkView.RPC(method, target, new byte[] { 1, 2, 3, (byte)useNumber });
                break;
            case "RPC_IntFloatString":
                ctx.PrimaryNetworkView.RPC(method, target, useNumber, 1.5f, "s" + useNumber);
                break;
            case "RPC_NetworkPlayer":
                ctx.PrimaryNetworkView.RPC(method, target, Network.player);
                break;
            case "RPC_NetworkViewID":
                ctx.PrimaryNetworkView.RPC(method, target, ctx.PrimaryNetworkView.viewID);
                break;
        }
    }

    public void Tick()
    {
        if (!ready) return;
        int totalSends = MethodOrder.Length * 2;
        if (sendPhase > totalSends) return;

        if (Time.realtimeSinceStartup - lastSend > 0.4f)
        {
            if (sendPhase < totalSends)
            {
                int methodIdx = sendPhase / 2;
                int useNumber = (sendPhase % 2) + 1;
                SendUse(MethodOrder[methodIdx], useNumber);
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
