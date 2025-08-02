from __future__ import annotations

from virtualenv.activation.via_template import ViaTemplateActivator


class FishActivator(ViaTemplateActivator):
    def templates(self):
        yield "activate.fish"

    def generate(self, creator):
        replacements = self.replacements(creator, creator.bin_dir)

        tcl_tk_setup = []
        if creator.interpreter.tcl_lib:
            tcl_tk_setup.append(f"if set -q TCL_LIBRARY; set -gx _OLD_VIRTUAL_TCL_LIBRARY $TCL_LIBRARY; end")
            tcl_tk_setup.append(f"set -gx TCL_LIBRARY '{creator.interpreter.tcl_lib}'")
        if creator.interpreter.tk_lib:
            tcl_tk_setup.append(f"if set -q TK_LIBRARY; set -gx _OLD_VIRTUAL_TK_LIBRARY $TK_LIBRARY; end")
            tcl_tk_setup.append(f"set -gx TK_LIBRARY '{creator.interpreter.tk_lib}'")
        replacements["__TCL_TK_SETUP__"] = "\n".join(tcl_tk_setup)

        tcl_tk_teardown = []
        if creator.interpreter.tcl_lib:
            tcl_tk_teardown.append(
                'if test -n "$_OLD_VIRTUAL_TCL_LIBRARY"; set -gx TCL_LIBRARY "$_OLD_VIRTUAL_TCL_LIBRARY"; set -e _OLD_VIRTUAL_TCL_LIBRARY; else; set -e TCL_LIBRARY; end',
            )
        if creator.interpreter.tk_lib:
            tcl_tk_teardown.append(
                'if test -n "$_OLD_VIRTUAL_TK_LIBRARY"; set -gx TK_LIBRARY "$_OLD_VIRTUAL_TK_LIBRARY"; set -e _OLD_VIRTUAL_TK_LIBRARY; else; set -e TK_LIBRARY; end',
            )
        replacements["__TCL_TK_TEARDOWN__"] = "; ".join(tcl_tk_teardown)

        text = self.instantiate_template(replacements, "activate.fish", creator)
        (creator.bin_dir / "activate.fish").write_text(text, encoding="utf-8")
        return [creator.bin_dir / "activate.fish"]

    def instantiate_template(self, replacements, template, creator):
        text = super().instantiate_template(replacements, template, creator)
        if "__TCL_TK_SETUP__" in replacements:
            text = text.replace(self.quote(replacements["__TCL_TK_SETUP__"]), replacements["__TCL_TK_SETUP__"])
        if "__TCL_TK_TEARDOWN__" in replacements:
            text = text.replace(self.quote(replacements["__TCL_TK_TEARDOWN__"]), replacements["__TCL_TK_TEARDOWN__"])
        return text


__all__ = [
    "FishActivator",
]
