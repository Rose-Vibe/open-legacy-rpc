using System;
using System.IO;
using System.Reflection;
using UnityEngine;

public class Loader : MonoBehaviour
{
    const int DefaultPort = 7777;
    int maxConnections = 4;

    ExperimentRole role;
    string serverAddress = "127.0.0.1";
    int port = DefaultPort;
    string password = "";
    string experimentName;
    string[] experimentArgs;
    IExperiment experiment;
    ExperimentContext context;
    bool started;

    // --- Lifecycle ---

    void Awake()
    {
        ParseArgs();

        if (experimentName == null)
        {
            Debug.Log("[Loader] No --experiment specified, running as bare shell");
        }
        else
        {
            LoadExperiment();
        }

        var secondRpc = GameObject.Find("SecondRpc");
        var inheritedRpc = GameObject.Find("InheritedRpc");

        context = new ExperimentContext
        {
            Role = role,
            Args = experimentArgs ?? new string[0],
            PrimaryNetworkView = GetComponent<NetworkView>(),
            Host = this,
            SecondRpc = secondRpc != null ? secondRpc.GetComponent<SecondRpcBehaviour>() : null,
            SecondRpcNetworkView = secondRpc != null ? secondRpc.GetComponent<NetworkView>() : null,
            InheritedRpc = inheritedRpc != null ? inheritedRpc.GetComponent<InheritedRpcDerived>() : null,
            InheritedRpcNetworkView = inheritedRpc != null ? inheritedRpc.GetComponent<NetworkView>() : null,
        };

        if (experiment != null)
            experiment.Setup(context);

        Debug.Log("[Loader] Role=" + role + " Experiment=" + (experimentName ?? "(none)") +
                  " Address=" + serverAddress + ":" + port);
    }

    void Start()
    {
        if (role == ExperimentRole.Server)
        {
            Debug.Log("[Loader] Initializing server on port " + port + " maxConnections=" + maxConnections);
            Network.InitializeServer(maxConnections, port, false);
        }
        else
        {
            Debug.Log("[Loader] Connecting to " + serverAddress + ":" + port +
                      (password.Length > 0 ? " (with password)" : ""));
            Network.Connect(serverAddress, port, password);
        }
        started = true;
    }

    void Update()
    {
        if (started && experiment != null)
            experiment.Tick();
    }

    void OnApplicationQuit()
    {
        if (experiment != null)
            experiment.Shutdown();
    }

    // --- Unity Networking Callbacks ---

    void OnServerInitialized()
    {
        Debug.Log("[Loader] *** OnServerInitialized ***");
        if (experiment != null)
            experiment.OnServerReady();
    }

    void OnConnectedToServer()
    {
        Debug.Log("[Loader] *** OnConnectedToServer ***");
        if (experiment != null)
            experiment.OnClientConnected();
    }

    void OnPlayerConnected(NetworkPlayer player)
    {
        Debug.Log("[Loader] *** OnPlayerConnected: " + player + " ***");
        if (experiment != null)
            experiment.OnPlayerConnected(player);
    }

    void OnPlayerDisconnected(NetworkPlayer player)
    {
        Debug.Log("[Loader] *** OnPlayerDisconnected: " + player + " ***");
        if (experiment != null)
            experiment.OnPlayerDisconnected(player);
    }

    void OnFailedToConnect(NetworkConnectionError error)
    {
        Debug.LogError("[Loader] *** OnFailedToConnect: " + error + " ***");
    }

    void OnDisconnectedFromServer(NetworkDisconnection info)
    {
        Debug.Log("[Loader] *** OnDisconnectedFromServer: " + info + " ***");
    }

    void OnMasterServerEvent(MasterServerEvent msEvent)
    {
        Debug.Log("[Loader] *** OnMasterServerEvent: " + msEvent + " ***");
    }

    // --- OnSerializeNetworkView delegation ---

    void OnSerializeNetworkView(BitStream stream, NetworkMessageInfo info)
    {
        if (context != null && context.SerializeCallback != null)
            context.SerializeCallback(stream, info);
    }

    // --- Pre-declared RPC methods (Option B) ---
    // Each exercises a different serialization path on the wire.
    // Experiments call these via networkView.RPC("RPC_Xxx", target, args).

    public Action<NetworkMessageInfo> OnRPC_Void;
    public Action<int, NetworkMessageInfo> OnRPC_Int;
    public Action<float, NetworkMessageInfo> OnRPC_Float;
    public Action<string, NetworkMessageInfo> OnRPC_String;
    public Action<Vector3, NetworkMessageInfo> OnRPC_Vector3;
    public Action<Quaternion, NetworkMessageInfo> OnRPC_Quaternion;
    public Action<byte[], NetworkMessageInfo> OnRPC_Bytes;
    public Action<int, float, string, NetworkMessageInfo> OnRPC_IntFloatString;
    public Action<NetworkPlayer, NetworkMessageInfo> OnRPC_NetworkPlayer;
    public Action<NetworkViewID, NetworkMessageInfo> OnRPC_NetworkViewID;

    // Alternate-name RPCs for name-hash experiments (same signatures as above)
    public Action<int, NetworkMessageInfo> OnRPC_Alpha;
    public Action<int, NetworkMessageInfo> OnRPC_Beta;
    public Action<int, NetworkMessageInfo> OnRPC_Gamma;

    [RPC]
    void RPC_Void(NetworkMessageInfo info)
    {
        Debug.Log("[RPC] RPC_Void from " + info.sender);
        if (OnRPC_Void != null) OnRPC_Void(info);
    }

    [RPC]
    void RPC_Int(int a, NetworkMessageInfo info)
    {
        Debug.Log("[RPC] RPC_Int(" + a + ") from " + info.sender +
                  " timestamp=" + info.timestamp + " Network.time=" + Network.time);
        if (OnRPC_Int != null) OnRPC_Int(a, info);
    }

