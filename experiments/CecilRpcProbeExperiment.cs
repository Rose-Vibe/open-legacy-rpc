using UnityEngine;

public class CecilRpcProbeExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;
    bool connected;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }
    public void OnServerReady() { ctx.Log("Server ready"); }
    public void OnPlayerConnected(NetworkPlayer player) { ctx.Log("Player connected: " + player); }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected");
        connected = true;
        lastSend = Time.realtimeSinceStartup;
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (!connected) return;
        if (sendPhase > 20) return;

        if (Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            switch (sendPhase)
            {
                case 0:
                    ctx.Log("Phase 0: RPC_Void — 1st (baseline)");
                    ctx.PrimaryNetworkView.RPC("RPC_Void", RPCMode.Server);
                    break;
                case 1:
                    ctx.Log("Phase 1: RPC_Void — 2nd (subsequent)");
                    ctx.PrimaryNetworkView.RPC("RPC_Void", RPCMode.Server);
                    break;
                case 2:
                    ctx.Log("Phase 2: Awake — 1st");
                    ctx.PrimaryNetworkView.RPC("Awake", RPCMode.Server);
                    break;
                case 3:
                    ctx.Log("Phase 3: Awake — 2nd");
                    ctx.PrimaryNetworkView.RPC("Awake", RPCMode.Server);
                    break;
                case 4:
                    ctx.Log("Phase 4: Start — 1st");
                    ctx.PrimaryNetworkView.RPC("Start", RPCMode.Server);
                    break;
                case 5:
                    ctx.Log("Phase 5: Start — 2nd");
                    ctx.PrimaryNetworkView.RPC("Start", RPCMode.Server);
                    break;
                case 6:
                    ctx.Log("Phase 6: Update — 1st");
                    ctx.PrimaryNetworkView.RPC("Update", RPCMode.Server);
                    break;
                case 7:
                    ctx.Log("Phase 7: Update — 2nd");
                    ctx.PrimaryNetworkView.RPC("Update", RPCMode.Server);
                    break;
                case 8:
                    ctx.Log("Phase 8: OnSerializeNetworkView — 1st");
                    ctx.PrimaryNetworkView.RPC("OnSerializeNetworkView", RPCMode.Server);
                    break;
                case 9:
                    ctx.Log("Phase 9: OnSerializeNetworkView — 2nd");
                    ctx.PrimaryNetworkView.RPC("OnSerializeNetworkView", RPCMode.Server);
                    break;
                case 10:
                    ctx.Log("Phase 10: ParseArgs — 1st");
                    ctx.PrimaryNetworkView.RPC("ParseArgs", RPCMode.Server);
                    break;
                case 11:
                    ctx.Log("Phase 11: ParseArgs — 2nd");
                    ctx.PrimaryNetworkView.RPC("ParseArgs", RPCMode.Server);
                    break;
                case 12:
                    ctx.Log("Phase 12: RPC_Gamma — 1st");
                    ctx.PrimaryNetworkView.RPC("RPC_Gamma", RPCMode.Server, 999);
                    break;
                case 13:
                    ctx.Log("Phase 13: RPC_Gamma — 2nd");
                    ctx.PrimaryNetworkView.RPC("RPC_Gamma", RPCMode.Server, 998);
                    break;
                case 14:
                    ctx.Log("EXPERIMENT_DONE");
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            sendPhase++;
        }
    }

    public void Shutdown() { }
}
