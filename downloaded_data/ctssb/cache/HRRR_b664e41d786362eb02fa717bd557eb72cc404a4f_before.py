# -*- coding: utf-8 -*-
"""
Created on Wed Jul  2 16:00:55 2014

@author: mattjohnson
"""


import numpy as np
import os
from scipy.io import netcdf
import bisect
import numpy.ma as ma

def compress_radartohrrr(radar_filename, sounding_filename, ceil_filename,radar_directory=os.getcwd(), sounding_directory=os.getcwd(), ceil_directory=os.getcwd(), output_directory = os.getcwd(), tsinds = None, hsinds = None, produce_file = False):
    """
    converts high resolution copol reflectivity into a matrix of reflectivities that correspond to the set of hrrr times
    and pressures for fair comparison, range in m, times in s, 
    """
    wkdir = os.getcwd()

    x = get_netcdf_variables(filename = radar_filename, directory = radar_directory,variablelist=
                                ['reflectivity_copol','range','time','signal_to_noise_ratio_copol'])

    copol = x[0][0][0]    

    ran = x[0][0][1]

    times = x[0][0][2]
    
    snr = x[0][0][3]
    
    [[sdata,sdim,sunits],sdate,f] = get_netcdf_variables(filename=sounding_filename,directory=sounding_directory,variablelist=['pres','alt'])
    
    [[cdata,cdim,cunits],cdate,f_c] = get_netcdf_variables(filename=ceil_filename,directory=ceil_directory,variablelist=['first_cbh'])
    
    cdata = np.array(cdata)
    
    hrrr_heights = np.interp(HRRR_PS[::-1],sdata[0][::-1],sdata[1][::-1])
    hrrr_heights = hrrr_heights[::-1]
    
    if tsinds == None and hsinds == None:
        [hsinds,tsinds] = calc_radar2hrrr_inds(times,ran,hrrr_heights)
        hsinds[-1] = hsinds[-1]-1
    

    
    cdata = cdata[0,:].T
    ceil_presence = []
    c_time = np.array(cdata.shape).max(axis=0)
    c_time_h = c_time/24
    ctsinds = set(range(0,c_time,c_time_h/2.))
    ctsinds-=set(range(0,c_time_h,c_time_h))
    ctsinds = list(ctsinds)
    ctsinds.append(0)
    ctsinds.append(c_time)
    ctsinds = sorted(ctsinds)
    
    for i in range(len(ctsinds)-1): 
        temp = cdata[ctsinds[i]:ctsinds[i+1]]
        if max(temp.tolist())<0:
            ceil_presence.append(2000)
        else:
            tempnew = filter_mask(temp,temp,0)
            ceil_presence.append(tempnew.mean(axis=0))
    
    ceil_presence = np.array(ceil_presence)
            
    copol = np.array(copol)
    snr = np.array(snr)
    copol = 10**(copol/10)
    snr = 10**(snr/10)
    
    print ceil_presence
    
    z = []
    zsnr = []
    y = []
    y2 = []
    
    q = max(hsinds.count(hsinds[-1]),hsinds.count(hsinds[0]))
    q = len(hsinds)-q

    for i in range(len(tsinds)-1):
        for j in range(len(hsinds)-1):
            if hsinds[j] != hsinds[j+1] and tsinds[i] != tsinds[i+1]:
                if ran[hsinds[j+1]] > ceil_presence[i] and ran[hsinds[j]] < ceil_presence[i]:
                     q = bisect.bisect_left(ran,ceil_presence[i])
                     temp_array1 = copol[tsinds[i]:tsinds[i+1],q:hsinds[j+1]]
                     temp_array2 = filter_mask(copol[tsinds[i]:tsinds[i+1],hsinds[j]:q],copol[tsinds[i]:tsinds[i+1],hsinds[j]:q],-15)
                     temp_array2 = ma.filled(temp_array2,0)
                     temp_array = np.zeros((tsinds[i+1]-tsinds[i],hsinds[j+1]-hsinds[j]))
                     temp_array = np.concatenate((temp_array1,temp_array2),axis=1)
                     temp = float(np.nanmean(np.nanmean(temp_array,axis=1),axis=0))
                     temp2 = float(np.nanmean(np.nanmean(snr[tsinds[i]:tsinds[i+1],hsinds[j]:hsinds[j+1]],axis=1),axis=0))
                elif ran[hsinds[j+1]] <= ceil_presence[0,i]:
                    temp_array = filter_mask(copol[tsinds[i]:tsinds[i+1],hsinds[j]:hsinds[j+1]],copol[tsinds[i]:tsinds[i+1],hsinds[j]:hsinds[j+1]],-15)
                    temp_array = ma.filled(temp_array,0)
                    temp = float(np.nanmean(np.nanmean(temp_array,axis=1),axis=0))
                    temp2 = temp2 = float(np.nanmean(np.nanmean(snr[tsinds[i]:tsinds[i+1],hsinds[j]:hsinds[j+1]],axis=1),axis=0))
                else:
                    temp = float(np.nanmean(np.nanmean(copol[tsinds[i]:tsinds[i+1],hsinds[j]:hsinds[j+1]],axis=1),axis=0))
                    temp2 = float(np.nanmean(np.nanmean(snr[tsinds[i]:tsinds[i+1],hsinds[j]:hsinds[j+1]],axis=1),axis=0))
                if temp == None or temp == []:
                    temp = np.nan
                if temp2 == None or temp2 == []:
                    temp2 = np.nan
                y.append(temp)
                y2.append(temp2)
        if y == [] or y == None:
            y = np.nan*np.ones(q)
        if y2 == [] or y2 == None:
            y2 = np.nan*np.ones(q)
        z.append(y)
        zsnr.append(y2)
        y = []
        y2 = []
        

    z = np.array(z)
    zsnr = np.array(zsnr)
    z = 10*np.log10(z)
    zsnr = 10*np.log10(zsnr)
    
    indexes = np.where(z==np.nan)
    indexes2 = np.where(zsnr==np.nan)
    indexes = np.array(indexes)
    indexes2 = np.array(indexes2)
    z = z.tolist()
    zsnr = zsnr.tolist()
    
    for i in range(indexes.shape[1]):
        z[indexes[0][i]][indexes[1][i]] = None
    for i in range(indexes2.shape[1]):
        zsnr[indexes[0][i]][indexes[1][i]] = None
    
    
    
    if produce_file:
        os.chdir(output_directory)
        import json
        import datetime
        date = datetime.datetime(int(radar_filename[15:19]),int(radar_filename[19:21]),int(radar_filename[21:23]))
        filestring = produce_radar_txt_string(date)
        g = open(filestring,'w')
        u = [z,zsnr,ceil_presence.tolist(),hrrr_heights.tolist(),tsinds,hsinds]
        json.dump(u,g)
        g.close()
        os.chdir(wkdir)
        x[-1].close()
        f.close()
        f_c.close()
        return [z,zsnr,ceil_presence.tolist(),hrrr_heights,tsinds,hsinds]
        
    x[-1].close()
    f.close()
    f_c.close()
    os.chdir(wkdir)
    return [z,zsnr,ceil_presence.tolist(),hrrr_heights,tsinds,hsinds]
        
