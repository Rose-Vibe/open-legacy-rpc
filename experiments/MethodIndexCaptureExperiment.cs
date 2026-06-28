using UnityEngine;

public class MethodIndexCaptureExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }
    public void OnServerReady() { ctx.Log("Server ready, waiting for client"); }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
    }

    public void OnClientConnected()
    {
        ctx.Log("Client connected, will send RPCs to server");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (sendPhase > 5) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.8f)
        {
            switch (sendPhase)
            {
                case 0:
                    ctx.Log("Sending RPC_Int(1000) — first use");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 1000);
                    break;
                case 1:
                    ctx.Log("Sending RPC_Int(1001) — should be subsequent");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 1001);
                    break;
                case 2:
                    ctx.Log("Sending RPC_Int(1002) — subsequent again");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 1002);
                    break;
                case 3:
                    ctx.Log("Sending RPC_Float(3.14) — first use of different method");
                    ctx.PrimaryNetworkView.RPC("RPC_Float", RPCMode.Server, 3.14f);
                    break;
                case 4:
                    ctx.Log("Sending RPC_Float(2.72) — subsequent");
                    ctx.PrimaryNetworkView.RPC("RPC_Float", RPCMode.Server, 2.72f);
                    break;
                case 5:
                    ctx.Log("EXPERIMENT_DONE");
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            sendPhase++;
        }
    }

    public void Shutdown() { }
}
