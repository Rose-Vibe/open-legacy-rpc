using UnityEngine;
using System;

public class InteropExperiment : IExperiment
{
    ExperimentContext ctx;
    int tickCount;
    bool connected;
    NetworkPlayer connectedPlayer;
    int syncValue = 0;

    public void Setup(ExperimentContext ctx)
    {
        this.ctx = ctx;
        ctx.SerializeCallback = OnSerialize;
    }

    public void OnServerReady() { ctx.Log("Server ready, waiting for client..."); }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
        connected = true;
        connectedPlayer = player;

        ctx.Log("Sending RPC_Int(777) to client...");
        ctx.PrimaryNetworkView.RPC("RPC_Int", player, 777);
    }

    public void OnPlayerDisconnected(NetworkPlayer player)
    {
        ctx.Log("Player disconnected: " + player);
        connected = false;
    }

    public void OnClientConnected()
    {
        ctx.Log("Client connected to server");
        connected = true;
    }

    public void Tick()
    {
        if (!connected) return;
        tickCount++;

        if (ctx.Role == ExperimentRole.Server)
        {
            if (tickCount == 50) syncValue = 42;
            else if (tickCount == 100) syncValue = 99;
            else if (tickCount == 150) syncValue = -1;
            else if (tickCount == 300) ctx.Log("EXPERIMENT_DONE");
        }
    }

    void OnSerialize(BitStream stream, NetworkMessageInfo info)
    {
        if (stream.isWriting)
        {
            stream.Serialize(ref syncValue);
        }
        else
        {
            int val = 0;
            stream.Serialize(ref val);
            ctx.Log("Received syncValue=" + val);
        }
    }

    public void Shutdown() { }
}
