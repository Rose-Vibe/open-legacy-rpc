using UnityEngine;

public class RpcVoidExperiment : IExperiment
{
    ExperimentContext ctx;
    bool sent;
    float sentTime;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }

    public void OnServerReady()
    {
        ctx.Log("Server ready, waiting for client");
    }

    public void OnClientConnected()
    {
        ctx.Log("Client connected, will send RPC_Void next tick");
        sentTime = Time.realtimeSinceStartup;
    }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
    }

    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (sent) {
            if (Time.realtimeSinceStartup - sentTime > 2.0f)
                ctx.Log("EXPERIMENT_DONE");
            return;
        }
        if (sentTime > 0 && Time.realtimeSinceStartup - sentTime > 0.5f)
        {
            ctx.Log("Sending RPC_Void to server");
            ctx.PrimaryNetworkView.RPC("RPC_Void", RPCMode.Server);
            sent = true;
            sentTime = Time.realtimeSinceStartup;
        }
    }

    public void Shutdown() { }
}
