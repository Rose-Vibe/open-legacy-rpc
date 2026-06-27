using UnityEngine;

/// Tests whether the RPC constant field affects delivery.
/// Runs as Unity CLIENT connecting to a Python server.
/// The Python server sends RPCs with various constant values.
/// Loader.RPC_Int already logs received RPCs via [RPC] attribute,
/// so we just count the log lines.
public class ConstantDeliveryExperiment : IExperiment
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

        // Send a ping RPC so the server knows we're ready
        ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, -1);
        ctx.Log("Sent ping to server");
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
