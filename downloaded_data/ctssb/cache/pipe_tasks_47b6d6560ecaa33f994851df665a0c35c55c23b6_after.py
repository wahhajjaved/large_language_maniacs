#
# LSST Data Management System
# Copyright 2008-2016 AURA/LSST.
#
# This product includes software developed by the
# LSST Project (http://www.lsst.org/).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the LSST License Statement and
# the GNU General Public License along with this program.  If not,
# see <https://www.lsstcorp.org/LegalNotices/>.
#
from __future__ import absolute_import, division, print_function

import lsst.pex.config as pexConfig
import lsst.pipe.base as pipeBase
import lsst.daf.base as dafBase
from lsst.afw.math import BackgroundList
from lsst.afw.table import SourceTable, IdFactory
from lsst.meas.algorithms import SourceDetectionTask
from lsst.meas.deblender import SourceDeblendTask
from lsst.meas.base import BasePlugin, SingleFrameMeasurementTask
from lsst.meas.algorithms import MeasureApCorrTask

__all__ = ["DetectAndMeasureConfig", "DetectAndMeasureTask"]

class DetectAndMeasureConfig(pexConfig.Config):
    """Config for DetectAndMeasureTask"""
    detection = pexConfig.ConfigurableField(
        target = SourceDetectionTask,
        doc = "Detect sources",
    )
    doDeblend = pexConfig.Field(
        dtype = bool,
        default = True,
        doc = "Deblend sources?",
    )
    deblend = pexConfig.ConfigurableField(
        target = SourceDeblendTask,
        doc = "Split blended sources into their components",
    )
    measurement = pexConfig.ConfigurableField(
        target = SingleFrameMeasurementTask,
        doc = "Measure sources",
    )
    doMeasureApCorr = pexConfig.Field(
        dtype = bool,
        default = False,
        doc = "Compute aperture corrections and set ApCorrMap in exposure?",
    )
    measureApCorr = pexConfig.ConfigurableField(
        target = MeasureApCorrTask,
        doc = "subtask to measure aperture corrections",
    )

    def setDefaults(self):
        pexConfig.Config.setDefaults(self)


## \addtogroup LSST_task_documentation
## \{
## \page DetectAndMeasureTask
## \ref DetectAndMeasureTask_ "DetectAndMeasureTask"
## \copybrief DetectAndMeasureTask
## \}

