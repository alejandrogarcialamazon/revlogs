"""Interfaz de línea de comandos y códigos de salida para automatización."""

import argparse
import logging
import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from .analyzer import (
    DEFAULT_ERROR_PATTERNS,
    DEFAULT_WARNING_PATTERNS,
    LogAnalyzer,
)
from .models import Severity
from .reader import DEFAULT_PATHS
from .reports import MarkdownRenderer, console_summary, write_report

LOGGER = logging.getLogger(__name__)


def _nonnegative(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("Debe ser mayor o igual a cero")
    return number


def _positive(value: str) -> int:
    number = _nonnegative(value)
    if number == 0:
        raise argparse.ArgumentTypeError("Debe ser mayor que cero")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analiza logs de texto y genera un reporte Markdown."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Archivos/directorios; por defecto se usan rutas típicas de Linux",
    )
    parser.add_argument("-r", "--recursive", action="store_true")
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="GLOB",
        help="Incluir archivos por nombre o ruta relativa; repetible",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="Excluir archivos o directorios; prevalece sobre --include",
    )
    parser.add_argument(
        "--include-reports",
        action="store_true",
        help="Permitir explícitamente el análisis de reportes de revlogs",
    )
    parser.add_argument("-o", "--output", type=Path, help="Reporte .md de destino")
    parser.add_argument(
        "--max-details",
        type=_nonnegative,
        default=50,
        help="Máximo de líneas de evidencia por archivo/categoría (50; 0: ninguna)",
    )
    parser.add_argument(
        "--max-excerpt-chars",
        type=_positive,
        default=1000,
        help="Máximo de caracteres por evidencia (1000)",
    )
    parser.add_argument(
        "--error-pattern",
        action="append",
        default=[],
        metavar="REGEX",
        help="Agrega un patrón de error; se puede repetir",
    )
    parser.add_argument(
        "--warning-pattern",
        action="append",
        default=[],
        metavar="REGEX",
        help="Agrega un patrón de advertencia; se puede repetir",
    )
    parser.add_argument(
        "--fail-on",
        choices=("error", "warning"),
        help="Devuelve 1 si hay errores, o errores/advertencias respectivamente",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if any(not pattern.strip() for pattern in (*args.include, *args.exclude)):
        parser.error("Los patrones de inclusión/exclusión no pueden estar vacíos")
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    output = args.output or Path("reports") / (
        f"revlogs_{datetime.now().astimezone():%Y%m%d_%H%M%S_%f}.md"
    )
    output = output.expanduser().absolute()
    if output.suffix.lower() != ".md":
        parser.error("El archivo de salida debe tener extensión .md")
    # No se permite reemplazar un archivo existente: podría ser un log de entrada.
    if output.exists() or output.is_symlink():
        parser.error(f"El destino ya existe: {output}")
    try:
        analyzer = LogAnalyzer(
            error_patterns=(*DEFAULT_ERROR_PATTERNS, *args.error_pattern),
            warning_patterns=(*DEFAULT_WARNING_PATTERNS, *args.warning_pattern),
            max_details=args.max_details,
            max_excerpt_chars=args.max_excerpt_chars,
        )
    except (re.error, ValueError) as exc:
        parser.error(f"Patrones o límites inválidos: {exc}")
    try:
        result = analyzer.scan(
            args.paths or DEFAULT_PATHS,
            recursive=args.recursive,
            excluded=(output,),
            include_patterns=args.include,
            exclude_patterns=args.exclude,
            skip_reports=not args.include_reports,
        )
        print(console_summary(result))
        write_report(output, result, MarkdownRenderer())
        print(f"\nReporte: {output}")
    except OSError as exc:
        LOGGER.error("No se pudo completar la operación: %s", exc)
        return 2
    except KeyboardInterrupt:
        LOGGER.warning("Análisis interrumpido")
        return 130
    if result.issues or not result.files:
        return 2
    if args.fail_on and result.total(Severity.ERROR):
        return 1
    if args.fail_on == "warning" and result.total(Severity.WARNING):
        return 1
    return 0
