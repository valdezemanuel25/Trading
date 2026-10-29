"""Read and write .zst files.

Uses the `zstandard` package when it is installed. Otherwise falls back to the system libzstd through ctypes,
so the backtest also runs where pip can't reach PyPI.
"""
import ctypes
import ctypes.util

try:
    import zstandard
except ImportError:
    zstandard = None

_lib = None


class _Buf(ctypes.Structure):
    _fields_ = [("ptr", ctypes.c_void_p), ("size", ctypes.c_size_t), ("pos", ctypes.c_size_t)]


def _libzstd():
    global _lib
    if _lib is None:
        name = ctypes.util.find_library("zstd") or "libzstd.so.1"
        lib = ctypes.CDLL(name)
        lib.ZSTD_createDStream.restype = ctypes.c_void_p
        lib.ZSTD_freeDStream.argtypes = [ctypes.c_void_p]
        lib.ZSTD_initDStream.argtypes = [ctypes.c_void_p]
        lib.ZSTD_decompressStream.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Buf), ctypes.POINTER(_Buf)]
        lib.ZSTD_decompressStream.restype = ctypes.c_size_t
        lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
        lib.ZSTD_getErrorName.argtypes = [ctypes.c_size_t]
        lib.ZSTD_getErrorName.restype = ctypes.c_char_p
        lib.ZSTD_compressBound.argtypes = [ctypes.c_size_t]
        lib.ZSTD_compressBound.restype = ctypes.c_size_t
        lib.ZSTD_compress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_int]
        lib.ZSTD_compress.restype = ctypes.c_size_t
        _lib = lib
    return _lib


def _check(lib, rc):
    if lib.ZSTD_isError(rc):
        raise IOError("zstd: " + lib.ZSTD_getErrorName(rc).decode())
    return rc


def decompress(data: bytes) -> bytes:
    if zstandard is not None:
        return zstandard.ZstdDecompressor().stream_reader(data).read()
    lib = _libzstd()
    ds = lib.ZSTD_createDStream()
    try:
        _check(lib, lib.ZSTD_initDStream(ds))
        src = ctypes.create_string_buffer(data, len(data))
        inb = _Buf(ctypes.cast(src, ctypes.c_void_p), len(data), 0)
        chunk = 1 << 22
        dst = ctypes.create_string_buffer(chunk)
        out = []
        while True:
            outb = _Buf(ctypes.cast(dst, ctypes.c_void_p), chunk, 0)
            _check(lib, lib.ZSTD_decompressStream(ds, ctypes.byref(outb), ctypes.byref(inb)))
            out.append(dst.raw[:outb.pos])
            if inb.pos >= inb.size and outb.pos < chunk:
                break
        return b"".join(out)
    finally:
        lib.ZSTD_freeDStream(ds)


def compress(data: bytes, level: int = 10) -> bytes:
    if zstandard is not None:
        return zstandard.ZstdCompressor(level=level).compress(data)
    lib = _libzstd()
    cap = lib.ZSTD_compressBound(len(data))
    dst = ctypes.create_string_buffer(cap)
    n = _check(lib, lib.ZSTD_compress(dst, cap, data, len(data), level))
    return dst.raw[:n]


def read_zst(path) -> bytes:
    with open(path, "rb") as fh:
        return decompress(fh.read())


def write_zst(path, data: bytes, level: int = 10):
    with open(path, "wb") as fh:
        fh.write(compress(data, level))