def calc_radar2hrrr_inds(times,radarh,hrrrhf):
    """
    works out indicies closest to each pressure level and hour and thus the matrices that need to be compressed to one value
    times in sec, pres in hPa
    """
    timesf = np.array(range(0,24))*60.*60.
    
    hhsave = []
    for i in range(len(hrrrhf.tolist())+1):
        if i == 0:
            hhsave.append(hrrrhf[0])
        elif i == len(hrrrhf.tolist()):
            hhsave.append(hrrrhf[-1])
        else:
            hhsave.append((hrrrhf[i-1]+hrrrhf[i])/2)

    hhsave = set(hhsave)
    radarset = set(radarh)
    hhtest = radarset.union(hhsave)
    hhtest = sorted(list(hhtest))
    hhsave = sorted(list(hhsave))
    
    hsinds = []
    for i in range(len(hhsave)):
        hsinds.append(hhtest.index(hhsave[i])-i)
            
    timesave = []
    for i in range(len(timesf)+1):
        if i == 0:
            timesave.append(timesf[0])
        elif i == len(timesf):
            timesave.append(timesf[-1])
        else:
            timesave.append((timesf[i-1]+timesf[i])/2)
            
    timestest = set(times)
    timestest = timestest.union(set(timesave))
    timestest = list(timestest)
    timesave = list(timesave)
    timestest = sorted(timestest)
    timesave = sorted(timesave)
    
    tsinds= []
    for i in range(len(timesave)):
        tsinds.append(timestest.index(timesave[i])-i)
        
    return [hsinds,tsinds]