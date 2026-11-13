"""Presupuestos de lectura, recorrido y evidencias compartidos por un scan."""

from dataclasses import dataclass


class ResourceLimitError(OSError):
    def __init__(self, message: str, *, stop_scan: bool = False) -> None:
        super().__init__(message)
        self.stop_scan = stop_scan


@dataclass(frozen=True)
class ScanLimits:
    max_line_bytes: int = 1024 * 1024
    max_file_bytes: int = 1024**3
    max_total_bytes: int = 4 * 1024**3
    max_files: int = 10_000
    max_entries: int = 100_000
    max_depth: int = 32
    max_total_details: int = 10_000
    max_issues: int = 1000

    def __post_init__(self) -> None:
        for name in (
            "max_line_bytes",
            "max_file_bytes",
            "max_total_bytes",
            "max_files",
            "max_entries",
            "max_issues",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} debe ser positivo")
        if self.max_depth < 0 or self.max_total_details < 0:
            raise ValueError("Profundidad y evidencias deben ser no negativas")
        if self.max_depth > 128:
            raise ValueError("max_depth no puede superar 128 en el recorrido recursivo")


@dataclass
class ScanBudget:
    limits: ScanLimits
    bytes_read: int = 0
    files: int = 0
    entries: int = 0
    details: int = 0
    stopped: bool = False

    def visit(self) -> None:
        if self.entries >= self.limits.max_entries:
            raise ResourceLimitError(
                "Límite de entradas del recorrido alcanzado", stop_scan=True
            )
        self.entries += 1

    def admit_file(self) -> None:
        if self.files >= self.limits.max_files:
            raise ResourceLimitError("Límite de archivos alcanzado", stop_scan=True)
        self.files += 1
