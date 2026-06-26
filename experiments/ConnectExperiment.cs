using UnityEngine;

public class ConnectExperiment : IExperiment
{
    ExperimentContext ctx;
    float readyTime;
    bool done;

    public void Setup(ExperimentContext ctx)
    {
        this.ctx = ctx;
        ctx.Log("ConnectExperiment setup, role=" + ctx.Role);
    }

    public void OnServerReady()
    {
        ctx.Log("Server ready, waiting for client connection");
        readyTime = Time.realtimeSinceStartup;
    }

    public void OnClientConnected()
    {
        ctx.Log("Client connected to server");
        readyTime = Time.realtimeSinceStartup;
    }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
        readyTime = Time.realtimeSinceStartup;
    }

    public void OnPlayerDisconnected(NetworkPlayer player)
    {
        ctx.Log("Player disconnected: " + player);
    }

    public void Tick()
    {
        if (done) return;
        if (readyTime > 0 && Time.realtimeSinceStartup - readyTime > 2.0f)
        {
            ctx.Log("EXPERIMENT_DONE");
            done = true;
        }
    }

    public void Shutdown()
    {
        ctx.Log("ConnectExperiment shutdown");
    }
}
