# -*- coding: utf-8 -*-
'''
Copyright (c) 2015 by Tobias Houska

This file is part of Statistical Parameter Estimation Tool (SPOTPY).

:author: Tobias Houska

Holds functions to analyse results out of the database. 
Note: This part of SPOTPY is in alpha status and not ready for production use.
'''





import numpy as np
import spotpy



font = {'family' : 'calibri',
    'weight' : 'normal',
    'size'   : 18}
        
def load_csv_results(filename, usecols=None):
    """
    Get an array of your results in the given file, without the first and the 
    last column. The first line may have a different objectivefunction and the last 
    line may be incomplete, which would result in an error.
    
    :filename: Expects an available filename, without the csv, in your working directory
    :type: str
    
    :return: Result array
    :rtype: array
    """
    if usecols == None:
        #return np.genfromtxt(filename+'.csv',delimiter=',',names=True,skip_footer=1,invalid_raise=False)[1:]   
        return np.genfromtxt(filename+'.csv',delimiter=',',names=True,invalid_raise=False)  
    else:
        return np.genfromtxt(filename+'.csv',delimiter=',',names=True,skip_footer=1,invalid_raise=False,usecols=usecols)[1:]   
        
def get_modelruns(results):
    """
    Get an shorter array out of your result array, containing just the 
    simulations of your model.
    
    :results: Expects an numpy array which should have indices beginning with "sim"
    :type: array
             
    :return: Array containing just the columns beginnning with the indice "sim"
    :rtype: array
    """   
    fields=[word for word in results.dtype.names if word.startswith('sim')]
    return results[fields]

def get_parameters(results):
    """
    Get an shorter array out of your result array, containing just the 
    parameters of your model.
    
    :results: Expects an numpy array which should have indices beginning with "par"
    :type: array
         
    :return: Array containing just the columns beginnning with the indice "par"
    :rtype: array
    """ 
    fields=[word for word in results.dtype.names if word.startswith('par')]
    results = results[fields]
    #print results.dtype.names# = get_parameternames(results)
    #results.dtype.names = get_parameternames(results)    
    return results

def get_parameternames(results):
    """
    Get list of strings with the names of the parameters of your model.
    
    :results: Expects an numpy array which should have indices beginning with "par"
    :type: array
    
    :return: Strings with the names of the analysed parameters 
    :rtype: list
        
    """
    fields=[word for word in results.dtype.names if word.startswith('par')]
    
    parnames=[]
    for field in fields:
        parnames.append(field[3:])
    return parnames
    
def get_maxlikeindex(results):
    """
    Get the maximum objectivefunction of your result array
    
    :results: Expects an numpy array which should of an index "like" for objectivefunctions 
    :type: array    
    
    :return: Index of the position in the results array with the maximum objectivefunction
        value and value of the maximum objectivefunction of your result array
    :rtype: int and float
    """        
    maximum=np.nanmax(results['like'])
    value=str(round(maximum,4))
    text=str('The best model run has an objectivefunction of: ')
    textv=text+value
    print(textv)
    index=np.where(results['like']==maximum)
    return index, maximum

def get_minlikeindex(results):
    """
    Get the minimum objectivefunction of your result array
    
    :results: Expects an numpy array which should of an index "like" for objectivefunctions 
    :type: array    
    
    :return: Index of the position in the results array with the minimum objectivefunction
        value and value of the minimum objectivefunction of your result array
    :rtype: int and float
    """            
    minimum=np.nanmin(results['like'])    
    value=str(round(maximum,4))
    text=str('The best model run has an objectivefunction of: ')
    textv=text+value
    print(textv)
    index=np.where(results['like']==minimum)
    return index, minimum    


def get_percentiles(results,sim_number=None):
    """
    Get 5,25,50,75 and 95 percentiles of your simulations
    
    :results: Expects an numpy array which should of an index "simulation" for simulations 
    :type: array    
    
    :sim_number: Optional, Number of your simulation, needed when working with multiple lists of simulations
    :type: int
    
    :return: Percentiles of simulations 
    :rtype: int and float
    """ 
    p5,p25,p50,p75,p95=[],[],[],[],[]
    fields=[word for word in results.dtype.names if word.startswith('simulation'+str(sim_number))]
    for i in range(len(fields)):
        p5.append(np.percentile(list(results[fields[i]]),5))
        p25.append(np.percentile(list(results[fields[i]]),25))
        p50.append(np.percentile(list(results[fields[i]]),50))
        p75.append(np.percentile(list(results[fields[i]]),75))    
        p95.append(np.percentile(list(results[fields[i]]),95))
    return p5,p25,p50,p75,p95

