import os
import pickle
import argparse
import numpy as np
import matplotlib.pyplot as plt
from scipy.misc import comb
from scipy.optimize import brentq
from copy import deepcopy

from astroML.decorators import pickle_results
from sklearn import preprocessing
from sklearn.svm import SVC, LinearSVC 
from sklearn.linear_model import LogisticRegression 
from sklearn.grid_search import GridSearchCV

import lsst.afw.table as afwTable
import lsst.afw.geom as afwGeom

def nterms(q, d):
    nterms = 1
    for n in range(1, q+1):
        for m in range(1, min(n, d) + 1):
            nterms += int(comb(n-1, m-1)*comb(d, m))
    return nterms

def phiPol(X, q):
    d = X.shape[-1]
    zDim = nterms(q, d)
    print "The model has {0} dimensions in Z space".format(zDim)
    Xz = np.zeros((X.shape[0], zDim-1)) # The intercept is not included in the input
    Xz[:,range(d)] = X
    count = 0
    if q >= 2:
        for i in range(d):
            for j in range(i, d):
                Xz[:,d + count] = X[:,i]*X[:,j]
                count += 1
    if q >= 3:
        for i in range(d):
            for j in range(i, d):
                for k in range(j, d):
                    Xz[:,d + count] = X[:,i]*X[:,j]*X[:,k]
                    count += 1
    if q >= 4:
        for i in range(d):
            for j in range(i, d):
                for k in range(j, d):
                    for l in range(k, d):
                        Xz[:,d + count] = X[:,i]*X[:,j]*X[:,k]*X[:,l]
                        count += 1
    if q >= 5:
        raise ValueError("Polynomials with order higher than 4 are not implemented.")

    return Xz

def getGood(cat, band='i', magCut=None):
    if not isinstance(cat, afwTable.tableLib.SourceCatalog) and\
       not isinstance(cat, afwTable.tableLib.SimpleCatalog):
        cat = afwTable.SourceCatalog.readFits(cat)
    flux = cat.get('cmodel.flux.'+band)
    fluxPsf = cat.get('flux.psf.'+band)
    ext = -2.5*np.log10(fluxPsf/flux)
    good = np.logical_and(True, ext < 5.0)
    if band == 'i':
        fluxI = flux
    else:
        fluxI = cat.get('cmodel.flux.i')
    fluxZeroI = cat.get('flux.zeromag.i')
    magI = -2.5*np.log10(fluxI/fluxZeroI)
    magAuto = cat.get('mag.auto')
    stellar = cat.get('stellar')
    goodStar = np.logical_and(good,np.logical_and(stellar, np.logical_and(magI < magAuto + 0.25, magI > magAuto - 0.1 - 0.25)))
    goodGal = np.logical_and(good, np.logical_and(np.logical_not(stellar), np.logical_and(magI < magAuto + 0.6, magI > magAuto - 1.3 - 0.6)))
    good = np.logical_or(goodStar, goodGal)
    if magCut is not None:
        good = np.logical_and(good, magI > magCut[0])
        good = np.logical_and(good, magI < magCut[1])
    return good

def testPosterior(posteriors, Y, bins=20):
    histTotal, bin_edges = np.histogram(posteriors, bins=bins)
    histStars, bin_edges = np.histogram(posteriors[Y], bins=bin_edges)
    fracStars = histStars*1.0/histTotal
    
    fig = plt.figure()
    plt.xlabel('Posterior', fontsize=18)
    plt.ylabel('Fraction of True Stars', fontsize=18)
    
    ind = bin_edges[:-1]
    width = bin_edges[1:] - bin_edges[:-1]
    plt.bar(ind, fracStars, width, fill=False)
    plt.plot(bin_edges, bin_edges)

    return fig

def plotMagEx(cat, band, withHSTLabels=True, magThreshold=23.5, exThreshold=0.04):
    mag, ex, good = getMags(cat, band)
    fig = plt.figure()
    if withHSTLabels:
        stellar = cat.get("stellar")
        stars = np.logical_and(good, stellar)
        gals = np.logical_and(good, np.logical_not(stellar))
        first = np.logical_or(mag >= magThreshold, ex > exThreshold)
        galsFirst = np.logical_and(gals, first)
        galsLater = np.logical_and(gals, np.logical_not(first))
        plt.scatter(mag[galsFirst], ex[galsFirst], marker='.', s=1, color='r', label='Galaxies')
        plt.scatter(mag[stars], ex[stars], marker='.', s=1, color='b', label='Stars')
        plt.scatter(mag[galsLater], ex[galsLater], marker='.', s=1, color='r')
    else:
        plt.scatter(mag[good], ex[good], marker='.', s=1)
    plt.xlabel('Magnitude HSC-'+band.upper(), fontsize=18)
    plt.ylabel('Extendedness HSC-'+band.upper(), fontsize=18)
    plt.xlim((mag[good].min(), mag[good].max()))
    plt.ylim((ex[good].min(), ex[good].max()))
    ax = fig.get_axes()[0]
    for tick in ax.xaxis.get_major_ticks():
        tick.label.set_fontsize(18)
    for tick in ax.yaxis.get_major_ticks():
        tick.label.set_fontsize(18)
    plt.legend(loc=1, fontsize=18)
    return fig

