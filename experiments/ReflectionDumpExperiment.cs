using UnityEngine;
using System.Reflection;

public class ReflectionDumpExperiment : IExperiment
{
    ExperimentContext ctx;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }

    public void OnServerReady()
    {
        ctx.Log("=== REFLECTION DUMP ===");

        var asm = typeof(Loader).Assembly;
        ctx.Log("Assembly: " + asm.FullName);

        var allTypes = asm.GetTypes();
        ctx.Log("Total types: " + allTypes.Length);

        int globalIdx = 0;
        foreach (var type in allTypes)
        {
            var methods = type.GetMethods(
                BindingFlags.Instance | BindingFlags.Static |
                BindingFlags.Public | BindingFlags.NonPublic |
                BindingFlags.DeclaredOnly);

            if (methods.Length == 0) continue;

            ctx.Log("TYPE " + type.Name + " (base=" + (ReferenceEquals(type.BaseType, null) ? "none" : type.BaseType.Name) + ") methods=" + methods.Length);

            foreach (var m in methods)
            {
                int token = m.MetadataToken;
                int rid = token & 0x00FFFFFF;
                string flags = "";
                if (m.IsConstructor) flags += " CTOR";
                if (m.IsVirtual) flags += " VIRT";
                if (m.IsAbstract) flags += " ABS";
                if (m.IsStatic) flags += " STATIC";
                if (m.IsSpecialName) flags += " SPECIAL";

                bool hasRpc = false;
                foreach (var attr in m.GetCustomAttributes(false))
                {
                    if (attr.GetType().Name == "RPC")
                    {
                        hasRpc = true;
                        break;
                    }
                }
                if (hasRpc) flags += " [RPC]";

                ctx.Log("  [" + globalIdx + "] RID=" + rid + " " + m.Name + flags);
                globalIdx++;
            }
        }

        ctx.Log("=== TOTAL METHODS: " + globalIdx + " ===");
        ctx.Log("EXPERIMENT_DONE");
    }

    public void OnPlayerConnected(NetworkPlayer player) { }
    public void OnPlayerDisconnected(NetworkPlayer player) { }
    public void OnClientConnected() { }
    public void Tick() { }
    public void Shutdown() { }
}
