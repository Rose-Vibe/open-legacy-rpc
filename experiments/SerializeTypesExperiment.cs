using UnityEngine;
using System;

public class SerializeTypesExperiment : IExperiment
{
    ExperimentContext ctx;
    int tickCount;
    bool connected;

    int intVal = 42;
    float floatVal = 3.14f;
    Vector3 vecVal = new Vector3(1.0f, 2.0f, 3.0f);
    Quaternion quatVal = Quaternion.Euler(30, 60, 90);
    bool boolVal = true;
    short shortVal = 1234;
    char charVal = 'X';

    int phase = 0;

    public void Setup(ExperimentContext ctx)
    {
        this.ctx = ctx;
        ctx.SerializeCallback = OnSerialize;
        ctx.EnableStateSynchronization(NetworkStateSynchronization.Unreliable);
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
            {
                phase = 1;
                intVal = 99;
                floatVal = -1.5f;
                vecVal = new Vector3(10, 20, 30);
                quatVal = Quaternion.identity;
                boolVal = false;
                shortVal = -1;
                charVal = 'Z';
            }
            else if (tickCount == 150)
            {
                ctx.Log("EXPERIMENT_DONE");
            }
        }
    }

    void OnSerialize(BitStream stream, NetworkMessageInfo info)
    {
        if (stream.isWriting)
        {
            stream.Serialize(ref intVal);
            stream.Serialize(ref floatVal, 0.00001f);
            stream.Serialize(ref vecVal, 0.00001f);
            stream.Serialize(ref quatVal, 0.00001f);
            stream.Serialize(ref boolVal);
            stream.Serialize(ref shortVal);
            stream.Serialize(ref charVal);
        }
        else
        {
            int i = 0; float f = 0; Vector3 v = Vector3.zero;
            Quaternion q = Quaternion.identity;
            bool b = false; short sh = 0; char c = '\0';
            stream.Serialize(ref i);
            stream.Serialize(ref f, 0.00001f);
            stream.Serialize(ref v, 0.00001f);
            stream.Serialize(ref q, 0.00001f);
            stream.Serialize(ref b);
            stream.Serialize(ref sh);
            stream.Serialize(ref c);
            ctx.Log("Received: int=" + i + " float=" + f + " vec=" + v +
                     " quat=" + q + " bool=" + b + " short=" + sh + " char=" + c);
        }
    }

    public void Shutdown() { }
}