def sampleWeightPosterior(clf, nSample=100):
    sigma = np.sqrt(clf.C)
    mean = np.zeros((len(clf.coef_[0])+1,))
    mean[0] = clf.intercept_[0]
    mean[1:] = clf.coef_[0]
    cov = np.zeros((len(mean), len(mean)))
    diag = range(len(mean))
    cov[diag, diag] = sigma
    return np.random.multivariate_normal(mean,cov,nSample)

def getBayesianPosteriors(clf, X, nSample=100):
    wSample = sampleWeightPosterior(clf, nSample=nSample)
    clfTemp = deepcopy(clf)
    bayesianPost = np.zeros((len(X),))
    for i in range(nSample):
        clfTemp.intercept_[0] = wSample[i][0]
        clfTemp.coef_[0] = wSample[i][1:]
        bayesianPost += clfTemp.predict_proba(X)[:,1]
    return bayesianPost/nSample

def getPsfShape(cat, band, type):
    q = np.zeros((len(cat),))
    rDet = np.zeros(q.shape)
    if type == 'sdss':
        column = 'shape.sdss.psf.{0}'.format(band)
    elif type == 'hsm':
        column = 'shape.hsm.psfMoments.{0}'.format(band)
    elif type == 'multishapelet':
        column = 'multishapelet.psf.ellipse.{0}'.format(band)
    else:
        raise ValueError('PSF shape type {0} is not implemented'.format(type))
    for i, record in enumerate(cat): 
        ellipse = afwGeom.ellipses.Axes(record.get(column))
        A = ellipse.getA(); B = ellipse.getB()
        q[i] = B/A
        rDet[i] = np.sqrt(A*B)
    return q, rDet

def getShape(cat, band, type, deconvType='trace', fallBack=True):
    q = np.zeros((len(cat),))
    rDet = np.zeros(q.shape)
    if type == 'hsm' or type == 'hsmDeconv':
        momentsKeyHsm = cat.schema.find('shape.hsm.moments.'+band).getKey()
        momentsPsfKeyHsm = cat.schema.find('shape.hsm.psfMoments.'+band).getKey()
        momentsFlagsKeyHsm = cat.schema.find('shape.hsm.moments.flags.'+band).getKey()
        momentsKeySdss = cat.schema.find('shape.sdss.'+band).getKey()
        momentsPsfKeySdss = cat.schema.find('shape.sdss.psf.'+band).getKey()
        momentsFlagsKeySdss = cat.schema.find('shape.sdss.flags.'+band).getKey()
    else:
        ellipseKey = cat.schema.find('cmodel.'+type + '.ellipse.' + band).getKey()
    for i, record in enumerate(cat): 
        if type == 'hsm':
            if not fallBack or not record.get(momentsFlagsKeyHsm):
                moments = record.get(momentsKeyHsm)
            else:
                moments = record.get(momentsKeySdss)
            xx = moments.getIxx(); yy = moments.getIyy(); xy = moments.getIxy()
            q[i] = np.sqrt((xx + yy - np.sqrt((xx-yy)**2 + 4*xy**2))/(xx + yy + np.sqrt((xx-yy)**2 + 4*xy**2)))
            rDet[i] = moments.getDeterminantRadius()
        elif type == 'hsmDeconv':
            if not fallBack or not record.get(momentsFlagsKeyHsm):
                moments = record.get(momentsKeyHsm)
                momentsPsf = record.get(momentsPsfKeyHsm)
            else:
                moments = record.get(momentsKeySdss)
                momentsPsf = record.get(momentsPsfKeySdss)
            xx = moments.getIxx() - momentsPsf.getIxx()
            yy = moments.getIyy() - momentsPsf.getIyy()
            xy = moments.getIxy() - momentsPsf.getIxy()
            q[i] = np.sqrt((xx + yy - np.sqrt((xx-yy)**2 + 4*xy**2))/(xx + yy + np.sqrt((xx-yy)**2 + 4*xy**2)))
            if deconvType == 'determinant':
                rDet[i] = xx*yy - xy*xy
            elif deconvType == 'trace':
                rDet[i] = (xx + yy)/2
            else:
                raise ValueError('Deconvolution type {0} not implemented'.format(deconvType))
        else:
            ellipse = afwGeom.ellipses.Axes(record.get(ellipseKey))
            A = ellipse.getA(); B = ellipse.getB()
            q[i] = B/A
            rDet[i] = np.sqrt(A*B)
    return q, rDet

def getMag(cat, band, magType):
    f = cat.get(magType + '.flux.' + band)
    f0 = cat.get('flux.zeromag.' + band)
    rat = f/f0
    mag = -2.5*np.log10(rat)
    return mag

