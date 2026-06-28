using UnityEngine;
using System;
using System.Reflection;
using System.Runtime.InteropServices;

public class MonoMethodEnumExperiment : IExperiment
{
    [DllImport("libmono")]
    static extern IntPtr mono_class_from_mono_type(IntPtr type);

    [DllImport("libmono")]
    static extern IntPtr mono_class_get_methods(IntPtr klass, ref IntPtr iter);

    [DllImport("libmono")]
    static extern IntPtr mono_method_get_name(IntPtr method);

    [DllImport("libmono")]
    static extern IntPtr mono_method_get_class(IntPtr method);

    [DllImport("libmono")]
    static extern IntPtr mono_class_get_name(IntPtr klass);

    [DllImport("libmono")]
    static extern uint mono_method_get_token(IntPtr method);

    [DllImport("libmono")]
    static extern uint mono_method_get_flags(IntPtr method, ref uint iflags);

    ExperimentContext ctx;

    public void Setup(ExperimentContext ctx) { this.ctx = ctx; }

    public void OnServerReady()
    {
        ctx.Log("=== MONO METHOD ENUM ===");

        DumpClassMethods(typeof(object), "System.Object");
        DumpClassMethods(typeof(UnityEngine.Object), "UE.Object");
        DumpClassMethods(typeof(Component), "Component");
        DumpClassMethods(typeof(Behaviour), "Behaviour");
        DumpClassMethods(typeof(MonoBehaviour), "MonoBehaviour");
        DumpClassMethods(typeof(Loader), "Loader");
        DumpClassMethods(typeof(SecondRpcBehaviour), "SecondRpcBehaviour");
        DumpClassMethods(typeof(InheritedRpcBase), "InheritedRpcBase");
        DumpClassMethods(typeof(InheritedRpcDerived), "InheritedRpcDerived");

        ctx.Log("EXPERIMENT_DONE");
    }

    void DumpClassMethods(Type type, string label)
    {
        IntPtr monoType = type.TypeHandle.Value;
        IntPtr klass = mono_class_from_mono_type(monoType);
        IntPtr iter = IntPtr.Zero;
        int idx = 0;

        ctx.Log("--- " + label + " ---");

        while (true)
        {
            IntPtr method = mono_class_get_methods(klass, ref iter);
            if (method == IntPtr.Zero) break;

            string name = Marshal.PtrToStringAnsi(mono_method_get_name(method));
            uint token = mono_method_get_token(method);
            int rid = (int)(token & 0x00FFFFFF);
            uint iflags = 0;
            uint flags = mono_method_get_flags(method, ref iflags);

            string f = "";
            if ((flags & 0x0010) != 0) f += " STATIC";
            if ((flags & 0x0800) != 0) f += " SPECIAL";
            if ((flags & 0x1000) != 0) f += " RTSPECIAL";

            ctx.Log("  [" + idx + "] " + name + " RID=" + rid +
                    " flags=0x" + flags.ToString("x4") + f);
            idx++;
        }
        ctx.Log("  total=" + idx);
    }

    public void OnClientConnected() { }
    public void OnPlayerConnected(NetworkPlayer player) { }
    public void OnPlayerDisconnected(NetworkPlayer player) { }
    public void Tick() { }
    public void Shutdown() { }
}
