using UnityEngine;
using System;

public class ClientInteropExperiment : IExperiment
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

    public void OnServerReady() { }

    public void OnPlayerConnected(NetworkPlayer player) { }

    public void OnPlayerDisconnected(NetworkPlayer player)
    {
        ctx.Log("Disconnected from server");
        connected = false;
    }

    public void OnClientConnected()
    {
        ctx.Log("Connected to server");
        connected = true;

        ctx.Log("Sending RPC_Int(42) to server...");
        ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 42);
    }

    public void Tick()
    {
        if (!connected) return;
        tickCount++;

        if (tickCount == 50)
        {
            ctx.Log("Sending RPC_Int(999) to server...");
            ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 999);
        }
        else if (tickCount == 300)
        {
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