def getMags(cat, band, checkExtendedness=True, good=True, checkSNR=True, catType='hsc', 
            noParent=True, iBandCut=True, sameBandCut=False, starDiff=1.0, galDiff=2.0, magAutoShift=0.0):
    if catType == 'hsc':
        f = cat.get('cmodel.flux.'+band)
        fErr = cat.get('cmodel.flux.err.'+band)
        f0 = cat.get('flux.zeromag.'+band)
        fPsf = cat.get('flux.psf.'+band)
        ex = -2.5*np.log10(fPsf/f)
        rat = f/f0
        mag = -2.5*np.log10(rat)
        snr = f/fErr
        if checkSNR:
            good = np.logical_and(good, snr > 5.0)
        if checkExtendedness:
            # Discard objects with extreme extendedness
            good = np.logical_and(good, ex < 5.0)
        if iBandCut:
            if band == 'i':
                fluxI = f
                fluxZeroI = f0
            else:
                fluxI = cat.get('cmodel.flux.i')
                fluxZeroI = cat.get('flux.zeromag.i')
            magI = -2.5*np.log10(fluxI/fluxZeroI)
            magAuto = cat.get('mag.auto')
            stellar = cat.get('stellar')
            goodStar = np.logical_and(good,np.logical_and(stellar, np.logical_and(magI < magAuto + 0.25, magI > magAuto - 0.1 - 0.25)))
            goodGal = np.logical_and(good, np.logical_and(np.logical_not(stellar), np.logical_and(magI < magAuto + 0.6, magI > magAuto - 1.3 - 0.6)))
            good = np.logical_or(goodStar, goodGal)
        elif sameBandCut:
            magAuto = cat.get('mag.auto')
            magAuto += magAutoShift
            stellar = cat.get('stellar')
            goodStar = np.logical_and(good,np.logical_and(stellar, np.logical_and(mag < magAuto + starDiff, mag > magAuto - starDiff)))
            goodGal = np.logical_and(good, np.logical_and(np.logical_not(stellar), np.logical_and(mag < magAuto + galDiff, mag > magAuto - galDiff)))
            good = np.logical_or(goodStar, goodGal)
        if noParent:
            good = np.logical_and(good, cat.get('parent.'+band) == 0)
        return mag, ex, snr, good
    elif catType == 'sdss':
        mag = cat.get('cModelMag.'+band)
        magPsf = cat.get('psfMag.'+band)
        ex = magPsf-mag
    else:
        raise ValueError("Unkown catalog type {0}".format(catTYpe))
        return mag, ex

def loadData(catType='hsc', **kargs):
    if catType == 'hsc':
        bands = kargs['bands']
        kargs.pop('bands')
        if 'g' not in bands:
            kargs['withG'] = False
        if 'r' not in bands:
            kargs['withR'] = False
        if 'i' not in bands:
            kargs['withI'] = False
        if 'z' not in bands:
            kargs['withZ'] = False
        if 'y' not in bands:
            kargs['withY'] = False
        return _loadDataHSC(**kargs)
    elif catType == 'sdss':
        return _loadDataSDSS(**kargs)
    else:
        raise ValueError("Unkown catalog type {0}".format(catType))

