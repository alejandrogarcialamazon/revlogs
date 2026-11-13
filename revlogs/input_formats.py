"""Compresión y codificación sobre el descriptor ya validado."""

import codecs
import gzip
import io
import zlib
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass

from .limits import ResourceLimitError, ScanLimits
from .safe_io import BinaryStream, LogSource


class InputFormatError(OSError):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ReadOptions:
    compression: str = "auto"
    encoding: str = "auto"
    errors: str = "strict"

    def __post_init__(self) -> None:
        if self.compression not in {"auto", "none", "gzip"} or self.errors not in {
            "strict",
            "replace",
            "ignore",
        }:
            raise ValueError("Compresión o política de decodificación inválida")
        if self.encoding != "auto":
            try:
                name = codecs.lookup(self.encoding).name
            except LookupError as exc:
                raise ValueError("Codificación desconocida") from exc
            if name not in {
                "ascii",
                "utf-8",
                "utf-8-sig",
                "iso8859-1",
                "cp1252",
                "utf-16",
                "utf-16-le",
                "utf-16-be",
                "utf-32",
                "utf-32-le",
                "utf-32-be",
            }:
                raise ValueError("Codificación no soportada por el lector acotado")


class LimitedCompressed(io.RawIOBase):
    def __init__(self, source: BinaryStream, maximum: int) -> None:
        self.source = source
        self.maximum = maximum

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.source.tell()

    def seek(self, offset: int, whence: int = 0) -> int:
        return self.source.seek(offset, whence)

    def read(self, size: int = -1) -> bytes:
        remaining = max(0, self.maximum - self.source.tell())
        requested = remaining + 1 if size < 0 else min(size, remaining + 1)
        data = self.source.read(requested)
        if len(data) > remaining:
            raise ResourceLimitError("Límite de bytes comprimidos alcanzado")
        return data


@contextmanager
def content_source(
    source: LogSource, options: ReadOptions, limits: ScanLimits
) -> Iterator[LogSource]:
    prefix = source.stream.read(2)
    source.stream.seek(0)
    compressed = options.compression == "gzip" or (
        options.compression == "auto"
        and (prefix == b"\x1f\x8b" or source.path.suffix.lower() == ".gz")
    )
    if not compressed:
        yield source
        return
    if prefix != b"\x1f\x8b":
        raise InputFormatError("Cabecera gzip inválida", "compression_error")
    with ExitStack() as stack:
        bounded = stack.enter_context(
            LimitedCompressed(source.stream, limits.max_compressed_bytes)
        )
        stream = stack.enter_context(gzip.GzipFile(fileobj=bounded, mode="rb"))
        try:
            yield LogSource(source.path, stream, compression="gzip")
        except (gzip.BadGzipFile, EOFError, zlib.error) as exc:
            raise InputFormatError(
                "Gzip corrupto o truncado", "compression_error"
            ) from exc


def select_encoding(prefix: bytes, configured: str) -> tuple[str, int, bytes]:
    name = configured if configured == "auto" else codecs.lookup(configured).name
    if name in {"auto", "utf-16", "utf-32"}:
        boms = (
            (codecs.BOM_UTF32_LE, "utf-32-le"),
            (codecs.BOM_UTF32_BE, "utf-32-be"),
            (codecs.BOM_UTF16_LE, "utf-16-le"),
            (codecs.BOM_UTF16_BE, "utf-16-be"),
        )
        detected = next(
            (
                encoding
                for bom, encoding in boms
                if prefix.startswith(bom)
                and (name == "auto" or encoding.startswith(name))
            ),
            None,
        )
        if name == "auto":
            name = detected or "utf-8"
        elif detected is None or not detected.startswith(name):
            raise InputFormatError(
                "La codificación seleccionada requiere BOM compatible", "decode_error"
            )
        else:
            name = detected
    if name == "utf-8-sig":
        name = "utf-8"
    width = 4 if name.startswith("utf-32") else 2 if name.startswith("utf-16") else 1
    newline = "\n".encode(name) if width > 1 else b"\n"
    return name, width, newline


def raw_line(stream: BinaryStream, maximum: int, width: int, newline: bytes) -> bytes:
    if width == 1:
        return stream.readline(maximum)
    data = bytearray()
    while len(data) < maximum:
        piece = stream.readline(maximum - len(data))
        if not piece:
            break
        data.extend(piece)
        missing = (-len(data)) % width
        if missing and len(data) < maximum:
            data.extend(stream.read(min(missing, maximum - len(data))))
        if data.endswith(newline):
            break
    return bytes(data)
