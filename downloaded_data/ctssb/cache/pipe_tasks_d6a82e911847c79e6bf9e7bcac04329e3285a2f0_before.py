#!/usr/bin/env python
#
# LSST Data Management System
# Copyright 2008, 2009, 2010, 2011, 2012 LSST Corporation.
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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.    See the
# GNU General Public License for more details.
#
# You should have received a copy of the LSST License Statement and
# the GNU General Public License along with this program.  If not,
# see <http://www.lsstcorp.org/LegalNotices/>.
#
import numpy
import lsst.pex.config as pexConfig
import lsst.afw.geom as afwGeom
import lsst.afw.image as afwImage
import lsst.afw.math as afwMath
import lsst.coadd.utils as coaddUtils
import lsst.pipe.base as pipeBase
from .coaddBase import CoaddBaseTask
from .interpImage import InterpImageTask
from .matchBackgrounds import MatchBackgroundsTask
from .coaddHelpers import groupPatchExposures, getGroupDataRef

__all__ = ["AssembleCoaddTask"]

class AssembleCoaddConfig(CoaddBaseTask.ConfigClass):
    subregionSize = pexConfig.ListField(
        dtype = int,
        doc = "Width, height of stack subregion size; " \
              "make small enough that a full stack of images will fit into memory at once.",
        length = 2,
        default = (2000, 2000),
    )
    doSigmaClip = pexConfig.Field(
        dtype = bool,
        doc = "Perform sigma clipped outlier rejection? If False then compute a simple mean.",
        default = True,
    )
    sigmaClip = pexConfig.Field(
        dtype = float,
        doc = "Sigma for outlier rejection; ignored if doSigmaClip false.",
        default = 3.0,
    )
    clipIter = pexConfig.Field(
        dtype = int,
        doc = "Number of iterations of outlier rejection; ignored if doSigmaClip false.",
        default = 2,
    )
    scaleZeroPoint = pexConfig.ConfigurableField(
        target = coaddUtils.ScaleZeroPointTask,
        doc = "Task to adjust the photometric zero point of the coadd temp exposures",
    )
    doInterp = pexConfig.Field(
        doc = "Interpolate over NaN pixels? Also extrapolate, if necessary, but the results are ugly.",
        dtype = bool,
        default = True,
    )
    interpFwhm = pexConfig.Field(
        doc = "FWHM of PSF used for interplation (arcsec)",
        dtype = float,
        default = 1.5,
    )
    interpImage = pexConfig.ConfigurableField(
        target = InterpImageTask,
        doc = "Task to interpolate (and extrapolate) over NaN pixels",
    )
    matchBackgrounds = pexConfig.ConfigurableField(
        target = MatchBackgroundsTask,
        doc = "Task to match backgrounds",
    )
    maxMatchResidualRatio = pexConfig.Field(
        doc = "Maximum ratio of the mean squared error of the background matching model to the variance " \
        "of the difference in backgrounds",
        dtype = float,
        default = 1.1
    )
    doWrite = pexConfig.Field(
        doc = "Persist coadd?",
        dtype = bool,
        default = True,
    )
    doMatchBackgrounds = pexConfig.Field(
        doc = "Match backgrounds of coadd temp exposures before coadding them. " \
        "If False, the coadd temp expsosures must already have been background subtracted or " \
        "matched backgrounds",
        dtype = bool,
        default = True,
    )
    autoReference = pexConfig.Field(
        doc = "Automatically select the coadd temp exposure to use as a reference for background matching? " \
              "Ignored if doMatchBackgrounds false. " \
              "If False you must specify the reference temp exposure as the data Id",
        dtype = bool,
        default = True,
    )
    badMaskPlanes = pexConfig.ListField(
        dtype = str,
        doc = "Mask planes that, if set, the associated pixel should not be included in the coaddTempExp.",
        default = ("EDGE",),
    )


