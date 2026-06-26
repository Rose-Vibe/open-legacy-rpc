using System;
using UnityEngine;

public enum ExperimentRole
{
    Server,
    Client
}

public delegate void SerializeHandler(BitStream stream, NetworkMessageInfo info);

public class ExperimentContext
{
    public ExperimentRole Role;
    public string[] Args;
    public NetworkView PrimaryNetworkView;
    public MonoBehaviour Host;

    public SerializeHandler SerializeCallback;

    public void Log(string message)
    {
        Debug.Log("[Experiment] " + message);
    }

    public void EnableStateSynchronization(NetworkStateSynchronization mode)
    {
        PrimaryNetworkView.stateSynchronization = mode;
    }

    public NetworkView CreateNetworkView()
    {
        var go = new GameObject("ExtraNetworkView");
        var nv = go.AddComponent<NetworkView>();
        nv.stateSynchronization = NetworkStateSynchronization.Off;
        return nv;
    }
}

public interface IExperiment
{
    void Setup(ExperimentContext ctx);
    void OnServerReady();
    void OnClientConnected();
    void OnPlayerConnected(NetworkPlayer player);
    void OnPlayerDisconnected(NetworkPlayer player);
    void Tick();
    void Shutdown();
}
