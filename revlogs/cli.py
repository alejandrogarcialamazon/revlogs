"""Interfaz de línea de comandos y códigos de salida para automatización."""

import argparse
import logging
import re
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from .analyzer import (
    DEFAULT_ERROR_PATTERNS,
    DEFAULT_WARNING_PATTERNS,
    LogAnalyzer,
)
from .configuration import load_config
from .exports import RENDERERS
from .input_formats import ReadOptions
from .limits import ScanLimits
from .models import Severity
from .reader import DEFAULT_PATHS
from .reports import console_summary, write_report

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
    parser.add_argument("--config", type=Path, help="Archivo TOML explícito")
    parser.add_argument(
        "--report-format", choices=("markdown", "json", "csv"), default="markdown"
    )
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--csv-output", type=Path)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Archivos/directorios; por defecto se usan rutas típicas de Linux",
    )
    parser.add_argument(
        "-r", "--recursive", action=argparse.BooleanOptionalAction, default=False
    )
    parser.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Tratar avisos operativos como errores",
    )
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
        action=argparse.BooleanOptionalAction,
        default=False,
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
    parser.add_argument(
        "-v", "--verbose", action=argparse.BooleanOptionalAction, default=False
    )
    parser.add_argument(
        "--compression", choices=("auto", "none", "gzip"), default="auto"
    )
    parser.add_argument("--encoding", default="auto")
    parser.add_argument(
        "--decode-errors", choices=("strict", "replace", "ignore"), default="strict"
    )
    parser.add_argument(
        "--format", choices=("text", "auto", "json", "syslog"), default="text"
    )
    parser.add_argument("--level-field", action="append", default=None)
    parser.add_argument(
        "--numeric-levels", choices=("python", "syslog"), default="python"
    )
    parser.add_argument("--error-literal", action="append", default=[], metavar="TEXT")
    parser.add_argument(
        "--warning-literal", action="append", default=[], metavar="TEXT"
    )
    parser.add_argument(
        "--regex-timeout",
        type=float,
        default=0.5,
        help="Timeout por línea en segundos (0,60]",
    )
    parser.add_argument("--regex-memory-mib", type=_positive, default=256)
    defaults = ScanLimits()
    for name in (
        "max_line_bytes",
        "max_file_bytes",
        "max_compressed_bytes",
        "max_total_bytes",
        "max_files",
        "max_entries",
        "max_depth",
        "max_total_details",
        "max_issues",
    ):
        parser.add_argument(
            "--" + name.replace("_", "-"),
            type=_nonnegative
            if name in ("max_depth", "max_total_details")
            else _positive,
            default=getattr(defaults, name),
        )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--help" in arguments or "-h" in arguments:
        parser.parse_args(arguments)
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", type=Path)
    config_args, _ = pre.parse_known_args(arguments)
    try:
        configured = load_config(config_args.config) if config_args.config else {}
    except (OSError, ValueError) as exc:
        parser.error(f"No se pudo cargar la configuración: {exc}")
    defaults = vars(parser.parse_args([]))
    explicit_parser = build_parser()
    for action in explicit_parser._actions:
        action.default = argparse.SUPPRESS
    explicit = vars(explicit_parser.parse_args(arguments))
    args = argparse.Namespace(**(defaults | configured | explicit))
    if args.format in ("json", "syslog") and any(
        (
            args.error_pattern,
            args.warning_pattern,
            args.error_literal,
            args.warning_literal,
        )
    ):
        parser.error("Patrones y literales solo se aplican a --format text o auto")
    if any(not pattern.strip() for pattern in (*args.include, *args.exclude)):
        parser.error("Los patrones de inclusión/exclusión no pueden estar vacíos")
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    suffixes = {"markdown": ".md", "json": ".json", "csv": ".csv"}
    output = args.output or Path("reports") / (
        f"revlogs_{datetime.now().astimezone():%Y%m%d_%H%M%S_%f}{suffixes[args.report_format]}"
    )
    requested = [(output, args.report_format)]
    if args.json_output is not None:
        requested.append((args.json_output, "json"))
    if args.csv_output is not None:
        requested.append((args.csv_output, "csv"))
    outputs = [(path.expanduser().absolute(), kind) for path, kind in requested]
    try:
        if len({path.resolve() for path, _ in outputs}) != len(outputs):
            parser.error("Los destinos de reportes deben ser diferentes")
        for path, kind in outputs:
            if path.suffix.lower() != suffixes[kind]:
                parser.error(f"Extensión de salida incompatible con {kind}")
            if path.exists() or path.is_symlink():
                parser.error(f"El destino ya existe: {path}")
    except (OSError, RuntimeError) as exc:
        parser.error(f"Destino de reporte inválido: {exc}")
    try:
        analyzer = LogAnalyzer(
            error_patterns=(*DEFAULT_ERROR_PATTERNS, *args.error_pattern),
            warning_patterns=(*DEFAULT_WARNING_PATTERNS, *args.warning_pattern),
            max_details=args.max_details,
            max_excerpt_chars=args.max_excerpt_chars,
            error_literals=args.error_literal,
            warning_literals=args.warning_literal,
            regex_timeout=args.regex_timeout,
            regex_memory_mib=args.regex_memory_mib,
            format=args.format,
            level_fields=args.level_field or ("level", "severity", "log.level"),
            numeric_levels=args.numeric_levels,
            read_options=ReadOptions(
                args.compression, args.encoding, args.decode_errors
            ),
            limits=ScanLimits(
                **{
                    name: getattr(args, name)
                    for name in ScanLimits.__dataclass_fields__
                }
            ),
        )
    except (re.error, ValueError) as exc:
        parser.error(f"Patrones o límites inválidos: {exc}")
    try:
        result = analyzer.scan(
            args.paths or DEFAULT_PATHS,
            recursive=args.recursive,
            excluded=tuple(path for path, _ in outputs),
            include_patterns=args.include,
            exclude_patterns=args.exclude,
            skip_reports=not args.include_reports,
            optional_paths=not args.paths,
            strict=args.strict,
        )
        print(console_summary(result))
        for path, kind in outputs:
            write_report(path, result, RENDERERS[kind]())
            print(f"\nReporte {kind}: {path}")
    except OSError as exc:
        LOGGER.error("No se pudo completar la operación: %s", exc)
        return 2
    except KeyboardInterrupt:
        LOGGER.warning("Análisis interrumpido")
        return 130
    if result.operational_failed:
        return 2
    if args.fail_on and result.total(Severity.ERROR):
        return 1
    if args.fail_on == "warning" and result.total(Severity.WARNING):
        return 1
    return 0