class AssembleCoaddTask(CoaddBaseTask):
    """Assemble a coadd from a set of coaddTempExp
    """
    ConfigClass = AssembleCoaddConfig
    _DefaultName = "assembleCoadd"

    def __init__(self, *args, **kwargs):
        CoaddBaseTask.__init__(self, *args, **kwargs)
        self.makeSubtask("interpImage")
        self.makeSubtask("matchBackgrounds")
        self.makeSubtask("scaleZeroPoint")
        
    @pipeBase.timeMethod
    def run(self, dataRef):
        """Assemble a coadd from a set of coaddTempExp

        The coadd is computed as a mean with optional outlier rejection.

        assembleCoaddTask only works on the dataset type 'coaddTempExp', which are 'coadd temp exposures.
        Each coaddTempExp is the size of a patch and contains data for one run, visit or
        (for a non-mosaic camera it will contain data for a single exposure).

        coaddTempExps, by default, will have backgrounds in them and will require
        config.doMatchBackgrounds = True. However, makeCoaddTempExp.py can optionally create background-
        subtracted coaddTempExps which can be coadded here by setting
        config.doMatchBackgrounds = False.

        @param dataRef: data reference for a coadd patch (of dataType 'Coadd') OR a data reference
        for a coadd temp exposure (of dataType 'Coadd_tempExp') which serves as the reference visit
        if config.doMatchBackgrounds true and config.autoReference false)
        If supplying a coadd patch: Must include keys "tract", "patch",
            plus the camera-specific filter key (e.g. "filter")
        Used to access the following data products (depending on the config):
        - [in] self.config.coaddName + "Coadd_tempExp"
        - [out] self.config.coaddName + "Coadd"

        @return: a pipeBase.Struct with fields:
        - coaddExposure: coadd exposure
        """
        skyInfo = self.getSkyInfo(dataRef)
        calExpRefList = self.selectExposures(dataRef, skyInfo)
        if len(calExpRefList) == 0:
            self.log.warn("No exposures to coadd")
            return
        self.log.info("Coadding %d exposures" % len(calExpRefList))

        butler = dataRef.getButler()
        groupData = groupPatchExposures(dataRef, calExpRefList, self.getCoaddDataset(),
                                        self.getTempExpDataset(), checkExist=False)
        tempExpRefList = [getGroupDataRef(butler, self.getTempExpDataset(), g, groupData.keys) for
                          g in groupData.groups.keys()]
        inputData = self.prepareInputs(tempExpRefList)
        tempExpRefList = inputData.tempExpRefList
        self.log.info("Found %d %s" % (len(inputData.tempExpRefList), self.getTempExpDataset()))
        if len(inputData.tempExpRefList) == 0:
            self.log.warn("No coadd temporary exposures found")
            return
        if self.config.doMatchBackgrounds:
            refImageScaler = self.getBackgroundReferenceScaler(dataRef)
            inputData = self.backgroundMatching(inputData, dataRef, refImageScaler)
            if len(inputData.tempExpRefList) == 0:
                self.log.warn("No valid background models")
                return

        coaddExp = self.assemble(skyInfo, inputData.tempExpRefList, inputData.imageScalerList,
                                 inputData.weightList,
                                 inputData.backgroundInfoList if self.config.doMatchBackgrounds else None)
        if self.config.doMatchBackgrounds:
            self.addBackgroundMatchingMetadata(coaddExp, inputData.tempExpRefList,
                                               inputData.backgroundInfoList)

        if self.config.doInterp:
            fwhmPixels = self.config.interpFwhm / skyInfo.wcs.pixelScale().asArcseconds(),
            self.interpImage.interpolateOnePlane(maskedImage=coaddExp.getMaskedImage(), planeName="EDGE",
                                                 fwhmPixels=self.config.interpFwhm)

        if self.config.doWrite:
            self.writeCoaddOutput(dataRef, coaddExp)

        return pipeBase.Struct(coaddExposure=coaddExp)


    def getBackgroundReferenceScaler(self, dataRef):
        """Construct an image scaler for the background reference frame

        If there is no reference frame ('autoReference'), then this is a no-op
        and None is returned

        @param dataRef: Data reference for the background reference frame, or None
        @return image scaler, or None
        """
        if self.config.autoReference:
            return None

        # We've been given the data reference
        dataset = self.getTempExpDataset()
        if not dataRef.datasetExists(dataset):
            raise RuntimeError("Could not find reference exposure %s %s." % (dataset, dataRef.dataId))

        refExposure = refExpDataRef.get(self.getTempExpDataset(), immediate=True)
        refImageScaler = self.scaleZeroPoint.computeImageScaler(
            exposure = refExposure,
            exposureId = dataRef.dataId,
            )
        return refImageScaler


    def prepareInputs(self, refList):
        """Prepare the input warps for coaddition

        This involves measuring weights and constructing image scalers
        for each of the inputs.

        @param refList: List of data references to tempExp
        @return Struct:
        - tempExprefList: List of data references to tempExp
        - weightList: List of weightings
        - imageScalerList: List of image scalers
        """
        statsCtrl = afwMath.StatisticsControl()
        statsCtrl.setNumSigmaClip(self.config.sigmaClip)
        statsCtrl.setNumIter(self.config.clipIter)
        statsCtrl.setAndMask(self.getBadPixelMask())
        statsCtrl.setNanSafe(True)

        # compute tempExpRefList: a list of tempExpRef that actually exist
        # and weightList: a list of the weight of the associated coadd tempExp
        # and imageScalerList: a list of scale factors for the associated coadd tempExp
        tempExpRefList = []
        weightList = []
        imageScalerList = []
        tempExpName = self.getTempExpDataset()
        for tempExpRef in refList:
            if not tempExpRef.datasetExists(tempExpName):
                self.log.warn("Could not find %s %s; skipping it" % (tempExpName, tempExpRef.dataId))
                continue

            tempExp = tempExpRef.get(tempExpName, immediate=True)
            maskedImage = tempExp.getMaskedImage()
            imageScaler = self.scaleZeroPoint.computeImageScaler(
                exposure = tempExp,
                exposureId = tempExpRef.dataId,
            )
            try:
                imageScaler.scaleMaskedImage(maskedImage)
            except Exception, e:
                self.log.warn("Scaling failed for %s (skipping it): %s" % (tempExpRef.dataId, e))
                continue
            statObj = afwMath.makeStatistics(maskedImage.getVariance(), maskedImage.getMask(),
                afwMath.MEANCLIP, statsCtrl)
            meanVar, meanVarErr = statObj.getResult(afwMath.MEANCLIP);
            weight = 1.0 / float(meanVar)
            self.log.info("Weight of %s %s = %0.3f" % (tempExpName, tempExpRef.dataId, weight))

            del maskedImage
            del tempExp

            tempExpRefList.append(tempExpRef)
            weightList.append(weight)
            imageScalerList.append(imageScaler)

        return pipeBase.Struct(tempExpRefList=tempExpRefList, weightList=weightList,
                               imageScalerList=imageScalerList)


    def backgroundMatching(self, inputData, refExpDataRef=None, refImageScaler=None):
        """Perform background matching on the prepared inputs

        If no reference is provided, the background matcher will select one.

        This method returns a new inputData Struct that can replace the original.

        @param inputData: Struct from prepareInputs() with tempExpRefList, weightList, imageScalerList
        @param refExpDataRef: Data reference for background reference tempExp, or None
        @param refImageScaler: Image scaler for background reference tempExp, or None
        @return Struct:
        - tempExprefList: List of data references to tempExp
        - weightList: List of weightings
        - imageScalerList: List of image scalers
        - backgroundInfoList: result from background matching
        """
        try:
            backgroundInfoList = self.matchBackgrounds.run(
                expRefList = inputData.tempExpRefList,
                imageScalerList = inputData.imageScalerList,
                refExpDataRef = refExpDataRef if not self.config.autoReference else None,
                refImageScaler = refImageScaler,
                expDatasetType = self.getTempExpDataset(),
            ).backgroundInfoList
        except Exception, e:
            self.log.fatal("Cannot match backgrounds: %s" % (e))
            raise pipeBase.TaskError("Background matching failed.")

        newWeightList = []
        newTempExpRefList = []
        newBackgroundStructList = []
        newScaleList = []
        # the number of good backgrounds may be < than len(tempExpList)
        # sync these up and correct the weights
        for tempExpRef, bgInfo, scaler, weight in zip(inputData.tempExpRefList, backgroundInfoList,
                                                      inputData.imageScalerList, inputData.weightList):
            if not bgInfo.isReference:
                # skip exposure if it has no backgroundModel
                # or if fit was bad
                if (bgInfo.backgroundModel is None):
                    self.log.info("No background offset model available for %s: skipping"%(
                        tempExpRef.dataId))
                    continue
                try:
                    varianceRatio =  bgInfo.matchedMSE / bgInfo.diffImVar
                except Exception, e:
                    self.log.info("MSE/Var ratio not calculable (%s) for %s: skipping" %
                                  (e, tempExpRef.dataId,))
                    continue
                if not numpy.isfinite(varianceRatio):
                    self.log.info("MSE/Var ratio not finite (%.2f / %.2f) for %s: skipping" %
                                  (bgInfo.matchedMSE, bgInfo.diffImVar,
                                   tempExpRef.dataId,))
                    continue
                elif (varianceRatio > self.config.maxMatchResidualRatio):
                    self.log.info("Bad fit. MSE/Var ratio %.2f > %.2f for %s: skipping" % (
                            varianceRatio, self.config.maxMatchResidualRatio, tempExpRef.dataId,))
                    continue

            newWeightList.append(1 / (1 / weight + bgInfo.fitRMS**2))
            newTempExpRefList.append(tempExpRef)
            newBackgroundStructList.append(bgInfo)
            newScaleList.append(scaler)

        return pipeBase.Struct(tempExpRefList=newTempExpRefList, weightList=newWeightList,
                               imageScalerList=newScaleList, backgroundInfoList=newBackgroundStructList)

    def assemble(self, skyInfo, tempExpRefList, imageScalerList, weightList, bgInfoList=None):
        """Assemble a coadd from input warps

        The assembly is performed over small areas on the image at a time, to
        conserve memory usage.

        @param skyInfo: Patch geometry information, from getSkyInfo
        @param tempExpRefList: List of data references to tempExp
        @param imageScalerList: List of image scalers
        @param weightList: List of weights
        @param bgInfoList: List of background data from background matching
        @return coadded exposure
        """
        tempExpName = self.getTempExpDataset()
        self.log.info("Assembling %s %s" % (len(tempExpRefList), tempExpName))

        statsCtrl = afwMath.StatisticsControl()
        statsCtrl.setNumSigmaClip(self.config.sigmaClip)
        statsCtrl.setNumIter(self.config.clipIter)
        statsCtrl.setAndMask(self.getBadPixelMask())
        statsCtrl.setNanSafe(True)
        statsCtrl.setCalcErrorFromInputVariance(True)

        if self.config.doSigmaClip:
            statsFlags = afwMath.MEANCLIP
        else:
            statsFlags = afwMath.MEAN

        if bgInfoList is None:
            bgInfoList = [None]*len(tempExpRefList)

        coaddExposure = afwImage.ExposureF(skyInfo.bbox, skyInfo.wcs)
        coaddExposure.setCalib(self.scaleZeroPoint.getCalib())
        coaddMaskedImage = coaddExposure.getMaskedImage()
        subregionSizeArr = self.config.subregionSize
        subregionSize = afwGeom.Extent2I(subregionSizeArr[0], subregionSizeArr[1])
        didSetMetadata = False
        for subBBox in _subBBoxIter(skyInfo.bbox, subregionSize):
            try:
                didSetMetadata = self.assembleSubregion(coaddExposure, subBBox, tempExpRefList,
                                                        imageScalerList, weightList, bgInfoList, statsFlags,
                                                        statsCtrl, not didSetMetadata)
            except Exception, e:
                self.log.fatal("Cannot compute coadd %s: %s" % (subBBox, e,))

        coaddUtils.setCoaddEdgeBits(coaddMaskedImage.getMask(), coaddMaskedImage.getVariance())

        return coaddExposure

    def assembleSubregion(self, coaddExposure, bbox, tempExpRefList, imageScalerList, weightList,
                          bgInfoList, statsFlags, statsCtrl, doSetMetadata=False):
        """Assemble the coadd for a sub-region

        @param coaddExposure: The target image for the coadd
        @param bbox: Sub-region to coadd
        @param tempExpRefList: List of data reference to tempExp
        @param imageScalerList: List of image scalers
        @param weightList: List of weights
        @param bgInfoList: List of background data from background matching
        @param statsFlags: Statistic for coadd
        @param statsCtrl: Statistics control object for coadd
        @param doSetMetadata: Set metadata on coadd?
        @return whether we set metadata on the coadd (which may be False even if doSetMetadata is True)
        """
        self.log.info("Computing coadd over %s" % bbox)
        tempExpName = self.getTempExpDataset()
        coaddMaskedImage = coaddExposure.getMaskedImage()
        coaddView = afwImage.MaskedImageF(coaddMaskedImage, bbox, afwImage.PARENT, False)
        maskedImageList = afwImage.vectorMaskedImageF() # [] is rejected by afwMath.statisticsStack
        didSetMetadata = False
        for tempExpRef, imageScaler, bgInfo in zip(tempExpRefList, imageScalerList, bgInfoList):
            exposure = tempExpRef.get(tempExpName + "_sub", bbox=bbox, imageOrigin="PARENT")
            maskedImage = exposure.getMaskedImage()
            imageScaler.scaleMaskedImage(maskedImage)

            if doSetMetadata:
                coaddExposure.setFilter(exposure.getFilter())
                didSetMetadata = True
            if self.config.doMatchBackgrounds and not bgInfo.isReference:
                backgroundModel = bgInfo.backgroundModel
                backgroundImage = backgroundModel.getImage() if \
                    self.matchBackgrounds.config.usePolynomial else \
                    backgroundModel.getImageF()
                backgroundImage.setXY0(coaddMaskedImage.getXY0())
                maskedImage += backgroundImage.Factory(backgroundImage, bbox, afwImage.PARENT, False)
                var = maskedImage.getVariance()
                var += (bgInfo.fitRMS)**2

            maskedImageList.append(maskedImage)

        with self.timer("stack"):
            coaddSubregion = afwMath.statisticsStack(
                maskedImageList, statsFlags, statsCtrl, weightList)

        coaddView <<= coaddSubregion
        return didSetMetadata


    def addBackgroundMatchingMetadata(self, coaddExposure, tempExpRefList, backgroundInfoList):
        """Add metadata from the background matching to the coadd

        @param coaddExposure: Coadd
        @param backgroundInfoList: List of background info, results from background matching
        """
        self.log.info("Adding exposure information to metadata")
        metadata = coaddExposure.getMetadata()
        metadata.addString("CTExp_SDQA1_DESCRIPTION",
                           "Background matching: Ratio of matchedMSE / diffImVar")
        for ind, (tempExpRef, backgroundInfo) in enumerate(zip(tempExpRefList, backgroundInfoList)):
            tempExpStr = '&'.join('%s=%s' % (k,v) for k,v in tempExpRef.dataId.items())
            if backgroundInfo.isReference:
                metadata.addString("ReferenceExp_ID", tempExpStr)
            else:
                metadata.addString("CTExp_ID_%d" % (ind), tempExpStr)
                metadata.addDouble("CTExp_SDQA1_%d" % (ind),
                                   backgroundInfo.matchedMSE/backgroundInfo.diffImVar)

    @classmethod
    def _makeArgumentParser(cls):
        """Create an argument parser
        """
        return AssembleCoaddArgumentParser(
            name=cls._DefaultName,
            datasetType=cls.ConfigClass().coaddName + "Coadd_tempExp"
            )

    def _getConfigName(self):
        """Return the name of the config dataset
        """
        return "%s_%s_config" % (self.config.coaddName, self._DefaultName)

    def _getMetadataName(self):
        """Return the name of the metadata dataset
        """
        return "%s_%s_metadata" % (self.config.coaddName, self._DefaultName)


