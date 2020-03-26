from .base_pass import BasePass
from .inline import InlinePass
from .deadcode import DeadCodePass
from .copy_propagation import CopyPropagationPass
from .record_to_vars import RecordToVarsPass
from .clean_imports import CleanImportsPass
from .unused_vars import UnusedVarsPass
from .remove_suffixes import RemoveSuffixesPass

PASSES = [
    InlinePass, DeadCodePass, CopyPropagationPass, RecordToVarsPass,
    CleanImportsPass, UnusedVarsPass, RemoveSuffixesPass
]
