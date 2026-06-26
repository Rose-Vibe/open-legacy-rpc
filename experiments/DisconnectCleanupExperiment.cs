using UnityEngine;

public class DisconnectCleanupExperiment : IExperiment
{
    ExperimentContext ctx;
    int phase;
    float lastAction;
    bool clientConnected;
    NetworkPlayer connectedPlayer;
    bool playerDisconnected;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }

    public void OnServerReady()
    {
        ctx.Log("Server ready, waiting for client...");
    }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        connectedPlayer = player;
        clientConnected = true;
        ctx.Log("Player connected: " + player);
    }

    public void OnPlayerDisconnected(NetworkPlayer player)
    {
        playerDisconnected = true;
        ctx.Log("Player disconnected: " + player);

        // Call the cleanup APIs we want to observe on the wire
        ctx.Log("Calling Network.RemoveRPCs(player)...");
        Network.RemoveRPCs(player);
        ctx.Log("RemoveRPCs done");

        ctx.Log("Calling Network.DestroyPlayerObjects(player)...");
        Network.DestroyPlayerObjects(player);
        ctx.Log("DestroyPlayerObjects done");
    }

    public void OnClientConnected()
    {
        ctx.Log("Client connected");
        clientConnected = true;

        // Allocate some ViewIDs to make cleanup interesting
        var vid1 = Network.AllocateViewID();
        var vid2 = Network.AllocateViewID();
        ctx.Log("Allocated ViewIDs: " + vid1 + ", " + vid2);

        // Send an RPC so there are buffered RPCs to remove
        ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.AllBuffered, 42);
        ctx.Log("Sent buffered RPC_Int(42)");
    }

    public void Tick()
    {
        if (ctx.Role == ExperimentRole.Server)
            ServerTick();
        else
            ClientTick();
    }

    void ServerTick()
    {
        if (phase > 5) return;

        switch (phase)
        {
            case 0:
                if (!clientConnected) return;
                ctx.Log("Phase 0: Client connected, sending RPC...");
                ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Others, 100);
                lastAction = Time.realtimeSinceStartup;
                phase = 1;
                break;
            case 1:
                if (Time.realtimeSinceStartup - lastAction < 2.0f) return;
                ctx.Log("Phase 1: Waiting for disconnect...");
                phase = 2;
                break;
            case 2:
                if (!playerDisconnected) return;
                ctx.Log("Phase 2: Disconnect detected, cleanup done");
                lastAction = Time.realtimeSinceStartup;
                phase = 3;
                break;
            case 3:
                if (Time.realtimeSinceStartup - lastAction < 3.0f) return;
                ctx.Log("EXPERIMENT_DONE");
                phase = 6;
                break;
        }
    }

    void ClientTick()
    {
        if (!clientConnected) return;

        // Client disconnects after 3 seconds
        if (Time.realtimeSinceStartup > 5.0f && phase == 0)
        {
            ctx.Log("Client disconnecting...");
            Network.Disconnect();
            phase = 1;
        }
    }

    public void Shutdown() { }
}