#@pickle_results("hscXY.pkl")
def _loadDataHSC(inputFile = "/u/garmilla/Data/HSC/sgClassCosmosDeepCoaddSrcHsc-119320150410GRIZY.fits", withMags=True, withExt=True,
                 withG=True, withR=True, withI=True, withZ=True, withY=True, doMagColors=True, magCut=None, withDepth=True,
                 withSeeing=True, withDevShape=True, withExpShape=True, withDevMag=True, withExpMag=True, withFracDev=True,
                 withPsfShape=True, withResolution=True, noParent=True, iBandCut=True, sameBandCut=False, starDiff=1.0, galDiff=2.0):
    if (not withMags) and (not withExt):
        raise ValueError("I need to use either shapes or magnitudes to train")
    if (not withMags) and (doMagColors):
        raise ValueError("I need to have magnitudes to do magnitude color mode")
    if (not withMags) and (magCut != None):
        raise ValueError("I need to have magnitudes to do magnitude cuts")
    if not isinstance(inputFile, afwTable.tableLib.SourceCatalog) and\
       not isinstance(inputFile, afwTable.tableLib.SimpleCatalog):
        cat = afwTable.SourceCatalog.readFits(inputFile)
    else:
        cat = inputFile
    Y = cat.get('stellar')
    bands = []
    if withG:
        bands.append('g') 
    if withR:
        bands.append('r') 
    if withI:
        bands.append('i') 
    if withZ:
        bands.append('z') 
    if withY:
        bands.append('y') 
    nBands = len(bands)
    nFeatures = nBands*(int(withMags) + int(withExt) + int(withDepth) + int(withSeeing) +\
                        2*int(withDevShape) +2*int(withExpShape) + int(withDevMag) +\
                        int(withExpMag) + int(withFracDev) + 2*int(withPsfShape) + int(withResolution))
    featCount = 0
    if withMags:
        magOffset=0
        featCount += 1
    if withExt:
        extOffset = featCount*nBands
        featCount += 1
    if withDepth:
        depthOffset = featCount*nBands
        featCount += 1
    if withSeeing:
        seeingOffset = featCount*nBands
        featCount += 1
    if withDevShape:
        devShapeOffset = featCount*nBands
        featCount += 2
    if withExpShape:
        expShapeOffset = featCount*nBands
        featCount += 2
    if withDevMag:
        devMagOffset = featCount*nBands
        featCount += 1
    if withExpMag:
        expMagOffset = featCount*nBands
        featCount += 1
    if withFracDev:
        fracDevOffset = featCount*nBands
        featCount += 1
    if withPsfShape:
        psfShapeOffset = featCount*nBands
        featCount += 2
    if withResolution:
        resolutionOffset = featCount*nBands
        featCount += 1

    assert nBands*featCount == nFeatures
   
    shape = (len(cat), nFeatures)
    X = np.zeros(shape)
    good=True
    for i, b in enumerate(bands):
        mag, ex, snr, good = getMags(cat, b, good=good, noParent=noParent, iBandCut=iBandCut, sameBandCut=sameBandCut, starDiff=starDiff, galDiff=galDiff)
        if withMags:
            good = np.logical_and(good, np.logical_not(np.isnan(mag)))
            good = np.logical_and(good, np.logical_not(np.isinf(mag)))
            X[:, i] = mag
        if withExt:
            good = np.logical_and(good, np.logical_not(np.isnan(ex)))
            good = np.logical_and(good, np.logical_not(np.isinf(ex)))
            X[:, extOffset+i] = ex
        if withDepth:
            good = np.logical_and(good, np.isfinite(snr))
            X[:, depthOffset+i] = snr
        if withSeeing:
            seeing = cat.get('seeing.'+b)
            good = np.logical_and(good, np.isfinite(seeing))
            X[:, seeingOffset+i] = seeing 
        if withDevShape:
            q, hlr = getShape(cat, b, 'dev')
            good = np.logical_and(good, np.isfinite(q))
            good = np.logical_and(good, np.isfinite(hlr))
            X[:, devShapeOffset+i] = q
            X[:, devShapeOffset+nBands+i] = hlr
        if withExpShape:
            q, hlr = getShape(cat, b, 'exp')
            good = np.logical_and(good, np.isfinite(q))
            good = np.logical_and(good, np.isfinite(hlr))
            X[:, expShapeOffset+i] = q
            X[:, expShapeOffset+nBands+i] = hlr
        if withDevMag:
            devMag = getMag(cat, b, 'cmodel.dev')
            good = np.logical_and(good, np.isfinite(devMag))
            X[:, devMagOffset+i] = devMag
        if withExpMag:
            expMag = getMag(cat, b, 'cmodel.exp')
            good = np.logical_and(good, np.isfinite(expMag))
            X[:, expMagOffset+i] = expMag
        if withFracDev:
            fracDev = cat.get('cmodel.fracDev.'+b)
            good = np.logical_and(good, np.isfinite(fracDev))
            X[:, fracDevOffset+i] = fracDev
        if withPsfShape:
            q, hlr = getPsfShape(cat, b, 'multishapelet')
            good = np.logical_and(good, np.isfinite(q))
            good = np.logical_and(good, np.isfinite(hlr))
            X[:, psfShapeOffset+i] = q
            X[:, psfShapeOffset+nBands+i] = hlr
        if withResolution:
            res = cat.get('shape.hsm.regauss.resolution.'+b)
            resFlag = cat.get('shape.hsm.regauss.flags.'+b)
            zeroOut = np.logical_and(resFlag, np.isnan(res))
            res[zeroOut] = 0.0
            good = np.logical_and(good, np.isfinite(res))
            X[:, resolutionOffset+i] = res

    if magCut != None:
        mag, ex, snr, good = getMags(cat, 'i', good=good)
        good = np.logical_and(good, mag >= magCut[0])
        good = np.logical_and(good, mag <= magCut[1])
    X = X[good]; Y = Y[good]
    if doMagColors:
        magIdx = bands.index('i')
        Xtemp = X.copy()
        X[:,0] = Xtemp[:,magIdx] #TODO: Make it possible to use other bands seamlessly
        for i in range(1,len(bands)):
            X[:,i] = Xtemp[:,i-1] - Xtemp[:,i]
    return X, Y

def _loadDataSDSS(inputFile = "sgSDSS.fits", withMags=True, withExt=True,
                  bands=['u', 'g', 'r', 'i', 'z'], doMagColors=True, magCut=None):
    if (not withMags) and (not withExt):
        raise ValueError("I need to use either shapes or magnitudes to train")
    if (not withMags) and (doMagColors):
        raise ValueError("I need to have magnitudes to do magnitude color mode")
    if (not withMags) and (magCut != None):
        raise ValueError("I need to have magnitudes to do magnitude cuts")
    cat = afwTable.SimpleCatalog.readFits(inputFile)
    Y = cat.get('stellar')
    nBands = len(bands)
    shape = (len(cat), nBands*(int(withMags)+int(withExt)))
    X = np.zeros(shape)
    for i, b in enumerate(bands):
        mag, ex = getMags(cat, b, catType='sdss')
        if withMags:
            X[:, i] = mag
        if withExt:
            if withMags:
                X[:, nBands+i] = ex
            else:
                X[:, i] = ex
    if magCut != None:
        good = True
        mag, ex = getMags(cat, 'r', catType='sdss')
        good = np.logical_and(good, mag >= magCut[0])
        good = np.logical_and(good, mag <= magCut[1])
        X = X[good]; Y = Y[good]
    if doMagColors:
        magIdx = bands.index('r')
        Xtemp = X.copy()
        X[:,0] = Xtemp[:,magIdx] #TODO: Make it possible to use other bands seamlessly
        for i in range(1,len(bands)):
            X[:,i] = Xtemp[:,i-1] - Xtemp[:,i]
    return X, Y

def selectTrainTest(X, nTrain = 0.8, nTest = 0.2):
    nTotal = len(X)
    nTrain = int(nTrain*nTotal)
    nTest = nTotal - nTrain
    indexes = np.random.choice(len(X), nTrain+nTest, replace=False)
    trainIndexes = (indexes[:nTrain],)
    testIndexes = (indexes[nTrain:nTrain+nTest],)
    return trainIndexes, testIndexes

