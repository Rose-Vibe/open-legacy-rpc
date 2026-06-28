from .write_compressed import validate as validate_writeCompressed
from .read_compressed import validate as validate_readCompressed
from .huffman import validate as validate_huffman
from .huffman_decode import validate as validate_huffmanDecode
from .bitstream_write import validate as validate_bitstream
from .bitstream_read import validate as validate_bitstreamRead
from .cell import validate as validate_cell
from .cell_decode import validate as validate_cellDecode
from .update_row import validate as validate_updateRow
from .update_row_decode import validate as validate_updateRowDecode
from .query_request import validate as validate_queryRequest
from .query_request_decode import validate as validate_queryRequestDecode
from .query_reply import validate as validate_queryReply
from .query_reply_decode import validate as validate_queryReplyDecode
from .remove_row import validate as validate_removeRow
from .remove_row_decode import validate as validate_removeRowDecode
from .rpc_encode import validate as validate_rpcEncode
from .rpc_decode import validate as validate_rpcDecode
from .rpc_first_use import validate as validate_rpcFirstUse
from .rpc_first_use_decode import validate as validate_rpcFirstUseDecode
from .method_hash import validate as validate_methodHash
from .method_index import validate as validate_methodIndex
from .state_sync import validate as validate_stateSync
from .state_sync_decode import validate as validate_stateSyncDecode
from .delta_state_sync import validate as validate_deltaStateSync
from .delta_sync_decode import validate as validate_deltaSyncDecode
from .view_id import validate as validate_viewId
from .view_id_param import validate as validate_viewIdParam
from .address_encode import validate as validate_addressEncode
from .address_decode import validate as validate_addressDecode
from .batch_index_encode import validate as validate_batchIndexEncode
from .batch_index_decode import validate as validate_batchIndexDecode

VALIDATORS = {
    'writeCompressed': validate_writeCompressed,
    'readCompressed': validate_readCompressed,
    'huffman': validate_huffman,
    'huffmanDecode': validate_huffmanDecode,
    'bitstream': validate_bitstream,
    'bitstreamRead': validate_bitstreamRead,
    'cell': validate_cell,
    'cellDecode': validate_cellDecode,
    'updateRow': validate_updateRow,
    'updateRowDecode': validate_updateRowDecode,
    'queryRequest': validate_queryRequest,
    'queryRequestDecode': validate_queryRequestDecode,
    'queryReply': validate_queryReply,
    'queryReplyDecode': validate_queryReplyDecode,
    'removeRow': validate_removeRow,
    'removeRowDecode': validate_removeRowDecode,
    'rpcEncode': validate_rpcEncode,
    'rpcDecode': validate_rpcDecode,
    'rpcFirstUse': validate_rpcFirstUse,
    'rpcFirstUseDecode': validate_rpcFirstUseDecode,
    'methodHash': validate_methodHash,
    'methodIndex': validate_methodIndex,
    'stateSync': validate_stateSync,
    'stateSyncDecode': validate_stateSyncDecode,
    'deltaStateSync': validate_deltaStateSync,
    'deltaSyncDecode': validate_deltaSyncDecode,
    'viewId': validate_viewId,
    'viewIdParam': validate_viewIdParam,
    'addressEncode': validate_addressEncode,
    'addressDecode': validate_addressDecode,
    'batchIndexEncode': validate_batchIndexEncode,
    'batchIndexDecode': validate_batchIndexDecode,
}
