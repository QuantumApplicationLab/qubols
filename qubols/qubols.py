from sympy.matrices import Matrix, SparseMatrix
import numpy as np
from qubols.encodings import RangedEfficientEncoding
from typing import Optional, Union, Dict
from dwave.samplers import SimulatedAnnealingSampler
import scipy.sparse as spsp
from .solution_vector import SolutionVector


class QUBOLS:
    def __init__(self, options: Optional[Union[Dict, None]] = None):
        """Linear Solver using QUBO

        Args:
            options: dictionary of options for solving the linear system
        """

        default_solve_options = {
            "sampler": SimulatedAnnealingSampler(),
            "encoding": RangedEfficientEncoding,
            "range": 1.0,
            "offset": 0.0,
            "num_qbits": 11,
            "num_reads": 100,
            "verbose": False,
        }
        self.options = self._validate_solve_options(options, default_solve_options)
        self.sampler = self.options.pop("sampler")

    @staticmethod
    def _validate_solve_options(
        options: Union[Dict, None], default_solve_options: Dict
    ) -> Dict:
        """validate the options used for the solve methods

        Args:
            options (Union[Dict, None]): options
        """
        valid_keys = default_solve_options.keys()

        if options is None:
            options = default_solve_options

        else:
            for k in options.keys():
                if k not in valid_keys:
                    raise ValueError(
                        "Option {k} not recognized, valid keys are {valid_keys}"
                    )
            for k in valid_keys:
                if k not in options.keys():
                    options[k] = default_solve_options[k]

        return options

    def solve(self, matrix: np.ndarray, vector: np.ndarray):
        """Solve the linear system

        Args:
            sampler (_type_, optional): _description_. Defaults to SimulatedAnnealingSampler().
            encoding (_type_, optional): _description_. Defaults to RealUnitQbitEncoding.
            nqbit (int, optional): _description_. Defaults to 10.

        Returns:
            _type_: _description_
        """
        if not isinstance(matrix, np.ndarray):
            matrix = matrix.todense()

        self.A = matrix
        self.b = vector
        self.size = self.A.shape[0]

        if not isinstance(self.options["offset"], list):
            self.options["offset"] = [self.options["offset"]] * self.size

        self.solution_vector = self.create_solution_vector()

        self.x = self.solution_vector.create_polynom_vector()
        self.qubo_dict = self.create_qubo_matrix(self.x)

        self.sampleset = self.sampler.sample_qubo(
            self.qubo_dict, num_reads=self.options["num_reads"]
        )
        self.lowest_sol = self.sampleset.lowest()

        return self.solution_vector.decode_solution(self.lowest_sol.record[0][0])

    def create_solution_vector(self):
        """initialize the soluion vector"""
        return SolutionVector(
            size=self.size,
            nqbit=self.options["num_qbits"],
            encoding=self.options["encoding"],
            range=self.options["range"],
            offset=self.options["offset"],
        )

    def create_qubo_matrix(self, x, prec=None):
        """Create the QUBO dictionary requried by dwave solvers
        to solve the linear system

        A x = b

        Args:
            Anp (np.array): matrix of the linear system
            bnp (np.array): righ hand side of the linear system
            x (sympy.Matrix): unknown

        Returns:
            _type_: _description_
        """

        cst_shift = self.A @ self.options["offset"]

        if isinstance(self.A, spsp.spmatrix):
            A = SparseMatrix(*self.A.shape, dict(self.A.todok().items()))
        else:
            A = Matrix(self.A)

        if isinstance(self.b, spsp.spmatrix):
            b = SparseMatrix(*self.b.shape, dict(self.b.todok().items()))
            b -= cst_shift.reshape(-1, 1)
        else:
            b = Matrix(self.b)
            b -= cst_shift.reshape(-1, 1)

        polynom = x.T @ A.T @ A @ x - x.T @ A.T @ b - b.T @ A @ x + b.T @ b
        polynom = polynom[0]
        polynom = polynom.expand()
        polynom = polynom.as_ordered_terms()

        out = dict()

        for term in polynom:
            m = term.args
            if len(m) == 0:
                continue

            if len(m) == 2:
                varname = str(m[1])
                varname = varname.split("**")[0]
                key = (varname, varname)

            elif len(m) == 3:
                key = (str(m[1]), str(m[2]))

            if key not in out:
                out[key] = 0.0

            out[key] += m[0]

        if prec is None:
            return out

        elif prec is not None:
            nremoved = 0
            out_cpy = dict()
            for k, v in out.items():
                if np.abs(v) > prec:
                    out_cpy[k] = v
                else:
                    nremoved += 1
            print("Removed %d elements" % nremoved)
            return out_cpy