def calc_like(results,evaluation):
    """
    Calculate another objectivefunction of your results
    
    :results: Expects an numpy array which should of an index "simulation" for simulations 
    :type: array    
    
    :evaluation: Expects values, which correspond to your simulations
    :type: list
    
    :return: New objectivefunction list 
    :rtype: list
    """ 
    likes=[]
    sim=get_modelruns(results)
    for s in sim:
        likes.append(spotpy.objectivefunctions.rmse(list(s),evaluation))
        #likes.append(objectivefunctions.agreementindex(list(s),evaluation))
    return likes

def compare_different_objectivefunctions(like1,like2):
    """
    Performs the Welch’s t-test (aka unequal variances t-test)
    
    :like1: objectivefunction values
    :type: list
    
    :like2: Other objectivefunction values
    :type: list
    
    :return: p Value
    :rtype: list
    """
    from scipy import stats
    out = stats.ttest_ind(like1,like2,equal_var=False)
    print(out)
    if out[1]>0.05:
        print('like1 is NOT signifikant different to like2: p>0.05')
    else:
        print('like1 is signifikant different to like2: p<0.05' )
    return out
    
def get_posterior(results,threshold=0.9):
    """
    Get the best XX% of your result array
    
    :results: Expects an numpy array which should have as first axis an index "like". This will be sorted. 
    :type: array  
    
    :threshold: Optional, ratio of values that will be deleted
    :type: float
    
    :return: Posterior result array
    :rtype: array
    """
    return np.sort(results,axis=0)[len(results)*threshold:]

def sort_like(results):
    return np.sort(results,axis=0)

def get_best_parameterset(results,maximize=True):
    """
    Get the best parameter set of your result array, depending on your first objectivefunction 
    
    :results: Expects an numpy array which should have as first axis an index "like" or "like1". 
    :type: array  
    
    :maximize: Optional, default=True meaning the highest objectivefunction is taken as best, if False the lowest objectivefunction is taken as best.
    :type: boolean
    
    :return: Best parameter set
    :rtype: array
    """
    try:
        likes=results['like']
    except ValueError:
        likes=results['like1']
    if maximize:
        best=np.nanmax(likes)
    else:
        best=np.nanmin(likes)
    index=np.where(likes==best)
    return get_parameters(results[index])

def get_min_max(spotpy_setup):
    """
    Get the minimum and maximum values of your parameters function of the spotpy setup 
    
    :spotpy_setup: Class with a parameters function
    :type: class  
    
    :return: Possible minimal and maximal values of all parameters in the parameters function of the spotpy_setup class
    :rtype: Two arrays
    """
    randompar=spotpy_setup.parameters()['random']        
    for i in range(1000):
        randompar=np.column_stack((randompar,self.parameter()['random']))
    return np.amin(randompar,axis=1),np.amax(randompar,axis=1)
    
def get_parbounds(spotpy_setup):
    """
    Get the minimum and maximum parameter bounds of your parameters function of the spotpy setup 
    
    :spotpy_setup: Class with a parameters function
    :type: class  
    
    :return: Possible minimal and maximal values of all parameters in the parameters function of the spotpy_setup class
    :rtype: list
    """
    parmin,parmax=get_min_max(spotpy_setup)
    bounds=[]
    for i in range(len(parmin)):
        bounds.append([parmin[i],parmax[i]])
    return bounds
    
def get_sensitivity_of_fast(results,like_index=None,M=4, print_to_console=True):
    """
    Get the sensitivity for every parameter of your result array, created with the FAST algorithm 
    
    :results: Expects an numpy array which should have as first axis an index "like" or "like1". 
    :type: array  
    
    :like_index: Optional, index of objectivefunction to base the sensitivity on, default=None first objectivefunction is taken 
    :type: int  
    
    :return: Sensitivity indices for every parameter
    :rtype: list
    """
    import math
    likes=results['like'+str(like_index)]
    print(likes.size)
    parnames = get_parameternames(results)
    parnumber=len(parnames)
    if likes.size % (parnumber) == 0:
        N = int(likes.size / parnumber)
    else:
        print("""
            Error: Number of samples in model output file must be a multiple of D, 
            where D is the number of parameters in your parameter file.
          """)
        exit()

    # Recreate the vector omega used in the sampling
    omega = np.empty([parnumber])
    omega[0] = math.floor((N - 1) / (2 * M))
    m = math.floor(omega[0] / (2 * M))

    if m >= (parnumber - 1):
        omega[1:] = np.floor(np.linspace(1, m, parnumber - 1))
    else:
        omega[1:] = np.arange(parnumber - 1) % m + 1

    # Calculate and Output the First and Total Order Values
    if print_to_console:
        print("Parameter First Total")
    Si = dict((k, [None] * parnumber) for k in ['S1', 'ST'])
    for i in range(parnumber):
        l = np.arange(i * N, (i + 1) * N)
        Si['S1'][i] = _compute_first_order(likes[l], N, M, omega[0])
        Si['ST'][i] = _compute_total_order(likes[l], N, omega[0])
        if print_to_console:
            print("%s %f %f" %
                  (parnames[i], Si['S1'][i], Si['ST'][i]))
    return Si

