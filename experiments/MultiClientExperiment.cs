using UnityEngine;
using System.Collections.Generic;

public class MultiClientExperiment : IExperiment
{
    ExperimentContext ctx;
    int phase;
    float lastSend;
    List<NetworkPlayer> connectedPlayers = new List<NetworkPlayer>();
    bool clientConnected;
    int receivedRpcCount;
    List<NetworkViewID> allocatedViewIDs = new List<NetworkViewID>();

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }
    public void OnServerReady() { ctx.Log("Server ready, waiting for clients..."); }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        connectedPlayers.Add(player);
        ctx.Log("Player connected: " + player + " (total: " + connectedPlayers.Count + ")");
    }

    public void OnPlayerDisconnected(NetworkPlayer player)
    {
        connectedPlayers.Remove(player);
        ctx.Log("Player disconnected: " + player + " (total: " + connectedPlayers.Count + ")");
    }

    public void OnClientConnected()
    {
        ctx.Log("Client connected to server");
        clientConnected = true;

        // Allocate 3 ViewIDs (matching Distance pattern)
        for (int i = 0; i < 3; i++)
        {
            var vid = Network.AllocateViewID();
            allocatedViewIDs.Add(vid);
            ctx.Log("Allocated ViewID: " + vid);
        }

        // Send our player index to server
        ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, Network.player.GetHashCode());
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
        if (phase > 10) return;

        if (phase == 0 || Time.realtimeSinceStartup - lastSend > 1.5f)
        {
            switch (phase)
            {
                case 0:
                    ctx.Log("Phase 0: waiting for 3 clients...");
                    if (connectedPlayers.Count >= 3)
                    {
                        ctx.Log("All 3 clients connected!");
                        lastSend = Time.realtimeSinceStartup;
                        phase++;
                    }
                    return;
                case 1:
                    // Send broadcast RPC to all
                    ctx.Log("Phase 1: Broadcasting RPC_Int(999) to all");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Others, 999);
                    break;
                case 2:
                    // Send targeted RPC to each client
                    for (int i = 0; i < connectedPlayers.Count; i++)
                    {
                        int val = (i + 1) * 111;
                        ctx.Log("Phase 2: Sending RPC_Int(" + val + ") to player " + connectedPlayers[i]);
                        ctx.PrimaryNetworkView.RPC("RPC_Int", connectedPlayers[i], val);
                    }
                    break;
                case 3:
                    // Send targeted string RPCs
                    for (int i = 0; i < connectedPlayers.Count; i++)
                    {
                        string msg = "hello_player_" + (i + 1);
                        ctx.Log("Phase 3: Sending RPC_String(\"" + msg + "\") to player " + connectedPlayers[i]);
                        ctx.PrimaryNetworkView.RPC("RPC_String", connectedPlayers[i], msg);
                    }
                    break;
                case 4:
                    ctx.Log("EXPERIMENT_DONE");
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            phase++;
        }
    }

    void ClientTick()
    {
        if (!clientConnected) return;
        // Client just receives - RPCs are logged by Loader
    }

    public void Shutdown() { }
}
