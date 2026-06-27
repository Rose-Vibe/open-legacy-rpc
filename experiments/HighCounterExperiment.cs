using UnityEngine;

public class HighCounterExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendCount;
    int totalToSend = 200;
    float lastSend;
    bool done;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }
    public void OnServerReady() { ctx.Log("Server ready, waiting for client"); }
    public void OnPlayerConnected(NetworkPlayer player) { ctx.Log("Player connected"); }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected, will send " + totalToSend + " RPC_Int calls");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (done) return;

        // Send RPCs as fast as possible (one per frame)
        if (sendCount < totalToSend)
        {
            ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, sendCount);
            sendCount++;

            if (sendCount % 50 == 0)
                ctx.Log("Sent " + sendCount + "/" + totalToSend);
        }
        else if (!done)
        {
            ctx.Log("All " + totalToSend + " RPCs sent");
            ctx.Log("EXPERIMENT_DONE");
            done = true;
        }
    }

    public void Shutdown() { }
}
