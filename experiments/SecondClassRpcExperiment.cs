using UnityEngine;

/// Tests RPC encoding from a second MonoBehaviour class (not Loader).
/// Captures will reveal: classGuid, methodHash, tag value, and constant field
/// for a class that is NOT the primary Loader class.
/// This simulates Distance's NetworkInstancedEventTransceiver scenario.
public class SecondClassRpcExperiment : IExperiment
{
    ExperimentContext ctx;
    int sendPhase;
    float lastSend;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }
    public void OnServerReady() { ctx.Log("Server ready"); }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
    }

    public void OnClientConnected()
    {
        ctx.Log("Client connected");
        if (ctx.SecondRpcNetworkView == null)
        {
            ctx.Log("ERROR: SecondRpcNetworkView not found in scene");
            return;
        }
        ctx.Log("SecondRpc NetworkView viewID=" + ctx.SecondRpcNetworkView.viewID);
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (ctx.SecondRpcNetworkView == null) return;
        if (sendPhase > 3) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            switch (sendPhase)
            {
                case 0:
                    ctx.Log("Phase 0: Sending ReceiveSerializeEvent with 4 bytes via SecondRpc NetworkView");
                    ctx.SecondRpcNetworkView.RPC("ReceiveSerializeEvent", RPCMode.Server,
                        new byte[] { 0xDE, 0xAD, 0xBE, 0xEF });
                    break;
                case 1:
                    ctx.Log("Phase 1: Sending ReceiveSerializeEvent with 16 bytes");
                    ctx.SecondRpcNetworkView.RPC("ReceiveSerializeEvent", RPCMode.Server,
                        new byte[] { 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
                                     0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F });
                    break;
                case 2:
                    ctx.Log("Phase 2: Sending ReceiveSerializeEvent with RPCMode.Others");
                    ctx.SecondRpcNetworkView.RPC("ReceiveSerializeEvent", RPCMode.Others,
                        new byte[] { 0xCA, 0xFE });
                    break;
                case 3:
                    ctx.Log("EXPERIMENT_DONE");
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            sendPhase++;
        }
    }

    public void Shutdown() { }
}
