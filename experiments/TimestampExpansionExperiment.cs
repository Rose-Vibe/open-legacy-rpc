using System;
using UnityEngine;

/// Investigates how Unity expands the 16-bit rpcCounter field in 0x1b
/// messages into the full NetworkMessageInfo.timestamp value.
///
/// Phase 1: Server sends 5 RPCs immediately (OthersBuffered) before client connects.
/// Phase 2: After client connects (OnPlayerConnected), server sends 10 more RPCs
///          live (Others) to test real-time delivery with clock skew.
public class TimestampExpansionExperiment : IExperiment
{
    ExperimentContext ctx;
    int tickCount;
    bool connected;
    bool serverReady;
    bool clientDetected;
    int phase1Sent;
    int phase2Sent;
    int phase2StartTick;

    const int PHASE1_RPCS = 5;
    const int PHASE1_INTERVAL_TICKS = 50;
    const int PHASE2_RPCS = 10;
    const int PHASE2_INTERVAL_TICKS = 50;
    const int CLIENT_TIMEOUT_TICKS = 3000;
    const int CLOCK_LOG_INTERVAL = 100;

    public void Setup(ExperimentContext ctx)
    {
        this.ctx = ctx;
        ctx.Log("=== CLOCK BASELINE ===");
        LogClocks("BASELINE");
        ctx.Log("=== END BASELINE ===");
    }

    void LogClocks(string label)
    {
        ctx.Log("CLOCKS [" + label + "]" +
                " realtimeSinceStartup=" + Time.realtimeSinceStartup +
                " TickCount=" + Environment.TickCount +
                " UtcNow=" + DateTime.UtcNow.ToString("o") +
                " Network.time=" + Network.time);
    }

    public void OnServerReady()
    {
        serverReady = true;
        ctx.Log("Server ready, Phase 1: sending " + PHASE1_RPCS + " buffered RPCs");
        LogClocks("SERVER_READY");
    }

    public void OnClientConnected()
    {
        connected = true;
        ctx.Log("Connected to server");
        LogClocks("CLIENT_CONNECTED");
    }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
        LogClocks("PLAYER_CONNECTED");
        if (ctx.Role == ExperimentRole.Server)
        {
            clientDetected = true;
            phase2StartTick = tickCount;
            ctx.Log("Starting Phase 2: " + PHASE2_RPCS + " live RPCs");
        }
    }

    public void OnPlayerDisconnected(NetworkPlayer player)
    {
        ctx.Log("Player disconnected: " + player);
    }

    public void Tick()
    {
        tickCount++;

        if (tickCount % CLOCK_LOG_INTERVAL == 0)
        {
            LogClocks("TICK_" + tickCount);
        }

        if (ctx.Role == ExperimentRole.Server && serverReady)
        {
            if (!clientDetected && phase1Sent < PHASE1_RPCS &&
                tickCount % PHASE1_INTERVAL_TICKS == 0)
            {
                int value = phase1Sent + 1;
                ctx.Log("PHASE1_SEND #" + value + " (buffered)");
                LogClocks("P1_SEND_" + value);
                ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.OthersBuffered, value);
                phase1Sent++;
            }

            if (clientDetected && phase2Sent < PHASE2_RPCS)
            {
                int ticksSincePhase2 = tickCount - phase2StartTick;
                if (ticksSincePhase2 > 0 && ticksSincePhase2 % PHASE2_INTERVAL_TICKS == 0)
                {
                    int value = 100 + phase2Sent + 1;
                    ctx.Log("PHASE2_SEND #" + (phase2Sent + 1) + " value=" + value + " (live)");
                    LogClocks("P2_SEND_" + (phase2Sent + 1));
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Others, value);
                    phase2Sent++;
                }
            }

            if (clientDetected && phase2Sent >= PHASE2_RPCS &&
                tickCount > phase2StartTick + PHASE2_RPCS * PHASE2_INTERVAL_TICKS + 200)
            {
                ctx.Log("EXPERIMENT_DONE");
            }
        }

        if (ctx.Role == ExperimentRole.Client && connected)
        {
            if (tickCount >= CLIENT_TIMEOUT_TICKS)
            {
                ctx.Log("Client timeout");
                ctx.Log("EXPERIMENT_DONE");
            }
        }
    }

    public void Shutdown()
    {
        ctx.Log("Shutdown");
    }
}