def _subBBoxIter(bbox, subregionSize):
    """Iterate over subregions of a bbox

    @param[in] bbox: bounding box over which to iterate: afwGeom.Box2I
    @param[in] subregionSize: size of sub-bboxes

    @return subBBox: next sub-bounding box of size subregionSize or smaller;
        each subBBox is contained within bbox, so it may be smaller than subregionSize at the edges of bbox,
        but it will never be empty
    """
    if bbox.isEmpty():
        raise RuntimeError("bbox %s is empty" % (bbox,))
    if subregionSize[0] < 1 or subregionSize[1] < 1:
        raise RuntimeError("subregionSize %s must be nonzero" % (subregionSize,))

    for rowShift in range(0, bbox.getHeight(), subregionSize[1]):
        for colShift in range(0, bbox.getWidth(), subregionSize[0]):
            subBBox = afwGeom.Box2I(bbox.getMin() + afwGeom.Extent2I(colShift, rowShift), subregionSize)
            subBBox.clip(bbox)
            if subBBox.isEmpty():
                raise RuntimeError("Bug: empty bbox! bbox=%s, subregionSize=%s, colShift=%s, rowShift=%s" % \
                    (bbox, subregionSize, colShift, rowShift))
            yield subBBox



class AssembleCoaddArgumentParser(pipeBase.ArgumentParser):
    """A version of lsst.pipe.base.ArgumentParser specialized for assembleCoadd.
    """
    def _makeDataRefList(self, namespace):
        """Make namespace.dataRefList from namespace.dataIdList.

           Interpret the config.doMatchBackgrounds, config.autoReference,
           and whether a visit/run supplied.
           If a visit/run is supplied, config.autoReference is automatically set to False.
           if config.doMatchBackgrounds == false, then a visit/run will be ignored if accidentally supplied.

        """
        keysCoadd = namespace.butler.getKeys(datasetType=namespace.config.coaddName + "Coadd",
                                             level=self._dataRefLevel)
        keysCoaddTempExp = namespace.butler.getKeys(datasetType=namespace.config.coaddName + "Coadd_tempExp",
                                                    level=self._dataRefLevel)

        if namespace.config.doMatchBackgrounds:
            if namespace.config.autoReference: #matcher will pick it's own reference image
                namespace.datasetType = namespace.config.coaddName + "Coadd"
                validKeys = keysCoadd
            else:
                namespace.datasetType = namespace.config.coaddName + "Coadd_tempExp"
                validKeys = keysCoaddTempExp
        else: #bkg subtracted coadd
            namespace.datasetType = namespace.config.coaddName + "Coadd"
            validKeys = keysCoadd

        namespace.dataRefList = []
        for dataId in namespace.dataIdList:
            # tract and patch are required
            for key in validKeys:
                if key not in dataId:
                    self.error("--id must include " + key)

            for key in dataId: # check if users supplied visit/run
                if (key not in keysCoadd) and (key in keysCoaddTempExp):  #user supplied a visit/run
                    if namespace.config.autoReference:
                        # user probably meant: autoReference = False
                        namespace.config.autoReference = False
                        datasetType = namespace.config.coaddName + "Coadd_tempExp"
                        print "Switching config.autoReference to False; applies only to background Matching."
                        break

            dataRef = namespace.butler.dataRef(
                datasetType = namespace.datasetType,
                dataId = dataId,
            )
            namespace.dataRefList.append(dataRef)

