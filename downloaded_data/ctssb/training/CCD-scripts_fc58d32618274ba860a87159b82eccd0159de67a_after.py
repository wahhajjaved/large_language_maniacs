import pandas as pd
import numpy as np
from numpy import unique
from scipy.stats import zscore,spearmanr,pearsonr
from scipy.fftpack import fft, ifft
from scipy.signal import butter,filtfilt
import seaborn as sns
import matplotlib.pylab as plt
import os
import matplotlib as mpl
from matplotlib import cm
from plotly.offline import download_plotlyjs, init_notebook_mode, plot, iplot
import networkx as nx
from sklearn import linear_model
from sklearn import cross_validation
from sklearn import metrics
from scipy.stats import ttest_1samp,skew
from mne.stats.multi_comp import fdr_correction
import plotly.plotly as py
from plotly.graph_objs import *
from nilearn import plotting
from nilearn import image
from scipy import stats, linalg
import glob



saveFigureLocation='/home/jmuraskin/Projects/CCD/Figures'

class MplColorHelper:

  def __init__(self, cmap_name, start_val, stop_val):
    self.cmap_name = cmap_name
    self.cmap = plt.get_cmap(cmap_name)
    self.norm = mpl.colors.Normalize(vmin=start_val, vmax=stop_val)
    self.scalarMap = cm.ScalarMappable(norm=self.norm, cmap=self.cmap)

  def get_rgb(self, val):
    return self.scalarMap.to_rgba(val)

def butter_lowpass(cutoff, fs, order=5):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    return b, a

def butter_lowpass_filter(data, cutoff, fs, order=5):
    b, a = butter_lowpass(cutoff, fs, order=order)
    y = filtfilt(b, a, data)
    return y




def getCCDSubjectData(filterOn=False,zscoreOn=True,lowpass=0.1,globalNR=0,saveMotionInfo=False,verbose=False,DMN_name='RSN3'):


    SubjInfo = pd.read_csv('/home/jmuraskin/Projects/CCD/CCD-scripts/NARSAD_stimulus_JM.csv')
    # SubjInfo.set_index('JM_INTERNAL',inplace=True)
    dmnIdeal=pd.read_csv('/home/jmuraskin/Projects/NFB/analysis/DMN_ideal_2.csv')

    drFileLocation='/home/jmuraskin/Projects/CCD/CPAC-out/pipeline_CCD_v1'

    GroupDF=[]
    numberOfICs=10
    columnNames=[]
    for rsnNumber in range(numberOfICs):
        columnNames.append('RSN%d' % rsnNumber)

    for indx,row in SubjInfo.iterrows():

        subj = row['JM_INTERNAL']
        if verbose:
            print 'Collecting Subject %s' % subj
        for scan in range(1,3,1):
            drFilePath = '%s/%s_data_/spatial_map_timeseries_for_DR/_scan_feedback_%d/_csf_threshold_0.96/_gm_threshold_0.7/_wm_threshold_0.96/_compcor_ncomponents_5_selector_pc10.linear1.wm0.global%d.motion1.quadratic1.gm0.compcor1.csf1/_spatial_map_PNAS_Smith09_rsn10/spatial_map_timeseries.txt' % (drFileLocation,subj,scan,globalNR)
            df=[]
            subjHasBoth=True
            if os.path.isfile('%s/%s_data_/spatial_map_timeseries_for_DR/_scan_feedback_%d/_csf_threshold_0.96/_gm_threshold_0.7/_wm_threshold_0.96/_compcor_ncomponents_5_selector_pc10.linear1.wm0.global%d.motion1.quadratic1.gm0.compcor1.csf1/_spatial_map_PNAS_Smith09_rsn10/spatial_map_timeseries.txt' % (drFileLocation,subj,1,globalNR)) and os.path.isfile('%s/%s_data_/spatial_map_timeseries_for_DR/_scan_feedback_%d/_csf_threshold_0.96/_gm_threshold_0.7/_wm_threshold_0.96/_compcor_ncomponents_5_selector_pc10.linear1.wm0.global%d.motion1.quadratic1.gm0.compcor1.csf1/_spatial_map_PNAS_Smith09_rsn10/spatial_map_timeseries.txt' % (drFileLocation,subj,2,globalNR)):
                try:
                    df = pd.read_csv(drFilePath,header=None,names=columnNames,delim_whitespace=True)
                    df['Subject_ID'] = subj
                    df['Subject'] = indx
                    df.index.name = 'TR'
                    df.reset_index(level=0,inplace=True)

                    DMN_vals=df[DMN_name]
                    if zscoreOn:
                        df['DMN_skew'] = skew(pd.Series(zscore(df[DMN_name])[:]))



                    else:
                        df['DMN_skew'] = skew(pd.Series(df[DMN_name])[:])
                    # for rsn in columnNames:
                    #     if filterOn:
                    #         if zscoreOn:
                    #             df[rsn]=pd.Series(zscore(butter_lowpass_filter(df[rsn][:],lowpass,0.5)))
                    #         else:
                    #             df[rsn]=pd.Series(butter_lowpass_filter(df[rsn][:],lowpass,0.5))
                    #     else:
                    #         if zscoreOn:
                    #             df[rsn]=pd.Series(zscore(df[rsn][:]))
                    #         else:
                    #             df[rsn]=pd.Series(df[rsn][:])
                    if row['SCAN_%d_PARADIGM' % scan]==1 or row['SCAN_%d_PARADIGM' % scan]==3:
                        for rsn in columnNames:
                            if filterOn:
                                if zscoreOn:
                                    df[rsn]=pd.Series(-1*zscore(butter_lowpass_filter(df[rsn][:],lowpass,0.5)))
                                else:
                                    df[rsn]=pd.Series(-1*butter_lowpass_filter(df[rsn][:],lowpass,0.5))

                            else:
                                if zscoreOn:

                                    df[rsn]=pd.Series(-1*zscore(df[rsn][:]))

                                else:

                                    df[rsn]=pd.Series(-1*df[rsn][:])


                        df['flip']=-1
                        flip=-1
                    else:
                        for rsn in columnNames:
                            if filterOn:
                                if zscoreOn:
                                    df[rsn]=pd.Series(zscore(butter_lowpass_filter(df[rsn][:],lowpass,0.5)))
                                else:
                                    df[rsn]=pd.Series(butter_lowpass_filter(df[rsn][:],lowpass,0.5))

                            else:
                                if zscoreOn:
                                    df[rsn]=pd.Series(zscore(df[rsn][:]))
                                else:
                                    df[rsn]=pd.Series(df[rsn][:])


                        df['flip']=1
                        flip=1

                    #get partial correlations
                    pcorr=partial_corr(np.column_stack([df[DMN_name],zscore(dmnIdeal['Wander']),zscore(dmnIdeal['Focus'])]))
                    df['DMN_pcorrWander']=pcorr[0,1 if flip==1 else 2]
                    df['DMN_pcorrFocus']=pcorr[0,2 if flip==1 else 1]
                    df['FB'] = 'FEEDBACK' if row['SCAN_%d_FEEDBACK' % scan]==1 else 'NOFEEDBACK'
                    df['scanorder']=scan

                    df['modelcorr']=pearsonr((dmnIdeal['Wander']-dmnIdeal['Focus']),df['RSN3'])[0]
                    df['first_half_corr']=pearsonr(flip*(dmnIdeal['Wander'][0:203]-dmnIdeal['Focus'][0:203]),df['RSN3'][0:203])[0]
                    df['second_half_corr']=pearsonr(flip*(dmnIdeal['Wander'][204:]-dmnIdeal['Focus'][204:]),df['RSN3'][204:])[0]
                    for rsn in columnNames:
                        df['%s_modelcorr' % rsn]=pearsonr((dmnIdeal['Wander']-dmnIdeal['Focus']),df[rsn])[0]
    #                 df['DMN']=pd.Series(zscore(nuisanceRegression(df[list(set(columnNames)-set(['RSN3']))],df['RSN3'])))
                    #load meanFD scores
                    fdFilePath='%s/%s_data_/frame_wise_displacement/_scan_feedback_%d/FD.1D' % (drFileLocation,subj,scan)
                    fd=pd.read_csv(fdFilePath,header=None,names=['fd'],delim_whitespace=True)
                    df['meanFD']=fd.mean()[0]
                    df['fd']=fd

                    motion=pd.read_csv('%s/%s_data_/motion_params/_scan_feedback_%d/motion_parameters.txt' % (drFileLocation,subj,scan),sep=',',index_col=False)
                    df['Movements_gt_threshold']=motion['Movements_gt_threshold']
                    df['Max_Relative_RMS_Displacement']=motion['Max_Relative_RMS_Displacement']
                    df['Mean_Relative_RMS_Displacement']=motion['Mean_Relative_RMS_Displacement']
                    fdFilePath='%s/%s_data_/frame_wise_displacement/_scan_tra/FD.1D' % (drFileLocation,subj)
                    fd=pd.read_csv(fdFilePath,header=None,names=['fd'],delim_whitespace=True)
                    df['train_meanFD']=fd.mean()[0]
                    # df['train_fd']=fd

                    if len(GroupDF)==0:
                        GroupDF=df
                    else:
                        GroupDF=pd.concat((GroupDF,df),ignore_index=True)
                except:
                    print 'No DR .txt file found or error for subject : %s' % subj

    GroupDF.reset_index(inplace=True)

    motionInfo=GroupDF.groupby(['Subject_ID','FB','scanorder'])['Max_Relative_RMS_Displacement','meanFD','train_meanFD'].mean()
    if saveMotionInfo:
        motionInfo.to_csv('/home/jmuraskin/Projects/CCD/CCD-scripts/analysis/CCD_meanFD.csv')

    # motionInfo_train=GroupDF.groupby(['Subject_ID']).mean()['train_meanFD']
    # if saveMotionInfo:
    #     motionInfo_train.to_csv('/home/jmuraskin/Projects/CCD/CCD-scripts/analysis/CCD_train_meanFD.csv')

    return GroupDF,motionInfo