def plot_fast_sensitivity(results,likes=['mean'],like_indices=None,number_of_sensitiv_pars=10):
    """
    Example, how to plot the sensitivity for every parameter of your result array, created with the FAST algorithm 
    
    :results: Expects an numpy array which should have as first axis an index "like" or "like1". 
    :type: array  
    
    :likes: Optional, header of your objectivefunction
    :type: list
    
    :like_indices: Optional, index of objectivefunction to base the sensitivity on, default=None first objectivefunction is taken 
    :type: int  
    
    :number_of_sensitiv_pars: Optional, this number of most sensitive parameters will be shown in the legend
    :type: int  
    
    :return: Parameter names which are sensitive, Sensitivity indices for every parameter, Parameter names which are not sensitive
    :rtype: Three lists
    """
    import matplotlib.pyplot as plt
    from matplotlib import colors
    cnames=list(colors.cnames)

    parnames=get_parameternames(results)
    fig=plt.figure(figsize=(16,12))
    all_names=[]
    all_no_names=[]
    for i in range(len(likes)):
        ax  = plt.subplot(len(likes),1,i+1)
        if like_indices==None:
            Si=get_sensitivity_of_fast(results['like'],parnames)
        else:
            Si=get_sensitivity_of_fast(results['like'+str(like_indices[i])],parnames)
        names=[]
        values=[]
        no_names=[]
        for j in range(len(list(Si.values())[1])):
            if list(Si.values())[1][j]>=sorted(np.sort(list(Si.values())[1]),reverse=True)[number_of_sensitiv_pars]:
                names.append(parnames[j])
                values.append(list(Si.values())[1][j])
            else:
                no_names.append(parnames[j])
        print(names)
        ax.plot([sorted(np.sort(list(Si.values())[1]),reverse=True)[number_of_sensitiv_pars]]*len(list(Si.values())[1]),'r--')
        #ax.bar(np.arange(0,len(Si.values()[1])),sorted(np.sort(Si.values()[1]),reverse=True),label=str(names))
        ax.bar(np.arange(0,len(list(Si.values())[1])),list(Si.values())[1],label=str(names))        
        ax.set_ylim([0,1])
        #ax.set_xlabel(names)
        ax.set_ylabel(likes[i])
        ax.legend()
        all_names.append(names)
        all_no_names.append(no_names)
    return all_names,values,all_no_names


   
def plot_heatmap_griewank(results,algorithms):
    """Example Plot as seen in the SPOTPY Documentation"""
    import matplotlib.pyplot as plt
    from matplotlib import colors
    cnames=list(colors.cnames)

    from matplotlib import ticker
    from matplotlib import cm
    font = {'family' : 'calibri',
        'weight' : 'normal',
        'size'   : 20}
    plt.rc('font', **font)  
    subplots=len(results)
    xticks=[-40,0,40]
    yticks=[-40,0,40]
    fig=plt.figure(figsize=(16,6))
    N = 2000
    x = np.linspace(-50.0, 50.0, N)
    y = np.linspace(-50.0, 50.0, N)
    
    x, y = np.meshgrid(x, y)
            
    z=1+ (x**2+y**2)/4000 - np.cos(x/np.sqrt(2))*np.cos(y/np.sqrt(3))
    #z = 100.0*(x - x**2.0)**2.0 + (1 - y)**2.0
    #
    #norm = cm.colors.Normalize(vmax=abs(z).max(), vmin=-abs(z).max())
    cmap = plt.get_cmap('autumn')
    #levels = np.linspace(-5, 5, 20)
    rows=2
    for i in range(subplots):
        ax  = plt.subplot(rows,subplots/rows,i+1)
        CS = ax.contourf(x, y, z,locator=ticker.LogLocator(),cmap=cm.rainbow)#cmap)#,levels=levels)
        #CS = ax.contourf(x, y, z,cmap=cm.rainbow)#cmap)#,levels=levels)
        ax.plot(results[i]['par0'],results[i]['par1'],'ko',alpha=0.2,markersize=1.9) 
        ax.xaxis.set_ticks([])  
        if i==0:
            ax.set_ylabel('y')
        if i==subplots/rows:
            ax.set_ylabel('y')
        if i>=subplots/rows:
            ax.set_xlabel('x')
            ax.xaxis.set_ticks(xticks)   
            
        if i!=0 and i!=subplots/rows:
            ax.yaxis.set_ticks([])
            
        
        ax.set_title(algorithms[i])
    
    #plt.tight_layout()  
    fig.savefig('test.png', bbox_inches='tight')  # <------ this  
    
    
