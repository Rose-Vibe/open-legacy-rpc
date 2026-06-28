using UnityEngine;
using System;
using System.Reflection;
using System.Runtime.InteropServices;

public class MethodSlotExperiment : IExperiment
{
    ExperimentContext ctx;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }

    public void OnServerReady()
    {
        ctx.Log("=== METHOD SLOT DUMP ===");
        ctx.Log("IntPtr.Size=" + IntPtr.Size);

        DumpMethodSlots(typeof(Loader), "Loader");
        DumpMethodSlots(typeof(SecondRpcBehaviour), "SecondRpcBehaviour");
        DumpMethodSlots(typeof(InheritedRpcBase), "InheritedRpcBase");
        DumpMethodSlots(typeof(InheritedRpcDerived), "InheritedRpcDerived");

        ctx.Log("EXPERIMENT_DONE");
    }

    void DumpMethodSlots(Type type, string label)
    {
        ctx.Log("--- " + label + " ---");

        var methods = type.GetMethods(
            BindingFlags.Instance | BindingFlags.Static |
            BindingFlags.Public | BindingFlags.NonPublic |
            BindingFlags.DeclaredOnly);

        foreach (var m in methods)
        {
            IntPtr handle = m.MethodHandle.Value;
            int token = m.MetadataToken;
            int rid = token & 0x00FFFFFF;

            string raw = "";
            for (int i = 0; i < 40; i++)
            {
                byte b = Marshal.ReadByte(handle, i);
                raw += b.ToString("x2");
            }

            short flagsField = Marshal.ReadInt16(handle, 0);
            int tokenField = Marshal.ReadInt32(handle, 4);
            int bits32 = Marshal.ReadInt32(handle, 32);
            short slotField = (short)(bits32 >> 16);

            string flags = "";
            bool hasRpc = false;
            foreach (var attr in m.GetCustomAttributes(false))
            {
                if (attr.GetType().Name == "RPC") { hasRpc = true; break; }
            }
            if (hasRpc) flags = " [RPC]";

            ctx.Log("  " + m.Name + " RID=" + rid +
                    " token=0x" + tokenField.ToString("x8") +
                    " slot=" + slotField +
                    " raw32=0x" + bits32.ToString("x8") +
                    flags);
        }
    }

    public void OnClientConnected() { }
    public void OnPlayerConnected(NetworkPlayer player) { }
    public void OnPlayerDisconnected(NetworkPlayer player) { }
    public void Tick() { }
    public void Shutdown() { }
}