def fb_subjectinfo(subject_id,getFeedback=True):
    #Get whether scan is a feedback scan or not
    from pandas import read_csv

    SubjInfo = read_csv('/home/jmuraskin/Projects/CCD/CCD-scripts/NARSAD_stimulus_JM.csv')
    SubjInfo.set_index('JM_INTERNAL',inplace=True)
    scan1=SubjInfo.loc[subject_id]['SCAN_1_FEEDBACK']
    if scan1:
        feedback=0
        noFeedback=1
    else:
        feedback=1
        noFeedback=0
    if getFeedback:
        return feedback
    if not getFeedback:
        return noFeedback

def subjectinfo_scan(subject_id,scan):
    #Get whether scan is a feedback scan or not
    from pandas import read_csv

    SubjInfo = read_csv('/home/jmuraskin/Projects/CCD/CCD-scripts/NARSAD_stimulus_JM.csv')
    SubjInfo.set_index('JM_INTERNAL',inplace=True)
    scan1=SubjInfo.loc[subject_id]['SCAN_%d_FEEDBACK' % scan]
    if scan1==1:
        feedback='Feedback'
    else:
        feedback='NoFeedback'
    return feedback


def getCCDSubjectTrainData(zscoreOn=True,globalNR=0,verbose=False):


    SubjInfo = pd.read_csv('/home/jmuraskin/Projects/CCD/CCD-scripts/NARSAD_stimulus_JM.csv')

    drFileLocation='/home/jmuraskin/Projects/CCD/CPAC-out/pipeline_CCD_v1'

    GroupDF=[]
    numberOfICs=10
    columnNames=[]
    for rsnNumber in range(numberOfICs):
        columnNames.append('RSN%d' % rsnNumber)

    for indx,row in SubjInfo.iterrows():

        subj = row['JM_INTERNAL']
        if verbose:
            print 'Collecting Subject %s' % subj
        drFilePath = '%s/%s_data_/spatial_map_timeseries_for_DR/_scan_tra/_csf_threshold_0.96/_gm_threshold_0.7/_wm_threshold_0.96/_compcor_ncomponents_5_selector_pc10.linear1.wm0.global%d.motion1.quadratic1.gm0.compcor1.csf1/_spatial_map_PNAS_Smith09_rsn10/spatial_map_timeseries.txt' % (drFileLocation,subj,globalNR)
        df=[]
        if os.path.exists(drFilePath):
            df = pd.read_csv(drFilePath,header=None,names=columnNames,delim_whitespace=True)
            df['Subject_ID'] = subj
            df['Subject'] = indx
            df.index.name = 'TR'
            df.reset_index(level=0,inplace=True)
            for rsn in columnNames:
                if zscoreOn:
                    df[rsn]=pd.Series(zscore(df[rsn][:]))

            if len(GroupDF)==0:
                GroupDF=df
            else:
                GroupDF=pd.concat((GroupDF,df),ignore_index=True)
        else:
            print 'Subject %s has no file' % subj

    GroupDF.reset_index(inplace=True)


    return GroupDF


def getSubjectButtonResponses():
    filelist=pd.read_csv('/home/jmuraskin/Projects/CCD/CCD-scripts/NARSAD_stimulus_JM.csv')

    for indx,f in enumerate(filelist['JM_INTERNAL']):
        for r in range(1,3):
            if int(f[-2:])<30:
                luminaFlag=0
            else:
                luminaFlag=1
            numberofbuttonPresses=getSubjectButtonPressScore('/home/jmuraskin/Projects/CCD/NARSAD-DMN-clean/%s_run%d.txt' % (f,r),luminaFlag)
            out={'number':numberofbuttonPresses,'filename':f}
            out['filename']=f
            if (indx+r)==1:
                df=pd.DataFrame(out,index=[0])
                df['subject']=f
                df['run']=r
            else:
                tmp=pd.DataFrame(out,index=[0])
                tmp['subject']=f
                tmp['run']=r
                df=pd.concat((df,tmp),ignore_index=0)
    return df