def plot_objectivefunction(results,evaluation,limit=None,sort=True):
    """Example Plot as seen in the SPOTPY Documentation"""
    import matplotlib.pyplot as plt
    from matplotlib import colors
    cnames=list(colors.cnames)
    likes=calc_like(results,evaluation)    
    data=likes
    #Calc confidence Interval    
    mean = np.average(data)
    # evaluate sample variance by setting delta degrees of freedom (ddof) to
    # 1. The degree used in calculations is N - ddof
    stddev = np.std(data, ddof=1)
    from scipy.stats import t
    # Get the endpoints of the range that contains 95% of the distribution
    t_bounds = t.interval(0.999, len(data) - 1)
    # sum mean to the confidence interval
    ci = [mean + critval * stddev / np.sqrt(len(data)) for critval in t_bounds]
    value="Mean: %f" % mean
    print(value)
    value="Confidence Interval 95%%: %f, %f" % (ci[0], ci[1])    
    print(value)
    threshold=ci[1]
    happend=None
    bestlike=[data[0]]
    for like in data:
        if like<bestlike[-1]:
            bestlike.append(like)
        if bestlike[-1]<threshold and not happend:
            thresholdpos=len(bestlike)
            happend=True
        else:
            bestlike.append(bestlike[-1])
    if limit:
        plt.plot(bestlike,'k-')#[0:limit])
        plt.axvline(x=thresholdpos,color='r')
        plt.plot(likes,'b-')
        #plt.ylim(ymin=-1,ymax=1.39)
    else:
        plt.plot(bestlike)
        
def plot_parametertrace_algorithms(results,algorithmnames=None,parameternames=None,xticks=[0,2000,4000]):
    """Example Plot as seen in the SPOTPY Documentation"""        
    import matplotlib.pyplot as plt
    from matplotlib import colors
    cnames=list(colors.cnames)
    font = {'family' : 'calibri',
        'weight' : 'normal',
        'size'   : 20}
    plt.rc('font', **font)   
    fig=plt.figure(figsize=(17,5))
    rep=len(results[0])
    subplots=len(results)
    rows=2
    for j in range(rows):
        for i in range(subplots):
            ax  = plt.subplot(rows,subplots,i+1+j*subplots)
            if j==0:
                if parameternames:
                    data=results[i]['par'+parameternames[0]]
                else:
                    data=results[i]['par0']
            if j==1:
                if parameternames:
                    data=results[i]['par'+parameternames[1]]
                else:
                    data=results[i]['par1']
                ax.set_xlabel(algorithmnames[i-subplots])
            
            ax.plot(data,'b-')
            ax.plot([1]*rep,'r--')
            ax.set_xlim(0,rep)
            ax.set_ylim(-50,50)            
            ax.xaxis.set_ticks(xticks)
            if i==0 and j==0:
                ax.set_ylabel('x')
                ax.yaxis.set_ticks([-50,0,50])
            if i==0 and j==1:
                ax.set_ylabel('y')    
                ax.yaxis.set_ticks([-50,0,50])
            if j==0:
                ax.xaxis.set_ticks([])
            if i>0:
                ax.yaxis.set_ticks([])
        
    plt.tight_layout()
    fig.savefig('test2.png', bbox_inches='tight')

    
def plot_parametertrace(results,parameternames=None):
    """
    Get a plot with all values of a given parameter in your result array.
    The plot will be saved as a .png file.
    
    :results: Expects an numpy array which should of an index "like" for objectivefunctions 
    :type: array   
    
    :parameternames: A List of Strings with parameternames. A line object will be drawn for each String in the List.
    :type: list
        
    :return: Plot of all traces of the given parameternames.
    :rtype: figure
    """  
    import matplotlib.pyplot as plt
    from matplotlib import colors
    cnames=list(colors.cnames)
    fig=plt.figure(figsize=(16,9))
    if not parameternames:
        parameternames=get_parameternames(results)
    names=''
    i=1
    for name in parameternames:
        ax = plt.subplot(len(parameternames),1,i)
        ax.plot(results['par'+name],label=name)
        names+=name+'_'
        ax.set_ylabel(name)
        if i==len(parameternames):
            ax.set_xlabel('Repetitions')
        if i==1:
            ax.set_title('Parametertrace')
        ax.legend()
        i+=1
    fig.savefig(names+'_trace.png')
    text='The figure as been saved as "'+names+'trace.png"' 
    print(text)

def plot_posterior_parametertrace(results,parameternames=None,threshold=0.1):
    """
    Get a plot with all values of a given parameter in your result array.
    The plot will be saved as a .png file.
    
    :results: Expects an numpy array which should of an index "like" for objectivefunctions 
    :type: array   
    
    :parameternames: A List of Strings with parameternames. A line object will be drawn for each String in the List.
    :type: list
        
    :return: Plot of all traces of the given parameternames.
    :rtype: figure
    """  
    import matplotlib.pyplot as plt
    from matplotlib import colors
    cnames=list(colors.cnames)
    fig=plt.figure(figsize=(16,9))
    
    results=sort_like(results)
    if not parameternames:
        parameternames=get_parameternames(results)
    names=''
    i=1
    for name in parameternames:
        ax = plt.subplot(len(parameternames),1,i)
        ax.plot(results['par'+name][int(len(results)*threshold):],label=name)
        names+=name+'_'
        ax.set_ylabel(name)
        if i==len(parameternames):
            ax.set_xlabel('Repetitions')
        if i==1:
            ax.set_title('Parametertrace')
        ax.legend()
        i+=1
    fig.savefig(names+'_trace.png')
    text='The figure as been saved as "'+names+'trace.png"'
    print(text) 

