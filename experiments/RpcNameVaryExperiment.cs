using UnityEngine;

public class RpcNameVaryExperiment : IExperiment
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
        ctx.Log("Client connected, will send RPCs with different names but same signature");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (sendPhase > 3) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            string[] names = { "RPC_Int", "RPC_Alpha", "RPC_Beta", "RPC_Gamma" };
            if (sendPhase < names.Length)
            {
                ctx.Log("Sending " + names[sendPhase] + "(99)");
                ctx.PrimaryNetworkView.RPC(names[sendPhase], RPCMode.Server, 99);
                lastSend = Time.realtimeSinceStartup;
                sendPhase++;
            }

            if (sendPhase >= names.Length)
                ctx.Log("EXPERIMENT_DONE");
        }
    }

    public void Shutdown() { }
}
