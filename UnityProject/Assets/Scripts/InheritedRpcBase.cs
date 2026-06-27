using System;
using UnityEngine;

public class InheritedRpcBase : MonoBehaviour
{
    public Action<int, NetworkMessageInfo> OnBaseRpc;

    [RPC]
    void BaseRpc(int value, NetworkMessageInfo info)
    {
        Debug.Log("[InheritedRpcBase] BaseRpc(" + value + ") from " + info.sender);
        if (OnBaseRpc != null) OnBaseRpc(value, info);
    }
}
