import numpy as np
import vigra
import itertools
try:
    import gurobipy as gu
except:
    pass

import h5py, cPickle
import sys

class RegressorC(object):

    def __init__(self, C=1, epsilon=0.1, penalty="l2",regularization="l2",pos_constr=False):
        """
            penalty : "l1" or "l2" penalty
            
        """
        
        self.penalty=penalty
        self._C = C
        self._epsilon = epsilon
        self.regularization=regularization
        
        self.pos_constr=pos_constr
    
    def get_Xhat(self,X):
        return np.hstack( [X,np.ones((X.shape[0],1))])
    
    def predictUnfiltered(self,X):
        
        oldShape = X.shape
        result = np.dot(self.get_Xhat(X.reshape((-1, X.shape[-1]))),self.w).reshape(X.shape[:-1])
        return result
    
    def fitcplex(self,X,Yl,tags, boxConstraints = None):
        import cwrapper.cplex
        import ctypes
        c_float_p = ctypes.POINTER(ctypes.c_float)
        c_char_p= ctypes.POINTER(ctypes.c_char)
        c_int_p= ctypes.POINTER(ctypes.c_int64)
        c_double_p= ctypes.POINTER(ctypes.c_double)
        X = X.astype(np.float64)
        Yl = Yl.astype(np.float64)
        X_p = X.ctypes.data_as(c_double_p)
        Yl_p = Yl.ctypes.data_as(c_double_p)
        numRows = X.shape[0]
        numCols = X.shape[1]
        self.w = np.zeros((numCols + 1), dtype = np.float64).reshape(-1, 1)
        w_p = self.w.ctypes.data_as(c_double_p)
        


        numConstraints = 0
        boxValues_p = None
        boxIndices_p = None
        boxFeatures_p = None
        dens_p = None
        if boxConstraints and type(boxConstraints) == dict:
            numConstraints = len(boxConstraints["boxValues"])
            boxValues = boxConstraints["boxValues"].astype(np.float64)
            boxValues_p = boxValues.ctypes.data_as(c_double_p)
            boxIndices = boxConstraints["boxIndices"].astype(np.int64)
            boxIndices_p = boxIndices.ctypes.data_as(c_int_p)
            boxFeatures = boxConstraints["boxFeatures"].astype(np.float64)
            boxFeatures_p = boxFeatures.ctypes.data_as(c_double_p)
            #filter out boxes of size 0
            boxSizes = [boxIndices[i+1] - boxIndices[i] for i in range(len(boxValues))]
            assert(np.count_nonzero(boxSizes) == len(boxValues))
            assert(len(boxFeatures.shape) == 2)
            print boxIndices[-1], boxFeatures.shape[0]
            assert(boxIndices[-1] == boxFeatures.shape[0])
            #self.dens = np.zeros((boxIndices[-1]), dtype = np.float64).reshape(-1, 1)
            #dens_p = self.dens.ctypes.data_as(c_double_p)
        #print "constraints:", boxFeatures.shape[0]

        #import sitecustomize
        #sitecustomize.debug_trace()
        cwrapper.cplex.extlib.fit(X_p, Yl_p, w_p, ctypes.c_int(tags[0]), numRows, numCols, ctypes.c_double(self._C),
                                ctypes.c_double(self._epsilon), numConstraints, boxValues_p, boxIndices_p,
                                boxFeatures_p)#, dens_p)
        #self.dens[np.where(self.dens < 0)] = 0

    def fitgurobi(self,X,Yl,tags, boxConstraints = None):
        import cwrapper.gurobi
        import ctypes
        #extlib.main()
        c_float_p = ctypes.POINTER(ctypes.c_float)
        c_char_p= ctypes.POINTER(ctypes.c_char)
        c_int_p= ctypes.POINTER(ctypes.c_int64)
        c_double_p= ctypes.POINTER(ctypes.c_double)
        X = X.astype(np.float64)
        Yl = Yl.astype(np.float64)
        X_p = X.ctypes.data_as(c_double_p)
        Yl_p = Yl.ctypes.data_as(c_double_p)
        numRows = X.shape[0]
        numCols = X.shape[1]
        self.w = np.zeros((numCols + 1), dtype = np.float64).reshape(-1, 1)
        w_p = self.w.ctypes.data_as(c_double_p)
        


        numConstraints = 0
        boxValues_p = None
        boxIndices_p = None
        boxFeatures_p = None
        dens_p = None
        if boxConstraints and type(boxConstraints) == dict:
            numConstraints = len(boxConstraints["boxValues"])
            boxValues = boxConstraints["boxValues"].astype(np.float64)
            boxValues_p = boxValues.ctypes.data_as(c_double_p)
            boxIndices = boxConstraints["boxIndices"].astype(np.int64)
            boxIndices_p = boxIndices.ctypes.data_as(c_int_p)
            boxFeatures = boxConstraints["boxFeatures"].astype(np.float64)
            boxFeatures_p = boxFeatures.ctypes.data_as(c_double_p)
            #filter out boxes of size 0
            boxSizes = [boxIndices[i+1] - boxIndices[i] for i in range(len(boxValues))]
            assert(np.count_nonzero(boxSizes) == len(boxValues))
            assert(len(boxFeatures.shape) == 2)
            print boxIndices[-1], boxFeatures.shape[0]
            assert(boxIndices[-1] == boxFeatures.shape[0])
            #self.dens = np.zeros((boxIndices[-1]), dtype = np.float64).reshape(-1, 1)
            #dens_p = self.dens.ctypes.data_as(c_double_p)
        #print "constraints:", boxFeatures.shape[0]

        #import sitecustomize
        #sitecustomize.debug_trace()
        cwrapper.gurobi.extlib.fit(X_p, Yl_p, w_p, ctypes.c_int(tags[0]), numRows, numCols, ctypes.c_double(self._C),
                                ctypes.c_double(self._epsilon), numConstraints, boxValues_p, boxIndices_p,
                                boxFeatures_p)#, dens_p)
        #self.dens[np.where(self.dens < 0)] = 0
        

    def predict(self, X):
        
        oldShape = X.shape
        result = np.dot(self.get_Xhat(X.reshape((-1, X.shape[-1]))),self.w).reshape(X.shape[:-1])
        return result

    def predictFiltered(self, X):
        
        oldShape = X.shape
        result = np.dot(self.get_Xhat(X.reshape((-1, X.shape[-1]))),self.w).reshape(X.shape[:-1])
        result[np.where(result < 0)] = 0
        return result

