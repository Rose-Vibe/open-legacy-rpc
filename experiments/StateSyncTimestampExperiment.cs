using System;
using UnityEngine;

/// Tests whether state sync (OnSerializeNetworkView) uses a u64 timestamp
/// in bytes 1-8, like RPCs do. Run with server up >65s before client
/// connects — if bytes 1-6 overflow past zero, it's a u64 timestamp.
///
/// Server sends state sync with incrementing values. Client logs received
/// values with clock info so we can correlate against pcap bytes.
public class StateSyncTimestampExperiment : IExperiment
{
    ExperimentContext ctx;
    int tickCount;
    bool connected;
    int syncValue = 0;
    int receivedCount;

    const int CLOCK_LOG_INTERVAL = 100;
    const int CLIENT_DONE_COUNT = 30;

    public void Setup(ExperimentContext ctx)
    {
        this.ctx = ctx;
        ctx.SerializeCallback = OnSerialize;
        ctx.EnableStateSynchronization(NetworkStateSynchronization.Unreliable);
        ctx.Log("State sync enabled: " + ctx.PrimaryNetworkView.stateSynchronization);
        ctx.Log("Observed: " + ctx.PrimaryNetworkView.observed);
        ctx.Log("ViewID: " + ctx.PrimaryNetworkView.viewID);
        ctx.Log("=== CLOCK BASELINE ===");
        LogClocks("BASELINE");
        ctx.Log("=== END BASELINE ===");
    }

    void LogClocks(string label)
    {
        ctx.Log("CLOCKS [" + label + "]" +
                " realtimeSinceStartup=" + Time.realtimeSinceStartup +
                " TickCount=" + Environment.TickCount +
                " Network.time=" + Network.time);
    }

    public void OnServerReady()
    {
        ctx.EnableStateSynchronization(NetworkStateSynchronization.Unreliable);
        ctx.Log("Server ready, stateSynchronization=" + ctx.PrimaryNetworkView.stateSynchronization);
        LogClocks("SERVER_READY");
    }

    public void OnClientConnected()
    {
        connected = true;
        ctx.EnableStateSynchronization(NetworkStateSynchronization.Unreliable);
        ctx.Log("Connected to server, stateSynchronization=" + ctx.PrimaryNetworkView.stateSynchronization);
        LogClocks("CLIENT_CONNECTED");
    }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected");
        LogClocks("PLAYER_CONNECTED");
        connected = true;
    }

    public void OnPlayerDisconnected(NetworkPlayer player)
    {
        ctx.Log("Player disconnected");
    }

    public void Tick()
    {
        tickCount++;

        if (tickCount % CLOCK_LOG_INTERVAL == 0)
            LogClocks("TICK_" + tickCount);

        if (ctx.Role == ExperimentRole.Server && connected)
        {
            syncValue = tickCount;
        }

        if (ctx.Role == ExperimentRole.Client)
        {
            if (receivedCount >= CLIENT_DONE_COUNT || tickCount >= 3000)
            {
                ctx.Log("received=" + receivedCount + " ticks=" + tickCount);
                ctx.Log("EXPERIMENT_DONE");
            }
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
            receivedCount++;
            ctx.Log("RECV syncValue=" + val +
                    " info.timestamp=" + info.timestamp +
                    " Network.time=" + Network.time +
                    " realtimeSinceStartup=" + Time.realtimeSinceStartup +
                    " count=" + receivedCount);
        }
    }

    public void Shutdown()
    {
        ctx.Log("Shutdown");
    }
}
