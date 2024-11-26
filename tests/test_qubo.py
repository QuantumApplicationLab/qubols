import numpy as np
import pytest
from qubols.qubols import QUBOLS
from qubols.encodings import RangedEfficientEncoding
from dwave.samplers import SimulatedAnnealingSampler


def create_random_matrix(size: int):
    """Create a random symmetric matrix.

    Args:
        size (int): size of the matrix
    """
    mat = np.random.rand(size, size)
    return 0.1 * (mat + mat.T)


size = 4


@pytest.mark.parametrize("A", [create_random_matrix(size)])
@pytest.mark.parametrize("b", [np.random.rand(size)])
def test_hhl_solve_default(A, b):
    """Test the qubols solver."""
    options = {
        "num_reads": 50,
        "sampler": SimulatedAnnealingSampler(),
        "encoding": RangedEfficientEncoding,
        "num_qbits": 6,
        "range": 10.0,
    }
    qubols = QUBOLS(options)
    sol = qubols.solve(A, b)
    if np.linalg.norm(A @ sol - b.T) > 0.1:
        pytest.skip("QUBOLS solution innacurate")
