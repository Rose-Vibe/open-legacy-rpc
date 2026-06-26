using UnityEngine;

public class PasswordExperiment : IExperiment
{
    ExperimentContext ctx;
    int phase;
    float lastSend;

    const string PASSWORD = "secret123";

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }

    public void OnServerReady()
    {
        ctx.Log("Server ready, setting password: " + PASSWORD);
        Network.incomingPassword = PASSWORD;
    }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected (password accepted): " + player);
    }

    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected successfully with password");
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (phase > 1) return;

        if (phase == 0 || Time.realtimeSinceStartup - lastSend > 0.5f)
        {
            switch (phase)
            {
                case 0:
                    ctx.Log("Sending test RPC after password auth");
                    ctx.PrimaryNetworkView.RPC("RPC_Int", RPCMode.Server, 42);
                    break;
                case 1:
                    ctx.Log("EXPERIMENT_DONE");
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            phase++;
        }
    }

    public void Shutdown() { }
}
