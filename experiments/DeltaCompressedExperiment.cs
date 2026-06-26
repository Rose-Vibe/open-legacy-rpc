using UnityEngine;

public class DeltaCompressedExperiment : IExperiment
{
    ExperimentContext ctx;
    int tickCount;
    bool connected;
    int valueA = 0;
    int valueB = 0;
    float valueC = 0f;

    public void Setup(ExperimentContext ctx)
    {
        this.ctx = ctx;
        ctx.SerializeCallback = OnSerialize;
        ctx.EnableStateSynchronization(NetworkStateSynchronization.ReliableDeltaCompressed);
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
        if (ctx.Role != ExperimentRole.Server) return;
        tickCount++;

        switch (tickCount)
        {
            case 30:
                ctx.Log("Setting valueA=42");
                valueA = 42;
                break;
            case 60:
                ctx.Log("No change (same values)");
                break;
            case 90:
                ctx.Log("Setting valueB=100");
                valueB = 100;
                break;
            case 120:
                ctx.Log("Setting valueC=3.14");
                valueC = 3.14f;
                break;
            case 150:
                ctx.Log("Setting valueA=999, valueB=0");
                valueA = 999;
                valueB = 0;
                break;
            case 180:
                ctx.Log("Setting all to 0");
                valueA = 0;
                valueB = 0;
                valueC = 0f;
                break;
            case 250:
                ctx.Log("EXPERIMENT_DONE");
                break;
        }
    }

    void OnSerialize(BitStream stream, NetworkMessageInfo info)
    {
        if (stream.isWriting)
        {
            stream.Serialize(ref valueA);
            stream.Serialize(ref valueB);
            stream.Serialize(ref valueC);
        }
        else
        {
            int a = 0, b = 0;
            float c = 0f;
            stream.Serialize(ref a);
            stream.Serialize(ref b);
            stream.Serialize(ref c);
            ctx.Log("Received a=" + a + " b=" + b + " c=" + c);
        }
    }

    public void Shutdown() { }
}
