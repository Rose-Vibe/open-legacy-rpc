using UnityEngine;

/// Tests whether Unity learns method_index from first-use/subsequent-use
/// pairs, or requires locally-correct indices.
///
/// Runs as Unity CLIENT connecting to wrong-index-server.py.
/// The Python server sends RPCs with wrong indices.
/// The Loader's [RPC] methods already log all received RPCs, so we
/// just wait and let the logs tell the story.
public class WrongIndexExperiment : IExperiment
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

        // Send a ping so the server knows we're ready
        ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, -1);
        ctx.Log("Sent ping to server");
    }

    public void Tick()
    {
        if (!connected) return;
        tickCount++;

        if (tickCount == 600)
        {
            ctx.Log("EXPERIMENT_DONE");
        }
    }

    public void Shutdown() { }
}