class RegressorGurobi(object):
    

    def __init__(self, C=1, epsilon=0.1, penalty="l2",regularization="l2",pos_constr=False):
        """
            penalty : "l1" or "l2" penalty
            
        """
        
        self.penalty=penalty
        self._C = C
        self._epsilon = epsilon
        self.regularization=regularization
        
        self.pos_constr=pos_constr
    
    def get_Xhat(self,X):
        return np.hstack( [X,np.ones((X.shape[0],1))])
    
    def predictUnfiltered(self,X):
        
        oldShape = X.shape
        result = np.dot(self.get_Xhat(X.reshape((-1, X.shape[-1]))),self.w).reshape(X.shape[:-1])
        return result

    def fit(self,X,Yl,tags = None, boxConstraints = None):

        
        #format for box constraints: [(boxvalue, features)]
        
        
        self.Nf = X.shape[1]
        X_hat=self.get_Xhat(X)
        import gurobipy as gu
        
        model=gu.Model()
        
        #model.setParam("Threads",2 )
        #model.setParam("BarConvTol", 1E-4)
        #print "creating vars ... ",
        #create the variables
        u_vars1=[model.addVar(name="u^+_%d"%i,lb=0,vtype=gu.GRB.CONTINUOUS) for i in range(X.shape[0])]
        u_vars2=[model.addVar(name="u^-_%d"%i,lb=0,vtype=gu.GRB.CONTINUOUS) for i in range(X.shape[0])]
        w_vars=[model.addVar(name="w_%d"%i,lb=-gu.GRB.INFINITY,vtype=gu.GRB.CONTINUOUS) for i in range(self.Nf+1)]
        
         
        model.update()
        print "done "
        
        #print "setting penalty objective %s ..."%self.penalty,
        obj=None
        if self.penalty=="l1":
            obj=self._C * (gu.quicksum([u for u in u_vars1 ])+gu.quicksum([u for u in u_vars2 ]))
        elif self.penalty=="l2":
            obj=self._C * (gu.quicksum([u*u for u in u_vars1 ])+gu.quicksum([u*u for u in u_vars2 ]))
        else:
            print  "penalty term not know !"
            raise RuntimeError
        
        
            
        obj += 0.5 * gu.quicksum(w * w for w in w_vars[:-1] )

        model.setObjective(obj)


        print "done"
        #print "objective = ", model.getObjective()
        
        ### add constraint for the variables
        print "adding constraint penalty"
        if tags:
            print "huh, wtf"
            for i in range(sum(tags)):
                #logme("%.2f"%(i/float(X_hat.shape[0])*100.0))
                constr=gu.quicksum([float(X_hat[i,j])*w_vars[j] for j in range(self.Nf+1)]) - u_vars1[i]<=float(Yl[i]) + self._epsilon
                model.addConstr(constr )
            for i in range(tags[0]):
                constr=gu.quicksum([-(float(X_hat[i,j])*w_vars[j])  for j in range(self.Nf+1)]) - u_vars2[i]<=-float(Yl[i]) + self._epsilon
                model.addConstr(constr)        
        else:
            for i in range(X.shape[0]):
		    constr=gu.quicksum([float(X_hat[i,j])*w_vars[j] for j in range(self.Nf+1)]) - u_vars1[i]<=float(Yl[i]) + self._epsilon
		    model.addConstr(constr )
		    constr=gu.quicksum([-(float(X_hat[i,j])*w_vars[j])  for j in range(self.Nf+1)]) - u_vars2[i]<=-float(Yl[i]) + self._epsilon
		    model.addConstr(constr)        

        model.update()
        #model.setParam('OutputFlag', False) 
        if boxConstraints is not None and len(boxConstraints) > 0:
            model.setParam("BarConvTol", 1E-4)
        model.optimize()
        
        #self.w=np.array([w.x for w in w_vars]).reshape(-1,1)
        ##print model.status==gu.GRB.status.OPTIMAL
        ##print "Obj: ",model.getObjective().getValue()

        self.w=np.array([w.x for w in w_vars]).reshape(-1,1)


        if boxConstraints is not None and len(boxConstraints) > 0:
            model.setParam("BarConvTol", 1E-8)
            numConstraintVariables = [features.shape[0] for (value, features) in boxConstraints]
            diffopminus = [model.addVar(name="diff-_%d"%i,lb=0,vtype=gu.GRB.CONTINUOUS) for i in
                            range(len(boxConstraints))]
            diffopplus = [model.addVar(name="diff+_%d"%i,lb=0,vtype=gu.GRB.CONTINUOUS) for i in
                            range(len(boxConstraints))]
            z_vars = []
            b_vars = []
            isForegroundIndicators = []

            for i in range(len(boxConstraints)):
                value, features = boxConstraints[i]
                assert features.shape[1] == self.Nf
                res = self.predict(features)
                res[np.where(res >0)] = 1
                res[np.where(res <0)] = 0
                isForegroundIndicators.append(res)

                z_vars.append([model.addVar(name = "z_{}_{}".format(i, j), vtype = gu.GRB.CONTINUOUS) for j in
                      range(features.shape[0]) ])
                b_vars.append([model.addVar(name = "b_{}_{}".format(i, j), lb = 0, vtype = gu.GRB.CONTINUOUS) for j in
                      range(features.shape[0]) ])


            model.update()

            for i, b_i,fore_i, z_i, boxConstraint in zip(range(len(boxConstraints)), b_vars, isForegroundIndicators, z_vars, boxConstraints):
                value, features = boxConstraint
                for b, fore, z, feature in zip(b_i, fore_i, z_i, features):

                    multconstr = gu.quicksum([float(feature[j]) * w_vars[j] for j in range(self.Nf)]) + w_vars[-1] <= z
                    model.addConstr(multconstr)
                    multconstr = -gu.quicksum([float(feature[j]) * w_vars[j] for j in range(self.Nf)]) - w_vars[-1] <= z
                    model.addConstr(multconstr)
                
                    active = float(1 - fore)

                    activeconstr1 = active >=  b
                    model.addConstr(activeconstr1)
                    activeconstr3 = 1 - active >=  gu.quicksum([float(feature[j])*w_vars[j] for j in range(self.Nf)])+\
                        w_vars[-1] + b
                    model.addConstr(activeconstr3)

                
                condensedFeatures = np.sum(features, axis = 0)
                boxconstrmax = diffopminus[i] >= 0.5 * (gu.quicksum([float(condensedFeatures[j])*w_vars[j] for j in
                                                                     range(self.Nf)])+float(features.shape[0]) \
                * w_vars[-1]) + 0.5 * gu.quicksum([z for z in z_i])  - float(value) 
                
                model.addConstr(boxconstrmax)


                boxconstrmin = diffopplus[i] >= float(value) - gu.quicksum([float(condensedFeatures[j])*w_vars[j] for
                            j in range(self.Nf)] ) - float(features.shape[0]) * w_vars[-1] - gu.quicksum([b for b in b_i]) 
                

                model.addConstr(boxconstrmin)

                obj += self._C * (1./features.shape[0]) * diffopplus[i] * diffopplus[i]
                obj += self._C * (1./features.shape[0]) * diffopminus[i] * diffopminus[i]

            model.setObjective(obj)
        
            model.update()    
            model.optimize()

            self.w=np.array([w.x for w in w_vars]).reshape(-1,1)

        model.write("test.lp")
        return self  

    def predict(self, X):
        
        oldShape = X.shape
        result = np.dot(self.get_Xhat(X.reshape((-1, X.shape[-1]))),self.w).reshape(X.shape[:-1])
        return result

        



