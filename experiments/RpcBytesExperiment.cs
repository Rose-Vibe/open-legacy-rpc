using UnityEngine;

public class RpcBytesExperiment : IExperiment
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
        ctx.Log("Client connected, will send RPC_Bytes");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (sendPhase > 2) return;

        if (sendPhase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            byte[][] values = {
                new byte[0],
                new byte[] { 0xDE, 0xAD, 0xBE, 0xEF },
                new byte[] { 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07,
                             0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F }
            };
            if (sendPhase < values.Length)
            {
                ctx.Log("Sending RPC_Bytes(" + values[sendPhase].Length + " bytes)");
                ctx.PrimaryNetworkView.RPC("RPC_Bytes", RPCMode.Server, values[sendPhase]);
                lastSend = Time.realtimeSinceStartup;
                sendPhase++;
            }

            if (sendPhase >= values.Length)
                ctx.Log("EXPERIMENT_DONE");
        }
    }

    public void Shutdown() { }
}
