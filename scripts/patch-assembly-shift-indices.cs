// Patch Assembly-CSharp.dll to add [RPC] attributes to Loader lifecycle
// methods, shifting all subsequent RPC method indices.
//
// This creates an assembly where the same RPC method names (RPC_Int, etc.)
// have DIFFERENT indices than the unpatched assembly. Used to test whether
// Unity handles cross-assembly method_index differences via learning.
//
// Usage:
//   mcs -r:Mono.Cecil.dll scripts/patch-assembly-shift-indices.cs \
//       -out:scripts/patch-assembly-shift-indices.exe
//   mono scripts/patch-assembly-shift-indices.exe <input.dll> <output.dll> [count]
//
// count: how many lifecycle methods to add [RPC] to (1-4, default 3)
//        Each added [RPC] shifts subsequent indices by 4.

using System;
using System.IO;
using System.Linq;
using Mono.Cecil;

class Program
{
    static int Main(string[] args)
    {
        if (args.Length < 2)
        {
            Console.Error.WriteLine("Usage: patch-assembly-shift-indices <input.dll> <output.dll> [count]");
            return 1;
        }

        string inputPath = args[0];
        string outputPath = args[1];
        int count = args.Length > 2 ? int.Parse(args[2]) : 3;

        string[] targetsInOrder = { "Awake", "Start", "Update", "OnApplicationQuit" };

        var resolver = new DefaultAssemblyResolver();
        resolver.AddSearchDirectory(Path.GetDirectoryName(Path.GetFullPath(inputPath)));
        var readerParams = new ReaderParameters { ReadSymbols = false, AssemblyResolver = resolver };
        var asm = AssemblyDefinition.ReadAssembly(inputPath, readerParams);
        var module = asm.MainModule;

        // Find the RPC attribute type reference
        TypeReference rpcAttrType = null;
        foreach (var type in module.Types)
        {
            foreach (var method in type.Methods)
            {
                foreach (var attr in method.CustomAttributes)
                {
                    if (attr.AttributeType.Name == "RPC")
                    {
                        rpcAttrType = attr.AttributeType;
                        break;
                    }
                }
                if (rpcAttrType != null) break;
            }
            if (rpcAttrType != null) break;
        }

        if (rpcAttrType == null)
        {
            Console.Error.WriteLine("Could not find existing [RPC] attribute in assembly");
            return 1;
        }

        // Find the RPC attribute constructor
        var rpcAttrTypeDef = rpcAttrType.Resolve();
        var rpcCtor = rpcAttrTypeDef.Methods.First(m => m.IsConstructor && !m.HasParameters);
        var rpcCtorRef = module.ImportReference(rpcCtor);

        // Find Loader type
        var loaderType = module.Types.FirstOrDefault(t => t.Name == "Loader");
        if (loaderType == null)
        {
            Console.Error.WriteLine("Could not find Loader type");
            return 1;
        }

        int added = 0;
        for (int i = 0; i < Math.Min(count, targetsInOrder.Length); i++)
        {
            string target = targetsInOrder[i];
            var method = loaderType.Methods.FirstOrDefault(m => m.Name == target);
            if (method == null)
            {
                Console.Error.WriteLine("Method not found: " + target);
                continue;
            }

            bool alreadyHas = method.CustomAttributes.Any(a => a.AttributeType.Name == "RPC");
            if (alreadyHas)
            {
                Console.Error.WriteLine("Already has [RPC]: " + target);
                continue;
            }

            method.CustomAttributes.Add(new CustomAttribute(rpcCtorRef));
            Console.Error.WriteLine("Added [RPC] to " + target + " (RID " +
                                    method.MetadataToken.RID + ")");
            added++;
        }

        asm.Write(outputPath);
        Console.Error.WriteLine("Wrote patched assembly: " + outputPath +
                                " (added " + added + " [RPC] attributes)");
        Console.Error.WriteLine("RPC indices for existing methods shifted by +" +
                                (added * 4));

        return 0;
    }
}