class SVR(object):


    options = [
        {"method" : "BoxedRegressionGurobi", "gui":["default", "svr"],
         "req":["ilastik.applets.counting.cwrapper.gurobi"], "boxes": True},
        {"method" : "BoxedRegressionCplex", "gui":["default", "svr"], "req":["ilastik.applets.counting.cwrapper.cplex"],
         "boxes": True},
        #{"method" : "svrBoxed-gurobi", "gui":["default", "svr"], "req":["gurobipy"]},
        {"method" : "RandomForest" ,"gui":["default","rf"], "req":["sklearn"], "boxes": False},
        #{"optimization" : "svr-sklearn", "kernel" : "rbf","gui":["default","svr"], "req":["sklearn"]},
        #{"method" : "svr-gurobi", "gui":["default", "svr"], "req":["gurobipy"]}
        
        #{"optimization" : "svr-gurobi", "gui":["default", "svr"], "req":["dummy"]}
    #{"optimization" : "svr", "kernel" : "linear","gui":["default","svr"]},
    #{"optimization" : "svr", "kernel" : "poly","gui":["default","svr"]},
    #{"optimization" : "svr", "kernel" : "sigmoid","gui":["default","svr"]},
    #{"optimization" : "quadratic", "kernel" : "linear","gui":["default","svr"]},
    #{"optimization" : "quadratic", "kernel" : "rbf","gui":["default","svr"]}
    #{"optimization" : "smo", "kernel" : "linear"},
    #{"optimization" : "smo", "kernel" : "gaussian"}
    ]


    def __init__(self, method = options[0]["method"], Sigma = 2.5, C = 1, epsilon = 0.000, \
                  ntrees=10, maxdepth=50, #RF parameters, maxdepth=None means grows until purity
                 **kwargs
                 ):
        """
        """
        self.DENSITYBOUND=True
        
        self._numRegressors = 0
        #self.upperBounds = [None, underMult, overMult]
        self._Sigma = Sigma
        self._C = C
        self._epsilon = epsilon

        #self._kernel = kernel
        self._method = method 
        
        #RF parameters:
        self._ntrees=ntrees
        self._maxdepth=maxdepth
        
    @classmethod
    def load(self, cachePath, targetname):
        f = h5py.File(cachePath, 'r')
        dataset = f[targetname]
        obj = cPickle.loads(dataset[0])
        f.close()
        return obj

    def smoothLabels(self, dot):
        
        backupindices = np.where(dot == 2)
        dot[backupindices] = 0
        sigma = self._Sigma
        
        
        oldShape = dot.shape
        if sigma > 0:
            try:
                dot = vigra.filters.gaussianSmoothing(dot.astype(np.float32).squeeze(), sigma) #TODO: use it later, but this
            except Exception,e:
                print "HHHHHHHH",dot.shape,dot.dtype
                print e
                raise Exception
            
        
        
        dot = dot.reshape(oldShape)
        dot[backupindices] = 0
        
        return dot,backupindices

    def prepareDataRefactored(self, dot, nindices):

        dot = dot.reshape(-1)
        pindices = np.where(dot > 0.0001)[0]
        #pindices = pindices[:250]
        lindices = None
        #if self.DENSITYBOUND:
        #    lindices = np.concatenate((nindices, pindices))
        #else:
        lindices = nindices

        #lindices = np.concatenate((pindices, nindices))
        numVariables = len(pindices) + len(lindices) 

        mapping = np.concatenate((pindices, lindices))

        tags = [len(pindices), len(lindices)]
        #print dot

        return dot, mapping, tags


    def prepareData(self, dot, smooth = True):

        dot, backupindices = self.smoothLabels(dot)

        #is terrible for debugging
        nindices = np.ravel_multi_index(backupindices, dot.shape) #TODO: CHANGE BACK
        dot = dot.reshape(-1)
        pindices = np.where(dot > 0.0001)[0]
        #pindices = pindices[:250]
        lindices = None
        #if self.DENSITYBOUND:
        #    lindices = np.concatenate((nindices, pindices))
        #else:
        lindices = nindices

        #lindices = np.concatenate((pindices, nindices))
        numVariables = len(pindices) + len(lindices) 

        mapping = np.concatenate((pindices, lindices))

        tags = [len(pindices), len(lindices)]
        #print dot

        return dot, mapping, tags
   
    def fit(self, img, dot, boxConstraints = [], smooth = True, numRegressors = 1):

        newDot, mapping, tags = \
        self.prepareData(dot, smooth)
        newImg = img.reshape((-1, img.shape[-1]))
        self.fitPrepared(newImg[mapping,:], newDot[mapping], tags, boxConstraints, numRegressors)


    def splitBoxConstraints(self, numRegressors, boxConstraints):
        
        if boxConstraints is None or type(boxConstraints) is not dict:
            return [None for i in range(numRegressors)]
        boxIndices = boxConstraints["boxIndices"]
        boxValues = boxConstraints["boxValues"]
        boxFeatures = boxConstraints["boxFeatures"]
        indices = np.arange(boxFeatures.shape[0])
        assert(boxFeatures.shape[0] == boxIndices[-1])
        np.random.shuffle(indices)
        splits = np.array_split(indices, numRegressors)
        boxConstraintList = []
        
        for split in splits:
            subBoxIndices = [0]
            subBoxValues = []
            split = np.sort(split)
            j = 1
            limit = boxIndices[j]
            for count, index in enumerate(split):
                if index >= limit:
                    if count != subBoxIndices[-1] and count != len(split):
                        subBoxIndices.append(count)
                    j = j + 1
                    limit = boxIndices[j]

            subBoxIndices.append(len(split))
            for j, _ in enumerate(subBoxIndices[:-1]):
                subVal = boxValues[j] * (subBoxIndices[j + 1] - subBoxIndices[j]) / (boxIndices[j + 1] - boxIndices[j])
                subBoxValues.append(subVal)

            subBoxFeatures = boxFeatures[split,:]
            subBoxConstraint = {"boxValues" : np.array(subBoxValues), "boxIndices" : np.array(subBoxIndices),
                                "boxFeatures" : subBoxFeatures}
            boxConstraintList.append(subBoxConstraint)

        return boxConstraintList




    def fitPrepared(self, img, dot, tags, boxConstraints = [], numRegressors = 1, trainAll = True):
        if trainAll:
            self._regressor = [None for i in range(numRegressors)]
            self._numRegressors = numRegressors
        else:
            self._regressor = [None]
            self._numRegressors = 1

        numFeatures = img.shape[-1]
        numVariables = sum(img.shape[:-1])
        if numVariables == 0:
            return
       
        if numRegressors == 1:
            try:
                self._regressor[0] = self._fit(img, dot, tags, boxConstraints)
            except:
                pass
            return 
        
        splitBoxConstraints = self.splitBoxConstraints(numRegressors, boxConstraints)
        
        for i in range(numRegressors):
            indices = np.random.randint(0,numVariables, size = numVariables / numRegressors)    
            indices.sort()
            cut = np.where(indices < tags[0])
            newTags = [len(cut[0]), len(indices) - len(cut[0])]

            
            if numVariables == 0:
                return 
            #tags.append(len(boxConstraints))
                
            newBoxConstraints = splitBoxConstraints[i]

            try:
                regressor = self._fit(img[indices, :], dot[indices], newTags, newBoxConstraints)
                self._regressor[i] = regressor
            except RuntimeError as err:
                logger.error("Error while training the regressor")
                raise err
                pass
            #train only one regressor
            if not trainAll:
                break

        self._numRegressors = len(self._regressor)

        return 
    

    def _fit(self, img, dot, tags, boxConstraints = []):
        
        numFeatures = img.shape[1]
        if self._method == "RandomForest":
            from sklearn.ensemble import RandomForestRegressor as RFR
            
            regressor = RFR(n_estimators=self._ntrees,max_depth=self._maxdepth)
            regressor.fit(img, dot)

        elif self._method == "svrBoxed-gurobi":
            regressor = RegressorGurobi(C = self._C, epsilon = self._epsilon)
            regressor.fit(img, dot, tags, self.getOldBoxConstraints(boxConstraints, numFeatures
                                                                   ))
        #elif self._method == "svrBoxed-gurobi":
        #    regressor = RegressorGurobi(C = self._C, epsilon = self._epsilon)
        #    regressor.fit(img, dot, tags, self.getOldBoxConstraints(boxConstraints, numFeatures
        #                                                           ))
        elif self._method == "BoxedRegressionGurobi":
            regressor = RegressorC(C = self._C, epsilon = self._epsilon)
            regressor.fitgurobi(img, dot, tags, boxConstraints)
        
        elif self._method == "BoxedRegressionCplex":
            regressor = RegressorC(C = self._C, epsilon = self._epsilon)
            regressor.fitcplex(img, dot, tags, boxConstraints)

        return regressor
        


    def predict(self, oldImage):
        oldShape = oldImage.shape
        resShape = oldShape[:-1]
        image = np.copy(oldImage.reshape((-1, oldImage.shape[-1])))
       
        reslist = []
        for r in self._regressor:
            if r is None:
                reslist.append(np.zeros(oldImage.shape[:-1]))
            else:
                reslist.append(r.predict(image))
            res = np.dstack(reslist)
            resShape = oldShape[:-1] + (len(self._regressor),)
        
        #res = np.zeros(oldShape[:-1])
        res = res.view(np.ndarray)
        res[res < 0] = 0
        return res.reshape(resShape)

    def writeHDF5(self, cachePath, targetname):
        f = h5py.File(cachePath, 'w')
        str_type = h5py.special_dtype(vlen = str)
        dataset = f.create_dataset(targetname, shape = (1,), dtype = str_type)
        dataset[0] = cPickle.dumps(self)
        f.close()

    def get_params(self):
        return {
            'method' : self._method,
            'Sigma' : self._Sigma,
            'C' : self._C,
            'epsilon' : self._epsilon,
            'ntrees' : self._ntrees,
            'maxdepth' : self._maxdepth
            }
    
    def set_params(self, **params):
        for key in params:
            setattr(self, "_" + key, params[key])
        return self

    def getOldBoxConstraints(self, newBoxConstraints, numFeatures):
        if newBoxConstraints == None:
            return None
        boxConstraints = []
        boxIndices = newBoxConstraints["boxIndices"]
        boxValues = newBoxConstraints["boxValues"]
        boxFeatures = newBoxConstraints["boxFeatures"]
        assert(len(boxFeatures.shape) == 2)
        for i, boxValue in enumerate(boxValues):
            slicing = slice(boxIndices[i], boxIndices[i + 1])
            valfeaturepair = (boxValue, boxFeatures[slicing,:])
            if valfeaturepair[1].shape[0] > 0:
                boxConstraints.append(valfeaturepair)
        return boxConstraints



