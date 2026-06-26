using UnityEngine;

public class InstantiateExperiment : IExperiment
{
    ExperimentContext ctx;
    int phase;
    float lastSend;
    bool clientConnected;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }
    public void OnServerReady() { ctx.Log("Server ready"); }

    public void OnPlayerConnected(NetworkPlayer player)
    {
        ctx.Log("Player connected: " + player);
        clientConnected = true;
    }

    public void OnPlayerDisconnected(NetworkPlayer player) { }
    public void OnClientConnected() { ctx.Log("Client connected"); }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Server) return;
        if (phase > 2) return;
        if (!clientConnected && phase > 0) return;

        if (phase == 0 || Time.realtimeSinceStartup - lastSend > 1.0f)
        {
            switch (phase)
            {
                case 0:
                    ctx.Log("Phase 0: waiting for client");
                    break;
                case 1:
                    var prefab = Resources.Load("NetworkPrefab");
                    if (prefab == null)
                    {
                        ctx.Log("ERROR: NetworkPrefab not found in Resources");
                        phase = 99;
                        return;
                    }
                    ctx.Log("Phase 1: Network.Instantiate at (1,2,3)");
                    Network.Instantiate(prefab, new Vector3(1, 2, 3),
                        Quaternion.identity, 0);
                    break;
                case 2:
                    ctx.Log("EXPERIMENT_DONE");
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            phase++;
        }
    }

    public void Shutdown() { }
}
