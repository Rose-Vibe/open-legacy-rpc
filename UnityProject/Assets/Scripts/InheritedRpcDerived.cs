using System;
using UnityEngine;

public class InheritedRpcDerived : InheritedRpcBase
{
    public Action<int, NetworkMessageInfo> OnDerivedRpc;

    [RPC]
    void DerivedRpc(int value, NetworkMessageInfo info)
    {
        Debug.Log("[InheritedRpcDerived] DerivedRpc(" + value + ") from " + info.sender);
        if (OnDerivedRpc != null) OnDerivedRpc(value, info);
    }
}
