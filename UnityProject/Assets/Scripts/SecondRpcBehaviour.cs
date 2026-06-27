using System;
using UnityEngine;

public class SecondRpcBehaviour : MonoBehaviour
{
    public Action<byte[], NetworkMessageInfo> OnReceiveSerializeEvent;

    [RPC]
    void ReceiveSerializeEvent(byte[] bytes, NetworkMessageInfo info)
    {
        Debug.Log("[SecondRpcBehaviour] ReceiveSerializeEvent(" + bytes.Length + " bytes) from " + info.sender);
        if (OnReceiveSerializeEvent != null) OnReceiveSerializeEvent(bytes, info);
    }
}
