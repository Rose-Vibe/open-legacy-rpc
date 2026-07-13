// Extract RPC method indices from a .NET assembly using Mono.Cecil.
//
// Reads the MethodDef table, identifies [RPC] methods, and computes
// the wire-format method_index for each:
//
//   method_index = (method_RID - 1 - interface_methods_before) * 4
//
// Usage:
//   mcs -r:/usr/lib/mono/gac/Mono.Cecil/0.11.0.0__0738eb9f132ed756/Mono.Cecil.dll \
//       scripts/extract-method-indices.cs -out:scripts/extract-method-indices.exe
//   mono scripts/extract-method-indices.exe <path-to-assembly.dll>
//
// Output: JSON array of {name, rid, interfaceMethodsBefore, index} objects.
//
// This does NOT emit method_tag. method_tag is not derivable from static IL
// metadata (RID, index, name, or signature) — no closed-form formula fits
// the known ground truth (see
// docs/research/2026-07-12-method-tag-real-derivation.md). It must be
// captured empirically from a real Unity-to-Unity pcap of this specific
// compiled assembly, decoded per
// docs/notes/unity-raknet-capture-decode-playbook.md, and registered via
// registerMethodTag(s) — not computed from this tool's output.

using System;
using System.Collections.Generic;
using System.Linq;
using Mono.Cecil;

class Program
{
    static int Main(string[] args)
    {
        if (args.Length < 1)
        {
            Console.Error.WriteLine("Usage: extract-method-indices <assembly.dll> [--all]");
            Console.Error.WriteLine("  --all  Include non-RPC methods in output");
            return 1;
        }

        string path = args[0];
        bool showAll = args.Contains("--all");

        AssemblyDefinition asm;
        try
        {
            var readerParams = new ReaderParameters { ReadSymbols = false };
            asm = AssemblyDefinition.ReadAssembly(path, readerParams);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("Failed to read assembly: " + ex.Message);
            return 1;
        }

        // Collect all methods in RID order across all types.
        // Unity's method_index formula operates on the global MethodDef table,
        // not per-type — RIDs are assembly-wide and sequential.
        var allMethods = new List<Tuple<MethodDefinition, int>>();
        foreach (var mod in asm.Modules)
        {
            foreach (var type in mod.Types)
            {
                CollectMethods(type, allMethods);
            }
        }

        // Sort by RID (MetadataToken.RID) to match the MethodDef table order
        allMethods.Sort((a, b) => a.Item2.CompareTo(b.Item2));

        // Count interface methods before each position and identify [RPC] methods
        int interfaceCount = 0;
        var results = new List<string>();
        var allResults = new List<string>();

        foreach (var pair in allMethods)
        {
            var method = pair.Item1;
            int rid = pair.Item2;
            bool isInterface = method.DeclaringType.IsInterface;

            if (isInterface)
            {
                interfaceCount++;
                if (showAll)
                {
                    allResults.Add(FormatEntry(method.Name, rid, interfaceCount - 1,
                        -1, true, false, method.DeclaringType.FullName));
                }
                continue;
            }

            int index = (rid - 1 - interfaceCount) * 4;
            bool isRpc = HasRpcAttribute(method);

            if (isRpc)
            {
                results.Add(FormatEntry(method.Name, rid, interfaceCount,
                    index, false, true, method.DeclaringType.FullName));
            }

            if (showAll)
            {
                allResults.Add(FormatEntry(method.Name, rid, interfaceCount,
                    index, false, isRpc, method.DeclaringType.FullName));
            }
        }

        // Output JSON
        var output = showAll ? allResults : results;
        Console.WriteLine("[");
        for (int i = 0; i < output.Count; i++)
        {
            Console.Write("  " + output[i]);
            Console.WriteLine(i < output.Count - 1 ? "," : "");
        }
        Console.WriteLine("]");

        Console.Error.WriteLine(string.Format(
            "Found {0} [RPC] methods, {1} interface methods, {2} total methods",
            results.Count, interfaceCount, allMethods.Count));

        return 0;
    }

    static void CollectMethods(TypeDefinition type, List<Tuple<MethodDefinition, int>> list)
    {
        foreach (var method in type.Methods)
        {
            int rid = (int)(method.MetadataToken.RID);
            list.Add(Tuple.Create(method, rid));
        }
        foreach (var nested in type.NestedTypes)
        {
            CollectMethods(nested, list);
        }
    }

    static bool HasRpcAttribute(MethodDefinition method)
    {
        if (!method.HasCustomAttributes) return false;
        foreach (var attr in method.CustomAttributes)
        {
            if (attr.AttributeType.Name == "RPC" ||
                attr.AttributeType.FullName == "UnityEngine.RPC")
                return true;
        }
        return false;
    }

    static string FormatEntry(string name, int rid, int ifaceBefore,
        int index, bool isInterface, bool isRpc, string typeName)
    {
        string indexHex = index >= 0 ? string.Format("\"0x{0:x2}\"", index) : "null";
        return string.Format(
            "{{\"name\": \"{0}\", \"rid\": {1}, \"interfaceMethodsBefore\": {2}, " +
            "\"index\": {3}, \"isInterface\": {4}, \"isRpc\": {5}, " +
            "\"type\": \"{6}\"}}",
            EscapeJson(name), rid, ifaceBefore,
            indexHex,
            isInterface ? "true" : "false",
            isRpc ? "true" : "false",
            EscapeJson(typeName));
    }

    static string EscapeJson(string s)
    {
        return s.Replace("\\", "\\\\").Replace("\"", "\\\"");
    }
}
