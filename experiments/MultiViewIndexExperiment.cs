using UnityEngine;

public class MultiViewIndexExperiment : IExperiment
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
        if (sendPhase > 12) return;

        if (Time.realtimeSinceStartup - lastSend > 1.0f)
        {
            switch (sendPhase)
            {
                // Loader RPCs (primary NetworkView)
                case 0:
                    ctx.Log("Phase 0: RPC_Void via primary — 1st");
                    ctx.PrimaryNetworkView.RPC("RPC_Void", RPCMode.Server);
                    break;
                case 1:
                    ctx.Log("Phase 1: RPC_Void via primary — 2nd");
                    ctx.PrimaryNetworkView.RPC("RPC_Void", RPCMode.Server);
                    break;
                case 2:
                    ctx.Log("Phase 2: RPC_Int(100) via primary — 1st");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 100);
                    break;
                case 3:
                    ctx.Log("Phase 3: RPC_Int(101) via primary — 2nd");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 101);
                    break;
                // SecondRpcBehaviour (separate NetworkView on different GO)
                case 4:
                    ctx.Log("Phase 4: ReceiveSerializeEvent(99) via SecondRpc — 1st");
                    ctx.SecondRpcNetworkView.RPC("ReceiveSerializeEvent", RPCMode.Server, 99);
                    break;
                case 5:
                    ctx.Log("Phase 5: ReceiveSerializeEvent(98) via SecondRpc — 2nd");
                    ctx.SecondRpcNetworkView.RPC("ReceiveSerializeEvent", RPCMode.Server, 98);
                    break;
                // InheritedRpcBase (separate NetworkView on different GO)
                case 6:
                    ctx.Log("Phase 6: BaseRpc(200) via InheritedRpc — 1st");
                    ctx.InheritedRpcNetworkView.RPC("BaseRpc", RPCMode.Server, 200);
                    break;
                case 7:
                    ctx.Log("Phase 7: BaseRpc(201) via InheritedRpc — 2nd");
                    ctx.InheritedRpcNetworkView.RPC("BaseRpc", RPCMode.Server, 201);
                    break;
                case 8:
                    ctx.Log("Phase 8: DerivedRpc(300) via InheritedRpc — 1st");
                    ctx.InheritedRpcNetworkView.RPC("DerivedRpc", RPCMode.Server, 300);
                    break;
                case 9:
                    ctx.Log("Phase 9: DerivedRpc(301) via InheritedRpc — 2nd");
                    ctx.InheritedRpcNetworkView.RPC("DerivedRpc", RPCMode.Server, 301);
                    break;
                // Back to primary: RPC_Gamma at the end of Loader's RPCs
                case 10:
                    ctx.Log("Phase 10: RPC_Gamma(500) via primary — 1st");
                    ctx.PrimaryNetworkView.RPC("RPC_Gamma", RPCMode.Server, 500);
                    break;
                case 11:
                    ctx.Log("Phase 11: RPC_Gamma(501) via primary — 2nd");
                    ctx.PrimaryNetworkView.RPC("RPC_Gamma", RPCMode.Server, 501);
                    break;
                case 12:
                    ctx.Log("EXPERIMENT_DONE");
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            sendPhase++;
        }
    }

    public void Shutdown() { }
}
