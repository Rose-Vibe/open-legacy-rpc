using UnityEngine;

public class RpcVector3Experiment : IExperiment
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
        ctx.Log("Client connected, will send RPC_Vector3 with varying values");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (sendPhase > 2) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            Vector3[] values = {
                Vector3.zero,
                new Vector3(1.0f, 2.0f, 3.0f),
                new Vector3(-100.5f, 0.001f, 999.999f)
            };
            if (sendPhase < values.Length)
            {
                ctx.Log("Sending RPC_Vector3(" + values[sendPhase] + ")");
                ctx.PrimaryNetworkView.RPC("RPC_Vector3", RPCMode.Server, values[sendPhase]);
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
