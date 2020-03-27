from typing import Dict
import inspect

import libcst as cst
import libcst.matchers as m

from ..common import parse_expr, parse_module, a2s


class CollectImports(cst.CSTVisitor):
    imprts: Dict[str, cst.BaseSmallStatement]
    mod: str

    def __init__(self, mod):
        self.imprts = {}
        self.mod = mod
        self.toplevel = 0

    def visit_IndentedBlock(self, node):
        self.toplevel += 1

    def leave_IndentedBlock(self, node):
        self.toplevel -= 1

    def visit_Assign(self, node) -> None:
        if (m.matches(node, m.Assign(targets=[m.AssignTarget(m.Name())]))
                and self.toplevel == 0):
            name = node.targets[0].target
            self.imprts[name.value] = cst.ImportFrom(
                module=parse_expr(self.mod),
                names=[cst.ImportAlias(name=name, asname=None)])

    def visit_Import(self, node) -> None:
        for alias in node.names:
            name = alias.asname.name.value if alias.asname is not None else alias.name.value

            # Regenerate alias to avoid trailing comma issue
            alias = cst.ImportAlias(name=alias.name, asname=alias.asname)
            self.imprts[name] = cst.Import(names=[alias])

    def visit_ImportFrom(self, node) -> None:
        for alias in node.names:
            name = alias.asname.name.value if alias.asname is not None else alias.name.value

            level = len(node.relative)
            if level > 0:
                parts = self.mod.split('.')
                mod_level = '.'.join(
                    parts[:-level]) if len(parts) > 1 else parts[0]
                if node.module is not None:
                    module = parse_expr(f'{mod_level}.{a2s(node.module)}')
                else:
                    module = parse_expr(mod_level)
            else:
                module = node.module

            # Regenerate alias to avoid trailing comma issue
            alias = cst.ImportAlias(name=alias.name, asname=alias.asname)
            self.imprts[name] = cst.ImportFrom(module=module, names=[alias])


_IMPORT_CACHE = {}


def collect_imports(obj):
    mod = inspect.getmodule(obj)
    if mod is None:
        return []

    mod_name = mod.__name__
    if mod_name in _IMPORT_CACHE:
        return _IMPORT_CACHE[mod_name]

    import_collector = CollectImports(mod=mod_name)
    obj_mod = parse_module(open(inspect.getsourcefile(obj)).read())
    obj_mod.visit(import_collector)
    imprts = import_collector.imprts
    _IMPORT_CACHE[mod_name] = imprts
    return imprts
