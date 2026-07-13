using UnityEngine;

/// Repro harness for the method_tag collision investigation
/// (docs/plans/method-tag-collision-repro.md).
///
/// Runs as Unity CLIENT connecting to tag-collision-server.py or
/// tag-collision-fixed-server.py. All scenario logic (which methods,
/// what values, what order, real API vs. hand-crafted packets) lives
/// in the Python driver — this class only establishes the connection
/// and waits. Loader's built-in [RPC] methods already log every
/// receipt, so the client log is the record of what actually dispatched.
public class TagCollisionExperiment : IExperiment
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

        // RPC_Gamma (tag 4) is the client-to-server ready ping every
        // scenario sends first. It's an outbound send, so it doesn't touch
        // the client's own receive-side dispatch cache -- S7 tests that
        // assumption directly rather than just asserting it here.
        ctx.PrimaryNetworkView.RPC("RPC_Gamma", RPCMode.Server, -1);
        ctx.Log("Sent ready ping");
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
