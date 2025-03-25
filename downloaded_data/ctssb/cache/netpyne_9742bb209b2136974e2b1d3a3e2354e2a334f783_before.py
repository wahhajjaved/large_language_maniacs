# checks.py 

def checkOutput(modelName, verbose=False):
	''' Compare output of models with expected results'''

	from .. import  sim
	if sim.rank == 0:
		expectedAll = {'numSyns': {}, 'numSpikes': {}}

		# tut2 expected output 
		expectedAll['numSyns']['tut2'] = 254
		expectedAll['numSpikes']['tut2'] = 944

		# tut3 expected output 
		expectedAll['numSyns']['tut3'] = 254
		expectedAll['numSpikes']['tut3'] = 538

		# tut4 expected output 
		expectedAll['numSyns']['tut4'] = 73
		expectedAll['numSpikes']['tut4'] = 1210

		# tut5 expected output 
		expectedAll['numSyns']['tut5'] = 7040
		expectedAll['numSpikes']['tut5'] = 4659

		# tut6 expected output 
		expectedAll['numSyns']['tut6'] = 16
		expectedAll['numSpikes']['tut6'] = 146

		# tut7 expected output 
		expectedAll['numSyns']['tut7'] = 2500
		expectedAll['numSpikes']['tut7'] = 583

		# tut_import expected output 
		expectedAll['numSyns']['tut_import'] = 340
		expectedAll['numSpikes']['tut_import'] = 3061  # check Traub cell mismatch

		# HHTut expected output 
		expectedAll['numSyns']['HHTut'] = 1839
		expectedAll['numSpikes']['HHTut'] = 2052

		# HybridTut expected output 
		expectedAll['numSyns']['HybridTut'] = 386
		expectedAll['numSpikes']['HybridTut'] = 2766

		# M1 expected output 
		expectedAll['numSyns']['M1'] = 4836
		expectedAll['numSpikes']['M1'] = 59755

		# PTcell expected output 
		expectedAll['numSyns']['PTcell'] = 1
		expectedAll['numSpikes']['PTcell'] = 4

		# cell_lfp expected output 
		expectedAll['numSyns']['cell_lfp'] = 1
		expectedAll['numSpikes']['cell_lfp'] = 1


		# compare all features
		for feature, expected in expectedAll.items():
			# numCells
			if feature == 'numCells':
				for pop in expected:
					try:				
						actual = len(sim.net.allPops[pop]['cellGids'])
						assert expected[modelName][pop] == actual
					except:
						print(('\nMismatch: model %s population %s %s is %s but expected value is %s' %(modelName, pop, feature, actual, expected[modelName][pop])))
						raise

			# numConns
			if feature == 'numSyns':
				try:				
					actual = sim.totalSynapses
					assert expected[modelName] == actual
				except:
					print(('\nMismatch: model %s %s is %s but expected value is %s' %(modelName, feature, actual, expected[modelName])))
					raise

			# numSpikes
			if feature == 'numSpikes':
				try:				
					actual = sim.totalSpikes
					assert expected[modelName] == actual
				except:
					print(('\nMismatch: model %s %s is %s but expected value is %s' %(modelName, feature, actual, expected[modelName])))
					raise

		return True