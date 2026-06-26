using UnityEngine;

public class RpcMultiParamExperiment : IExperiment
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
        ctx.Log("Client connected, will send RPC_IntFloatString");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (sendPhase > 2) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            if (sendPhase == 0)
            {
                ctx.Log("Sending RPC_IntFloatString(0, 0.0, \"\") [pre-connect throwaway]");
                ctx.PrimaryNetworkView.RPC("RPC_IntFloatString", RPCMode.Server, 0, 0.0f, "");
            }
            else if (sendPhase == 1)
            {
                ctx.Log("Sending RPC_IntFloatString(42, 3.14, \"hello\")");
                ctx.PrimaryNetworkView.RPC("RPC_IntFloatString", RPCMode.Server, 42, 3.14f, "hello");
            }
            else
            {
                ctx.Log("Sending RPC_IntFloatString(99, 2.718, \"world\")");
                ctx.PrimaryNetworkView.RPC("RPC_IntFloatString", RPCMode.Server, 99, 2.718f, "world");
            }
            lastSend = Time.realtimeSinceStartup;
            sendPhase++;

            if (sendPhase > 2)
                ctx.Log("EXPERIMENT_DONE");
        }
    }

    public void Shutdown() { }
}
