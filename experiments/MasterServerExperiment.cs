using UnityEngine;

public class MasterServerExperiment : IExperiment
{
    ExperimentContext ctx;
    int phase;
    float lastAction;
    bool registered;
    bool hostListReceived;

    int masterPort = 23466;

    public void Setup(ExperimentContext ctx)
    {
        this.ctx = ctx;
        if (ctx.Args.Length > 0)
            int.TryParse(ctx.Args[0], out masterPort);
    }

    public void OnServerReady()
    {
        ctx.Log("Server ready, registering with master server on port " + masterPort + "...");
        MasterServer.ipAddress = "127.0.0.1";
        MasterServer.port = masterPort;
        MasterServer.dedicatedServer = true;
        MasterServer.RegisterHost("TestGame", "MyTestServer", "test_comment");
        ctx.Log("RegisterHost called");
    }

    public void OnPlayerConnected(NetworkPlayer player) { }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected, querying master server on port " + masterPort + "...");
        MasterServer.ipAddress = "127.0.0.1";
        MasterServer.port = masterPort;
        MasterServer.RequestHostList("TestGame");
        ctx.Log("RequestHostList called");
    }

    public void Tick()
    {
        if (ctx.Role == ExperimentRole.Server)
            ServerTick();
        else
            ClientTick();
    }

    void ServerTick()
    {
        if (phase == 0)
        {
            // Wait for registration
            if (Time.realtimeSinceStartup > 15.0f)
            {
                ctx.Log("Timeout waiting for registration");
                phase = 99;
            }
        }
        else if (phase == 1)
        {
            // Registered, wait a bit then done
            if (Time.realtimeSinceStartup - lastAction > 10.0f)
            {
                ctx.Log("EXPERIMENT_DONE");
                phase = 99;
            }
        }
    }

    void ClientTick()
    {
        if (phase == 0 && Time.realtimeSinceStartup > 5.0f)
        {
            // Request host list
            MasterServer.ipAddress = "127.0.0.1";
            MasterServer.port = 23466;
            MasterServer.RequestHostList("TestGame");
            ctx.Log("RequestHostList called");
            lastAction = Time.realtimeSinceStartup;
            phase = 1;
        }
        else if (phase == 1)
        {
            var hosts = MasterServer.PollHostList();
            if (hosts != null && hosts.Length > 0)
            {
                ctx.Log("Got host list: " + hosts.Length + " hosts");
                foreach (var h in hosts)
                {
                    ctx.Log("  Host: " + h.gameName + " ip=" + string.Join(",", h.ip) +
                            " port=" + h.port + " players=" + h.connectedPlayers +
                            "/" + h.playerLimit + " comment=" + h.comment +
                            " guid=" + h.guid + " nat=" + h.useNat +
                            " pw=" + h.passwordProtected);
                }
                hostListReceived = true;
                ctx.Log("EXPERIMENT_DONE");
                phase = 99;
            }
            else if (Time.realtimeSinceStartup - lastAction > 10.0f)
            {
                ctx.Log("Timeout waiting for host list");
                phase = 99;
            }
        }
    }

    public void Shutdown() { }
}