def getSubjectButtonPressScore(filename,luminaFlag):
    config=pd.read_table(filename,delimiter=';',comment='#')
    numButton=0
    for indx in config[config[' Stim Text']==' Push Button'].index[:]:
        numTmp=0
        for n in range(5):
            if luminaFlag:
                if config.iloc[indx+n][' STIM']==' LUMINA' and numTmp==0:
                    numButton+=1
                    numTmp+=1
            else:
                if config.iloc[indx+n][' STIM']!='53' and numTmp==0:
                    numButton+=1
                    numTmp+=1
    return numButton




def getSubjectList(GroupDF,RejectMotion=True,motionThresh=0.2,motionType='RMS',poor_performer=20):
    #Reject Depressed subjects
    depressed=['CCD072','CCD098','CCD083','CCD062','CCD061','CCD051','CCD087']

    # poor_performers=['CCD094','CCD075','CCD086','CCD080','CCD076','CCD065','CCD034']

    #reject large motion subjects
    allsubj=unique(GroupDF['Subject_ID'])
    if motionType=='FD':
        motionReject=unique((GroupDF[GroupDF.meanFD>motionThresh]['Subject_ID']))
    else:
        motionReject=unique((GroupDF[GroupDF.Max_Relative_RMS_Displacement>motionThresh]['Subject_ID']))
    if RejectMotion:
        goodsubj=np.setdiff1d(allsubj,motionReject)
    else:
        goodsubj=allsubj

    #remove depressed
    goodsubj=np.setdiff1d(goodsubj,np.array(depressed))

    df=getSubjectButtonResponses()
    tmp=df.groupby('subject')['number'].sum()
    goodperformers=np.array(tmp[tmp>poor_performer].index[:])
    #remove poor performers
    goodsubj=np.intersect1d(goodsubj,goodperformers)

    return goodsubj,motionReject


def getBlockedPerformance(GroupDF,goodsubj):
    # Setup Block design analysis Up-Regulation (wander) and Down-Regulation (focus)


    blockedDF=[]
    for rsn in ['RSN3']:
        #enumerate(unique(GroupDF[(GroupDF['feedback_sleep']+GroupDF['train_sleep'])==0]['Subject']))
        for fb in ['FEEDBACK','NOFEEDBACK']:
            for subjNo,subj in enumerate(unique(GroupDF[GroupDF.Subject_ID.isin(goodsubj)]['Subject_ID'])):


                WanderBlockAve=[]
                FocusBlockAve=[]
                tmpDF=GroupDF[np.all([GroupDF['Subject_ID']==subj,GroupDF['FB']==fb],axis=0)]
                flip=np.mean(GroupDF[np.all([GroupDF['Subject_ID']==subj,GroupDF['FB']==fb],axis=0)]['flip'])
                if flip==1:
                    WanderBlocks=[[14,29],[78,108],[127,172],[206,236],[285,300],[334,379]]
                    FocusBlocks=[[31,76],[110,125],[174,204],[238,283],[302,332],[381,396]]
                else:
                    FocusBlocks=[[14,29],[78,108],[127,172],[206,236],[285,300],[334,379]]
                    WanderBlocks=[[31,76],[110,125],[174,204],[238,283],[302,332],[381,396]]
                for indx,wblock in enumerate(WanderBlocks):
                    if indx==0:
                        WanderBlockAve=tmpDF[np.all([tmpDF['TR']>=wblock[0],tmpDF['TR']<=wblock[1]],axis=0)][rsn]
                    else:
                        WanderBlockAve=pd.concat((WanderBlockAve,tmpDF[np.all([tmpDF['TR']>=wblock[0],tmpDF['TR']<=wblock[1]],axis=0)][rsn]))
                for indx,fblock in enumerate(FocusBlocks):
                    if indx==0:
                        FocusBlockAve=tmpDF[np.all([tmpDF['TR']>=fblock[0],tmpDF['TR']<=fblock[1]],axis=0)][rsn]
                    else:
                        FocusBlockAve=pd.concat((FocusBlockAve,tmpDF[np.all([tmpDF['TR']>=fblock[0],tmpDF['TR']<=fblock[1]],axis=0)][rsn]))
                average=[WanderBlockAve.mean(),FocusBlockAve.mean()]
                std=[WanderBlockAve.std(),FocusBlockAve.std()]
    #             indxs=np.concatenate((WanderBlockNumber,FocusBlockNumber))
                wf=['Wander','Focus']
                tmpDF=pd.DataFrame({'average':average,'Condition':wf,'FB':[fb]*2,'std':std})
                tmpDF['subj']=subj
                tmpDF['RSN']=rsn

                if len(blockedDF)<1:
                    blockedDF=tmpDF
                else:
                    blockedDF=pd.concat((blockedDF,tmpDF))
    return blockedDF

def createTimeSeriesPlots(GroupDF,goodsubj,DMN_name='RSN3',title='DMN_Activity',ylabel='',figsize=(18,9),savefig=True):

    sns.set_context("paper")
    #plt.subplots(2,1,figsize=(12, 6))
    f, axarr = plt.subplots(1, sharex=True,figsize=figsize)
    sns.set(style="white")
    dmnPlot=sns.tsplot(data=GroupDF[GroupDF.Subject_ID.isin(goodsubj)],time='TR',unit='Subject',condition='FB',value=DMN_name,ci=68)
    #get ideal DMN time line
    dmnIdeal=pd.read_csv('/home/jmuraskin/Projects/NFB/analysis/DMN_ideal_2.csv')
    dmnPlot.plot((dmnIdeal['Wander']-dmnIdeal['Focus'])/(3*max(dmnIdeal['Wander'])),'k--')
    #dmnPlot.plot(dmnIdeal['Focus'][4:]/(3*max(dmnIdeal['Focus'])),'r--')
    # dmnPlot.set_ylim([-.8,.8])
    dmnPlot.set_ylabel(ylabel,{'fontsize':18})
    dmnPlot.set_xlabel('TR')
    dmnPlot.set_title(title,{'fontsize':24})
    if savefig:
        f.savefig('%s/%s_timeseries.pdf' % (saveFigureLocation,DMN_name), dpi=600)


def createSubjectModelBarPlot(GroupDF,goodsubj,r_scramble,figsize=(18,9),withThreshold=True,savefig=True,ax=[],palette=['b','g']):

    if type(ax)==list:
        f, axarr = plt.subplots(1, sharex=True,figsize=figsize)
        sns.set(style="white")

    maxModel=GroupDF[GroupDF.Subject_ID.isin(goodsubj)].groupby(['Subject'])['modelcorr'].max().sort_values(ascending=False)
    sortedOrder=maxModel.index

    sns.barplot(data=GroupDF[GroupDF.Subject_ID.isin(goodsubj)],x='Subject',y='modelcorr',hue='FB',order=sortedOrder,ax=ax,palette=palette)


    ax.plot([0,len(goodsubj)],[r_scramble[0],r_scramble[0]],'g--',label='Feedback On Threshold')
    ax.plot([0,len(goodsubj)],[r_scramble[1],r_scramble[1]],'b--',label='Feedback Off Threshold')

    if savefig:
        f.savefig('%s/Subject_ModelCorrelations.pdf' % saveFigureLocation, dpi=600)
    return r_scramble

