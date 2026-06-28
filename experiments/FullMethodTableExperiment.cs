using UnityEngine;
using System;
using System.Reflection;

public class FullMethodTableExperiment : IExperiment
{
    ExperimentContext ctx;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }

    public void OnServerReady()
    {
        ctx.Log("=== FULL METHOD TABLE DUMP ===");

        DumpType(typeof(Loader), "Loader");
        DumpType(typeof(SecondRpcBehaviour), "SecondRpcBehaviour");
        DumpType(typeof(InheritedRpcBase), "InheritedRpcBase");
        DumpType(typeof(InheritedRpcDerived), "InheritedRpcDerived");

        ctx.Log("EXPERIMENT_DONE");
    }

    void DumpType(Type type, string label)
    {
        ctx.Log("--- " + label + " (base=" + type.BaseType.Name + ") ---");

        var methods = type.GetMethods(
            BindingFlags.Instance | BindingFlags.Static |
            BindingFlags.Public | BindingFlags.NonPublic);

        ctx.Log("Total methods (with inherited): " + methods.Length);

        int idx = 0;
        foreach (var m in methods)
        {
            int token = m.MetadataToken;
            int rid = token & 0x00FFFFFF;
            string declaring = m.DeclaringType.Name;
            string flags = "";
            if (m.IsVirtual) flags += "V";
            if (m.IsAbstract) flags += "A";
            if (m.IsSpecialName) flags += "S";

            bool hasRpc = false;
            foreach (var attr in m.GetCustomAttributes(false))
            {
                if (attr.GetType().Name == "RPC")
                {
                    hasRpc = true;
                    break;
                }
            }
            if (hasRpc) flags += "[RPC]";

            ctx.Log("  [" + idx + "] " + declaring + "::" + m.Name +
                    " RID=" + rid + " " + flags);
            idx++;
        }
    }

    public void OnClientConnected() { }
    public void OnPlayerConnected(NetworkPlayer player) { }
    public void OnPlayerDisconnected(NetworkPlayer player) { }
    public void Tick() { }
    public void Shutdown() { }
}