def galaxySubSample(X, Y, equalNumbers=True, galFrac=0.1):
    nTot = len(Y)
    nStar = np.sum(Y)
    nGal = nTot - nStar
    if equalNumbers:
        nSub = nStar    
    else:
        nSub = int(galFrac*nGal)   
    idx = np.arange(nTot)
    stars = Y
    gals = np.logical_not(Y)
    galIdx = idx[gals]
    galIdxSub = np.random.choice(galIdx, size=nSub, replace=False)
    goodGals = np.zeros(idx.shape, dtype=bool)
    for i in range(len(goodGals)):
        goodGals[i] = idx[i] in galIdxSub
    good = np.logical_or(stars, goodGals)
    Xsub = X[good]; Ysub = Y[good]
    return Xsub, Ysub

def getClassifier(clfType = 'svc', *args, **kargs):
    if clfType == 'svc':
        return SVC(*args, **kargs)
    elif clfType == 'linearsvc' or clfType == 'linearsvm':
        return LinearSVC(*args, **kargs)
    elif clfType == 'logit' or clfType == 'logistic':
        return LogisticRegression(*args, **kargs)
    else:
        raise ValueError("I don't know the classifier type {0}".format(clfType))

def testMagCuts(clf, X_test, Y_test, testMags, magWidth=1.0, minMag=18.0, maxMag=27.0, num=200,
                doProb=False, probThreshold=0.5, bands=['g', 'r', 'i', 'z', 'y'],
                doMagColors=True, Y_predict=None):
    if Y_predict is not None:
        print "I won't use the classifier that you passed, instead I'll used the predicted labels that you passed"
    mags = np.linspace(minMag, maxMag, num=num)
    starCompl = np.zeros(mags.shape)
    starPurity = np.zeros(mags.shape)
    galCompl = np.zeros(mags.shape)
    galPurity = np.zeros(mags.shape)
    if doProb:
        Probs = np.zeros(mags.shape)
        ProbsMin = np.zeros(mags.shape)
        ProbsMax = np.zeros(mags.shape)
    for i, mag in enumerate(mags):
        if doMagColors:
            idxs = np.where(testMags < mag + magWidth/2)
        else:
            idxs = np.where(testMags < mag + magWidth/2)
        mags_cuts = testMags[idxs]
        X_test_cuts = X_test[idxs]
        Y_test_cuts = Y_test[idxs]
        if Y_predict is not None:
            Y_predict_cuts = Y_predict[idxs]
        if doMagColors:
            idxs = np.where(mags_cuts > mag - magWidth/2)
        else:
            idxs = np.where(mags_cuts > mag - magWidth/2)
        mags_cuts = mags_cuts[idxs]
        X_test_cuts = X_test_cuts[idxs]
        Y_test_cuts = Y_test_cuts[idxs]
        if Y_predict is not None:
            Y_predict_cuts = Y_predict_cuts[idxs]
        starIdxsTrue = np.where(Y_test_cuts == 1)
        galIdxsTrue = np.where(Y_test_cuts == 0)
        if Y_predict is None:
            Y_predict_cuts = clf.predict(X_test_cuts)
        starIdxsPredict = np.where(Y_predict_cuts == 1)
        galIdxsPredict = np.where(Y_predict_cuts == 0)
        if doProb:
            cutProbs = clf.predict_proba(X_test_cuts)[:,1]
            Probs[i] = np.mean(cutProbs[starIdxsTrue])
            minIdxs = np.where(cutProbs[starIdxsTrue] < Probs[i])
            maxIdxs = np.where(cutProbs[starIdxsTrue] > Probs[i])
            ProbsMin[i] = np.mean(cutProbs[starIdxsTrue][minIdxs])
            ProbsMax[i] = np.mean(cutProbs[starIdxsTrue][maxIdxs])
            starIdxsPredict = np.where(cutProbs > probThreshold)
            galIdxsPredict = np.where(cutProbs <= probThreshold)
            Y_predict_cuts[starIdxsPredict] = 1
            Y_predict_cuts[galIdxsPredict] = 0

        nStarsTrue = np.sum(Y_test_cuts)
        nStarsCorrect = np.sum(Y_predict_cuts[starIdxsTrue])
        nStarsPredict = np.sum(Y_predict_cuts)
        nGalsTrue = len(Y_test_cuts) - nStarsTrue
        nGalsCorrect = len(galIdxsTrue[0]) - np.sum(Y_predict_cuts[galIdxsTrue])
        nGalsPredict = len(Y_predict_cuts) - nStarsPredict

        if nStarsTrue > 0:
            starCompl[i] = float(nStarsCorrect)/nStarsTrue
        if nStarsPredict > 0:
            starPurity[i] = float(nStarsCorrect)/nStarsPredict
        if nGalsTrue > 0:
            galCompl[i] = float(nGalsCorrect)/nGalsTrue
        if nGalsPredict > 0:
            galPurity[i] = float(nGalsCorrect)/nGalsPredict
    if doProb:
        return mags, starCompl, starPurity, galCompl, galPurity, Probs, ProbsMin, ProbsMax
    else:
        return mags, starCompl, starPurity, galCompl, galPurity

