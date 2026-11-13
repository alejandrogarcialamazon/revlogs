"""Clasificación por nivel del evento, independiente del texto del mensaje."""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

from .matching import Counter, Counts
from .models import Severity


class ParseError(ValueError):
    """Una línea candidata a formato estructurado no se pudo clasificar."""


@dataclass(frozen=True)
class ParsedLine:
    counts: Counts
    format: str


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ParseError("JSON con claves duplicadas")
        result[key] = value
    return result


def _level(value: object, numeric: str) -> Severity | None:
    if isinstance(value, str):
        text = value.strip().casefold()
        if text in {
            "emerg",
            "emergency",
            "alert",
            "crit",
            "critical",
            "fatal",
            "err",
            "error",
        }:
            return Severity.ERROR
        if text in {"warn", "warning"}:
            return Severity.WARNING
        if text in {
            "info",
            "information",
            "informational",
            "notice",
            "debug",
            "trace",
            "notset",
        }:
            return None
        if text.isascii() and text.isdigit() and len(text) <= 3:
            value = int(text)
    if isinstance(value, int) and not isinstance(value, bool):
        if numeric == "syslog" and 0 <= value <= 7:
            return (
                Severity.ERROR
                if value <= 3
                else Severity.WARNING
                if value == 4
                else None
            )
        if numeric == "python" and value in {0, 10, 20, 30, 40, 50}:
            return (
                Severity.ERROR
                if value >= 40
                else Severity.WARNING
                if value == 30
                else None
            )
    raise ParseError("Nivel de severidad desconocido o de tipo inválido")


def _field(record: dict[str, object], name: str) -> tuple[bool, object]:
    if name in record:
        return True, record[name]
    current: object = record
    for part in name.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


class LogParser:
    def __init__(
        self,
        format: str = "text",
        level_fields: Sequence[str] = ("level", "severity", "log.level"),
        numeric_levels: str = "python",
    ) -> None:
        if format not in {"text", "auto", "json", "syslog"} or numeric_levels not in {
            "python",
            "syslog",
        }:
            raise ValueError("Formato o convención de niveles inválidos")
        if (
            not level_fields
            or len(level_fields) > 16
            or any(
                not name or len(name) > 128 or any(not part for part in name.split("."))
                for name in level_fields
            )
        ):
            raise ValueError(
                "Se requieren 1–16 campos de nivel, de hasta 128 caracteres"
            )
        self.format = format
        self.level_fields = tuple(level_fields)
        self.numeric_levels = numeric_levels

    def parse(self, line: str, counter: Counter) -> ParsedLine:
        mode = self.format
        text = line.lstrip()
        if mode == "auto":
            mode = (
                "json"
                if text.startswith("{")
                else "syslog"
                if re.match(r"^<\d", text)
                else "text"
            )
        if mode == "text":
            return ParsedLine(counter(line), "text")
        severity: Severity | None
        if mode == "json":
            try:
                record = json.loads(text, object_pairs_hook=_object)
            except (ValueError, RecursionError) as exc:
                raise ParseError("JSON inválido o demasiado anidado") from exc
            if not isinstance(record, dict):
                raise ParseError("Se requiere un objeto JSON por línea")
            levels = [
                _level(value, self.numeric_levels)
                for name in self.level_fields
                for present, value in [_field(record, name)]
                if present
            ]
            if not levels:
                raise ParseError("JSON sin campo de nivel configurado")
            if any(value != levels[0] for value in levels):
                raise ParseError("JSON con niveles de severidad contradictorios")
            severity = levels[0]
        else:
            match = re.match(r"^<([0-9]{1,3})>(.+)$", text)
            if match is None or int(match[1]) > 191 or not match[2].strip():
                raise ParseError("Syslog requiere PRI entre 0 y 191 y contenido")
            severity = _level(int(match[1]) % 8, "syslog")
        return ParsedLine({severity: 1} if severity is not None else {}, mode)
