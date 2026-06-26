using UnityEngine;
using System;

public class SerializeBasicExperiment : IExperiment
{
    ExperimentContext ctx;
    int tickCount;
    bool connected;
    int syncValue = 0;

    public void Setup(ExperimentContext ctx)
    {
        this.ctx = ctx;
        ctx.SerializeCallback = OnSerialize;
    }

    public void OnServerReady() { ctx.Log("Server ready"); }
    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected");
        connected = true;
    }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected");
        connected = true;
    }

    public void Tick()
    {
        if (!connected) return;
        tickCount++;

        if (ctx.Role == ExperimentRole.Server)
        {
            if (tickCount == 50)
                syncValue = 42;
            else if (tickCount == 100)
                syncValue = 99;
            else if (tickCount == 150)
                syncValue = -1;
            else if (tickCount == 200)
                ctx.Log("EXPERIMENT_DONE");
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
