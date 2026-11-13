"""Búsqueda literal y regex personalizadas aisladas con tiempo y memoria acotados."""

import multiprocessing
import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from multiprocessing.connection import Connection
from re import Pattern

from .models import Severity

DEFAULT_ERROR_PATTERNS = (r"\b(?:ERROR|CRITICAL|FATAL)\b",)
DEFAULT_WARNING_PATTERNS = (r"\b(?:WARNING|WARN)\b",)
Counts = dict[Severity, int]
Counter = Callable[[str], Counts]


class SearchError(OSError):
    def __init__(self, message: str, code: str = "search_failure") -> None:
        super().__init__(message)
        self.code = code


def compile_rules(
    errors: Sequence[str], warnings: Sequence[str]
) -> dict[Severity, Pattern[str]]:
    rules: dict[Severity, Pattern[str]] = {}
    for severity, patterns in ((Severity.ERROR, errors), (Severity.WARNING, warnings)):
        if not patterns:
            raise ValueError("Se requiere al menos un patrón por categoría")
        rule = re.compile(
            "|".join(f"(?:{pattern})" for pattern in patterns), re.IGNORECASE
        )
        if rule.search(""):
            raise ValueError("Los patrones no deben coincidir con texto vacío")
        rules[severity] = rule
    return rules


def count_rules(rules: dict[Severity, Pattern[str]], line: str) -> Counts:
    return {
        severity: sum(1 for match in rule.finditer(line) if match.end() > match.start())
        for severity, rule in rules.items()
    }


def _worker(
    connection: Connection, errors: list[str], warnings: list[str], memory_mib: int
) -> None:
    try:
        import resource

        cap = memory_mib * 1024**2
        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        if hard != resource.RLIM_INFINITY:
            cap = min(cap, hard)
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        try:
            rules = compile_rules(errors, warnings)
        except re.error as exc:
            connection.send(("regex_error", str(exc)))
            return
        except (ValueError, RecursionError, MemoryError) as exc:
            connection.send(("value_error", str(exc) or "Sin memoria para compilar"))
            return
        connection.send(("ready", ""))
        while True:
            line = connection.recv()
            connection.send(
                (
                    "counts",
                    {
                        key.value: value
                        for key, value in count_rules(rules, line).items()
                    },
                )
            )
    except (EOFError, BrokenPipeError):
        pass
    except BaseException:
        try:
            connection.send(("failure", "El worker no pudo completar la búsqueda"))
        except (OSError, MemoryError):
            pass
    finally:
        connection.close()


class RegexWorker:
    def __init__(
        self, errors: list[str], warnings: list[str], timeout: float, memory_mib: int
    ) -> None:
        self.timeout = timeout
        context = multiprocessing.get_context("spawn")
        self.connection, child = context.Pipe()
        self.process = context.Process(
            target=_worker, args=(child, errors, warnings, memory_mib), daemon=True
        )
        try:
            self.process.start()
            child.close()
            if not self.connection.poll(5):
                raise ValueError("Timeout de arranque/compilación de regex")
            kind, message = self.connection.recv()
            if kind == "regex_error":
                raise re.error(str(message))
            if kind != "ready":
                raise ValueError(str(message))
        except (EOFError, OSError) as exc:
            child.close()
            self.close()
            raise ValueError("Worker no disponible durante la compilación") from exc
        except BaseException:
            child.close()
            self.close()
            raise

    def close(self) -> None:
        self.connection.close()
        if self.process.pid is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(0.2)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(0.2)
            self.process.close()

    def count(self, line: str) -> Counts:
        try:
            self.connection.send(line)
            if not self.connection.poll(self.timeout):
                raise SearchError(
                    "Tiempo máximo de regex por línea excedido", "regex_timeout"
                )
            kind, payload = self.connection.recv()
            if kind != "counts":
                raise SearchError("El worker no pudo completar la búsqueda")
            return {Severity(key): int(value) for key, value in payload.items()}
        except (EOFError, BrokenPipeError, OSError) as exc:
            if isinstance(exc, SearchError):
                raise
            raise SearchError("Worker de regex no disponible") from exc


class PatternMatcher:
    def __init__(
        self,
        errors: Sequence[str],
        warnings: Sequence[str],
        *,
        error_literals: Sequence[str] = (),
        warning_literals: Sequence[str] = (),
        timeout: float = 0.5,
        memory_mib: int = 256,
    ) -> None:
        if not 0 < timeout <= 60 or not 64 <= memory_mib <= 4096:
            raise ValueError("Timeout debe ser (0,60] y memoria regex 64–4096 MiB")
        all_patterns = (*errors, *warnings, *error_literals, *warning_literals)
        if len(all_patterns) > 64 or any(
            len(pattern) > 4096 for pattern in all_patterns
        ):
            raise ValueError(
                "Máximo 64 patrones/literales y 4096 caracteres por entrada"
            )
        if any(not literal for literal in (*error_literals, *warning_literals)):
            raise ValueError("Los literales no pueden estar vacíos")
        self.errors = [*errors, *(re.escape(value) for value in error_literals)]
        self.warnings = [*warnings, *(re.escape(value) for value in warning_literals)]
        self.isolated = (
            tuple(errors) != DEFAULT_ERROR_PATTERNS
            or tuple(warnings) != DEFAULT_WARNING_PATTERNS
        )
        self.timeout = timeout
        self.memory_mib = memory_mib
        self.rules = {} if self.isolated else compile_rules(self.errors, self.warnings)
        if self.isolated:
            worker = RegexWorker(self.errors, self.warnings, timeout, memory_mib)
            worker.close()

    @contextmanager
    def session(self) -> Iterator[Counter]:
        worker: RegexWorker | None = None

        def counter(line: str) -> Counts:
            nonlocal worker
            if not self.isolated:
                return count_rules(self.rules, line)
            if worker is None:
                try:
                    worker = RegexWorker(
                        self.errors, self.warnings, self.timeout, self.memory_mib
                    )
                except (OSError, ValueError, re.error) as exc:
                    raise SearchError("No se pudo iniciar el worker de regex") from exc
            return worker.count(line)

        try:
            yield counter
        finally:
            if worker is not None:
                worker.close()