def createScanOrderBarPlot(GroupDF,goodsubj,BV=False,ax=[],savefig=True):
    if type(ax)==list:
        plt.figure()
    if BV:
        sns.factorplot(data=GroupDF[GroupDF.Subject_ID.isin(goodsubj)],x='FB',y='modelcorr',hue='scanorder',kind='bar',units='Subject',ci=68)
    else:
        sns.violinplot(data=GroupDF[GroupDF.Subject_ID.isin(goodsubj)],x='FB',y='modelcorr',hue='scanorder',split='True',bw=.4,inner='quartile',ax=ax, color='w')


    if savefig:
        plt.savefig('%s/ScanOrder_ModelCorrelations.pdf' % saveFigureLocation,dpi=600)

def printModelCorrelations(GroupDF,goodsubj,DMN_name='RSN3'):
    dmnIdeal=pd.read_csv('/home/jmuraskin/Projects/NFB/analysis/DMN_ideal_2.csv')
    print 'No Feedback Focus Correlation= %0.2f' % GroupDF[GroupDF.Subject_ID.isin(goodsubj)].groupby(['FB','TR']).mean()[DMN_name].loc['NOFEEDBACK'].corr(dmnIdeal['Focus'])
    print 'Feedback Focus Correlation= %0.2f' % GroupDF[GroupDF.Subject_ID.isin(goodsubj)].groupby(['FB','TR']).mean()[DMN_name].loc['FEEDBACK'].corr(dmnIdeal['Focus'])
    print 'No Feedback Wander Correlation= %0.2f' % GroupDF[GroupDF.Subject_ID.isin(goodsubj)].groupby(['FB','TR']).mean()[DMN_name].loc['NOFEEDBACK'].corr(dmnIdeal['Wander'])
    print 'Feedback Wander Correlation= %0.2f' % GroupDF[GroupDF.Subject_ID.isin(goodsubj)].groupby(['FB','TR']).mean()[DMN_name].loc['FEEDBACK'].corr(dmnIdeal['Wander'])
    print 'No Feedback Overall Correlation= %0.2f' % GroupDF[GroupDF.Subject_ID.isin(goodsubj)].groupby(['FB','TR']).mean()[DMN_name].loc['NOFEEDBACK'].corr(dmnIdeal['Wander']-dmnIdeal['Focus'])
    print 'Feedback Overall Correlation= %0.2f' % GroupDF[GroupDF.Subject_ID.isin(goodsubj)].groupby(['FB','TR']).mean()[DMN_name].loc['FEEDBACK'].corr(dmnIdeal['Wander']-dmnIdeal['Focus'])


def generateHeatMaps(GroupDF,goodsubj,GroupTrain=[]):

    numberOfICs=10
    columnNames=[]
    for rsnNumber in range(numberOfICs):
            columnNames.append('RSN%d' % rsnNumber)


    heatmapDF=GroupDF[GroupDF.Subject_ID.isin(goodsubj)].groupby(['Subject_ID','FB','TR']).mean()
    hmDiff=np.zeros((10,10,len(unique(GroupDF[GroupDF.Subject_ID.isin(goodsubj)]['Subject_ID']))))
    hmFB=hmDiff.copy()
    hmNFB=hmDiff.copy()
    if len(GroupTrain)>0:
        heatmapTrainDF=GroupTrain[GroupTrain.Subject_ID.isin(goodsubj)].groupby(['Subject_ID','TR']).mean()
        hmTrain=hmDiff.copy()
        hmFB_Train=hmDiff.copy()
        hmNFB_Train=hmDiff.copy()

    for indx,subj in enumerate(unique(GroupDF[GroupDF.Subject_ID.isin(goodsubj)]['Subject_ID'])):
        hmFB[:,:,indx]=heatmapDF.loc[subj,'FEEDBACK'][columnNames].corr()
        hmNFB[:,:,indx]=heatmapDF.loc[subj,'NOFEEDBACK'][columnNames].corr()
        hmDiff[:,:,indx]=np.arctanh(heatmapDF.loc[subj,'FEEDBACK'][columnNames].corr())*np.sqrt(405)-np.arctanh(heatmapDF.loc[subj,'NOFEEDBACK'][columnNames].corr())*np.sqrt(405)
        if len(GroupTrain)>0:
            hmTrain[:,:,indx]=heatmapTrainDF.loc[subj][columnNames].corr()
            hmFB_Train[:,:,indx]=np.arctanh(heatmapDF.loc[subj,'FEEDBACK'][columnNames].corr())*np.sqrt(405)-np.arctanh(heatmapTrainDF.loc[subj][columnNames].corr())*np.sqrt(175)
            hmNFB_Train[:,:,indx]=np.arctanh(heatmapDF.loc[subj,'NOFEEDBACK'][columnNames].corr())*np.sqrt(405)-np.arctanh(heatmapTrainDF.loc[subj][columnNames].corr())*np.sqrt(175)

    if len(GroupTrain)>0:
        return hmFB,hmNFB,hmDiff,hmTrain,hmFB_Train,hmNFB_Train
    else:
        return hmFB,hmNFB,hmDiff


def partial_corr(C):
    """
    Returns the sample linear partial correlation coefficients between pairs of variables in C, controlling
    for the remaining variables in C.
    Parameters
    ----------
    C : array-like, shape (n, p)
        Array with the different variables. Each column of C is taken as a variable
    Returns
    -------
    P : array-like, shape (p, p)
        P[i, j] contains the partial correlation of C[:, i] and C[:, j] controlling
        for the remaining variables in C.
    """

    C = np.asarray(C)
    p = C.shape[1]
    P_corr = np.zeros((p, p), dtype=np.float)
    for i in range(p):
        P_corr[i, i] = 1
        for j in range(i+1, p):
            idx = np.ones(p, dtype=np.bool)
            idx[i] = False
            idx[j] = False
            beta_i = linalg.lstsq(C[:, idx], C[:, j])[0]
            beta_j = linalg.lstsq(C[:, idx], C[:, i])[0]

            res_j = C[:, j] - C[:, idx].dot( beta_i)
            res_i = C[:, i] - C[:, idx].dot(beta_j)

            corr = stats.pearsonr(res_i, res_j)[0]
            P_corr[i, j] = corr
            P_corr[j, i] = corr

    return P_corr

def generateHeatMaps_pcorr(GroupDF,goodsubj):

    numberOfICs=10
    columnNames=[]
    for rsnNumber in range(numberOfICs):
            columnNames.append('RSN%d' % rsnNumber)

    heatmapDF=GroupDF[GroupDF.Subject_ID.isin(goodsubj)].groupby(['Subject_ID','FB','TR']).mean()
    hmDiff=np.zeros((10,10,len(unique(GroupDF[GroupDF.Subject_ID.isin(goodsubj)]['Subject_ID']))))
    hmFB=hmDiff.copy()
    hmNFB=hmDiff.copy()

    for indx,subj in enumerate(unique(GroupDF[GroupDF.Subject_ID.isin(goodsubj)]['Subject_ID'])):
        hmFB[:,:,indx]=partial_corr(heatmapDF.loc[subj,'FEEDBACK'][columnNames])
        hmNFB[:,:,indx]=partial_corr(heatmapDF.loc[subj,'NOFEEDBACK'][columnNames].corr())
        hmDiff[:,:,indx]=np.arctan(hmFB[:,:,indx])-np.arctan(hmNFB[:,:,indx])

    return hmFB,hmNFB,hmDiff