if __name__ == "__main__":

    np.set_printoptions(precision=4)
    np.set_printoptions(threshold = 'nan')
    img = np.load("img.npy")
    dot = np.load("dot.npy")
    #img = img[...,[2]]
    #img = img[..., None]
    
    DENSITYBOUND=False

    #shortExample
#    limits = [50, 200]
#    img = img[limits[0]:limits[1],limits[0]:limits[1],:]
#    dot = dot[limits[0]:limits[1],limits[0]:limits[1]]

   #ToyExample
    #img = np.ones((9,9,2),dtype=np.float32)
    #dot = np.zeros((9,9))
    #img = 1 * img
    #img[:,:,1] = np.random.rand(*img.shape[:-1])
    #img[0,0] = 3
    #img[1,1] = 3
    #img[3:6,3:6] = 50
    #dot[4,4] = 1
    #dot[5,5] = 1
    #dot[0,0] = 2
    #dot[1,1] = 2

    backup_image = np.copy(img)
    sigma = 0
    Counter = SVR(method = "BoxedRegressionGurobi", Sigma= sigma)
    testdot, testmapping, testtags = Counter.prepareData(dot,smooth = True)
    testimg = img.reshape((-1, img.shape[-1]))
    #print "blub", testimg.shape
    #print testimg
    #print testdot, np.sum(testdot)
    
    boxIndices = np.array([0, 25])
    boxFeatures = np.array(img[:5,:5],dtype=np.float64)
    boxValues = np.array([5])
    boxFeatures = boxFeatures.reshape((-1, boxFeatures.shape[-1]))
    
    boxConstraints = {"boxValues": boxValues, "boxIndices" : boxIndices, "boxFeatures" :boxFeatures}
    #boxConstraints = None

    print testtags
    numRegressors = 1
    success = Counter.fitPrepared(testimg[testmapping,:], testdot[testmapping], testtags,
                                  boxConstraints = boxConstraints, numRegressors = numRegressors)
    print Counter._regressor[0].w
    #3uccess = Counter.fitPrepared(testimg[indices,:], testdot[indices], testtags[:len(indices)], epsilon = 0.000)
    #print Counter.w, Counter.
    print "learning finished"

    #conversion step
    #Q = kernelize(B, method = "gaussian")
    ##Q = B * B.transpose()
    #tags = np.zeros(numVariables,dtype=np.int8)
    #tags[0:len(pindices)] = 1
    #tags[len(pindices):] = -1
    #c = dot[allIndices] * (-tags)+ epsilon
    #upperBounds = [None, pMult, lMult]
    #success,solution = optimize(tags,Q,c,upperBounds)
    ## Put model data into dense matrices
    #print Counter.b, Counter.w
    newdot = Counter.predict(backup_image)

    print "prediction"
    #print img
    #print newdot
    print "sum", np.sum(newdot) / numRegressors
    #try: 
    #    import matplotlib.pyplot as plt
    #    import matplotlib
    #    fig = plt.figure()
    #    fig.add_subplot(1,3,1)
    #    plt.imshow(testimg[...,0].astype('uint8').reshape(backup_image.shape[:-1]), cmap=matplotlib.cm.gray)
    #    fig.add_subplot(1,3,2)
    #    plt.imshow(newdot.reshape(backup_image.shape[:-1]), cmap=matplotlib.cm.gray)
    #    fig.add_subplot(1,3,3)
    #    plt.imshow(testdot.reshape(backup_image.shape[:-1]), cmap=matplotlib.cm.gray)
    #    plt.show()
    #except:
    #    pass






    #print Counter.w, Counter.b
    #debug_trace()
    #
    #c = [1, 1, 0]
    #Q = [[1, 1, 0], [0, 1, 1], [0, 0, 1]]
    #A = [[1, 2, 3], [1, 1, 0]]
    #sense = [GRB.GREATER_EQUAL, GRB.GREATER_EQUAL]
    #rhs = [4, 1]
    #lb = [0, 0, 0]
    #ub = [GRB.INFINITY, GRB.INFINITY, GRB.INFINITY]
    #vtype = [GRB.CONTINUOUS, GRB.CONTINUOUS, GRB.CONTINUOUS]
    #sol = [0]*3
    #
    ## Optimize
    #
    #success = dense_optimize(2, 3, c, Q, A, sense, rhs, lb, ub, vtype, sol)
    #
    #if success:
    #  print 'x: ', sol[0], 'y: ', sol[1], 'z: ', sol[2]
    #for i in range(numVariables):
    #    m.addVar()


