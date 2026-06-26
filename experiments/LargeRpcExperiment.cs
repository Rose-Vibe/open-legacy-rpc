using UnityEngine;

public class LargeRpcExperiment : IExperiment
{
    ExperimentContext ctx;
    int phase;
    float lastSend;
    bool clientConnected;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }
    public void OnServerReady() { ctx.Log("Server ready"); }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
        clientConnected = true;
    }

    public void OnPlayerDisconnected(NetworkPlayer player) { }
    public void OnClientConnected()
    {
        ctx.Log("Client connected");
        clientConnected = true;
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Server) return;
        if (!clientConnected) return;
        if (phase > 7) return;

        if (phase == 0 || Time.realtimeSinceStartup - lastSend > 2.0f)
        {
            int[] sizes = { 100, 500, 1000, 2000, 5000, 10000 };
            if (phase < sizes.Length)
            {
                int size = sizes[phase];
                byte[] data = new byte[size];
                // Fill with a recognizable pattern
                for (int i = 0; i < size; i++)
                    data[i] = (byte)((i + phase) & 0xFF);
                ctx.Log("Phase " + phase + ": Sending RPC_Bytes(" + size + " bytes)");
                ctx.PrimaryNetworkView.RPC("RPC_Bytes", RPCMode.Others, data);
            }
            else if (phase == sizes.Length)
            {
                ctx.Log("EXPERIMENT_DONE");
            }
            lastSend = Time.realtimeSinceStartup;
            phase++;
        }
    }

    public void Shutdown() { }
}