def plotMagCuts(clf, X_test=None, Y_test=None, X=None, fig=None, linestyle='-', mags=None,
                starCompl=None, starPurity=None, galCompl=None, Probs=None, ProbsMin=None,
                ProbsMax=None, galPurity=None, title=None, xlabel=None, **kargs):
    if 'doProb' in kargs:
        doProb = kargs['doProb']
    else:
        doProb = False
    if 'minMag' in kargs:
        minMag = kargs['minMag']
    else:
        minMag = 18.0
    if 'maxMag' in kargs:
        maxMag = kargs['maxMag']
    else:
        maxMag = 26.0
    if doProb:
        if mags == None or starCompl == None or starPurity == None or galCompl == None\
           or galPurity == None or Probs == None or ProbsMin == None or ProbsMax == None:
            mags, starCompl, starPurity, galCompl, galPurity, Probs, ProbsMin, ProbsMax = testMagCuts(clf, X_test, Y_test, X, **kargs)
    else:
        if mags == None or starCompl == None or starPurity == None or galCompl == None or galPurity == None:
            mags, starCompl, starPurity, galCompl, galPurity = testMagCuts(clf, X_test, Y_test, X, **kargs)
    if not fig:
        fig = plt.figure()
        ax = plt.subplot(1, 2, 0)
        if title is not None:
            ax.set_title(title + " (Stars)", fontsize=18)
        else:
            ax.set_title("Stars", fontsize=18)
        if xlabel is None:
            ax.set_xlabel("Mag Cut Center", fontsize=18)
        else:
            ax.set_xlabel(xlabel, fontsize=18)
        ax.set_ylabel("Star Scores", fontsize=18)
        ax.set_xlim(minMag, maxMag)
        ax.set_ylim(0.0, 1.0)
        for tick in ax.xaxis.get_major_ticks():
            tick.label.set_fontsize(18)
        for tick in ax.yaxis.get_major_ticks():
            tick.label.set_fontsize(18)
        hadFig = False
    else:
        ax = fig.get_axes()[0]
        hadFig = True
    ax.plot(mags, starCompl, 'r', label='Completeness', linestyle=linestyle)
    ax.plot(mags, starPurity, 'b', label='Purity', linestyle=linestyle)
    if not hadFig:
        ax.legend(loc='lower left', fontsize=18)
    
    if not hadFig:
        ax = plt.subplot(1, 2, 1)
        if title is not None:
            ax.set_title(title + " (Galaxies)", fontsize=18)
        else:
            ax.set_title("Galaxies", fontsize=18)
        if xlabel is None:
            ax.set_xlabel("Mag Cut Center", fontsize=18)
        else:
            ax.set_xlabel(xlabel, fontsize=18)
        ax.set_ylabel("Galaxy Scores", fontsize=18)
        ax.set_xlim(minMag, maxMag)
        ax.set_ylim(0.0, 1.0)
        for tick in ax.xaxis.get_major_ticks():
            tick.label.set_fontsize(18)
        for tick in ax.yaxis.get_major_ticks():
            tick.label.set_fontsize(18)
    else:
        ax = plt.subplot(1, 2, 1)
    ax.plot(mags, galCompl, 'r', label='Completeness', linestyle=linestyle)
    ax.plot(mags, galPurity, 'b', label='Purity', linestyle=linestyle)
    if not hadFig:
        ax.legend(loc='lower left', fontsize=18)
    
    if doProb:
        probs = clf.predict_proba(X_test)
        figProb, ax  = plt.subplots(1)
        plt.title("Logistic Regression", fontsize=18)
        plt.xlabel("Magnitude", fontsize=18)
        plt.ylabel("P(Star)", fontsize=18)
        ax.set_xlim(minMag, maxMag)
        ax.set_ylim(0.0, 1.0)
        ax.scatter(X[:, 0][np.logical_not(Y_test)], probs[:,1][np.logical_not(Y_test)], color='red', marker=".", s=3, label='Galaxies')
        ax.scatter(X[:, 0][Y_test], probs[:,1][Y_test], color='blue', marker=".", s=3, label='Stars')
        #ax.fill_between(mags, ProbsMin, ProbsMax, facecolor='grey', alpha=0.5)
        for tick in ax.xaxis.get_major_ticks():
            tick.label.set_fontsize(18)
        for tick in ax.yaxis.get_major_ticks():
            tick.label.set_fontsize(18)
        ax.legend(loc='lower left', fontsize=18)

    if doProb:
        return fig, figProb
    else:
        return fig

def plotDecFunc(clf, X, X_plot=None):
    assert X.shape[1] == 2
    if X_plot is not None:
        assert X_plot.shape == X.shape
    else:
        X_plot = X

    decFunc = clf.decision_function(X)

    fig = plt.figure()

    sc = plt.scatter(X_plot[:,0], X_plot[:,1], c=decFunc, marker="o", s=2, edgecolor="none")

    cb = plt.colorbar(sc, use_gridspec=True)

    return fig

