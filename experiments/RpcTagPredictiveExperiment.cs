using UnityEngine;

// Phase 1 (method_tag investigation): predictive confirmation run.
//
// All 11 predicted tags below were computed BEFORE this capture, from the
// name-only shared-derivation rule in
// docs/plans/method-tag-shared-derivation-hypotheses.md:
//
//   s   = '00' + Huffman(name) + code(0) + code(0) + ...
//   cap = 8 * ceil(len(Huffman(name)) / 8)
//   tag = int(s[cap : cap+2], 2) << 2
//
// Names were chosen (via brute-force search over the formula, not by hand)
// to cover the rule's boundary/spill-value space: for each of the four
// 2-bit spill values {0,4,8,12}, one TRUNC name and one PAD name, plus one
// EXACT-fit name and one SHORT (<=6-byte identifier) name. One predicted
// combination is deliberately absent: PAD+tag0. Given the fixed 16-bit
// padding codeword ('0101011110001101'), every PAD case reads its 2 tag
// bits from offsets 1-5 of that codeword, and none of those 5 windows is
// '00' -- so PAD+tag0 is not just unobserved here, it should be
//*structurally impossible*. If a real capture ever shows a PAD-boundary
// frame with observed tag 0, that falsifies the padding-codeword model,
// not just this experiment's sample.
//
// Declaration order below is deliberately shuffled (not alphabetical, not
// grouped by predicted tag) as a lightweight sanity check that tag
// depends only on the name, not declaration position -- the substantive
// version of that question was already closed by the cross-build
// evidence (LargeDelta-*.pcap).
//
// name       | boundary | r | predicted_tag | identifier (class_guid+method_hash)
// RPC_B      | TRUNC    | 1 | 0              | 0c93b276d5b1a8
// RPC_D      | TRUNC    | 1 | 8              | 0c93b276d5b133
// RPC_IC     | TRUNC    | 0 | 4              | 0c93b276d5b1d53b
// RPC_M      | TRUNC    | 0 | 12             | 0c93b276d5b17d
// RPC_A      | EXACT    | 2 | 4              | 0c93b276d5b154
// RPC_I      | PAD      | 3 | 8              | 0c93b276d5b1d4
// RPC_K      | PAD      | 4 | 4              | 0c93b276d5b1ab65
// RPC_Q      | PAD      | 5 | 8              | 0c93b276d5b155da
// RPC_J      | PAD      | 6 | 4              | 0c93b276d5b1ab75
// RPC_C      | PAD      | 7 | 12             | 0c93b276d5b19daa
// BaseRpc    | SHORT/PAD| 6 | 4              | 2a0db0645285
//
// Reuses the Phase 1a smoke-test finding: Unity validates the RPC name
// against NetworkView.observed on the SENDER before it will transmit
// anything, so this class must be AddComponent'd and assigned as
// .observed on both peers, not just the receiver.
public class PredictiveTagBehaviour : MonoBehaviour
{
    [RPC] void RPC_J(int v, NetworkMessageInfo info) { Debug.Log("[RPC] RPC_J(" + v + ") from " + info.sender); }
    [RPC] void RPC_A(int v, NetworkMessageInfo info) { Debug.Log("[RPC] RPC_A(" + v + ") from " + info.sender); }
    [RPC] void BaseRpc(int v, NetworkMessageInfo info) { Debug.Log("[RPC] BaseRpc(" + v + ") from " + info.sender); }
    [RPC] void RPC_D(int v, NetworkMessageInfo info) { Debug.Log("[RPC] RPC_D(" + v + ") from " + info.sender); }
    [RPC] void RPC_Q(int v, NetworkMessageInfo info) { Debug.Log("[RPC] RPC_Q(" + v + ") from " + info.sender); }
    [RPC] void RPC_B(int v, NetworkMessageInfo info) { Debug.Log("[RPC] RPC_B(" + v + ") from " + info.sender); }
    [RPC] void RPC_M(int v, NetworkMessageInfo info) { Debug.Log("[RPC] RPC_M(" + v + ") from " + info.sender); }
    [RPC] void RPC_I(int v, NetworkMessageInfo info) { Debug.Log("[RPC] RPC_I(" + v + ") from " + info.sender); }
    [RPC] void RPC_C(int v, NetworkMessageInfo info) { Debug.Log("[RPC] RPC_C(" + v + ") from " + info.sender); }
    [RPC] void RPC_K(int v, NetworkMessageInfo info) { Debug.Log("[RPC] RPC_K(" + v + ") from " + info.sender); }
    [RPC] void RPC_IC(int v, NetworkMessageInfo info) { Debug.Log("[RPC] RPC_IC(" + v + ") from " + info.sender); }
}

public class RpcTagPredictiveExperiment : IExperiment
{
    static readonly string[] Names =
    {
        "RPC_J", "RPC_A", "BaseRpc", "RPC_D", "RPC_Q",
        "RPC_B", "RPC_M", "RPC_I", "RPC_C", "RPC_K", "RPC_IC",
    };

    ExperimentContext ctx;
    bool connected;
    int sendIndex;
    float lastSend;

    public void Setup(ExperimentContext ctx)
    {
        this.ctx = ctx;
        var behaviour = ctx.PrimaryNetworkView.gameObject.AddComponent<PredictiveTagBehaviour>();
        ctx.PrimaryNetworkView.observed = behaviour;
    }

    public void OnServerReady() { ctx.Log("Server ready"); }
    public void OnPlayerConnected(NetworkPlayer player) { ctx.Log("Player connected"); }
    public void OnPlayerDisconnected(NetworkPlayer player) { }

    public void OnClientConnected()
    {
        ctx.Log("Client connected, will send " + Names.Length + " RPCs in sequence");
        connected = true;
    }

    public void Tick()
    {
        if (ctx.Role != ExperimentRole.Client) return;
        if (!connected || sendIndex >= Names.Length) return;

        if (sendIndex == 0 || Time.realtimeSinceStartup - lastSend > 0.3f)
        {
            string name = Names[sendIndex];
            int value = sendIndex + 1;
            ctx.Log("Sending " + name + "(" + value + ")");
            ctx.PrimaryNetworkView.RPC(name, RPCMode.Server, value);
            lastSend = Time.realtimeSinceStartup;
            sendIndex++;

            if (sendIndex >= Names.Length)
                ctx.Log("EXPERIMENT_DONE");
        }
    }

    public void Shutdown() { }
}
