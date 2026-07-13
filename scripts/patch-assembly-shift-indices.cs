// Patch Assembly-CSharp.dll to shift RPC method indices by a configurable,
// non-uniform amount, by (a) tagging existing non-RPC methods with [RPC]
// and/or (b) injecting brand-new, never-invoked filler methods directly
// into the Loader type's method list at chosen positions.
//
// This creates an assembly where the same RPC method names (RPC_Int, etc.)
// have DIFFERENT indices than the unpatched assembly — and, with a
// non-uniform recipe, different DELTAS from each other — used to test
// whether Unity's subsequent-use dispatch handles cross-assembly
// method_index differences via the 0x07 batch-index adoption recipe
// (see docs/research/2026-07-13-batch-index-decoder-was-broken.md).
//
// Usage:
//   mcs -r:Mono.Cecil.dll scripts/patch-assembly-shift-indices.cs \
//       -out:scripts/patch-assembly-shift-indices.exe
//   mono scripts/patch-assembly-shift-indices.exe <input.dll> <output.dll> [recipe]
//
// recipe: comma-separated ANCHOR:COUNT pairs, e.g.
//   "START:2,RPC_Void:1,RPC_Int:3,RPC_Float:0,RPC_String:2,RPC_Vector3:4,
//    RPC_Quaternion:0,RPC_Bytes:3,RPC_IntFloatString:1,RPC_NetworkPlayer:5,
//    RPC_NetworkViewID:0,RPC_Alpha:2,RPC_Beta:0,RPC_Gamma:2"
//   ANCHOR is a Loader method name (or "START" for before the first RPC
//   method); COUNT is how many new filler [RPC] methods to insert
//   immediately after that anchor (before it, for START). Each filler
//   method shifts the index of every RPC method that follows it by +4.
//   Since anchors are interspersed among the existing RPC_* methods,
//   different existing methods end up shifted by different total amounts
//   — a non-uniform delta, unlike the old fixed-count/uniform-shift
//   version of this script.
//
// If no recipe is given, a built-in default (~+100 by RPC_Gamma, varying
// per method) is used — see DefaultRecipe below.
//
// Legacy behavior (tagging existing lifecycle methods with [RPC], no new
// methods) is no longer the default since the assembly only has ~20
// taggable existing methods, all clustered before/after the RPC_* block —
// not enough to produce genuinely non-uniform per-method deltas. Filler
// injection has no such ceiling.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Mono.Cecil;
using Mono.Cecil.Cil;

class Program
{
    const string DefaultRecipe =
        "START:2,RPC_Void:1,RPC_Int:3,RPC_Float:0,RPC_String:2,RPC_Vector3:4," +
        "RPC_Quaternion:0,RPC_Bytes:3,RPC_IntFloatString:1,RPC_NetworkPlayer:5," +
        "RPC_NetworkViewID:0,RPC_Alpha:2,RPC_Beta:0,RPC_Gamma:2";

    static int Main(string[] args)
    {
        if (args.Length < 2)
        {
            Console.Error.WriteLine("Usage: patch-assembly-shift-indices <input.dll> <output.dll> [recipe]");
            return 1;
        }

        string inputPath = args[0];
        string outputPath = args[1];
        string recipe = args.Length > 2 ? args[2] : DefaultRecipe;

        var resolver = new DefaultAssemblyResolver();
        resolver.AddSearchDirectory(Path.GetDirectoryName(Path.GetFullPath(inputPath)));
        var readerParams = new ReaderParameters { ReadSymbols = false, AssemblyResolver = resolver };
        var asm = AssemblyDefinition.ReadAssembly(inputPath, readerParams);
        var module = asm.MainModule;

        // Find the RPC attribute constructor from an existing tagged method.
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
        var rpcAttrTypeDef = rpcAttrType.Resolve();
        var rpcCtor = rpcAttrTypeDef.Methods.First(m => m.IsConstructor && !m.HasParameters);
        var rpcCtorRef = module.ImportReference(rpcCtor);

        var loaderType = module.Types.FirstOrDefault(t => t.Name == "Loader");
        if (loaderType == null)
        {
            Console.Error.WriteLine("Could not find Loader type");
            return 1;
        }

        // Borrow NetworkMessageInfo's TypeReference from an existing RPC
        // method so filler methods have a realistic single-param signature.
        var templateMethod = loaderType.Methods.First(m => m.Name == "RPC_Void");
        var infoParamType = module.ImportReference(templateMethod.Parameters[0].ParameterType);

        // Parse the recipe into an ordered list of (anchorName, count).
        var recipeEntries = new List<Tuple<string, int>>();
        foreach (var part in recipe.Split(','))
        {
            var kv = part.Trim().Split(':');
            if (kv.Length != 2)
            {
                Console.Error.WriteLine("Bad recipe entry: " + part);
                return 1;
            }
            recipeEntries.Add(Tuple.Create(kv[0].Trim(), int.Parse(kv[1].Trim())));
        }

        int fillerNum = 0;
        int totalInserted = 0;

        // Apply entries in the order given, tracking a running RID-position
        // cursor so each anchor's insertion point accounts for previously
        // inserted fillers. Anchors must appear in the recipe in the same
        // order their target methods appear in Loader (START first).
        foreach (var entry in recipeEntries)
        {
            string anchor = entry.Item1;
            int count = entry.Item2;
            if (count == 0) continue;

            int insertIndex;
            if (anchor == "START")
            {
                var firstRpc = loaderType.Methods.First(m => m.Name == "RPC_Void");
                insertIndex = loaderType.Methods.IndexOf(firstRpc);
            }
            else
            {
                var anchorMethod = loaderType.Methods.FirstOrDefault(m => m.Name == anchor);
                if (anchorMethod == null)
                {
                    Console.Error.WriteLine("Anchor method not found: " + anchor);
                    return 1;
                }
                insertIndex = loaderType.Methods.IndexOf(anchorMethod) + 1;
            }

            for (int i = 0; i < count; i++)
            {
                string name = "RPC_Filler_" + fillerNum;
                var filler = new MethodDefinition(
                    name,
                    MethodAttributes.Private | MethodAttributes.HideBySig,
                    module.TypeSystem.Void);
                filler.Parameters.Add(new ParameterDefinition("info", ParameterAttributes.None, infoParamType));
                filler.Body = new MethodBody(filler);
                filler.Body.GetILProcessor().Append(Instruction.Create(OpCodes.Ret));
                filler.CustomAttributes.Add(new CustomAttribute(rpcCtorRef));

                loaderType.Methods.Insert(insertIndex + i, filler);
                fillerNum++;
                totalInserted++;
            }

            Console.Error.WriteLine("Inserted " + count + " filler(s) at anchor '" + anchor +
                                     "' (Loader.Methods index " + insertIndex + ")");
        }

        asm.Write(outputPath);
        Console.Error.WriteLine("Wrote patched assembly: " + outputPath +
                                 " (" + totalInserted + " filler [RPC] methods inserted, recipe=\"" + recipe + "\")");
        Console.Error.WriteLine("This produces a NON-UNIFORM shift: methods after more fillers " +
                                 "shift by proportionally more (+4 per filler before them).");

        return 0;
    }
}
