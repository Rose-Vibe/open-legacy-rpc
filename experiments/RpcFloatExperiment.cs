using UnityEngine;

public class RpcFloatExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }
    public void OnServerReady() { ctx.Log("Server ready"); }
    public void OnPlayerConnected(NetworkPlayer player) { ctx.Log("Player connected"); }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected, will send RPC_Float with varying values");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (sendPhase > 4) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            float[] values = { 0.0f, 1.0f, 3.14159f, -1.0f, float.MaxValue };
            if (sendPhase < values.Length)
            {
                ctx.Log("Sending RPC_Float(" + values[sendPhase] + ")");
                ctx.PrimaryNetworkView.RPC("RPC_Float", RPCMode.Server, values[sendPhase]);
                lastSend = Time.realtimeSinceStartup;
                sendPhase++;
            }

            if (sendPhase >= values.Length)
            {
                ctx.Log("EXPERIMENT_DONE");
            }
        }
    }

    public void Shutdown() { }
}
