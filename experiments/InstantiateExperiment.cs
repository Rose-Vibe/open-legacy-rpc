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
        if (phase > 4) return;
        if (!clientConnected && phase > 0) return;

        if (phase == 0 || Time.realtimeSinceStartup - lastSend > 1.0f)
        {
            switch (phase)
            {
                case 0:
                    ctx.Log("Phase 0: waiting for client");
                    break;
                case 1:
                    var prefab1 = Resources.Load("NetworkPrefab");
                    if (prefab1 == null)
                    {
                        ctx.Log("ERROR: NetworkPrefab not found");
                        phase = 99;
                        return;
                    }
                    ctx.Log("Phase 1: Instantiate NetworkPrefab at (1,2,3) group=0");
                    Network.Instantiate(prefab1, new Vector3(1, 2, 3),
                        Quaternion.identity, 0);
                    break;
                case 2:
                    var prefab2 = Resources.Load("NetworkPrefab2");
                    if (prefab2 == null)
                    {
                        ctx.Log("ERROR: NetworkPrefab2 not found");
                        phase = 99;
                        return;
                    }
                    ctx.Log("Phase 2: Instantiate NetworkPrefab2 at (10,20,30) group=0");
                    Network.Instantiate(prefab2, new Vector3(10, 20, 30),
                        Quaternion.Euler(45, 90, 0), 0);
                    break;
                case 3:
                    var prefab3 = Resources.Load("NetworkPrefab");
                    ctx.Log("Phase 3: Instantiate NetworkPrefab at (0,0,0) group=5");
                    Network.Instantiate(prefab3, Vector3.zero,
                        Quaternion.identity, 5);
                    break;
                case 4:
                    ctx.Log("EXPERIMENT_DONE");
                    break;
            }
            lastSend = Time.realtimeSinceStartup;
            phase++;
        }
    }

    public void Shutdown() { }
}
