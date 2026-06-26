using UnityEngine;

public class RpcIntExperiment : IExperiment
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
        ctx.Log("Client connected, will send RPC_Int with varying values");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (sendPhase > 4) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            int[] values = { 0, 1, 42, -1, 2147483647 };
            if (sendPhase < values.Length)
            {
                ctx.Log("Sending RPC_Int(" + values[sendPhase] + ")");
                ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, values[sendPhase]);
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
