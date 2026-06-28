using UnityEngine;

/// Tests whether the 16-bit "zeros" field (bits 88-103) in RPCs carries
/// Network.time as a timestamp. Unity client connects to a Python server
/// that sends RPCs with varying values in that field. Loader.RPC_Int now
/// logs info.timestamp and Network.time for each received RPC.
public class TimestampFieldExperiment : IExperiment
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
        ctx.Log("Network.time at connect: " + Network.time);
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
