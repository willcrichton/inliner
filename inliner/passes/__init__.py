from .array_index import ArrayIndexPass
from .clean_imports import CleanImportsPass
from .copy_propagation import CopyPropagationPass
from .deadcode import DeadcodePass
from .expand_self import ExpandSelfPass
from .expand_tuples import ExpandTuplesPass
from .inline import InlinePass
from .lifetimes import LifetimesPass
from .simplify_varargs import SimplifyVarargsPass
from .unread_vars import UnreadVarsPass

PASSES = [
    ArrayIndexPass,
    CleanImportsPass,
    CopyPropagationPass,
    DeadcodePass,
    ExpandSelfPass,
    ExpandTuplesPass,
    InlinePass,
    LifetimesPass,
    SimplifyVarargsPass,
    UnreadVarsPass
] # yapf: disable
