using UnityEngine;

/// Tests whether Unity cares about RPC counter continuity.
/// Runs as Unity CLIENT connecting to a Python server.
/// The Python server sends RPCs with gaps in the counter sequence.
public class CounterGapExperiment : IExperiment
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
