from inliner.visitors import FindAssignments
from utils import func_to_module


def test_find_assignments_basic():
    def prog():
        x = 1

    FindAssignments()
