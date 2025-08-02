from __future__ import annotations

from virtualenv.activation.via_template import ViaTemplateActivator


class CShellActivator(ViaTemplateActivator):
    @classmethod
    def supports(cls, interpreter):
        return interpreter.os != "nt"

    def templates(self):
        yield "activate.csh"

    @staticmethod
    def quote(path):
        return f"'{path}'" if path else "''"


__all__ = [
    "CShellActivator",
]
