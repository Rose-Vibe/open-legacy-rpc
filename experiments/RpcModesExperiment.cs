using UnityEngine;

public class RpcModesExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }
    public void OnServerReady() { ctx.Log("Server ready"); }
    public void OnPlayerConnected(NetworkPlayer player) { ctx.Log("Player connected"); }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected, will send RPC_Int via different RPCModes");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (sendPhase > 3) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            switch (sendPhase)
            {
                case 0:
                    ctx.Log("Sending RPC_Int(10) via RPCMode.Server");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 10);
                    break;
                case 1:
                    ctx.Log("Sending RPC_Int(20) via RPCMode.All");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.All, 20);
                    break;
                case 2:
                    ctx.Log("Sending RPC_Int(30) via RPCMode.Others");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Others, 30);
                    break;
                case 3:
                    ctx.Log("Sending RPC_Int(40) via RPCMode.AllBuffered");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.AllBuffered, 40);
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            sendPhase++;

            if (sendPhase > 3)
                ctx.Log("EXPERIMENT_DONE");
        }
    }

    public void Shutdown() { }
}
