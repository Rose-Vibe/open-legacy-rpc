using UnityEngine;

public class NetworkGroupExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;
    NetworkView groupView1;
    NetworkView groupView2;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }

    public void OnServerReady()
    {
        ctx.Log("Server ready");

        ctx.PrimaryNetworkView.group = 0;

        groupView1 = ctx.CreateNetworkView();
        groupView1.group = 1;
        groupView1.viewID = new NetworkViewID();

        groupView2 = ctx.CreateNetworkView();
        groupView2.group = 2;
        groupView2.viewID = new NetworkViewID();
    }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
    }

    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected, will send RPCs on different groups");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (sendPhase > 5) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            switch (sendPhase)
            {
                case 0:
                    ctx.Log("Sending RPC_Int(100) on group 0 (default)");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 100);
                    break;
                case 1:
                    ctx.Log("Sending RPC_Int(200) on group 0 again");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 200);
                    break;
                case 2:
                    ctx.Log("Setting PrimaryNetworkView.group = 1");
                    ctx.PrimaryNetworkView.group = 1;
                    ctx.Log("Sending RPC_Int(301) on group 1");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 301);
                    break;
                case 3:
                    ctx.Log("Setting PrimaryNetworkView.group = 2");
                    ctx.PrimaryNetworkView.group = 2;
                    ctx.Log("Sending RPC_Int(402) on group 2");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 402);
                    break;
                case 4:
                    ctx.Log("Setting PrimaryNetworkView.group = 5");
                    ctx.PrimaryNetworkView.group = 5;
                    ctx.Log("Sending RPC_Int(505) on group 5");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 505);
                    break;
                case 5:
                    ctx.Log("Setting PrimaryNetworkView.group = 0");
                    ctx.PrimaryNetworkView.group = 0;
                    ctx.Log("Sending RPC_Int(600) on group 0 again");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 600);
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            sendPhase++;

            if (sendPhase > 5)
                ctx.Log("EXPERIMENT_DONE");
        }
    }

    public void Shutdown() { }
}
