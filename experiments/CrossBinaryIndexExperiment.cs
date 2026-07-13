using UnityEngine;

/// Tests cross-binary RPC method_index handling.
///
/// Two Unity builds with different assemblies (one patched with extra [RPC]
/// methods, shifting all indices) connect and exchange RPCs.
///
/// Both log what they receive via Loader's built-in [RPC] logging.
/// If RPCs are received correctly despite different indices, it proves
/// Unity learns from first-use/subsequent-use pairs.
public class CrossBinaryIndexExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;
    bool ready;

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

    public void Tick()
    {
        if (!ready) return;
        if (sendPhase > 20) return;

        if (Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            RPCMode target = ctx.Role == ExperimentRole.Server
                ? RPCMode.Others : RPCMode.Server;
            string prefix = ctx.Role == ExperimentRole.Server ? "S" : "C";

            switch (sendPhase)
            {
                case 0:
                    ctx.Log(prefix + ": Sending RPC_Int(1000) — 1st");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", target, 1000);
                    break;
                case 1:
                    ctx.Log(prefix + ": Sending RPC_Int(1001) — 2nd");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", target, 1001);
                    break;
                case 2:
                    ctx.Log(prefix + ": Sending RPC_Int(1002) — 3rd");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", target, 1002);
                    break;
                case 3:
                    ctx.Log(prefix + ": Sending RPC_Float(3.14) — 1st");
                    ctx.PrimaryNetworkView.RPC("RPC_Float", target, 3.14f);
                    break;
                case 4:
                    ctx.Log(prefix + ": Sending RPC_Float(2.72) — 2nd");
                    ctx.PrimaryNetworkView.RPC("RPC_Float", target, 2.72f);
                    break;
                case 5:
                    ctx.Log(prefix + ": Sending RPC_String(hello) — 1st");
                    ctx.PrimaryNetworkView.RPC("RPC_String", target, "hello");
                    break;
                case 6:
                    ctx.Log(prefix + ": Sending RPC_String(world) — 2nd");
                    ctx.PrimaryNetworkView.RPC("RPC_String", target, "world");
                    break;
                case 7:
                    ctx.Log(prefix + ": Sending RPC_Alpha(42) — 1st");
                    ctx.PrimaryNetworkView.RPC("RPC_Alpha", target, 42);
                    break;
                case 8:
                    ctx.Log(prefix + ": Sending RPC_Alpha(43) — 2nd");
                    ctx.PrimaryNetworkView.RPC("RPC_Alpha", target, 43);
                    break;
                case 9:
                    ctx.Log("EXPERIMENT_DONE");
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            sendPhase++;
        }
    }

    public void Shutdown() { }
}
