"""Configuración TOML explícita con esquema validado y sin ejecución de código."""

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib as toml
else:
    from ._vendor import tomli as toml

from .limits import ScanLimits

BOOLEANS = {"redact", "recursive", "strict", "include_reports", "verbose"}
LISTS = {
    "redact_literal",
    "include",
    "exclude",
    "error_pattern",
    "warning_pattern",
    "error_literal",
    "warning_literal",
    "level_field",
    "paths",
}
INTEGERS = {
    *ScanLimits.__dataclass_fields__,
    "max_details",
    "max_excerpt_chars",
    "regex_memory_mib",
}
STRINGS = {
    "state",
    "report_format",
    "json_output",
    "csv_output",
    "output",
    "format",
    "numeric_levels",
    "compression",
    "encoding",
    "decode_errors",
    "fail_on",
}
CHOICES = {
    "report_format": {"markdown", "json", "csv"},
    "format": {"text", "auto", "json", "syslog"},
    "numeric_levels": {"python", "syslog"},
    "compression": {"auto", "none", "gzip"},
    "decode_errors": {"strict", "replace", "ignore"},
    "fail_on": {"error", "warning"},
}


def load_config(path: Path) -> dict[str, object]:
    path = path.expanduser().absolute()
    with path.open("rb") as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise ValueError("La configuración supera 64 KiB")
    try:
        raw: object = toml.loads(data.decode("utf-8"))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError(
            "TOML inválido; revisar sintaxis y codificación UTF-8"
        ) from exc
    if not isinstance(raw, dict) or set(raw) - {"schema_version", "revlogs"}:
        raise ValueError("Tablas o claves raíz de configuración desconocidas")
    version = raw.get("schema_version", 1)
    if type(version) is not int or version != 1:
        raise ValueError("schema_version debe ser el entero 1")
    settings = raw.get("revlogs")
    if not isinstance(settings, dict):
        raise ValueError("Se requiere la tabla [revlogs]")
    result: dict[str, object] = {}
    for key, value in settings.items():
        if key in BOOLEANS:
            valid = type(value) is bool
        elif key in LISTS:
            valid = isinstance(value, list) and all(
                isinstance(item, str) and bool(item.strip()) for item in value
            )
        elif key in INTEGERS:
            valid = type(value) is int and value >= (
                0 if key in {"max_depth", "max_total_details", "max_details"} else 1
            )
        elif key == "regex_timeout":
            valid = type(value) in {int, float} and 0 < value <= 60
        elif key in STRINGS:
            valid = isinstance(value, str) and bool(value.strip())
        else:
            raise ValueError("Clave de configuración desconocida")
        if not valid or (key in CHOICES and value not in CHOICES[key]):
            raise ValueError(f"Tipo o valor inválido para {key}")
        result[key] = value
    if "paths" in result:
        values = settings["paths"]
        result["paths"] = [
            (path.parent / Path(value).expanduser()).absolute() for value in values
        ]
    for name in ("output", "json_output", "csv_output", "state"):
        if name in result:
            result[name] = (path.parent / Path(settings[name]).expanduser()).absolute()
    return result
