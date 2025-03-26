# coding=utf-8
"""Augmentation of the OpenMM app layer for constant-pH sampling."""

from simtk.openmm.app import Simulation
from simtk import openmm
from .driver import SAMSApproach, Stage, UpdateRule, NCMCProtonDrive
from .calibration import SAMSCalibrationEngine
from protons.app import proposals
from protons.app.logger import log
import sys
from datetime import datetime
from typing import Optional, List


class ConstantPHSimulation(Simulation):
    """ConstantPHSimulation is an API for running constant-pH simulation in OpenMM analogous to app.Simulation."""

    def __init__(
        self,
        topology,
        system,
        compound_integrator,
        drive,
        move=None,
        pools=None,
        platform=None,
        platformProperties=None,
        state=None,
    ):
        """Create a ConstantPHSimulation.

        Parameters
        ----------
        topology : Topology
            A Topology describing the the system to simulate
        system : System or XML file name
            The OpenMM System object to simulate (or the name of an XML file
            with a serialized System)
        compound_integrator : openmm.CompoundIntegrator or XML file name
            The OpenMM Integrator to use for simulating the System (or the name of an XML file with a serialized System)
            Needs to have 2 integrators. The first integrator is used for MD, the second integrator is used for NCMC.
            The NCMC integrator needs to be a CustomIntegrator with the following two properties defined:
                first_step: 0 or 1. 0 indicates the first step in an NCMC protocol and can be used for special actions
                required such as computing the energy prior to perturbation.
                protocol_work: double, the protocol work performed by external moves in between steps.
        drive : protons ProtonDrive
            A ProtonDrive object that can manipulate the protonation states of the system.
        move: StateProposal, default None
            An MC proposal move for updating titration states.
        pools: dict, default is None
            A dictionary of titration group indices to group together.
        platform : Platform=None
            If not None, the OpenMM Platform to use
        platformProperties : map=None
            If not None, a set of platform-specific properties to pass to the
            Context's constructor
        state : XML file name=None
            The name of an XML file containing a serialized State. If not None,
            the information stored in state will be transferred to the generated
            Simulation object.
        """

        super(ConstantPHSimulation, self).__init__(
            topology,
            system,
            compound_integrator,
            platform=platform,
            platformProperties=platformProperties,
            state=state,
        )

        self.drive = drive
        self.drive.attach_context(self.context)

        if move is None:
            move = proposals.UniformProposal()
        self.move = move

        # The index of the current protonation state update
        self.currentUpdate = 0

        # A list of reporters specifically for protonation state updates
        self.update_reporters = []

        if pools is not None:
            drive.define_pools(pools)

        if self.drive.calibration_state is not None:
            self.sams = SAMSCalibrationEngine(drive)
        else:
            self.sams = None

        self.calibration_reporters = list()  # keeps track of calibration results
        self.last_dev = None  # deviation at last iteration if sams
        self.last_gk = None  # weights at last iteration if sams

        return

    def step(self, steps):
        """Advance the simulation by integrating a specified number of time steps."""
        self._simulate(endStep=self.currentStep + steps)

    def update(self, updates, move=None, pool=None):
        """Advance the simulation by propagating the protonation states a specified number of times.

        Parameters
        ----------

        updates : int
            The number of independent updates to perform.
        move : StateProposal
            Type of move to update system. Uses pre-specified move if not given.
        pool : str
            The identifier for the pool of residues to update.
        """
        self._update(endUpdate=self.currentUpdate + updates, pool=pool, move=move)

    def _update(self, pool=None, move=None, endUpdate=None, endTime=None):

        if move is None:
            move = self.move
        if endUpdate is None:
            endUpdate = sys.maxsize
        nextReport = [None] * len(self.update_reporters)
        while self.currentUpdate < endUpdate and (
            endTime is None or datetime.now() < endTime
        ):
            nextUpdates = endUpdate - self.currentUpdate
            anyReport = False
            for i, reporter in enumerate(self.update_reporters):
                nextReport[i] = reporter.describeNextReport(self)
                if 0 < nextReport[i][0] <= nextUpdates:
                    nextUpdates = nextReport[i][0]
                    anyReport = True
            updatesToGo = nextUpdates
            while updatesToGo > 1:
                # Only take 1 steps at a time, since each ncmc move is assumed to take a long time
                self.drive.update(move, residue_pool=pool, nattempts=1)
                updatesToGo -= 1
                if endTime is not None and datetime.now() >= endTime:
                    return
            self.drive.update(move, residue_pool=pool, nattempts=updatesToGo)

            self.currentUpdate += nextUpdates
            if anyReport:
                for reporter, nextR in zip(self.update_reporters, nextReport):
                    if nextR[0] == nextUpdates:
                        reporter.report(self)

    def adapt(self):
        """
        Adapt the weights for the residue that is being calibrated.
        """
        if self.drive.calibration_state is None:
            raise ValueError("Proton drive has no calibration state attached.")

        nextReport = [None] * len(self.calibration_reporters)
        anyReport = False
        for i, reporter in enumerate(self.calibration_reporters):
            nextReport[i] = reporter.describeNextReport(self)
            if 0 < nextReport[i][0] <= 1:
                anyReport = True

        # No adaptation performed if the simulation is in equilibrium
        if self.drive.calibration_state._stage is not Stage.EQUILIBRIUM:
            # adapt the zeta/g_k values, and the result is the deviation from the target histogram.
            self.last_dev = self.sams.adapt_zetas(
                self.drive.calibration_state._update_rule,
                stage=self.drive.calibration_state._stage,
                b=self.drive.calibration_state._beta_sams,
                end_of_slowdecay=self.drive.calibration_state._end_of_burnin,
            )

            self.last_gk = self.drive.calibration_state.free_energies

            # If the histogram is flat below the criterion
            # Flatness is defined as the sum of absolute deviations
            # if minimum iterations have been performed, start SAMS decay
            if (
                self.drive.calibration_state._current_adaptation == 0
                and self.drive.calibration_state._stage is Stage.NODECAY
            ):
                self.drive.calibration_state._stage = Stage.SLOWDECAY
            # If flatter than criterion, decay the gain faster
            elif (
                self.last_dev < self.drive.calibration_state._flatness_criterion
                and self.drive.calibration_state._stage == Stage.SLOWDECAY
            ):
                log.info(
                    "Histogram flat below {}. Initiating the slow-gain phase.".format(
                        self.drive.calibration_state._flatness_criterion
                    )
                )
                self.drive.calibration_state._stage = Stage.FASTDECAY
                self.drive.calibration_state._end_of_slowdecay = int(
                    self.drive.calibration_state._current_adaptation
                )
            # If 10x flatter than criterion, stop adapting
            elif (
                self.last_dev < self.drive.calibration_state._flatness_criterion / 10
                and self.drive.calibration_state._stage == Stage.FASTDECAY
            ):
                self.drive.calibration_state._stage = Stage.EQUILIBRIUM

        if anyReport:
            for reporter, nextR in zip(self.calibration_reporters, nextReport):
                if nextR[0] == 1:
                    reporter.report(self)

        return self.last_dev, self.last_gk