def plotDecBdy(clf, mags, X=None, fig=None, Y=None, withScatter=False, linestyle='-', const=None, ylim=None, xlim=None):
    if X is None:
        magsStd = mags
        exMu = 0.0; exSigma = 1.0
    else:
        magMu = np.mean(X[:,0])
        magSigma = np.std(X[:,0])
        magsStd = (mags - magMu)/magSigma
        exMu = np.mean(X[:,1])
        exSigma = np.std(X[:,1])

    def F(ex, mag):
        ex = (ex-exMu)/exSigma
        if isinstance(ex, np.ndarray):
            mag = mag*np.ones(ex.shape) 
            X = np.vstack([mag, ex]).T
            return clf.decision_function(X)
        else:
            retval = clf.decision_function([mag, ex])[0]
            return retval

    exts = np.zeros(mags.shape)
    for i, mag in enumerate(magsStd):
        try:
            brentMin = -2.0; brentMax = 0.5
            exts[i] = brentq(F, brentMin, brentMax, args=(mag,))
        except:
            print "mag=", mag*magSigma + magMu
            figT = plt.figure()
            arr = np.linspace(brentMin, brentMax, num=100)
            plt.plot(arr, F(arr, mag))
            return figT

    if const is not None:
        exts = np.ones(exts.shape)*const
        linestyle = ':'
    if fig is None:
        fig = plt.figure()
        if withScatter and Y is not None:
            gals = np.logical_not(Y)
            plt.scatter(X[gals][:,0], X[gals][:,1], marker='.', s=1, color='red', label='Galaxies')
            plt.scatter(X[Y][:,0], X[Y][:,1], marker='.', s=1, color='blue', label='Stars')
        plt.plot(mags, exts, color='k', linestyle=linestyle, linewidth=2)
        ax = fig.get_axes()[0]
        for tick in ax.xaxis.get_major_ticks():
            tick.label.set_fontsize(18)
        for tick in ax.yaxis.get_major_ticks():
            tick.label.set_fontsize(18)
        plt.xlabel('Magnitude HSC-R', fontsize=18)
        plt.ylabel('Extendedness HSC-R', fontsize=18)
        ax.legend(loc='upper right', fontsize=18)
        if ylim is not None:
            ax.set_ylim(ylim)
        if xlim is not None:
            ax.set_xlim(xlim)
    else:
        ax = fig.get_axes()[0]
        ax.plot(mags, exts, color='k', linestyle=linestyle, linewidth=2)

    return fig

def fitBands(bands=['g', 'r', 'i', 'z', 'y'], clfType='logit', param_grid={'C':[1.0, 10.0, 100.0]},
             magCut=None, inputFile = '/u/garmilla/Data/HSC/sgClassCosmosDeepCoaddSrcHsc-119320150410GRIZY.fits', catType='hsc', n_jobs=4,
             seed=0, cols=None, makePlots=None, doMagColors=False, samePop=True, galSub=False, galFrac=0.1, equalNumbers=True, 
             withCV=True, clfKargs={'C': 10.0}, X=None, Y=None, fig=None, compareToExtCut=False, linestyle='--', 
             skipBands=[], **kargs):
    np.random.seed(0)
    cat = afwTable.SourceCatalog.readFits(inputFile)
    if samePop:
        assert cols is not None
        if X is None or Y is None:
            X, Y = loadData(bands=bands, catType=catType, inputFile=cat, doMagColors=doMagColors, magCut=magCut, **kargs)
        if galSub:
            X, Y = galaxySubSample(X, Y, galFrac=galFrac, equalNumbers=equalNumbers)
        trainIndexes, testIndexes = selectTrainTest(X)
    for i, b in enumerate(bands):
        if b in skipBands:
            continue
        print "Running analysis for band HSC-{0}".format(b.upper())
        if samePop:
            colsBand = deepcopy(cols)
            for j in range(len(colsBand)):
                colsBand[j] += i
            Xsub = X[:,colsBand]
        else:
            X, Y = loadData(bands=[b], catType=catType, inputFile=cat, doMagColors=doMagColors, magCut=magCut, **kargs)
            print "I'll use {0} objects to train on this band".format(len(X))
            if galSub:
                X, Y = galaxySubSample(X, Y, galFrac=galFrac, equalNumbers=equalNumbers)

            if cols is not None:
                Xsub = X[:,cols]
            else:
                Xsub = X
        if not samePop:
            trainIndexes, testIndexes = selectTrainTest(Xsub)
        trainMean = np.mean(Xsub[trainIndexes], axis=0); trainStd = np.std(Xsub[trainIndexes], axis=0)
        X_train = (Xsub[trainIndexes] - trainMean)/trainStd; Y_train = Y[trainIndexes]
        X_test = (Xsub[testIndexes] - trainMean)/trainStd; Y_test = Y[testIndexes]
        estimator = getClassifier(clfType=clfType, **clfKargs)
        if withCV:
            clf = GridSearchCV(estimator, param_grid, n_jobs=n_jobs)
        else:
            clf = estimator
        clf.fit(X_train, Y_train)
        if makePlots is not None:
            if b in makePlots:
                if fig is None:
                    fig = plotMagCuts(clf, X_test=X_test, Y_test=Y_test, X=X[testIndexes][:,2], linestyle=linestyle,
                                      xlabel='Magnitude HSC-I', title='Single Band SVM')
                else:
                    fig = plotMagCuts(clf, X_test=X_test, Y_test=Y_test, X=X[testIndexes][:,2], linestyle=linestyle, fig=fig,
                                      xlabel='Magnitude HSC-I', title='Single Band SVM')
        if withCV:
            print "The best estimator parameters are"
            print clf.best_params_
            clf = clf.best_estimator_
        score = clf.score(X_test, Y_test)
        print "score=", score
        trainMean = np.mean(Xsub, axis=0); trainStd = np.std(Xsub, axis=0)
        X_train = (Xsub - trainMean)/trainStd; Y_train = Y
        clf.fit(X_train, Y_train)
        if clfType == 'logit' or clfType == 'linearsvc':
            #print "coeffs*std= {0:.2f} & {1:.2f} & {2:.2f} & {3:.2f} & {4:.2f} & {5:.2f} & {6:.2f} & {7:.2f} & {8:.2f} & {9:.2f} & {10:.2f} & {11:.2f} & {12:.2f} & {13:.2f}".format(*tuple(clf.coef_[0]))
            #print "coeffs*std= {0:.2f} & {1:.2f} & {2:.2f} & {3:.2f} & {4:.2f} & {5:.2f} & {6:.2f} & {7:.2f} & {8:.2f} & {9:.2f} & {10:.2f}".format(*tuple(clf.coef_[0]))
            print "coeffs*std", clf.coef_[0]
            coeffs = clf.coef_/trainStd
            coeffs = coeffs[0]
            intercept = clf.intercept_ - np.sum(clf.coef_*trainMean/trainStd)
            intercept = intercept[0]
            print "coeffs=", coeffs
            print "intercept=", intercept
            if cols is not None:
                if len(cols) == 1:
                    print "Cut={0}".format(-intercept/coeffs[0])
    if compareToExtCut:
        assert samePop
        cols = [6]
        Xsub = X[:,cols]
        trainMean = np.mean(Xsub[trainIndexes], axis=0); trainStd = np.std(Xsub[trainIndexes], axis=0)
        X_train = (Xsub[trainIndexes] - trainMean)/trainStd; Y_train = Y[trainIndexes]
        X_test = (Xsub[testIndexes] - trainMean)/trainStd; Y_test = Y[testIndexes]
        estimator = getClassifier(clfType='linearsvc')
        if 'gamma' in param_grid:
            param_grid.pop('gamma')
        clf = GridSearchCV(estimator, param_grid, n_jobs=n_jobs)
        clf.fit(X_train, Y_train)
        print "score=", clf.score(X_test, Y_test)
        coeffs = clf.best_estimator_.coef_/trainStd
        intercept = clf.best_estimator_.intercept_ - np.sum(clf.best_estimator_.coef_*trainMean/trainStd)
        intercept = intercept[0]
        print "Cut={0}".format(-intercept/coeffs[0])
        fig = plotMagCuts(clf, X_test=X_test, Y_test=Y_test, X=X[testIndexes][:,2], fig=fig, linestyle=':')
    return fig, X, Y

