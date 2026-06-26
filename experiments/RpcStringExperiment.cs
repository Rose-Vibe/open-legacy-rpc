using UnityEngine;

public class RpcStringExperiment : IExperiment
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
        ctx.Log("Client connected, will send RPC_String with varying values");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (sendPhase > 4) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            string[] values = { "throwaway", "", "A", "Hello", "Hello World! This is a longer string for testing." };
            if (sendPhase < values.Length)
            {
                ctx.Log("Sending RPC_String(\"" + values[sendPhase] + "\")");
                ctx.PrimaryNetworkView.RPC("RPC_String", RPCMode.Server, values[sendPhase]);
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
