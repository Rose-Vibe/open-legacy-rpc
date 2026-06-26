using UnityEngine;

public class ViewIDAllocExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }

    public void OnServerReady()
    {
        ctx.Log("Server ready");
    }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
    }

    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (sendPhase > 4) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            switch (sendPhase)
            {
                case 0:
                    ctx.Log("Phase 0: Allocating first ViewID");
                    NetworkViewID id1 = Network.AllocateViewID();
                    ctx.Log("Allocated ViewID 1: " + id1);
                    break;
                case 1:
                    ctx.Log("Phase 1: Allocating second ViewID");
                    NetworkViewID id2 = Network.AllocateViewID();
                    ctx.Log("Allocated ViewID 2: " + id2);
                    break;
                case 2:
                    ctx.Log("Phase 2: Allocating third ViewID");
                    NetworkViewID id3 = Network.AllocateViewID();
                    ctx.Log("Allocated ViewID 3: " + id3);
                    break;
                case 3:
                    ctx.Log("Phase 3: Sending RPC with allocated value as param");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 42);
                    break;
                case 4:
                    ctx.Log("Phase 4: Sending second RPC");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 99);
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            sendPhase++;

            if (sendPhase > 4)
                ctx.Log("EXPERIMENT_DONE");
        }
    }

    public void Shutdown() { }
}