    [RPC]
    void RPC_Float(float a, NetworkMessageInfo info)
    {
        Debug.Log("[RPC] RPC_Float(" + a + ") from " + info.sender);
        if (OnRPC_Float != null) OnRPC_Float(a, info);
    }

    [RPC]
    void RPC_String(string s, NetworkMessageInfo info)
    {
        Debug.Log("[RPC] RPC_String(\"" + s + "\") from " + info.sender);
        if (OnRPC_String != null) OnRPC_String(s, info);
    }

    [RPC]
    void RPC_Vector3(Vector3 v, NetworkMessageInfo info)
    {
        Debug.Log("[RPC] RPC_Vector3(" + v + ") from " + info.sender);
        if (OnRPC_Vector3 != null) OnRPC_Vector3(v, info);
    }

    [RPC]
    void RPC_Quaternion(Quaternion q, NetworkMessageInfo info)
    {
        Debug.Log("[RPC] RPC_Quaternion(" + q + ") from " + info.sender);
        if (OnRPC_Quaternion != null) OnRPC_Quaternion(q, info);
    }

    [RPC]
    void RPC_Bytes(byte[] data, NetworkMessageInfo info)
    {
        Debug.Log("[RPC] RPC_Bytes(" + data.Length + " bytes) from " + info.sender);
        if (OnRPC_Bytes != null) OnRPC_Bytes(data, info);
    }

    [RPC]
    void RPC_IntFloatString(int a, float b, string c, NetworkMessageInfo info)
    {
        Debug.Log("[RPC] RPC_IntFloatString(" + a + ", " + b + ", \"" + c + "\") from " + info.sender);
        if (OnRPC_IntFloatString != null) OnRPC_IntFloatString(a, b, c, info);
    }

    [RPC]
    void RPC_NetworkPlayer(NetworkPlayer p, NetworkMessageInfo info)
    {
        Debug.Log("[RPC] RPC_NetworkPlayer(" + p + ") from " + info.sender);
        if (OnRPC_NetworkPlayer != null) OnRPC_NetworkPlayer(p, info);
    }

    [RPC]
    void RPC_NetworkViewID(NetworkViewID id, NetworkMessageInfo info)
    {
        Debug.Log("[RPC] RPC_NetworkViewID(" + id + ") from " + info.sender);
        if (OnRPC_NetworkViewID != null) OnRPC_NetworkViewID(id, info);
    }

    [RPC]
    void RPC_Alpha(int a, NetworkMessageInfo info)
    {
        Debug.Log("[RPC] RPC_Alpha(" + a + ") from " + info.sender);
        if (OnRPC_Alpha != null) OnRPC_Alpha(a, info);
    }

    [RPC]
    void RPC_Beta(int a, NetworkMessageInfo info)
    {
        Debug.Log("[RPC] RPC_Beta(" + a + ") from " + info.sender);
        if (OnRPC_Beta != null) OnRPC_Beta(a, info);
    }

    [RPC]
    void RPC_Gamma(int a, NetworkMessageInfo info)
    {
        Debug.Log("[RPC] RPC_Gamma(" + a + ") from " + info.sender);
        if (OnRPC_Gamma != null) OnRPC_Gamma(a, info);
    }

    // --- Arg parsing ---

    void ParseArgs()
    {
        var args = Environment.GetCommandLineArgs();
        var extraArgs = new System.Collections.Generic.List<string>();
        bool pastSeparator = false;

        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == "--")
            {
                pastSeparator = true;
                continue;
            }

            if (!pastSeparator) continue;

            if (args[i] == "--server")
            {
                role = ExperimentRole.Server;
            }
            else if (args[i] == "--client")
            {
                role = ExperimentRole.Client;
            }
            else if (args[i] == "--experiment" && i + 1 < args.Length)
            {
                experimentName = args[++i];
            }
            else if (args[i] == "--address" && i + 1 < args.Length)
            {
                serverAddress = args[++i];
            }
            else if (args[i] == "--port" && i + 1 < args.Length)
            {
                port = int.Parse(args[++i]);
            }
            else if (args[i] == "--password" && i + 1 < args.Length)
            {
                password = args[++i];
            }
            else if (args[i] == "--max-connections" && i + 1 < args.Length)
            {
                maxConnections = int.Parse(args[++i]);
            }
            else
            {
                extraArgs.Add(args[i]);
            }
        }

        experimentArgs = extraArgs.ToArray();
    }

    // --- DLL loading ---

    void LoadExperiment()
    {
        var exePath = Environment.GetCommandLineArgs()[0];
        var basePath = Path.GetDirectoryName(Path.GetFullPath(exePath));
        if (string.IsNullOrEmpty(basePath))
            basePath = Directory.GetCurrentDirectory();
        var dllPath = Path.Combine(basePath, "Experiments");
        dllPath = Path.Combine(dllPath, "Experiments.dll");

        if (!File.Exists(dllPath))
        {
            Debug.LogError("[Loader] Experiment DLL not found at " + dllPath);
            return;
        }

        Debug.Log("[Loader] Loading experiment DLL from " + dllPath);
        var assembly = Assembly.LoadFrom(dllPath);
        var type = assembly.GetType(experimentName);

        if (type == null)
        {
            Debug.LogError("[Loader] Experiment class '" + experimentName + "' not found in DLL");
            return;
        }

        if (!typeof(IExperiment).IsAssignableFrom(type))
        {
            Debug.LogError("[Loader] Class '" + experimentName + "' does not implement IExperiment");
            return;
        }

        experiment = (IExperiment)Activator.CreateInstance(type);
        Debug.Log("[Loader] Loaded experiment: " + experimentName);
    }
}
