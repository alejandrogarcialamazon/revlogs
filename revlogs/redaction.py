"""Redacción optativa antes de almacenar evidencias o truncarlas."""

import re
from collections.abc import Sequence

_ASSIGNMENT = re.compile(
    r"""(?i)(["']?(?:password|passwd|secret|token|api[_-]?key|access[_-]?token)["']?\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;}]+)"""
)
_BEARER = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]+")
_CREDENTIALS = re.compile(r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@")
_EMAIL = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}"
)


class Redactor:
    """Reglas fijas y literales; no ejecuta expresiones regulares del usuario."""

    def __init__(self, enabled: bool = False, literals: Sequence[str] = ()) -> None:
        if len(literals) > 64 or any(not x or len(x) > 4096 for x in literals):
            raise ValueError(
                "Redacción: máximo 64 literales no vacíos de 4096 caracteres"
            )
        self.enabled = enabled or bool(literals)
        self.literals = sorted(set(literals), key=len, reverse=True)

    def apply(self, text: str) -> str:
        if not self.enabled:
            return text
        for literal in self.literals:
            text = text.replace(literal, "[REDACTED]")
        text = _ASSIGNMENT.sub(lambda m: m[1] + '"[REDACTED]"', text)
        text = _BEARER.sub(lambda m: m[1] + "[REDACTED]", text)
        text = _CREDENTIALS.sub(lambda m: m[1] + "[REDACTED]@", text)
        return _EMAIL.sub("[REDACTED]", text)