def dist (A,B):
        return np.linalg.norm(np.array(A)-np.array(B))

def get_idx_interv(d, D):
    k=0
    while(d>D[k]):
        k+=1
    return  k-1

class InvalidInputError(Exception):
    pass

def deCasteljau(b,t):
    N=len(b)
    if(N<2):
        raise InvalidInputError("The  control polygon must have at least two points")
    a=np.copy(b) #shallow copy of the list of control points
    for r in range(1,N):
        a[:N-r,:]=(1-t)*a[:N-r,:]+t*a[1:N-r+1,:]
    return a[0,:]

def BezierCv(b, nr=5):
    t=np.linspace(0, 1, nr)
    return np.array([deCasteljau(b, t[k]) for k in range(nr)])

def makeChordDiagram(G,cmap='coolwarm',plotName='ChordDiagram',scale=[-1.0,1.0],title='',savefig=True):

    widthScale=50.0/max(scale)
    COL = MplColorHelper(cmap, scale[0], scale[1])
    #GET LABEL NAMES IF THERE ARE ANY
    labels=G.node.keys()
    Edges=G.edge
    #Get all edge weights
    E=[]
    Weights=[]
    for indx1,j in enumerate(Edges):
        for indx2,k in enumerate(Edges[j]):
            E.append([j,k])
            if j==k:
                Weights.append(0)
            else:
                Weights.append(Edges[j][k]['weight'])
    layt=nx.drawing.layout.circular_layout(G)
    L=len(layt)

    dist(layt[0], layt[5])

    Dist=[0, dist([1,0], 2*[np.sqrt(2)/2]), np.sqrt(2),
    dist([1,0],  [-np.sqrt(2)/2, np.sqrt(2)/2]), 2.0]
    params=[1.2, 1.5, 1.8, 2.1]

    #set node color
    minColor=np.array(COL.get_rgb(scale[0]))*255.0
    maxColor=np.array(COL.get_rgb(scale[1]))*255.0
    node_color=['rgba(%f,%f,%f,1)' % (minColor[0],minColor[1],minColor[2]),
                'rgba(%f,%f,%f,1)' % (maxColor[0],maxColor[1],maxColor[2])]*5

    #Get Node Positions
    Xn=[layt[k][0] for k in range(L)]
    Yn=[layt[k][1] for k in range(L)]


    lines=[]# the list of dicts defining   edge  Plotly attributes
    edge_info=[]# the list of points on edges where  the information is placed

    for j, e in enumerate(E):
        A=np.array(layt[e[0]])
        B=np.array(layt[e[1]])
        d=dist(A, B)
        K=get_idx_interv(d, Dist)
        b=[A, A/params[K], B/params[K], B]
        # color=edge_colors[0]
        pts=BezierCv(b, nr=5)
        mark=list(deCasteljau(b,0.9))
        rgb=np.array(COL.get_rgb(Weights[j]))*255.0

        lines.append(Scatter(x=list(pts[:,0]),
                             y=list(pts[:,1]),
                             mode='lines',
                             line=Line(
                                      shape='spline',
                                      color='rgba(%d,%d,%d,.9)' % (rgb[0],rgb[1],rgb[2]),
                                      width=abs(Weights[j])*widthScale#The  width is proportional to the edge weight
                                     ),
                            hoverinfo='none'
                           )
                    )




    trace2=Scatter(x=Xn,
               y=Yn,
               mode='markers',
               name='',
               marker=Marker(symbol='dot',
                             size=.5,
                             color=node_color,
                             cmin=scale[0],cmax=scale[1],
                             colorscale='coolwarm',
                             colorbar = dict(tickangle=20,thickness=15,x=1.2)
                             ),
               text=labels,
               hoverinfo='text',

               )

    axis=dict(showline=False, # hide axis line, grid, ticklabels and  title
              zeroline=False,
              showgrid=False,
              showticklabels=False,
              title=''
              )
    width=600
    height=575

    layout=Layout(title=title,
                  paper_bgcolor='rgba(0,0,0,0)',
                  plot_bgcolor='rgba(0,0,0,0)',
                  font= Font(size=12),
                  showlegend=False,
                  autosize=False,
                  width=width,
                  height=height,
                  xaxis=XAxis(axis),
                  yaxis=YAxis(axis),
                  margin=Margin(l=120,
                                r=120,
                                b=92,
                                t=135,
                              ),
                  hovermode='closest',
                  images=[dict(
                        source="./RSN/RSN0.png",
                        xref="paper", yref="paper",
                        x=.93, y=.4,
                        sizex=.2, sizey=.2,
                        xanchor="left", yanchor="bottom",
                        layer='below'

                      ),
                    dict(
                        source="./RSN/RSN1.png",
                        xref="paper", yref="paper",
                        x=.85, y=.7,
                        sizex=.2, sizey=.2,
                        xanchor="left", yanchor="bottom",
                        layer='below'

                      ),
                    dict(
                        source="./RSN/RSN2.png",
                        xref="paper", yref="paper",
                        x=.55, y=.94,
                        sizex=.2, sizey=.2,
                        xanchor="left", yanchor="bottom",
                        layer='below'

                      ),
                    dict(
                        source="./RSN/RSN3.png",
                        xref="paper", yref="paper",
                        x=.25, y=.94,
                        sizex=.2, sizey=.2,
                        xanchor="left", yanchor="bottom",
                        layer='below'

                      ),
                    dict(
                        source="./RSN/RSN4.png",
                        xref="paper", yref="paper",
                        x=-0.02, y=.7,
                        sizex=.2, sizey=.2,
                        xanchor="left", yanchor="bottom",
                        layer='below'

                      ),
                    dict(
                        source="./RSN/RSN5.png",
                        xref="paper", yref="paper",
                        x=-.1, y=.4,
                        sizex=.2, sizey=.2,
                        xanchor="left", yanchor="bottom",
                        layer='below'

                      ),
                    dict(
                        source="./RSN/RSN6.png",
                        xref="paper", yref="paper",
                        x=-0.03, y=.1,
                        sizex=.2, sizey=.2,
                        xanchor="left", yanchor="bottom",
                        layer='below'

                      ),
                    dict(
                        source="./RSN/RSN7.png",
                        xref="paper", yref="paper",
                        x=.25, y=-0.14,
                        sizex=.2, sizey=.2,
                        xanchor="left", yanchor="bottom",
                        layer='below'

                      ),
                    dict(
                        source="./RSN/RSN8.png",
                        xref="paper", yref="paper",
                        x=.55, y=-0.14,
                        sizex=.2, sizey=.2,
                        xanchor="left", yanchor="bottom",
                        layer='below'

                      ),
                    dict(
                        source="./RSN/RSN9.png",
                        xref="paper", yref="paper",
                        x=.85, y=.1,
                        sizex=.2, sizey=.2,
                        xanchor="left", yanchor="bottom",
                        layer='below'

                      )]
                  )

    data=Data(lines+edge_info+[trace2])
    fig=Figure(data=data, layout=layout)
    if savefig:
        py.image.save_as(fig, filename='%s/%s.png' % (saveFigureLocation,plotName))
    return fig


