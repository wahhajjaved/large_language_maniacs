# Copyright (C) 2014 Jan Blechta
#
# This file is part of FENaPack.
#
# FENaPack is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# FENaPack is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with FENaPack.  If not, see <http://www.gnu.org/licenses/>.

from dolfin import (PETScKrylovSolver, compile_extension_module,
        as_backend_type, PETScMatrix, SystemAssembler)
from petsc4py import PETSc

__all__ = ['FieldSplitSolver']

class FieldSplitSolver(PETScKrylovSolver):
    def __init__(self, space):
        # Setup GMRES with RIGHT preconditioning
        ksp = PETSc.KSP()
        ksp.create(PETSc.COMM_WORLD)
        ksp.setType(PETSc.KSP.Type.GMRES)
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        self._ksp = ksp

        # Setup SCHUR with UPPER factorization
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.FIELDSPLIT)
        pc.setFieldSplitType(PETSc.PC.CompositeType.SCHUR)
        pc.setFieldSplitSchurFactType(PETSc.PC.SchurFactType.UPPER)
        is0 = dofmap_dofs_is(space.sub(0).dofmap())
        is1 = dofmap_dofs_is(space.sub(1).dofmap())
        pc.setFieldSplitIS(['u', is0], ['p', is1])
        is0.destroy()
        self._is1 = is1 # Will be needed by Schur PC

        # Init mother class
        PETScKrylovSolver.__init__(self, ksp)

    # Override PETScKrylovSolver::set_operator() method
    def set_operator(self, A):
        PETScKrylovSolver.set_operator(self, A)
        self._ksp.setOperators(as_backend_type(A).mat())

    # Discard PETScKrylovSolver::set_operators() method
    def set_operators(self, *args):
        raise NotImplementedError

    def setup(self, *args):
        # Setup KSP and PC
        ksp = self._ksp
        ksp.setUp()
        pc = ksp.getPC()
        pc.setUp()

        # Get sub-KSPs, sub-PCs
        ksp0, ksp1 = pc.getFieldSplitSubKSP()
        pc0, pc1 = ksp0.getPC(), ksp1.getPC()

        # Setup approximation of 0,0-block inverse
        ksp0.setFromOptions()
        pc0.setFromOptions()

        # Setup approximation of Schur complement inverse
        ksp1.setType(PETSc.KSP.Type.PREONLY)
        pc1.setType(PETSc.PC.Type.PYTHON)
        pc1.setPythonContext(PCD_preconditioner(self._is1, *args))
        self._is1.destroy()


class PCD_preconditioner(object):
    def __init__(self, *args):
        if args:
            self.set_operators(*args)
            self.setup()
    def setup(self):
        self._mp = PETScMatrix()
        self._fp = PETScMatrix()
        self._ap = PETScMatrix()
        # TODO: What are correct BCs?
        assembler = SystemAssembler(self._Mp, self._Lp, self._bcs_Ap)
        assembler.assemble(self._mp)
        assembler = SystemAssembler(self._Fp, self._Lp, self._bcs_Ap)
        assembler.assemble(self._fp)
        assembler = SystemAssembler(self._Ap, self._Lp, self._bcs_Ap)
        assembler.assemble(self._ap)
        self._mp = self._mp.mat().getSubMatrix(self._isp, self._isp)
        self._ap = self._ap.mat().getSubMatrix(self._isp, self._isp)
        self._fp = self._fp.mat().getSubMatrix(self._isp, self._isp)
        self.prepare_factors()
    def apply(self, pc, x, y):
        # y = S^{-1} x = M_p^{-1} F_p  A_p^{-1} x
        self._ksp_ap.solve(x, y)
        # TODO: Try matrix-free!
        # TODO: Is modification of x safe?
        self._fp.mult(y, x)
        self._ksp_mp.solve(x, y)
    def set_operators(self, isp, Mp, Fp, Ap, Lp, bcs_Ap):
        self._isp = isp
        self._Mp = Mp
        self._Fp = Fp
        self._Ap = Ap
        self._Lp = Lp
        self._bcs_Ap = bcs_Ap
    def prepare_factors(self):
        # Prepare Mp factorization
        ksp = PETSc.KSP()
        ksp.create(PETSc.COMM_WORLD)
        ksp.setType(PETSc.KSP.Type.PREONLY)
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.CHOLESKY)
        pc.setFactorSolverPackage('mumps')
        self._mp.setOption(PETSc.Mat.Option.SPD, True)
        ksp.setOperators(self._mp)
        ksp.setUp()
        self._ksp_mp = ksp

        # Prepare Ap factorization
        ksp = PETSc.KSP()
        ksp.create(PETSc.COMM_WORLD)
        ksp.setType(PETSc.KSP.Type.PREONLY)
        pc = ksp.getPC()
        pc.setType(PETSc.PC.Type.CHOLESKY)
        pc.setFactorSolverPackage('mumps')
        self._mp.setOption(PETSc.Mat.Option.SPD, True)
        ksp.setOperators(self._ap)
        ksp.setUp()
        self._ksp_ap = ksp


dofmap_dofs_is_cpp_code = """
#ifdef SWIG
%include "petsc4py/petsc4py.i"
#endif

#include <vector>
#include <petscis.h>
#include <dolfin/fem/GenericDofMap.h>

namespace dolfin {

  IS dofmap_dofs_is(const GenericDofMap& dofmap)
  {
    const std::vector<dolfin::la_index> dofs = dofmap.dofs();
    IS is;
    ISCreateGeneral(PETSC_COMM_WORLD, dofs.size(), dofs.data(),
                    PETSC_COPY_VALUES, &is);
    return is;
  }

}
"""

dofmap_dofs_is = \
    compile_extension_module(dofmap_dofs_is_cpp_code).dofmap_dofs_is
del dofmap_dofs_is_cpp_code
