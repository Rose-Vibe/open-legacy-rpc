using UnityEngine;

public class MethodIndexExperiment : IExperiment
{
    ExperimentContext ctx;
    bool pinged;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }
    public void OnServerReady() { }
    public void OnPlayerConnected(NetworkPlayer player) { }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected, sending ready ping");
        ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, -1);
        pinged = true;
        ctx.Log("Ping sent, waiting for server test RPCs...");
    }

    public void Tick() { }
    public void Shutdown() { }
}