def heatmap2Chord(matrix,plotName='ChordDiagram',title='',savefig=True,scale=[-1,1]):

    # check size of matrix
    matSize=np.shape(matrix)
    if len(matSize)==3:
        #get mean of matrix
        matrix=np.mean(matrix,axis=2)

    G = nx.from_numpy_matrix(matrix)

    fig=makeChordDiagram(G,cmap='coolwarm',plotName='ChordDiagram',scale=scale,title=title,savefig=savefig)

    return fig



def LinRegression(X,y):
    regr = linear_model.LinearRegression()
    regr.fit(X,y)

    score=regr.score(X,y)
    resids=y-regr.predict(X)

    return score,resids,regr.coef_,regr.predict(X)


def leaveOneOutCV(clf,X,y,LOO=False,numFolds=10):
    from sklearn.cross_validation import LeaveOneOut,KFold
    coefs=np.zeros((X.shape[1],))
    intercept=0.0
    predicted=np.zeros((len(y),))
    if LOO:
        loo = LeaveOneOut(n=len(y))
        numFolds=len(y)
    else:
        loo = KFold(n=len(y),n_folds=numFolds)
        # numFolds=10
    for train_index, test_index in loo:
        clf.fit(X[train_index,:],y[train_index])
        predicted[test_index]=clf.predict(X[test_index,:])
        intercept+=clf.intercept_
        coefs+=clf.coef_

    intercept=intercept/numFolds
    coefs=coefs/numFolds
    return predicted,intercept,coefs

def bayesianRidge(X,y):
    clf = linear_model.BayesianRidge(compute_score=True)
    predicted = cross_validation.cross_val_predict(clf, X,y,cv=408)
    return clf,predicted

def GroupRegression(GroupDF,goodsubj,feedback,numFolds=10,addMotion=True,verbose=False):

    numberOfICs=10
    columnNames=[]
    for rsnNumber in range(numberOfICs):
            columnNames.append('RSN%d' % rsnNumber)
    dmnIdeal=pd.read_csv('/home/jmuraskin/Projects/NFB/analysis/DMN_ideal_2.csv')

    SubjectDF = GroupDF[GroupDF.Subject_ID.isin(goodsubj)].groupby(['Subject_ID','FB','TR']).mean()
    clf = linear_model.LinearRegression()

    for indx,subj in enumerate(unique(GroupDF['Subject_ID'])):
        if verbose:
            print "Running Subject- %s" % subj
        if addMotion:
            X=np.column_stack((np.array(SubjectDF.loc[subj,feedback][columnNames]),zscore(SubjectDF.loc[subj,feedback]['fd'])))
        else:
            X=np.array(SubjectDF.loc[subj,feedback][columnNames])
        if verbose:
            print X.shape
        predicted,intercepts,coef = leaveOneOutCV(clf,X,dmnIdeal['Wander']-dmnIdeal['Focus'],numFolds=numFolds)
        if indx==0:
            groupGLM=pd.DataFrame({'TR':range(408),'predicted':predicted,'subj':[subj]*408})
            coefs=pd.DataFrame({'Coef':coef,'pe':range(X.shape[1]),'subj':[subj]*X.shape[1]})
            performance=pd.DataFrame({'R':[pearsonr(dmnIdeal['Wander']-dmnIdeal['Focus'],predicted)[0]],'subj':[subj]})
        else:
            df=pd.DataFrame({'TR':range(408),'predicted':predicted,'subj':[subj]*408})
            groupGLM=pd.concat((groupGLM,df),ignore_index=True)
            coefs=pd.concat((coefs,pd.DataFrame({'Coef':coef,'pe':range(X.shape[1]),'subj':[subj]*X.shape[1]})),ignore_index=True)
            performance=pd.concat((performance,pd.DataFrame({'R':[pearsonr(dmnIdeal['Wander']-dmnIdeal['Focus'],predicted)[0]],'subj':[subj]})),ignore_index=True)

    return groupGLM,coefs,performance

def linearRegressionData(GroupDF,goodsubj,numFolds=10,addMotion=True,verbose=False):
    print 'Running Feedback on Regressions'
    fb_pred,fb_coefs,fb_performance=GroupRegression(GroupDF[GroupDF.Subject_ID.isin(goodsubj)],goodsubj,'FEEDBACK',numFolds=numFolds,addMotion=addMotion,verbose=verbose)
    print 'Finished...'
    print 'Running Feedback off Regressions'
    nfb_pred,nfb_coefs,nfb_performance=GroupRegression(GroupDF[GroupDF.Subject_ID.isin(goodsubj)],goodsubj,'NOFEEDBACK',numFolds=numFolds,addMotion=addMotion,verbose=verbose)
    print 'Finished...'

    fb_pred['fb']='FEEDBACK'
    nfb_pred['fb']='NOFEEDBACK'
    predictions=pd.concat((fb_pred,nfb_pred),ignore_index=True)

    fb_coefs['fb']='FEEDBACK'
    nfb_coefs['fb']='NOFEEDBACK'
    coefs=pd.concat((fb_coefs,nfb_coefs),ignore_index=True)

    fb_performance['fb']='FEEDBACK'
    nfb_performance['fb']='NOFEEDBACK'
    performance=pd.concat((fb_performance,nfb_performance),ignore_index=True)

    return predictions,coefs,performance,fb_coefs,nfb_coefs