def plot_posterior(results,evaluation,dates=None,ylabel='Posterior model simulation',xlabel='Time',objectivefunction='NSE',objectivefunctionmax=True,calculatelike=True,sort=True, bestperc=0.1):
    """
    Get a plot with the maximum objectivefunction of your simulations in your result 
    array.
    The plot will be saved as a .png file.
    
    Args:
        results (array): Expects an numpy array which should of an index "like" for 
              objectivefunctions and "sim" for simulations.
  
        evaluation (list): Should contain the values of your observations. Expects that this list has the same lenght as the number of simulations in your result array.
    Kwargs:
        dates (list): A list of datetime values, equivalent to the evaluation data.
        
        ylabel (str): Labels the y-axis with the given string.

        xlabel (str): Labels the x-axis with the given string.
                
        objectivefunction (str): Name of the objectivefunction function used for the simulations.
        
        objectivefunctionmax (boolean): If True the maximum value of the objectivefunction will be searched. If false, the minimum will be searched.
        
        calculatelike (boolean): If True, the NSE will be calulated for each simulation in the result array.
    
    Returns: 
        figure. Plot of the simulation with the maximum objectivefunction value in the result array as a blue line and dots for the evaluation data.
    
    A really great idea. A way you might use me is
    >>> bcf.analyser.plot_bestmodelrun(results,evaluation, ylabel='Best model simulation')
        
    """
    import matplotlib.pyplot as plt
    from matplotlib import colors
    import random

    cnames=list(colors.cnames)


    plt.rc('font', **font)
    if sort:
        results=sort_like(results)
    if calculatelike:
        likes=calc_like(results)
        maximum=max(likes)
        par=get_parameters(results)
        sim=get_modelruns(results)
        index=likes.index(maximum)
        bestmodelrun=list(sim[index])
        bestparameterset=list(par[index])
        
    else:
        if objectivefunctionmax==True:
            index,maximum=get_maxlikeindex(results)
        else:
            index,maximum=get_minlikeindex(results)
        sim=get_modelruns(results)
        bestmodelrun=list(sim[index][0])#Transform values into list to ensure plotting
        bestparameterset=list(get_parameters(results)[index][0])

    parameternames=list(get_parameternames(results)    )
    bestparameterstring=''
    maxNSE=spotpy.objectivefunctions.nashsutcliff(bestmodelrun,evaluation)
    for i in range(len(parameternames)):
        if i%8==0:
            bestparameterstring+='\n'
        bestparameterstring+=parameternames[i]+'='+str(round(bestparameterset[i],4))+','
    fig=plt.figure(figsize=(16,8))
    if dates is not None:
        chains=int(max(results['chain']))
        colors=list(cnames)
        random.shuffle(colors)        

        for s in sim[5000:]:
            plt.plot(dates,list(s),'c-',alpha=0.05)        
        plt.plot(dates,bestmodelrun,'b-',label='Simulations: '+objectivefunction+'='+str(round(maxNSE,4)))        
        plt.plot(dates,evaluation,'ro',label='Evaluation')
    else:
        for s in s:
            plt.plot(dates,list(s),'c-',alpha=0.05)
        plt.plot(bestmodelrun,'b-',label='Simulations: '+objectivefunction+'='+str(round(maxNSE,4)))
        plt.plot(evaluation,'ro',label='Evaluation')
    plt.legend()
    plt.ylabel(ylabel)
    plt.xlabel(xlabel)
    plt.ylim(0,70) #DELETE WHEN NOT USED WITH SOIL MOISTUR RESULTS
    plt.title('Maximum objectivefunction of Simulations with '+bestparameterstring[0:-2])
#    plt.text(0, 0, bestparameterstring[0:-2],
#        horizontalalignment='left',
#        verticalalignment='bottom')
    fig.savefig('bestmodelrun.png')
    text='The figure as been saved as "bestmodelrun.png"'
    print(text)
    

