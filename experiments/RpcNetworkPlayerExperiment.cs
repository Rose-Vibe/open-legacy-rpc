using UnityEngine;

public class RpcNetworkPlayerExperiment : IExperiment
{
    ExperimentContext ctx;
    int phase;
    float lastSend;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }
    public void OnServerReady() { ctx.Log("Server ready"); }
    public void OnPlayerConnected(NetworkPlayer player) { ctx.Log("Player connected: " + player); }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected, testing NetworkPlayer and NetworkViewID RPC params");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (phase > 3) return;

        if (phase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            switch (phase)
            {
                case 0:
                    ctx.Log("Sending RPC_NetworkPlayer(Network.player)");
                    ctx.PrimaryNetworkView.RPC("RPC_NetworkPlayer", RPCMode.Server, Network.player);
                    break;
                case 1:
                    ctx.Log("Sending RPC_NetworkViewID(viewID)");
                    ctx.PrimaryNetworkView.RPC("RPC_NetworkViewID", RPCMode.Server,
                        ctx.PrimaryNetworkView.viewID);
                    break;
                case 2:
                    ctx.Log("Sending RPC_NetworkViewID(AllocatedViewID)");
                    var newID = Network.AllocateViewID();
                    ctx.PrimaryNetworkView.RPC("RPC_NetworkViewID", RPCMode.Server, newID);
                    break;
                case 3:
                    ctx.Log("EXPERIMENT_DONE");
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            phase++;
        }
    }

    public void Shutdown() { }
}