def createRegressionPlots(predictions,performance,coefs,fb_coefs,nfb_coefs,GroupDF,goodsubj,savefig=True):
    f=plt.figure(figsize=(22,12))
    ax1=plt.subplot2grid((2,4),(0,0), colspan=3)
    ax2=plt.subplot2grid((2,4),(0,3))
    ax3=plt.subplot2grid((2,4),(1,0), colspan=2)
    ax4=plt.subplot2grid((2,4),(1,2), colspan=2)

    dmnIdeal=pd.read_csv('/home/jmuraskin/Projects/NFB/analysis/DMN_ideal_2.csv')

    sns.tsplot(data=predictions,time='TR',value='predicted',unit='subj',condition='fb',ax=ax1)
    ax1.plot((dmnIdeal['Wander']-dmnIdeal['Focus'])/3,'k--')
    ax1.set_title('Average Predicted Time Series')

    g=sns.violinplot(data=performance,x='fb',y='R',split=True,bw=.3,inner='quartile',ax=ax2)
    # plt.close(g.fig)

    g=sns.violinplot(data=coefs,x='pe',y='Coef',hue='fb',split=True,bw=.3,inner='quartile',ax=ax3)
    g.plot([-1,len(unique(coefs['pe']))],[0,0],'k--')
    g.set_xlim([-.5,len(unique(coefs['pe']))])
    ylim=g.get_ylim()
    t,p = ttest_1samp(np.array(performance[performance.fb=='FEEDBACK']['R'])-np.array(performance[performance.fb=='NOFEEDBACK']['R']),0)
    ax2.set_title('Mean Subject Time Series Correlations-p=%0.2f' % p)

    t,p = ttest_1samp(np.array(fb_coefs['Coef'].reshape(len(unique(GroupDF[GroupDF.Subject_ID.isin(goodsubj)]['Subject_ID'])),len(unique(coefs['pe'])))),0)
    p05_FB,padj=fdr_correction(p,0.05)
    t,p = ttest_1samp(np.array(nfb_coefs['Coef'].reshape(len(unique(GroupDF[GroupDF.Subject_ID.isin(goodsubj)]['Subject_ID'])),len(unique(coefs['pe'])))),0)
    p05_NFB,padj=fdr_correction(p,0.05)
    for idx,(pFDR_FB,pFDR_NFB) in enumerate(zip(p05_FB,p05_NFB)):
        if pFDR_FB:
            ax3.scatter(idx,ylim[1]-.05,marker='*',s=75)
        if pFDR_NFB:
            ax3.scatter(idx,ylim[0]+.05,marker='*',s=75)


    t,p=ttest_1samp(np.array(fb_coefs['Coef']-nfb_coefs['Coef']).reshape(len(unique(GroupDF[GroupDF.Subject_ID.isin(goodsubj)]['Subject_ID'])),len(unique(coefs['pe']))),0)
    p05,padj=fdr_correction(p,0.05)

    sns.barplot(x=range(len(t)),y=t,ax=ax4,color='Red')
    for idx,pFDR in enumerate(p05):
        if pFDR:
            ax4.scatter(idx,t[idx]+ np.sign(t[idx])*0.2,marker='*',s=75)
    ax4.set_xlim([-0.5,len(unique(coefs['pe']))])
    ax4.set_xlabel('pe')
    ax4.set_ylabel('t-value')
    ax4.set_title('FB vs. nFB PE')

    for ax in [ax1,ax2,ax3,ax4]:
        for item in ([ax.title, ax.xaxis.label, ax.yaxis.label]):
            item.set_fontsize(18)
        for item in (ax.get_xticklabels() + ax.get_yticklabels()):
            item.set_fontsize(12)

    f.tight_layout()
    if savefig:
        f.savefig('%s/RSN_LinearRegPrediction.pdf' % saveFigureLocation,dpi=300)


def createTFCEfMRIOverlayImages(folder,suffix,title='',vmax=8,display_mode='z',slices=range(-20,50,10),threshold=0.94999,plotToAxis=False,f=[],axes=[],colorbar=True,tight_layout=False,draw_cross=False):


    TFCEposImg,posImg,TFCEnegImg,negImg=getFileNamesfromFolder(folder,suffix)

    bg_img='./Templates/MNI152_.5mm_masked_edged.nii.gz'
    # threshold=0.949
    pos=image.math_img("np.multiply(img1,img2)",
                         img1=image.threshold_img(TFCEposImg,threshold=threshold),img2=posImg)
    neg=image.math_img("np.multiply(img1,img2)",
                         img1=image.threshold_img(TFCEnegImg,threshold=threshold),img2=negImg)
    fw=image.math_img("img1-img2",img1=pos,img2=neg)

    if plotToAxis:
        display=plotting.plot_stat_map(fw,display_mode=display_mode,threshold=0,
                                       cut_coords=slices,vmax=vmax,colorbar=colorbar,bg_img=bg_img,black_bg=False,title=title,dim=0,figure=f,axes=axes,draw_cross=draw_cross)
    else:
        display=plotting.plot_stat_map(fw,display_mode=display_mode,threshold=0,
        cut_coords=slices,vmax=vmax,colorbar=colorbar,bg_img=bg_img,
        black_bg=False,title=title,dim=0)
    if tight_layout:
        display.tight_layout()
    return display


def runRLMR(y,X,modelNames=[],RLM=True,addconstant=True,plotFigure=True,figsize=(20,20)):
    import statsmodels.api as sm
    if addconstant:
        X=sm.add_constant(X)
    if RLM:
        model = sm.RLM(y, X)
    else:
        model = sm.OLS(y,X)
    results = model.fit()
    print results.summary()

    if plotFigure:
        if RLM:
            #first figure out how many plots
            numX=X.shape[1]-1
            if numX>2:
                fig, axarr = plt.subplots(int(np.ceil(numX/3.0)),3,figsize=figsize)
            else:
                fig, axarr = plt.subplots(1,2,figsize=figsize)
            row=0
            column=0
            for n in range(1,numX+1):
    #             fig, axarr = plt.subplots(int(np.ceil(numX/3.0)),3,figsize=(10,10))
                if numX>2:
                    sm.graphics.plot_ccpr(results,results.model.exog_names[n], ax = axarr[row][column])
                else:
                    sm.graphics.plot_ccpr(results,results.model.exog_names[n], ax = axarr[column])

                axarr[row][column].set_title(modelNames[n-1])
                column+=1
                if column==3:
                    column=0
                    row+=1
            for indx,t in enumerate(range(n,int(np.ceil(numX/3.0))*3)):
                fig.delaxes(axarr[row][column])
                column+=1

        else:
            fig, axarr = plt.subplots(figsize=figsize)
            fig=sm.graphics.plot_ccpr_grid(results,fig=fig)
    return results




def getFileNamesfromFolder(folder,suffix):
    #File loader for randomise TFCE folders

    TFCEposImg=glob.glob('%s/%s_tfce_corrp_tstat1.nii.gz' % (folder,suffix))
    posImg=glob.glob('%s/%s_tstat1.nii.gz' % (folder,suffix))
    TFCEnegImg=glob.glob('%s/%s_tfce_corrp_tstat2.nii.gz' % (folder,suffix))
    negImg=glob.glob('%s/%s_tstat2.nii.gz' % (folder,suffix))

    return TFCEposImg,posImg,TFCEnegImg,negImg


