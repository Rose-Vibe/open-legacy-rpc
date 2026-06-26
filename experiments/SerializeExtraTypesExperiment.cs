using UnityEngine;

public class SerializeExtraTypesExperiment : IExperiment
{
    ExperimentContext ctx;
    int tick;

    NetworkPlayer testPlayer;
    NetworkViewID testViewID;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }

    public void OnServerReady()
    {
        ctx.Log("Server ready, enabling ReliableDeltaCompressed sync");
        ctx.EnableStateSynchronization(NetworkStateSynchronization.ReliableDeltaCompressed);
        ctx.SerializeCallback = Serialize;
    }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
        testPlayer = player;
        testViewID = ctx.PrimaryNetworkView.viewID;
    }

    public void OnPlayerDisconnected(NetworkPlayer player) { }
    public void OnClientConnected() { ctx.Log("Client connected"); }

    void Serialize(BitStream stream, NetworkMessageInfo info)
    {
        stream.Serialize(ref testPlayer);
        stream.Serialize(ref testViewID);
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Server) return;
        tick++;
        if (tick == 120)
        {
            ctx.Log("EXPERIMENT_DONE");
        }
    }

    public void Shutdown() { }
}
