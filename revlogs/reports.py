"""Presentaciones intercambiables del resultado del análisis."""

import html
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

from .models import REPORT_MARKER, ScanResult, Severity


class ReportRenderer(Protocol):
    """Contrato para incorporar nuevos formatos sin modificar el analizador."""

    def render(self, result: ScanResult) -> Iterator[str]: ...


def _safe(value: str) -> str:
    """Escapa texto no confiable para mostrarlo como contenido Markdown literal."""
    value = "".join(
        char if char.isprintable() else f"\\x{ord(char):02x}" for char in value
    )
    value = html.escape(value, quote=True)
    for character in "\\`*_{}[]()#+-.!|~":
        value = value.replace(character, f"\\{character}")
    return value


def console_summary(result: ScanResult) -> str:
    rows = [
        "RESUMEN DE LOGS",
        f"Líneas estructuradas: {sum(f.structured_lines for f in result.files)} | Texto: {sum(f.text_lines for f in result.files)} | Fallos de parseo: {sum(f.parse_errors for f in result.files)}",
        f"Bytes leídos: {result.bytes_read} | Incidencias sin detalle: {result.issues_omitted} | Muestras limitadas globalmente: {result.details_limited}",
        (
            f"Archivos: {len(result.files)} | "
            f"Líneas: {sum(item.lines_read for item in result.files)} | "
            f"Errores: {result.total(Severity.ERROR)} | "
            f"Advertencias: {result.total(Severity.WARNING)} | "
            f"Incidencias de lectura/rutas: {len(result.issues)}"
        ),
        "",
        f"Estado operativo: {'fallido' if result.operational_failed else 'completo'} | Avisos: {sum(not i.blocking for i in result.issues)} | Estricto: {result.strict}",
        "ERRORES  WARNINGS  LÍNEAS  ESTADO     ARCHIVO",
    ]
    for item in result.files:
        state = "completo" if item.complete else "parcial"
        # ascii evita secuencias de control introducidas por nombres de archivo.
        rows.append(
            f"{item.categories[Severity.ERROR].occurrences:7d}  "
            f"{item.categories[Severity.WARNING].occurrences:8d}  "
            f"{item.lines_read:6d}  {state:9s}  {str(item.path)!a}"
        )
    return "\n".join(rows)


class MarkdownRenderer:
    def render(self, result: ScanResult) -> Iterator[str]:
        yield f"{REPORT_MARKER}\n"
        yield "# Reporte de análisis de logs\n\n"
        yield f"Inicio: {result.started_at.isoformat(timespec='seconds')}\n\n"
        if result.finished_at is not None:
            yield f"Fin: {result.finished_at.isoformat(timespec='seconds')}\n\n"
        yield "## Resumen ejecutivo\n\n"
        yield f"Líneas estructuradas: {sum(f.structured_lines for f in result.files)}; texto: {sum(f.text_lines for f in result.files)}; fallos de parseo: {sum(f.parse_errors for f in result.files)}.\n\n"
        yield f"Bytes leídos: {result.bytes_read}; incidencias sin detalle: {result.issues_omitted}; muestras limitadas globalmente: {result.details_limited}.\n\n"
        yield f"Estado operativo: **{'fallido' if result.operational_failed else 'completo'}**; modo estricto: {result.strict}.\n\n"
        yield "| Métrica | Total |\n| --- | ---: |\n"
        yield f"| Archivos procesados (incluye parciales) | {len(result.files)} |\n"
        yield f"| Líneas leídas | {sum(f.lines_read for f in result.files)} |\n"
        yield f"| Errores | {result.total(Severity.ERROR)} |\n"
        yield f"| Advertencias | {result.total(Severity.WARNING)} |\n"
        yield f"| Incidencias de lectura/rutas | {len(result.issues)} |\n"
        yield (
            "\nLos totales cuentan coincidencias no superpuestas por categoría, "
            "sin distinguir mayúsculas. Una línea puede aportar varias "
            "coincidencias y pertenecer a ambas categorías. Las evidencias son "
            "muestras limitadas; los contadores incluyen todas las coincidencias "
            "de las líneas clasificadas correctamente. Los archivos parciales pueden "
            "incluir líneas leídas sin clasificar.\n\n"
        )
        yield "## Desglose por archivo\n\n"
        for item in result.files:
            yield f"- {_safe(str(item.path))}: codificación {_safe(item.encoding)}, compresión {item.compression}, líneas con pérdida {item.decode_issues}.\n"
        yield "\n"
        yield "| Archivo | Líneas | Errores | Warnings | Estado | Latin-1 |\n"
        yield "| --- | ---: | ---: | ---: | --- | ---: |\n"
        for item in result.files:
            yield (
                f"| {_safe(str(item.path))} | {item.lines_read} | "
                f"{item.categories[Severity.ERROR].occurrences} | "
                f"{item.categories[Severity.WARNING].occurrences} | "
                f"{'Completo' if item.complete else 'Parcial'} | "
                f"{item.fallback_lines} |\n"
            )
        for severity, title in (
            (Severity.ERROR, "Errores"),
            (Severity.WARNING, "Warnings"),
        ):
            yield f"\n## {title} ({result.total(severity)})\n\n"
            if not result.total(severity):
                yield "Sin coincidencias.\n\n"
            for item in result.files:
                category = item.categories[severity]
                if not category.occurrences:
                    continue
                yield f"### {_safe(str(item.path))}\n\n"
                yield (
                    f"Coincidencias: **{category.occurrences}**; "
                    f"líneas afectadas: **{category.matching_lines}**.\n\n"
                )
                for evidence in category.evidence:
                    yield (
                        f"- Línea {evidence.line_number} "
                        f"({evidence.occurrences} coincidencias): "
                        f"{_safe(evidence.text)}\n"
                    )
                omitted = category.matching_lines - len(category.evidence)
                if omitted:
                    yield f"\nOtras {omitted} líneas con coincidencias sin detalle.\n"
                yield "\n"
        yield "## Incidencias de lectura y rutas\n\n"
        if not result.issues:
            yield "Sin incidencias.\n"
        for issue in result.issues:
            level = "Error" if issue.blocking else "Aviso"
            yield f"- {level} [{_safe(issue.code)}] {_safe(str(issue.path))}: {_safe(issue.message)}\n"


def write_report(path: Path, result: ScanResult, renderer: ReportRenderer) -> None:
    """Publica el reporte completo atómicamente, sin sobrescribir archivos.

    El enlace duro evita la carrera entre comprobar existencia y publicar.
    El temporal se crea en el mismo directorio, con permisos privados (0600).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            for chunk in renderer.render(result):
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
