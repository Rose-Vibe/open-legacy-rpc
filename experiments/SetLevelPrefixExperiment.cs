using UnityEngine;

public class SetLevelPrefixExperiment : IExperiment
{
    ExperimentContext ctx;
    int phase;
    float lastSend;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }
    public void OnServerReady() { ctx.Log("Server ready"); }
    public void OnPlayerConnected(NetworkPlayer player) { ctx.Log("Player connected"); }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected, testing SetLevelPrefix");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (phase > 5) return;

        if (phase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            switch (phase)
            {
                case 0:
                    ctx.Log("Phase 0: RPC with default prefix (0)");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 100);
                    break;
                case 1:
                    ctx.Log("Phase 1: SetLevelPrefix(1)");
                    Network.SetLevelPrefix(1);
                    break;
                case 2:
                    ctx.Log("Phase 2: RPC with prefix 1");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 200);
                    break;
                case 3:
                    ctx.Log("Phase 3: SetLevelPrefix(42)");
                    Network.SetLevelPrefix(42);
                    break;
                case 4:
                    ctx.Log("Phase 4: RPC with prefix 42");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 300);
                    break;
                case 5:
                    ctx.Log("EXPERIMENT_DONE");
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            phase++;
        }
    }

    public void Shutdown() { }
}
