from .write_compressed import generate as generate_writeCompressed
from .read_compressed import generate as generate_readCompressed
from .huffman import generate as generate_huffman
from .huffman_decode import generate as generate_huffmanDecode
from .bitstream_write import generate as generate_bitstream
from .bitstream_read import generate as generate_bitstreamRead
from .cell import generate as generate_cell
from .cell_decode import generate as generate_cellDecode
from .update_row import generate as generate_updateRow
from .update_row_decode import generate as generate_updateRowDecode
from .query_request import generate as generate_queryRequest
from .query_request_decode import generate as generate_queryRequestDecode
from .query_reply import generate as generate_queryReply
from .query_reply_decode import generate as generate_queryReplyDecode
from .remove_row import generate as generate_removeRow
from .remove_row_decode import generate as generate_removeRowDecode
from .rpc_encode import generate as generate_rpcEncode
from .rpc_decode import generate as generate_rpcDecode
from .rpc_first_use import generate as generate_rpcFirstUse
from .rpc_first_use_decode import generate as generate_rpcFirstUseDecode
from .method_hash import generate as generate_methodHash
from .method_index import generate as generate_methodIndex
from .state_sync import generate as generate_stateSync
from .state_sync_decode import generate as generate_stateSyncDecode
from .delta_state_sync import generate as generate_deltaStateSync
from .delta_sync_decode import generate as generate_deltaSyncDecode
from .view_id import generate as generate_viewId
from .view_id_param import generate as generate_viewIdParam
from .address_encode import generate as generate_addressEncode
from .address_decode import generate as generate_addressDecode

GENERATORS = {
    'writeCompressed': generate_writeCompressed,
    'readCompressed': generate_readCompressed,
    'huffman': generate_huffman,
    'huffmanDecode': generate_huffmanDecode,
    'bitstream': generate_bitstream,
    'bitstreamRead': generate_bitstreamRead,
    'cell': generate_cell,
    'cellDecode': generate_cellDecode,
    'updateRow': generate_updateRow,
    'updateRowDecode': generate_updateRowDecode,
    'queryRequest': generate_queryRequest,
    'queryRequestDecode': generate_queryRequestDecode,
    'queryReply': generate_queryReply,
    'queryReplyDecode': generate_queryReplyDecode,
    'removeRow': generate_removeRow,
    'removeRowDecode': generate_removeRowDecode,
    'rpcEncode': generate_rpcEncode,
    'rpcDecode': generate_rpcDecode,
    'rpcFirstUse': generate_rpcFirstUse,
    'rpcFirstUseDecode': generate_rpcFirstUseDecode,
    'methodHash': generate_methodHash,
    'methodIndex': generate_methodIndex,
    'stateSync': generate_stateSync,
    'stateSyncDecode': generate_stateSyncDecode,
    'deltaStateSync': generate_deltaStateSync,
    'deltaSyncDecode': generate_deltaSyncDecode,
    'viewId': generate_viewId,
    'viewIdParam': generate_viewIdParam,
    'addressEncode': generate_addressEncode,
    'addressDecode': generate_addressDecode,
}