def plot_bestmodelrun(results,evaluation,dates=None,ylabel='Best model simulation',xlabel='Time',objectivefunction='NSE',objectivefunctionmax=True,calculatelike=True):
    """
    Get a plot with the maximum objectivefunction of your simulations in your result 
    array.
    The plot will be saved as a .png file.
    
    Args:
        results (array): Expects an numpy array which should of an index "like" for 
              objectivefunctions and "sim" for simulations.
  
        evaluation (list): Should contain the values of your observations. Expects that this list has the same lenght as the number of simulations in your result array.
    Kwargs:
        dates (list): A list of datetime values, equivalent to the evaluation data.
        
        ylabel (str): Labels the y-axis with the given string.

        xlabel (str): Labels the x-axis with the given string.
                
        objectivefunction (str): Name of the objectivefunction function used for the simulations.
        
        objectivefunctionmax (boolean): If True the maximum value of the objectivefunction will be searched. If false, the minimum will be searched.
        
        calculatelike (boolean): If True, the NSE will be calulated for each simulation in the result array.
    
    Returns: 
        figure. Plot of the simulation with the maximum objectivefunction value in the result array as a blue line and dots for the evaluation data.
    
    A really great idea. A way you might use me is
    >>> bcf.analyser.plot_bestmodelrun(results,evaluation, ylabel='Best model simulation')
        
    """
    import matplotlib.pyplot as plt
    from matplotlib import colors
    cnames=list(colors.cnames)
    plt.rc('font', **font)       
    if calculatelike:
        likes=[]
        sim=get_modelruns(results)
        par=get_parameters(results)
        for s in sim:
            likes.append(spotpy.objectivefunctions.nashsutcliff(s,evaluation))
        maximum=max(likes)
        index=likes.index(maximum)
        bestmodelrun=list(sim[index])
        bestparameterset=list(par[index])
        
    else:
        if objectivefunctionmax==True:
            index,maximum=get_maxlikeindex(results)
        else:
            index,maximum=get_minlikeindex(results)
        bestmodelrun=list(get_modelruns(results)[index][0])#Transform values into list to ensure plotting
        bestparameterset=list(get_parameters(results)[index][0])
        
    parameternames=list(get_parameternames(results)    )
    bestparameterstring=''
    maxNSE=spotpy.objectivefunctions.nashsutcliff(bestmodelrun,evaluation)
    for i in range(len(parameternames)):
        if i%8==0:
            bestparameterstring+='\n'
        bestparameterstring+=parameternames[i]+'='+str(round(bestparameterset[i],4))+','
    fig=plt.figure(figsize=(16,8))
    if dates is not None:
        plt.plot(dates,bestmodelrun,'b-',label='Simulations: '+objectivefunction+'='+str(round(maxNSE,4)))        
        plt.plot(dates,evaluation,'ro',label='Evaluation')
    else:
        plt.plot(bestmodelrun,'b-',label='Simulations: '+objectivefunction+'='+str(round(maxNSE,4)))
        plt.plot(evaluation,'ro',label='Evaluation')
    plt.legend()
    plt.ylabel(ylabel)
    plt.xlabel(xlabel)
    plt.ylim(0,70) #DELETE WHEN NOT USED WITH SOIL MOISTUR RESULTS
    plt.title('Maximum objectivefunction of Simulations with '+bestparameterstring[0:-2])
#    plt.text(0, 0, bestparameterstring[0:-2],
#        horizontalalignment='left',
#        verticalalignment='bottom')
    fig.savefig('bestmodelrun.png')
    text='The figure as been saved as "bestmodelrun.png"'
    print(text)


def plot_bestmodelruns(results,evaluation,algorithms=None,dates=None,ylabel='Best model simulation',xlabel='Date',objectivefunctionmax=True,calculatelike=True):
    """
    Get a plot with the maximum objectivefunction of your simulations in your result 
    array.
    The plot will be saved as a .png file.
    
    Args:
        results (list of arrays): Expects list of numpy arrays which should of an index "like" for 
              objectivefunctions and "sim" for simulations.
  
        evaluation (list): Should contain the values of your observations. Expects that this list has the same lenght as the number of simulations in your result array.
    Kwargs:
        dates (list): A list of datetime values, equivalent to the evaluation data.
        
        ylabel (str): Labels the y-axis with the given string.

        xlabel (str): Labels the x-axis with the given string.
                
        objectivefunction (str): Name of the objectivefunction function used for the simulations.
        
        objectivefunctionmax (boolean): If True the maximum value of the objectivefunction will be searched. If false, the minimum will be searched.
        
        calculatelike (boolean): If True, the NSE will be calulated for each simulation in the result array.
    
    Returns: 
        figure. Plot of the simulation with the maximum objectivefunction value in the result array as a blue line and dots for the evaluation data.
    
    A really great idea. A way you might use me is
    >>> bcf.analyser.plot_bestmodelrun(results,evaluation, ylabel='Best model simulation')
        
    """
    import matplotlib.pyplot as plt
    from matplotlib import colors
    cnames=list(colors.cnames)


    plt.rc('font', **font)
    fig=plt.figure(figsize=(17,8))
    colors=['grey', 'black', 'brown','red','orange', 'yellow','green','blue',]
    plt.plot(dates,evaluation,'ro',label='Evaluation data')
    for i in range(len(results)):       
        if calculatelike:
            likes=[]
            sim=get_modelruns(results[i])
            par=get_parameters(results[i])
            for s in sim:
                likes.append(spotpyobjectivefunctions.lognashsutcliff(evaluation,list(s)))                                
                                
            maximum=max(likes)
            index=likes.index(maximum)
            bestmodelrun=list(sim[index])
            bestparameterset=list(par[index])
            print(bestparameterset)
            
        else:
            if objectivefunctionmax==True:
                index,maximum=get_maxlikeindex(results[i])
            else:
                index,maximum=get_minlikeindex(results[i])
            bestmodelrun=list(get_modelruns(results[i])[index][0])#Transform values into list to ensure plotting
        
        maxLike=spotpy.objectivefunctions.lognashsutcliff(evaluation,bestmodelrun)        
        
        if dates is not None:
            plt.plot(dates,bestmodelrun,'-',color=colors[i],label=algorithms[i]+': LogNSE='+str(round(maxLike,4)))        
            
        else:
            plt.plot(bestmodelrun,'-',color=colors[i],label=algorithms[i]+': AI='+str(round(maxLike,4))) 
            #plt.plot(evaluation,'ro',label='Evaluation data')
        plt.legend(bbox_to_anchor=(.0, 0), loc=3)
        plt.ylabel(ylabel)
        plt.xlabel(xlabel)
        plt.ylim(15,50) #DELETE WHEN NOT USED WITH SOIL MOISTUR RESULTS

        fig.savefig('bestmodelrun.png')
        text='The figure as been saved as "bestmodelrun.png"'
        print(text)

