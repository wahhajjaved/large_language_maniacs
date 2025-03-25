""" A module that manages the parallel call to C++ executables """
from __future__ import absolute_import

from .argumentparser import get_args
from ..parser import parse_ini_file
import subprocess
import sys


def call(executable, mpi_exec, mpi_numprocflag, mpi_preflags, mpi_postflags, inifile=None):
    # If we have an inifile, parse it and look for special keys that modify the execution
    num_processes = 2  # a default
    command = [mpi_exec, mpi_numprocflag, num_processes]
    if mpi_preflags:
        command += mpi_preflags
    command += [executable]
    if mpi_postflags:
        command += mpi_postflags
    if inifile:
        iniargument = inifile
        iniinfo = parse_ini_file(inifile)
        if "__inifile_optionkey" in iniinfo:
            command.append(iniinfo["__inifile_optionkey"])
        command.append(iniargument)
        if "__num_processes" in iniinfo:
            command[2] = iniinfo["__num_processes"]

    return subprocess.call(command)


# This is also used as the standard wrapper by cmake
if __name__ == "__main__":
    # Parse the given arguments
    args = get_args()
    if not args["mpi_exec"]:
        sys.stderr.write("call_parallel.py: error: Mpi executable not given.\n" +
                          "usage: call_parallel.py [-h] -e EXEC -i INI --mpi-exec MPI_EXEC \n" +
                          "                        --mpi-numprocflag MPI_NUMPROCFLAG [-s SOURCE]\n")
        sys.exit(1)
    if not args["mpi_numprocflag"]:
        sys.stderr.write("call_parallel.py: error: Mpi number of processes flag not given.\n" +
                         "usage: call_parallel.py [-h] -e EXEC -i INI --mpi-exec MPI_EXEC \n" +
                         "                         --mpi-numprocflag MPI_NUMPROCFLAG [-s SOURCE]\n")
        sys.exit(1)
    # check if flags are  provided
    if args["mpi_preflags"] == ['']:
        args["mpi_preflags"] = None
    if args["mpi_postflags"] == ['']:
        args["mpi_postflags"] = None
    sys.exit(call(args["exec"], args["mpi_exec"], args["mpi_numprocflag"], args["mpi_preflags"], args["mpi_postflags"], args["ini"]))
