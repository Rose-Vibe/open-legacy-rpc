using UnityEngine;

/// Tests RPCMode.Others relay behavior.
/// When client sends RPCMode.Others, the server should relay to all OTHER clients.
/// Run with 2 clients to capture the relay packet.
/// Captures will reveal: does the server preserve the original mode when relaying?
/// Also tests RPCMode.Others on the SecondRpc (ReceiveSerializeEvent) to match
/// what Distance does with instanced event relay.
public class RpcModeOthersRelayExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;
    int connectedPlayers;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }
    public void OnServerReady() { ctx.Log("Server ready, waiting for 2 clients"); }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        connectedPlayers++;
        ctx.Log("Player connected: " + player + " (total: " + connectedPlayers + ")");
    }

    public void OnClientConnected()
    {
        ctx.Log("Client connected");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (sendPhase > 4) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            switch (sendPhase)
            {
                case 0:
                    ctx.Log("Phase 0: Sending RPC_Int(42) with RPCMode.Others via Loader");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Others, 42);
                    break;
                case 1:
                    ctx.Log("Phase 1: Sending RPC_Int(99) with RPCMode.All via Loader");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.All, 99);
                    break;
                case 2:
                    if (ctx.SecondRpcNetworkView != null)
                    {
                        ctx.Log("Phase 2: Sending ReceiveSerializeEvent with RPCMode.Others via SecondRpc");
                        ctx.SecondRpcNetworkView.RPC("ReceiveSerializeEvent", RPCMode.Others,
                            new byte[] { 0xDE, 0xAD });
                    }
                    else
                    {
                        ctx.Log("Phase 2: SKIP (SecondRpcNetworkView not available)");
                    }
                    break;
                case 3:
                    if (ctx.SecondRpcNetworkView != null)
                    {
                        ctx.Log("Phase 3: Sending ReceiveSerializeEvent with RPCMode.Server via SecondRpc");
                        ctx.SecondRpcNetworkView.RPC("ReceiveSerializeEvent", RPCMode.Server,
                            new byte[] { 0xCA, 0xFE });
                    }
                    else
                    {
                        ctx.Log("Phase 3: SKIP (SecondRpcNetworkView not available)");
                    }
                    break;
                case 4:
                    ctx.Log("EXPERIMENT_DONE");
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            sendPhase++;
        }
    }

    public void Shutdown() { }
}