def plot_objectivefunctiontraces(results,evaluation,algorithms,filename='Like_trace'):
    import matplotlib.pyplot as plt
    from matplotlib import colors
    cnames=list(colors.cnames)
    font = {'family' : 'calibri',
        'weight' : 'normal',
        'size'   : 20}
    plt.rc('font', **font)   
    fig=plt.figure(figsize=(16,3))
    xticks=[5000,15000]
    
    for i in range(len(results)):
        ax  = plt.subplot(1,len(results),i+1)
        likes=calc_like(results[i],evaluation)  
        ax.plot(likes,'b-')
        ax.set_ylim(0,25)
        ax.set_xlim(0,len(results[0]))
        ax.set_xlabel(algorithms[i])
        ax.xaxis.set_ticks(xticks)
        if i==0:
            ax.set_ylabel('RMSE')
            ax.yaxis.set_ticks([0,10,20])   
        else:
            ax.yaxis.set_ticks([])        
        
    plt.tight_layout()
    fig.savefig(str(filename)+'.png')


def plot_regression(results,evaluation):
    import matplotlib.pyplot as plt
    from matplotlib import colors
    cnames=list(colors.cnames)
    fig=plt.figure(figsize=(16,9))
    simulations=get_modelruns(results)
    for sim in simulations:
        plt.plot(evaluation,list(sim),'bo',alpha=.05)
    plt.ylabel('simulation')
    plt.xlabel('evaluation')
    plt.title('Regression between simulations and evaluation data')
    fig.savefig('regressionanalysis.png')
    text='The figure as been saved as "regressionanalysis.png"'
    print(text)
    
    
def plot_parameterInteraction(results):
    '''Input:  List with values of parameters and list of strings with parameter names
       Output: Dotty plot of parameter distribution and gaussian kde distribution'''
    import matplotlib.pyplot as plt
    from matplotlib import colors
    import pandas as pd
    cnames=list(colors.cnames)
    parameterdistribtion=get_parameters(results)
    parameternames=get_parameternames(results)  
    df = pd.DataFrame(np.asarray(parameterdistribtion).T.tolist(), columns=parameternames)
    
    pd.tools.plotting.scatter_matrix(df, alpha=0.2, figsize=(12, 12), diagonal='kde')
    plt.savefig('ParameterInteraction',dpi=300)    
    
    
def plot_allmodelruns(modelruns,observations,dates=None):
    '''Input:  Array of modelruns and list of Observations
       Output: Plot with all modelruns as a line and dots with the Observations
    ''' 
    import matplotlib.pyplot as plt
    from matplotlib import colors
    cnames=list(colors.cnames)
    fig=plt.figure(figsize=(16,9))
    ax = plt.subplot(1,1,1)
    if dates is not None:
        for i in range(len(modelruns)):
            if i==0:
                ax.plot(dates, modelruns[i],'b',alpha=.05,label='Simulations')
            else:            
                ax.plot(dates, modelruns[i],'b',alpha=.05)

    else:
        for i in range(len(modelruns)):
            if i==0:
                ax.plot(modelruns[i],'b',alpha=.05,label='Simulations')
            else:            
                ax.plot(modelruns[i],'b',alpha=.05)
    ax.plot(observations,'ro',label='Evaluation')
    ax.legend()
    ax.set_xlabel = 'Best model simulation'
    ax.set_ylabel = 'Evaluation points'
    ax.set_title  = 'Maximum objectivefunction of Simulations'
    fig.savefig('bestmodel.png')
    text='The figure as been saved as "Modelruns.png"' 
    print(text)
    
  
