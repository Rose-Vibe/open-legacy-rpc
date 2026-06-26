using UnityEngine;

public class NetworkGroupFilterExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }

    public void OnServerReady()
    {
        ctx.Log("Server ready");
    }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
    }

    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (sendPhase > 6) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            switch (sendPhase)
            {
                case 0:
                    ctx.Log("Phase 0: Sending RPC_Int(10) on group 0");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 10);
                    break;
                case 1:
                    ctx.Log("Phase 1: Disabling receiving for group 1");
                    Network.SetReceivingEnabled(Network.player, 1, false);
                    ctx.Log("Phase 1: Sending RPC_Int(11) on group 0");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 11);
                    break;
                case 2:
                    ctx.Log("Phase 2: Disabling sending for group 2");
                    Network.SetSendingEnabled(2, false);
                    ctx.Log("Phase 2: Sending RPC_Int(12) on group 0");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 12);
                    break;
                case 3:
                    ctx.Log("Phase 3: Setting view to group 2 (sending disabled)");
                    ctx.PrimaryNetworkView.group = 2;
                    ctx.Log("Phase 3: Sending RPC_Int(13) on group 2 (should be blocked)");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 13);
                    break;
                case 4:
                    ctx.Log("Phase 4: Re-enabling sending for group 2");
                    Network.SetSendingEnabled(2, true);
                    ctx.Log("Phase 4: Sending RPC_Int(14) on group 2 (should go through)");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 14);
                    break;
                case 5:
                    ctx.Log("Phase 5: Setting view back to group 0");
                    ctx.PrimaryNetworkView.group = 0;
                    ctx.Log("Phase 5: Sending RPC_Int(15) on group 0");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 15);
                    break;
                case 6:
                    ctx.Log("Phase 6: Enabling receiving for group 1");
                    Network.SetReceivingEnabled(Network.player, 1, true);
                    ctx.Log("Phase 6: Sending RPC_Int(16) on group 0");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 16);
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            sendPhase++;

            if (sendPhase > 6)
                ctx.Log("EXPERIMENT_DONE");
        }
    }

    public void Shutdown() { }
}
