using UnityEngine;

public class ViewIDOverflowExperiment : IExperiment
{
    ExperimentContext ctx;
    bool clientConnected;
    bool allocated;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }
    public void OnServerReady() { ctx.Log("Server ready"); }
    public void OnPlayerConnected(NetworkPlayer player) { ctx.Log("Player connected: " + player); }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected");
        clientConnected = true;
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (!clientConnected || allocated) return;
        allocated = true;

        ctx.Log("Allocating ViewIDs until failure or 200 reached...");
        for (int i = 0; i < 200; i++)
        {
            try
            {
                var vid = Network.AllocateViewID();
                if (i < 5 || i % 25 == 0 || i >= 45)
                    ctx.Log("ViewID[" + i + "] = " + vid);

                if (vid.ToString().Contains("Unassigned") || vid.ToString() == "0")
                {
                    ctx.Log("Got unassigned/zero ViewID at index " + i + " — stopping");
                    break;
                }
            }
            catch (System.Exception e)
            {
                ctx.Log("Exception at index " + i + ": " + e.Message);
                break;
            }
        }
        ctx.Log("EXPERIMENT_DONE");
    }

    public void Shutdown() { }
}
