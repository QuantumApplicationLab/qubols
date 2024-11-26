from sympy.matrices import Matrix
from sympy.polys import Poly
from copy import deepcopy
import numpy as np
from typing import Optional, Union, Dict, Tuple, List
from dwave.samplers import SimulatedAnnealingSampler
import dimod
from .qubo_poly import QUBO_POLY
from .mixed_solution_vector import MixedSolutionVector_V2 as MixedSolutionVector


class QUBO_POLY_MIXED(QUBO_POLY):

    def __init__(
        self,
        mixed_solution_vectors: MixedSolutionVector,
        options: Optional[Union[Dict, None]] = None,
    ):
        """Solve the following equation

        ..math:
            P_0 + P_1 x + P_2 x^2 + ... + P_n x^n = 0

        Args:
            mixed_solution_vectors (MixedSolutionVector): Solution vector for the varialbes
            options (Optional[Union[Dict, None]], optional): dictionary of options for solving the system. Defaults to None.
        """
        default_solve_options = {
            "sampler": SimulatedAnnealingSampler(),
            "num_reads": 100,
            "verbose": False,
        }

        self.options = self._validate_solve_options(
            deepcopy(options), default_solve_options
        )
        self.sampler = self.options.pop("sampler")
        self.mixed_solution_vectors = mixed_solution_vectors

    def create_bqm(self, matrices: Tuple, strength: float = 10) -> dimod.BQM:
        """Create the bqm from the matrices

        Args:
            matrices (tuple): matrix of the system
            stregth (float): couplign stregth for the substitution. Default 10

        Returns:
            dimod.bqm: binary quadratic model
        """

        self.matrices = matrices
        self.num_variables = self.matrices[1].shape[1]

        self.x = self.mixed_solution_vectors.create_polynom_vector()
        self.extract_all_variables()

        return self.create_qubo_matrix(self.x, strength=strength)

    def sample_bqm(self, bqm: dimod.bqm, num_reads: int) -> dimod.SampleSet:
        """Sample the bqm"""
        sampleset = self.sampler.sample(bqm, num_reads=num_reads)
        self.create_variables_mapping(sampleset)
        return sampleset

    def solve(self, matrices: Tuple, strength: float = 10) -> List:
        """Solve the system of equations

        Args:
            matrices (Tuple): Matrices of the system
            strength (float, optional): Strength of the susbtitution. Defaults to 10.

        Returns:
            List: Solution of the system
        """

        # create the bqm
        self.qubo_dict = self.create_bqm(matrices, strength=strength)

        # sample the bqm
        self.sampleset = self.sample_bqm(
            self.qubo_dict, num_reads=self.options["num_reads"]
        )
        self.lowest_sol = self.sampleset.lowest()

        # sample the systen and return the solution
        return self.decode_solution(self.lowest_sol.record[0][0])

    def extract_all_variables(self):
        """Extracs all the variable names and expressions"""
        self.all_vars = []
        self.all_expr = []
        for var in self.x:
            expr = [(str(k), v) for k, v in var.as_coefficients_dict().items()]
            self.all_expr.append(expr)
            self.all_vars += [str(k) for k in var.as_coefficients_dict().keys()]

    def create_polynom(self, x: np.ndarray) -> Poly:
        """Creates the polynom from the matrices

        Args:
            x (np.ndarray):

        Returns:
            Poly: a polynom
        """
        self.num_equations = self.matrices[1].shape[0]
        polynom = Matrix([0] * self.num_equations)

        for imat, matrix in enumerate(self.matrices):

            for idx, val in zip(matrix.coords.T, matrix.data):
                if imat == 0:
                    polynom[idx[0]] += val
                else:
                    polynom[idx[0]] += val * x[idx[1:]].prod()
        return polynom

    def create_qubo_matrix(
        self, x: np.ndarray, strength: float = 10, prec: Union[float, None] = None
    ) -> dimod.BQM:
        """Create the QUBO dictionary requried by dwave solvers
        to solve the polynomial equation P0 + P1 x + P2 x^2 + ... = 0

        Args:
            x (np.ndarray): x vector
            strength (int, optional): strength of the substitution. Defaults to 10.
            prec (floa, optional):precision. Defaults to None.

        Returns:
            dimod.BQM: Binary quadratic model
        """
        polynom = self.create_polynom(np.array(x))

        polynom = polynom.T @ polynom

        polynom = polynom[0]
        polynom = polynom.expand()
        polynom = polynom.as_ordered_terms()
        polynom = self.create_poly_dict(polynom, prec=prec)
        bqm = dimod.make_quadratic(polynom, strength=strength, vartype=dimod.BINARY)

        return bqm

    @staticmethod
    def create_poly_dict(polynom: Poly, prec: Union[float, None] = None) -> Dict:
        """Creates a dict from the sympy polynom

        Args:
            polynom (Poly): polynom of the system
            prec (float,None): precision of the terms to keep

        Returns:
            Dict: dictionary represetnation of the polynom
        """
        out = dict()

        for term in polynom:
            m = term.args
            if len(m) == 0:
                continue

            if len(m) == 2:
                varname = str(m[1])
                tmp = varname.split("**")
                if len(tmp) == 1:
                    exponent = 1
                else:
                    varname, exponent = tmp
                    exponent = int(exponent)
                key = (varname,) * exponent

            elif len(m) > 2:
                key = tuple()
                for mi in m[1:]:
                    mi = str(mi)
                    tmp = mi.split("**")
                    if len(tmp) == 1:
                        key += (tmp[0],)
                    if len(tmp) == 2:
                        varname = tmp[0]
                        exp = int(tmp[1])
                        key += (varname,) * exp

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

    def decode_solution(self, data: np.ndarray) -> np.ndarray:
        """Decodes the solution vector

        Args:
            data (np.ndarray): sampled values

        Returns:
            np.ndarray: numerical values for the solution
        """
        return self.mixed_solution_vectors.decode_solution(data[self.index_variables])

    def create_variables_mapping(self, sol: dimod.SampleSet):
        """generates the index of variables in the solution vector

        Args:
            sol (dimod.Sampleset): sampleset from the sampler
        """
        # extract the data of the original variables
        self.index_variables, self.mapped_variables = [], []
        for ix, s in enumerate(sol.variables):
            if s in self.all_vars:
                self.index_variables.append(ix)
                self.mapped_variables.append(s)

    def compute_energy(self, vector: np.ndarray, bqm: dimod.BQM) -> Tuple:
        """Compue the QUBO energy of the vector containing the solution of the initial problem

        Args:
            vector (np.ndarray): solution of the problem
        """
        closest_vec = []
        bin_encoding_vector = []
        encoded_variables = []
        for val, svec in zip(vector, self.mixed_solution_vectors.encoded_reals):
            closest_val, bin_encoding = svec.find_closest(val)
            closest_vec.append(closest_val)
            bin_encoding_vector += bin_encoding
            encoded_variables += [str(sv) for sv in svec.variables]

        bqm_input_variables = {}
        for v in bqm.variables:
            if v in encoded_variables:
                idx = encoded_variables.index(v)
                bqm_input_variables[v] = bin_encoding_vector[idx]
            else:
                var_tmp = v.split("*")
                itmp = 0
                for vtmp in var_tmp:
                    idx = encoded_variables.index(vtmp)
                    val = bin_encoding_vector[idx]
                    if itmp == 0:
                        bqm_input_variables[v] = val
                        itmp = 1
                    else:
                        bqm_input_variables[v] *= val

        return (
            closest_vec,
            (bin_encoding_vector, encoded_variables),
            bqm_input_variables,
        ), bqm.energy(bqm_input_variables)