def run(doMagColors=False, clfType='logit', param_grid={'C':[0.1, 1.0, 10.0]},
        magCut=None, doProb=False, inputFile = '/u/garmilla/Data/HSC/sgClassCosmosDeepCoaddSrcHsc-119320150411GRIZY.fits', catType='hsc', n_jobs=4,
        probFit=False, probFile='prob.pkl', cols=None, **kargs):
    X, Y = loadData(catType=catType, inputFile=inputFile, doMagColors=doMagColors, magCut=magCut, **kargs)
    if cols is not None:
        X = X[:, cols]
    trainIndexes, testIndexes = selectTrainTest(X)
    trainMean = np.mean(X[trainIndexes], axis=0); trainStd = np.std(X[trainIndexes], axis=0)
    X_train = (X[trainIndexes] - trainMean)/trainStd; Y_train = Y[trainIndexes]
    X_test = (X[testIndexes] - trainMean)/trainStd; Y_test = Y[testIndexes]
    if probFit:
        clfKargs = {}
        for k in param_grid:
            assert len(param_grid[k]) == 1
            clfKargs[k] = param_grid[k][0]
        clf = getClassifier(clfType=clfType, probability=True, **clfKargs)
    else:
        estimator = getClassifier(clfType=clfType)
        clf = GridSearchCV(estimator, param_grid, n_jobs=n_jobs)
    clf.fit(X_train, Y_train)
    score = clf.score(X_test, Y_test)
    print "score=", score
    if probFit:
        import pickle
        with open(probFile, 'wb') as f:
            pickle.dump((clf, trainIndexes, testIndexes, X, Y), f)
    else:
        print "The best estimator parameters are"
        print clf.best_params_
    trainMean = np.mean(X, axis=0); trainStd = np.std(X, axis=0)
    X_train = (X - trainMean)/trainStd; Y_train = Y
    clf.best_estimator_.fit(X_train, Y_train)
    print "coeffs*std=", clf.best_estimator_.coef_
    print "coeffs=", clf.best_estimator_.coef_/trainStd
    print "intercept=", clf.best_estimator_.intercept_ - np.sum(clf.best_estimator_.coef_*trainMean/trainStd)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Build the extreme deconvolution model..")
    parser.add_argument('--clfType', default='svc', type=str,
                        help='Type of classifier to use')
    parser.add_argument('--inputFile', default='sgClassCosmosDeepCoaddSrcHsc-119320150325GRIZY.fits', type=str,
                        help='File containing the input catalog')
    parser.add_argument('--catType', default='hsc', type=str,
                        help='If `hsc` assume the input file is an hsc catalog, `sdss` assume the input file is an sdss catalog.')
    parser.add_argument('--probFit', action='store_true',
                        help='If present, simply do a fit with probability set to True')
    parser.add_argument('--probFile', default='prob.pkl', type=str,
                        help='Name of the file to store the probabilistic classifier')
    kargs = vars(parser.parse_args())
    kargs['bands'] = ['r']
    run(**kargs)
