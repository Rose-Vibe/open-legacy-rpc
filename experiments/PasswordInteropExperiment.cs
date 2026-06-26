using UnityEngine;

public class PasswordInteropExperiment : IExperiment
{
    ExperimentContext ctx;
    int phase;
    float lastSend;
    bool clientConnected;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }

    public void OnServerReady()
    {
        ctx.Log("Server ready, setting password...");
        Network.incomingPassword = "testpass";
        ctx.Log("Password set to 'testpass'");
    }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected (password accepted): " + player);
        clientConnected = true;
    }

    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected (password accepted)");
        clientConnected = true;
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Server) return;
        if (!clientConnected) return;
        if (phase > 1) return;

        if (phase == 0 || Time.realtimeSinceStartup - lastSend > 1.0f)
        {
            if (phase == 0)
            {
                ctx.Log("Sending RPC_Int(42) to verify connection works");
                ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Others, 42);
            }
            else
            {
                ctx.Log("EXPERIMENT_DONE");
            }
            lastSend = Time.realtimeSinceStartup;
            phase++;
        }
    }

    public void Shutdown() { }
}