def plot_autocorellation(parameterdistribution,parametername):
    '''Input:  List of sampled values for one Parameter
       Output: Parameter Trace, Histogramm and Autocorrelation Plot'''
    import matplotlib.pyplot as plt
    from matplotlib import colors
    import pandas as pd
    cnames=list(colors.cnames)
    fig=plt.figure(figsize=(16,9))
    ax = plt.subplot(1,1,1)
    pd.tools.plotting.autocorrelation_plot(parameterdistribution)
    plt.savefig('Autocorellation'+str(parametername),dpi=300)
    

def plot_gelman_rubin(r_hat_values):
    '''Input:  List of R_hat values of chains (see Gelman & Rubin 1992) 
       Output: Plot as seen for e.g. in (Sadegh and Vrugt 2014)'''
    import matplotlib.pyplot as plt
    from matplotlib import colors
    cnames=list(colors.cnames)
    fig=plt.figure(figsize=(16,9))
    ax = plt.subplot(1,1,1)
    ax.plot(r_hat_values)
    ax.plot([1.2]*len(r_hat_values),'k--')
    ax.set_xlabel='r_hat'
    
        
def gelman_rubin(x):
    '''NOT USED YET'''
    if np.shape(x) < (2,):
        raise ValueError(
            'Gelman-Rubin diagnostic requires multiple chains of the same length.')
    try:
        m, n = np.shape(x)
    except ValueError:
        return [gelman_rubin(np.transpose(y)) for y in np.transpose(x)]
    # Calculate between-chain variance
    B_over_n = np.sum((np.mean(x, 1) - np.mean(x)) ** 2) / (m - 1)
    # Calculate within-chain variances
    W = np.sum(
        [(x[i] - xbar) ** 2 for i,
         xbar in enumerate(np.mean(x,
                                   1))]) / (m * (n - 1))
    # (over) estimate of variance
    s2 = W * (n - 1) / n + B_over_n
    # Pooled posterior variance estimate
    V = s2 + B_over_n / m
    # Calculate PSRF
    R = V / W
    return R


def plot_Geweke(parameterdistribution,parametername):
    '''Input:  Takes a list of sampled values for a parameter and his name as a string
       Output: Plot as seen for e.g. in BUGS or PyMC'''
    import matplotlib.pyplot as plt
    from matplotlib import colors
    cnames=list(colors.cnames)
    # perform the Geweke test
    Geweke_values = _Geweke(parameterdistribution)
    
    # plot the results
    fig = plt.figure()
    plt.plot(Geweke_values,label=parametername)
    plt.legend()
    plt.title(parametername + '- Geweke_Test')
    plt.xlabel('Subinterval')
    plt.ylabel('Geweke Test')
    plt.ylim([-3,3])
    
    # plot the delimiting line
    plt.plot( [2]*len(Geweke_values), 'r-.')
    plt.plot( [-2]*len(Geweke_values), 'r-.')

def _compute_first_order(outputs, N, M, omega):
    '''Needed for FAST sensitivity''' 
    f = np.fft.fft(outputs)
    Sp = np.power(np.absolute(f[np.arange(1, int(N / 2))]) / N, 2)
    V = 2 * np.sum(Sp)
    D1 = 2 * np.sum(Sp[np.arange(1, M + 1) * int(omega) - 1])
    return D1 / V

def _compute_total_order(outputs, N, omega):
    '''Needed for FAST sensitivity''' 
    f = np.fft.fft(outputs)
    Sp = np.power(np.absolute(f[np.arange(1, int(N / 2))]) / N, 2)
    V = 2 * np.sum(Sp)
    Dt = 2 * sum(Sp[np.arange(int(omega / 2))])
    return (1 - Dt / V)    

def _Geweke(samples, intervals=20):
    '''Calculates Geweke Z-Scores'''    
    length=len(samples)/intervals/2
    # discard the first 10 per cent
    first = 0.1*len(samples)
    
    # create empty array to store the results
    z = np.empty(intervals)
    
    for k in np.arange(0, intervals):
        # starting points of the two different subsamples
        start1 = first + k*length
        start2 = len(samples)/2 + k*length
                
        # extract the sub samples
        subsamples1 = samples[start1:start1+length]
        subsamples2 = samples[start2:start2+length]
        
        # calculate the mean and the variance
        mean1 = np.mean(subsamples1)
        mean2 = np.mean(subsamples2)
        var1  = np.var(subsamples1)
        var2  = np.var(subsamples2)
        
        # calculate the Geweke test
        z[k] = (mean1-mean2)/np.sqrt(var1+var2)    
    return z
