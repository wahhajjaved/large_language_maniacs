import numpy as np
import scipy.stats as st
import math,time
import sys
from sklearn.metrics import mean_squared_error


class maxMin_Normalizer:


	#output=str(sys.argv[1])+'max-min'

	#output_file=open(output,'w')

	def run(self):
		beg=time.time()
		
		#output=str(sys.argv[1])+'max-min'
		def dataPrepare(item):
			''' get the values, remove the categorical data'''
			a=item.split(',')
			label=a[len(a)-1].split('\n')[0]
			data=a[5:len(a)-1]#removing IPsrc,IPdst,portsrc,portdsc,proto
			return data

		def getValues(janela):
			''' take the local values of the current batch'''
			vmax=[]
			vmin=[]
			umean=[]
			sigmin=[]    
			for i in range(len(janela[0])):
				column=janela[:,i].astype(np.float64)
				vmax.append(max(column))
				vmin.append(min(column))
				umean.append(np.mean(column))
				sigmin.append(np.std(column)) 
			return vmax,vmin,umean,sigmin

		
		def normalizing(janela,refMax,refMin):
			# normalized = (x-min(x))/(max(x)-min(x))
			global N

			for i in range(N):
				aux=np.subtract(janela[:,i].astype(np.float64),refMin[i])
				aux2=np.subtract(refMax[i],refMin[i])
				if (aux2 == 0):
					janela[:,i]=0.5 #https://docs.tibco.com/pub/spotfire/7.0.0/doc/html/norm/norm_scale_between_0_and_1.htm
					#If Emax is equal to Emin then Normalized (ei) is set to 0.5.
				else:
					janela[:,i]=np.nan_to_num(np.divide(aux,aux2).tolist())
				for j in range(len(janela[:,i])):
					if float(janela[:,i][j])>1:
						janela[:,i][j]=1


			return janela

		def verifyMetrics(localMax,localMin,refMax,refMin):
			'''
			function to verify if the values of the current chunks are different that references. (procedure metrics in paper)
			'''
			global N
			global windowSize
			global m1 #metric1 treshold 
			global m2 #metric2 threshold
			metric1 = False
			metric2 = False
			metric1Counter = 0
			for i in range(N):
				if (localMin[i] < refMin[i]):
					metric1Counter+=1
				if (localMax[i] > refMax[i]):
					metric1Counter+=1
				if refMin[i] == 0: #to avoid zero division
					if ((refMin[i]-localMin[i])/1 > m2):
						metric2 = True
				else:
					if ((refMin[i]-localMin[i])/refMin[i] > m2):
						metric2 = True
				if refMax[i]==0:#to avoid zero division
					if ((localMax[i]-refMax[i])/1 > m2):
						metric2 = True
				else:
					if ((localMax[i]-refMax[i])/refMax[i] > m2):
						metric2 = True
			if (metric1Counter/windowSize > m1):
				metric1 = True

			return metric1,metric2


		global windowSize
		windowSize=int(sys.argv[1]) #as paper
		#windowSize=50
		global N
		N=40 #number of features


		global m1 #metric1 treshold 
		global m2 #metric2 threshold

		m1=0.05
		m2=0.05

		numberBins=math.ceil(math.sqrt(N))

		global windowsNumber
		windowsNumber = 0


		janMax  = [] #janela de valores medios. Vou manter N valores 
		janMin  = []
		janMean = []
		janStd  = []

		histogram = {} #histogram with frequency of the samples
		for j in range(N):
			histogram[j]=0

		files=open('classes-17.out','r')
		saida = open("max-min-classes-17-norm.out", "w")

		lines=files.readlines()

		np.set_printoptions(precision=3)
		np.set_printoptions(suppress=True,formatter={'float_kind':'{:f}'.format})

		batch=[]
		#a=lines[0:100000]
		for i in lines:
		   batch.append(dataPrepare(i))

		before=batch
		batch=np.array(batch)

		print 'file loaded'

		jan=[]  #take a windows everytime we have a batch

		beg=time.time()
		for i in range(0,len(batch), windowSize): #
				jan = batch[i:i+windowSize]		
				#calGlobal(localMax,localMin,localMean,localStd)

				if windowsNumber == 0:
					refMax,refMin,localMean,localStd = getValues(jan)
					salida=normalizing(jan,refMax,refMin)
				else:
					localMax,localMin,localMean,localStd=getValues(jan)
					metric1,metric2=verifyMetrics(localMax,localMin,refMax,refMin)
					if (metric1 and metric2):
						refMax=localMax
						refMin=localMin
					
					t=normalizing(jan,refMax,refMin)		

				

				if windowsNumber!=0:
					salida=np.vstack((salida,t))
				
				windowsNumber+=1 #incrementing this number
				if (windowsNumber % 1000) == 0:
					print "windowsNumber: "+str(windowsNumber)

	#	lower, upper = 0, 1
	#	salida=np.asfarray(salida)
	#	salidaNew = [lower + (upper - lower) * x for x in salida]			
		
		end=time.time()-beg




		''' to write in file'''
		for k in salida:
			tmp = []
			for l in k:
				tmp.append(str(l))
			linhaSaida =  ",".join(tmp)
			saida.write(linhaSaida+"\n")

		end=time.time()-beg

		saida.write(str('processing time : '+str(end)))

		saida.close()
		return salida,end


		'''
		to calculate the mean square error
		'''
		# original_maxmin=[]
		# t=np.asfarray(before)
		# salida=np.asfarray(salida)
		# for i in range(N):
		# 	original_maxmin.append(mean_squared_error(t[:,i],salida[:,i]))

		# output_file.write(str(original_maxmin)+'\n')

		# output_file.write(str('processing time : '+str(end)))

		# output_file.close()
