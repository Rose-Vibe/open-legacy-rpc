using UnityEngine;

public class MethodIndexU2UExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;
    float startTime;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }

    public void OnServerReady()
    {
        ctx.Log("Server ready");
    }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
    }

    public void OnPlayerDisconnected(NetworkPlayer player) { }

    bool connected;

    public void OnClientConnected()
    {
        ctx.Log("Client connected, will send RPCs with 1s delays");
        connected = true;
        lastSend = Time.realtimeSinceStartup;
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (!connected) return;
        if (sendPhase > 8) return;

        if (Time.realtimeSinceStartup - lastSend > 1.0f)
        {
            switch (sendPhase)
            {
                case 0:
                    ctx.Log("Sending RPC_Int(1000) — 1st");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 1000);
                    break;
                case 1:
                    ctx.Log("Sending RPC_Int(1001) — 2nd");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 1001);
                    break;
                case 2:
                    ctx.Log("Sending RPC_Float(3.14) — 1st");
                    ctx.PrimaryNetworkView.RPC("RPC_Float", RPCMode.Server, 3.14f);
                    break;
                case 3:
                    ctx.Log("Sending RPC_Float(2.72) — 2nd");
                    ctx.PrimaryNetworkView.RPC("RPC_Float", RPCMode.Server, 2.72f);
                    break;
                case 4:
                    ctx.Log("Sending RPC_String(hello) — 1st");
                    ctx.PrimaryNetworkView.RPC("RPC_String", RPCMode.Server, "hello");
                    break;
                case 5:
                    ctx.Log("Sending RPC_String(world) — 2nd");
                    ctx.PrimaryNetworkView.RPC("RPC_String", RPCMode.Server, "world");
                    break;
                case 6:
                    ctx.Log("Sending RPC_Alpha(42) — 1st");
                    ctx.PrimaryNetworkView.RPC("RPC_Alpha", RPCMode.Server, 42);
                    break;
                case 7:
                    ctx.Log("Sending RPC_Alpha(43) — 2nd");
                    ctx.PrimaryNetworkView.RPC("RPC_Alpha", RPCMode.Server, 43);
                    break;
                case 8:
                    ctx.Log("EXPERIMENT_DONE");
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            sendPhase++;
        }
    }

    public void Shutdown() { }
}
