import libcst as cst
from libcst.metadata import ScopeProvider


class ReplaceNodes(cst.CSTTransformer):
    def __init__(self, replacements):
        self.replacements = replacements

    def on_leave(self, original_node, updated_node):
        return self.replacements.get(original_node, updated_node)


def bulk_rename(mod, targets):
    scopes = cst.MetadataWrapper(mod,
                                 unsafe_skip_copy=True).resolve(ScopeProvider)

    global_scope = scopes[mod]
    all_scopes = set(scopes.values())
    replacements = {}

    # Replace all access in scopes where src is not assigned
    for scope in all_scopes:
        for (src, dst) in targets:
            if scope is global_scope or src not in scope.assignments:
                for access in scope.accesses[src]:
                    replacements[access.node] = cst.Name(dst)

    # Replace all assignments in global scope
    for (src, dst) in targets:
        for assgn in global_scope.assignments[src]:
            replacements[assgn.node] = cst.Name(dst)

    return mod.visit(ReplaceNodes(replacements))


def rename(mod, src, dst):
    return bulk_rename(mod, [(src, dst)])
