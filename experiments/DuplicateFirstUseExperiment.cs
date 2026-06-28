using UnityEngine;

/// Tests whether Unity drops duplicate first-use RPCs.
/// Runs as Unity CLIENT connecting to a Python server.
/// The Python server sends the same RPC method with first-use encoding
/// multiple times. We log each received RPC to see which ones arrive.
public class DuplicateFirstUseExperiment : IExperiment
{
    ExperimentContext ctx;
    int tickCount;
    bool connected;

    public void Setup(ExperimentContext ctx)
    {
        this.ctx = ctx;
    }

    public void OnServerReady() { }
    public void OnPlayerConnected(NetworkPlayer player) { }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Connected to server");
        connected = true;
        ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, -1);
        ctx.Log("Sent ready ping");
    }

    public void Tick()
    {
        if (!connected) return;
        tickCount++;
        if (tickCount == 500)
        {
            ctx.Log("EXPERIMENT_DONE");
        }
    }

    public void Shutdown() { }
}