class DetectAndMeasureTask(pipeBase.Task):
    """!Detect and deblend sources and measure them using single-frame measurement

    @anchor DetectAndMeasureTask_
    
    @section pipe_tasks_detectAndMeasure_Contents  Contents

     - @ref pipe_tasks_detectAndMeasure_Purpose
     - @ref pipe_tasks_detectAndMeasure_Initialize
     - @ref pipe_tasks_detectAndMeasure_IO
     - @ref pipe_tasks_detectAndMeasure_Config
     - @ref pipe_tasks_detectAndMeasure_Debug
     - @ref pipe_tasks_detectAndMeasure_Example

    @section pipe_tasks_detectAndMeasure_Purpose  Description

    Given an exposure with some kind of PSF model (it does not have to be accurate)
    detect sources, deblend them and perform single-frame measurement.

    @section pipe_tasks_detectAndMeasure_Initialize  Task initialisation

    @copydoc \_\_init\_\_

    @section pipe_tasks_detectAndMeasure_IO  Invoking the Task

    The main method is `run`.

    Measurement is rather complicated, so that code lives in a method `measure`.
    It would be wise to replace this by a higher-level measurement task.

    @section pipe_tasks_detectAndMeasure_Config  Configuration parameters

    See @ref DetectAndMeasureConfig

    @section pipe_tasks_detectAndMeasure_Debug  Debug variables

    This task has no debug display

    @section pipe_tasks_detectAndMeasure_Example   A complete example of using DetectAndMeasureTask

    This code is in @link detectAndMeasureExample.py@endlink in the examples directory,
    and can be run as, e.g.:
    @code
    python examples/detectAndMeasureExample.py --display
    @endcode
    @dontinclude detectAndMeasureExample.py

    Import the task (there are some other standard imports; read the file if you're curious)
    @skipline import DetectAndMeasureTask

    Create the taskm run it and display the results.
    @skip def run
    @until displayAstrometry
    """
    ConfigClass = DetectAndMeasureConfig
    _DefaultName = "detectAndMeasure"

    def __init__(self, dataPrefix="", schema=None, **kwargs):
        """Construct a DetectAndMeasureTask

        Arguments in addition to the standard Task arguments:
        @param[in] dataPrefix  prefix for name of source tables;
            - for calexp use the default of ""
            - for coadds use coaddName + "Coadd"
        @param[in,out] schema  schema for sources; if None then one is constructed
        """
        pipeBase.Task.__init__(self, **kwargs)
        self.dataPrefix = dataPrefix
        self.algMetadata = dafBase.PropertyList()
        if schema is None:
            schema = SourceTable.makeMinimalSchema()
        self.schema = schema
        self.makeSubtask("detection", schema=self.schema)
        if self.config.doDeblend:
            self.makeSubtask("deblend", schema=self.schema)
        self.makeSubtask("measurement", schema=self.schema, algMetadata=self.algMetadata)
        if self.config.doMeasureApCorr:
            # add field to flag stars useful for measuring aperture correction
            self.makeSubtask("measureApCorr", schema=schema)

    @pipeBase.timeMethod
    def run(self, exposure, exposureIdInfo, background=None, allowApCorr=True):
        """!Detect, deblend and perform single-frame measurement on sources and refine the background model

        @param[in,out] exposure  exposure to process. Background must already be subtracted
            to reasonable accuracy, else detection will fail.
            The background model is refined and resubtracted.
            apCorrMap is set if measuring aperture correction.
        @param[in]     exposureIdInfo  ID info for exposure (an lsst.daf.butlerUtils.ExposureIdInfo)
        @param[in,out] background  background model to be modified (an lsst.afw.math.BackgroundList),
            or None to create a new background model
        @param[in] allowApCorr  allow measuring and applying aperture correction?

        @return pipe_base Struct containing these fields:
        - exposure: input exposure (as modified in the course of runing)
        - sourceCat: source catalog (an lsst.afw.table.SourceTable)
        - background: background model (input as modified, or a new model if input is None);
            an lsst.afw.math.BackgroundList
        """
        if background is None:
            background = BackgroundList()

        sourceIdFactory = IdFactory.makeSource(exposureIdInfo.expId, exposureIdInfo.unusedBits)

        table = SourceTable.make(self.schema, sourceIdFactory)
        table.setMetadata(self.algMetadata)

        detRes = self.detection.run(table=table, exposure=exposure, doSmooth=True)
        sourceCat = detRes.sources
        if detRes.fpSets.background:
            background.append(detRes.fpSets.background)

        if self.config.doDeblend:
            self.deblend.run(
                exposure = exposure,
                sources = sourceCat,
                psf = exposure.getPsf(),
            )

        self.measure(
            exposure = exposure,
            exposureIdInfo = exposureIdInfo,
            sourceCat = sourceCat,
            allowApCorr = allowApCorr,
        )

        return pipeBase.Struct(
            exposure = exposure,
            sourceCat = sourceCat,
            background = background,
        )

    def measure(self, exposure, exposureIdInfo, sourceCat, allowApCorr=True):
        """Measure sources

        @param[in,out] exposure  exposure to process. Background must already be subtracted
            to reasonable accuracy, else detection will fail.
            Set apCorrMap if measuring aperture correction.
        @param[in]     exposureIdInfo  ID info for exposure (an lsst.daf.butlerUtils.ExposureIdInfo)
        @param[in,out] background  background model to be modified (an lsst.afw.math.BackgroundList),
            or None to create a new background model
        @param[in] allowApCorr  allow measuring and applying aperture correction?
        """
        if self.config.doMeasureApCorr or allowApCorr:
            # NOTE: The measurement task has a serious misfeature when it comes to applying
            # aperture correction (one that will be fixed in DM-5877): it applies aperture
            # correction after performing ALL measurements, regardless of their execution
            # order.  As a result, no plugins, in particular those whose measurements rely
            # on aperture corrected fluxes, were getting aperture-corrected fluxes.
            #
            # To work around this, we measure fluxes and apply aperture correction where
            # appropriate in three phases (as described step-by-step below):
            #    1) run plugins up to order APCORR_ORDER to measure all fluxes
            #    2) apply aperture correction to all appropriate fluxes
            #    3) run the remaining plugins with aperture correction disabled
            #       (to avoid applying the correction twice)

            # 1) run plugins with order up to APCORR_ORDER to measure all fluxes
            self.measurement.run(
                measCat = sourceCat,
                exposure = exposure,
                exposureId = exposureIdInfo.expId,
                endOrder = BasePlugin.APCORR_ORDER,
            )

            sourceCat.sort(SourceTable.getParentKey())

            if self.config.doMeasureApCorr and allowApCorr:
                # measure the aperture correction map
                apCorrMap = self.measureApCorr.run(exposure=exposure, catalog=sourceCat).apCorrMap
                exposure.getInfo().setApCorrMap(apCorrMap)

            # 2) run APCORR_ORDER only to apply the aperture correction to the measured
            # fluxes. The effect of this step is simply to apply the aperture correction
            # (using the apCorrMap measured above or perhaps in a previous stage) to any
            # flux measurements present whose plugins were registered with shouldApCorr=True
            # (no actual plugins are run in this step)
            self.measurement.run(
                measCat = sourceCat,
                exposure = exposure,
                exposureId = exposureIdInfo.expId,
                beginOrder = BasePlugin.APCORR_ORDER,
                endOrder = BasePlugin.APCORR_ORDER + 1,
                allowApCorr = allowApCorr,
            )
            # 3) run the remaining APCORR_ORDER+1 plugins, whose measurements should be
            # performed on aperture corrected fluxes, disallowing apCorr (to avoid applying it
            # more than once, noting that, when allowApCorr=True, self._applyApCorrIfWanted()
            # in meas_base's SingleFrameMeasurement runs with no regard to beginOrder, so
            # running with allowApCorr=True in any call to measurement.run subsequent to step 2)
            # would erroneously re-apply the aperture correction to already-corrected fluxes)
            self.measurement.run(
                measCat = sourceCat,
                exposure = exposure,
                exposureId = exposureIdInfo.expId,
                beginOrder = BasePlugin.APCORR_ORDER + 1,
                allowApCorr = False,
            )
        else:
            self.measurement.run(
                measCat = sourceCat,
                exposure = exposure,
                exposureId = exposureIdInfo.expId,
                allowApCorr = False,
            )
