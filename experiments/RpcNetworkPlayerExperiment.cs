using UnityEngine;

public class RpcNetworkPlayerExperiment : IExperiment
{
    ExperimentContext ctx;
    int phase;
    float lastSend;
    bool clientConnected;
    NetworkPlayer connectedPlayer;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }
    public void OnServerReady() { ctx.Log("Server ready"); }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
        connectedPlayer = player;
        clientConnected = true;
    }

    public void OnPlayerDisconnected(NetworkPlayer player) { }
    public void OnClientConnected() { ctx.Log("Client connected"); }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Server) return;
        if (!clientConnected) return;
        if (phase > 6) return;

        if (phase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            switch (phase)
            {
                case 0:
                    ctx.Log("Sending RPC_NetworkViewID(PrimaryViewID = " + ctx.PrimaryNetworkView.viewID + ")");
                    ctx.PrimaryNetworkView.RPC("RPC_NetworkViewID", RPCMode.All,
                        ctx.PrimaryNetworkView.viewID);
                    break;
                case 1:
                    var id1 = Network.AllocateViewID();
                    ctx.Log("Sending RPC_NetworkViewID(AllocatedID = " + id1 + ")");
                    ctx.PrimaryNetworkView.RPC("RPC_NetworkViewID", RPCMode.All, id1);
                    break;
                case 2:
                    var id2 = Network.AllocateViewID();
                    ctx.Log("Sending RPC_NetworkViewID(AllocatedID = " + id2 + ")");
                    ctx.PrimaryNetworkView.RPC("RPC_NetworkViewID", RPCMode.All, id2);
                    break;
                case 3:
                    var id3 = Network.AllocateViewID();
                    ctx.Log("Sending RPC_NetworkViewID(AllocatedID = " + id3 + ")");
                    ctx.PrimaryNetworkView.RPC("RPC_NetworkViewID", RPCMode.All, id3);
                    break;
                case 4:
                    ctx.Log("Sending RPC_NetworkPlayer(server = " + Network.player + ")");
                    ctx.PrimaryNetworkView.RPC("RPC_NetworkPlayer", RPCMode.All, Network.player);
                    break;
                case 5:
                    ctx.Log("Sending RPC_NetworkPlayer(client = " + connectedPlayer + ")");
                    ctx.PrimaryNetworkView.RPC("RPC_NetworkPlayer", RPCMode.All, connectedPlayer);
                    break;
                case 6:
                    ctx.Log("EXPERIMENT_DONE");
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            phase++;
        }
    }

    public void Shutdown() { }
}
