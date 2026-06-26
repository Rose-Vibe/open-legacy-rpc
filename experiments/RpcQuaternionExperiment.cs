using UnityEngine;

public class RpcQuaternionExperiment : IExperiment
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
        ctx.Log("Client connected, will send RPC_Quaternion");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (sendPhase > 1) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            Quaternion[] values = {
                Quaternion.identity,
                Quaternion.Euler(45.0f, 90.0f, 180.0f)
            };
            if (sendPhase < values.Length)
            {
                ctx.Log("Sending RPC_Quaternion(" + values[sendPhase] + ")");
                ctx.PrimaryNetworkView.RPC("RPC_Quaternion", RPCMode.Server, values[sendPhase]);
                lastSend = Time.realtimeSinceStartup;
                sendPhase++;
            }

            if (sendPhase >= values.Length)
                ctx.Log("EXPERIMENT_DONE");
        }
    }

    public void Shutdown() { }
}