def make_pysurfer_images(folder,suffix='cope1',threshold=0.9499,coords=(),surface='inflated',fwhm=0,filename='',saveFolder=[]):
    from surfer import Brain, io
    TFCEposImg,posImg,TFCEnegImg,negImg=getFileNamesfromFolder(folder,suffix)

    pos=image.math_img("np.multiply(img1,img2)",
                         img1=image.threshold_img(TFCEposImg,threshold=threshold),img2=posImg)
    neg=image.math_img("np.multiply(img1,img2)",
                         img1=image.threshold_img(TFCEnegImg,threshold=threshold),img2=negImg)
    fw=image.math_img("img1-img2",img1=pos,img2=neg)

    if fwhm==0:
        smin=np.min(np.abs(fw.get_data()[fw.get_data()!=0]))
    else:
        smin=2

    mri_file = "%s/thresholded_posneg.nii.gz" % folder
    fw.to_filename(mri_file)

    """Bring up the visualization"""
    brain = Brain("fsaverage", "split", surface ,views=['lat', 'med'], offscreen=True , background="white")

    """Project the volume file and return as an array"""

    reg_file = os.path.join("/opt/freesurfer","average/mni152.register.dat")
    surf_data_lh = io.project_volume_data(mri_file, "lh", reg_file,smooth_fwhm=fwhm)
    surf_data_rh = io.project_volume_data(mri_file, "rh", reg_file,smooth_fwhm=fwhm)


    """
    You can pass this array to the add_overlay method for a typical activation
    overlay (with thresholding, etc.).
    """
    brain.add_overlay(surf_data_lh, min=smin, max=5, name="ang_corr_lh", hemi='lh')
    brain.add_overlay(surf_data_rh, min=smin, max=5, name="ang_corr_rh", hemi='rh')

    if len(coords)>0:
        if coords[0]>0:
            hemi='rh'
        else:
            hemi='lh'
        brain.add_foci(coords, map_surface="pial", color="gold",hemi=hemi)

    if len(saveFolder)>0:
        folder=saveFolder
        brain.save_image('%s/%s.png' % (folder,filename))
    else:
        brain.save_image('%s/surfaceplot.jpg' % folder)
    brain.close()

def make_pysurfer_images_lh_rh(folder,suffix='cope1',hemi='lh',threshold=0.9499,coords=(),surface='inflated',fwhm=0,filename='',saveFolder=[],vmax=5.0):
    from surfer import Brain, io
    TFCEposImg,posImg,TFCEnegImg,negImg=getFileNamesfromFolder(folder,suffix)

    pos=image.math_img("np.multiply(img1,img2)",
                         img1=image.threshold_img(TFCEposImg,threshold=threshold),img2=posImg)
    neg=image.math_img("np.multiply(img1,img2)",
                         img1=image.threshold_img(TFCEnegImg,threshold=threshold),img2=negImg)
    fw=image.math_img("img1-img2",img1=pos,img2=neg)

    if fwhm==0:
        smin=np.min(np.abs(fw.get_data()[fw.get_data()!=0]))
    else:
        smin=2

    mri_file = "%s/thresholded_posneg.nii.gz" % folder
    fw.to_filename(mri_file)

    """Bring up the visualization"""
    brain = Brain("fsaverage",surface,hemi=hemi, offscreen=True , background="white")

    """Project the volume file and return as an array"""

    reg_file = os.path.join("/opt/freesurfer","average/mni152.register.dat")
    surf_data = io.project_volume_data(mri_file, hemi, reg_file,smooth_fwhm=fwhm)
    #  surf_data_rh = io.project_volume_data(mri_file, "rh", reg_file,smooth_fwhm=fwhm)


    """
    You can pass this array to the add_overlay method for a typical activation
    overlay (with thresholding, etc.).
    """
    brain.add_overlay(surf_data, min=smin, max=vmax, name="activation", hemi=hemi)
    # brain.overlays["activation"]
    # brain.add_overlay(surf_data_rh, min=smin, max=5, name="ang_corr_rh", hemi='rh')

    if len(coords)>0:
        if coords[0]>0:
            hemi2='rh'
        else:
            hemi2='lh'
        brain.add_foci(coords, map_surface="pial", color="gold",hemi=hemi2)

    if len(saveFolder)>0:
        folder=saveFolder
        brain.save_montage('%s/%s-%s.png' % (folder,hemi,filename),['l', 'm'], orientation='h')

    else:
        brain.save_image('%s/surfaceplot.jpg' % folder)
    brain.close()

def phaseScrambleTS(ts):
    """Returns a TS: original TS power is preserved; TS phase is shuffled."""
    fs = fft(ts)
    pow_fs = np.abs(fs) ** 2.
    phase_fs = np.angle(fs)
    phase_fsr = phase_fs.copy()
    phase_fsr_lh = phase_fsr[1:len(phase_fsr)/2]
    np.random.shuffle(phase_fsr_lh)
    phase_fsr_rh = -phase_fsr_lh[::-1]
    phase_fsr = np.append(phase_fsr[0],
                          np.append(phase_fsr_lh,
                                    np.append(phase_fsr[len(phase_fsr)/2],
                                              phase_fsr_rh)))
    fsrp = np.sqrt(pow_fs) * (np.cos(phase_fsr) + 1j * np.sin(phase_fsr))
    tsr = ifft(fsrp)
    return np.real(tsr)

def get_null_correlations(GroupDF,goodsubj,nperms=1000,p=0.05):
    dmnIdeal=pd.read_csv('/home/jmuraskin/Projects/NFB/analysis/DMN_ideal_2.csv')
    r_scram=np.zeros((len(goodsubj),2))
    #get pvalue spot
    val=-1*nperms*p
    for fb_indx,fb in enumerate(['FEEDBACK','NOFEEDBACK']):
        for s_indx,subj in enumerate(goodsubj):
    #         print 'Running subject %s #%d' % (fb,s_indx)
            ts=GroupDF[np.all([GroupDF['Subject_ID']==subj,GroupDF['FB']==fb],axis=0)]['RSN3']
            rs=np.zeros((nperms,))
            for n in range(nperms):
                ts_scram=phaseScrambleTS(ts)
                rs[n]=pearsonr(ts_scram,dmnIdeal['Wander']-dmnIdeal['Focus'])[0]
            flat=rs.flatten()
            flat.sort()
            r_scram[s_indx,fb_indx]=flat[val]
    return r_scram




def get_FB_scores(filename,signflip=1):
    from scipy.interpolate import interp1d

    TRs=range(6,824,2)

    #first get the header information
    cfg_details=pandas.read_table(filename,sep=':', nrows=8,header=None,names=['variables','values'])

    #check if run completed Num Stim should be 412
    if int(cfg_details[cfg_details.variables=='#NUM STIM   ']['values'].values[0])!=412:
        return []


    #get feedback information
    fb=int(cfg_details[cfg_details.variables=='#FEEDBACK   ']['values'])

    #get rest of table
    config=pandas.read_table(filename, delimiter=';',comment='#')
    # get focus outputs
    focus=config[np.all([config[' STIM']==' STIM',config[' Show']==fb,config[' Stim Text']==' Focus'],axis=0)][' Classifier Output'].sum()
    # get wander outputs
    wander=config[np.all([config[' STIM']==' STIM',config[' Show']==fb,config[' Stim Text']==' Wander'],axis=0)][' Classifier Output'].sum()

    #get timeseries of outputs
    clf_output=config[config[' STIM']==' STIM'][' Detrended Output'].values
    #get time of classifier
    time=config[config[' STIM']==' STIM']['Time Stamp'].values
    #find where classifier outputs are high (in the begininning)
    clf_output[clf_output>10]=np.mean(clf_output[clf_output<10])
    #interpolate onto normal time grid
    f = interp1d(map(float,time),clf_output)
    #zscore and make into dataframe
    df=pandas.DataFrame({'time':TRs,'clf':zscore(signflip*f(TRs))})
    df['fb']=fb
    df['focus']=focus
    df['wander']=wander
    return df
