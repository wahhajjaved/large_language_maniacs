import omnical.info as Oi, omnical.calib as Oc, omnical._omnical as _O
#import omnical.calibration_omni as omni
import numpy as np, numpy.linalg as la
from copy import deepcopy
import os, unittest
import nose.tools as nt

redinfo_psa32 = os.path.dirname(os.path.realpath(__file__)) + '/../doc/redundantinfo_PSA32.txt'
#infotestpath = os.path.dirname(os.path.realpath(__file__)) + '/redundantinfo_test.bin'
infotestpath = os.path.dirname(os.path.realpath(__file__)) + '/calib_test_redinfo.npz'
testdata = os.path.dirname(os.path.realpath(__file__)) + '/testinfo/calib_test_data_%02d.npz'

VERBOSE = False

class TestRedundantInfo(unittest.TestCase):
    def setUp(self):
        self.legacy_info = Oi.RedundantInfoLegacy(filename=redinfo_psa32, txtmode=True)
        self.info = Oc.RedundantInfo()
        self.info.init_from_reds(self.legacy_info.get_reds(), self.legacy_info.antloc)
    def test_pack_calpar(self):
        calpar = np.zeros((2,3,self.info.calpar_size(self.info.nAntenna, len(self.info.ublcount))), dtype=np.float32)
        self.assertTrue(np.all(self.info.pack_calpar(calpar) == 0))
        self.assertRaises(AssertionError, self.info.pack_calpar, calpar[...,:-1])
        bp = np.array([[1+2j,3+4j,5+6j],[2+1j,4+3j,6+5j]])
        amp,phs = np.log10(np.abs(bp)), np.angle(bp)
        gains = {0:bp}
        self.info.pack_calpar(calpar,gains=gains)
        self.assertTrue(np.allclose(calpar[...,3+0], amp))
        self.assertTrue(np.allclose(calpar[...,32+3+0],phs))
        calpar *= 0
        gains = {1:bp[0]}
        self.info.pack_calpar(calpar,gains=gains)
        self.assertTrue(np.allclose(calpar[0,:,3+1], amp[0]))
        self.assertTrue(np.allclose(calpar[1,:,3+1], amp[0]))
        self.assertTrue(np.allclose(calpar[0,:,32+3+1],phs[0]))
        self.assertTrue(np.allclose(calpar[1,:,32+3+1],phs[0]))
        vis = {(0,16):bp}
        self.info.pack_calpar(calpar,vis=vis)
        self.assertTrue(np.allclose(calpar[...,3+2*32+2*12], bp.real))
        self.assertTrue(np.allclose(calpar[...,3+2*32+2*12+1], bp.imag))
    def test_unpack_calpar(self):
        calpar = np.zeros((2,3,self.info.calpar_size(self.info.nAntenna, len(self.info.ublcount))), dtype=np.float32)
        m,g,v = self.info.unpack_calpar(calpar)
        antchisq = [k for k in m if k.startswith('chisq') and len(k) > len('chisq')]
        self.assertEqual(m['iter'].shape, (2,3))
        self.assertEqual(len(antchisq), self.info.nAntenna)
        self.assertTrue(np.all(m['iter'] == 0))
        self.assertTrue(np.all(m['chisq'] == 0))
        for k in antchisq:
            self.assertTrue(np.all(m[k] == 0))
        self.assertEqual(len(g), 32)
        for i in xrange(32):
            self.assertTrue(np.all(g[i] == 1)) # 1 b/c 10**0 = 1
        self.assertEqual(len(v), len(self.info.ublcount))
        ubls = {}
        for i,j in v:
            n = self.info.bl1dmatrix[i,j]
            ubls[self.info.bltoubl[n]] = n
        for u in xrange(len(self.info.ublcount)):
            self.assertTrue(ubls.has_key(u))
    def test_order_data(self):
        antpos = np.array([[0.,0,0],[1,0,0],[2,0,0],[3,0,0]])
        reds = [[(0,1),(1,2),(2,3)],[(0,2),(1,3)]]
        i = Oc.RedundantInfo()
        i.init_from_reds(reds,antpos)
        dd = {
            (0,1):np.array([[0,1j]]),
            (1,2):np.array([[0,1j]]),
            (2,3):np.array([[0,1j]]),
            (2,0):np.array([[0,1j]]),
            (1,3):np.array([[0,1j]]),
        }
        d = i.order_data(dd)
        self.assertTrue(np.all(d[...,0] == np.array([[0,1j]])))
        self.assertTrue(np.all(d[...,1] == np.array([[0,1j]])))
        self.assertTrue(np.all(d[...,2] == np.array([[0,1j]])))
        self.assertTrue(np.all(d[...,3] == np.array([[0,1j]]).conj()))
        self.assertTrue(np.all(d[...,4] == np.array([[0,1j]])))


class TestMethods(unittest.TestCase):
    def setUp(self):
        self.info = Oi.RedundantInfoLegacy(filename=redinfo_psa32, txtmode=True)

        self.info2 = Oc.RedundantInfo()
        self.info2.init_from_reds([[(0, 4), (1, 5), (2, 6), (3, 7), (4, 8), (5, 9)],
                             [(0, 3), (1, 4), (2, 5), (3, 6), (4, 7), (5, 8), (6, 9)],
                             [(0, 6), (1, 7), (2, 8), (3, 9)],
                             [(0, 5), (1, 6), (2, 7), (3, 8), (4, 9)],
                             [(0, 8), (1, 9)],
                             [(0, 7), (1, 8), (2, 9)],
                             [(0, 2), (1, 3), (2, 4), (3, 5), (4, 6), (5, 7), (6, 8), (7, 9)],
                             [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9)]],
                             np.array([[0., 0., 1.],
                                       [0., 50., 1.],
                                       [0., 100., 1.],
                                       [0., 150., 1.],
                                       [0., 200., 1.],
                                       [0., 250., 1.],
                                       [0., 300., 1.],
                                       [0., 350., 1.],
                                       [0., 400., 1.],
                                       [0., 450., 1.]]))

        self.freqs = np.linspace(.1, .2, 16)
        self.times = np.arange(4)
        self.reds = self.info2.get_reds()
        self.true_vis = {}
        for i, rg in enumerate(self.reds):
            rd = np.array(np.random.randn(self.times.size, self.freqs.size) + 1j * np.random.randn(self.times.size, self.freqs.size), dtype=np.complex64)
            self.true_vis[rg[0]] = rd
        self.true_gains = {i: np.ones((self.times.size, self.freqs.size), dtype=np.complex64) for i in self.info2.subsetant}
        self.data = {}
        self.bl2red = {}
        for rg in self.reds:
            for r in rg:
                self.bl2red[r] = rg[0]
        for redgp in self.reds:
            for ai, aj in redgp:
                self.data[ai, aj] = self.true_vis[self.bl2red[ai, aj]] * self.true_gains[ai] * np.conj(self.true_gains[aj])
        self.unitgains = {ant: np.ones((self.times.size, self.freqs.size), dtype=np.complex64) for ant in self.info2.subsetant}
        self.unitdata = {(ai, aj): np.ones((self.times.size, self.freqs.size), dtype=np.complex64) for ai,aj in self.info2.bl_order()}
    def test_redcal(self):
        #check that logcal give 0 chi2 for all 20 testinfos
        for index in xrange(20):
            arrayinfopath = os.path.dirname(os.path.realpath(__file__)) + '/testinfo/test'+str(index+1)+'_array_info.txt'
            c = Oc.RedundantCalibrator(56)
            c.compute_redundantinfo(arrayinfopath, tol=.1)
            info = Oc.RedundantInfo()
            info.init_from_reds(c.Info.get_reds(), c.Info.get_antpos())
            npz = np.load(testdata % index)
            bls = [tuple(bl) for bl in npz['bls']]
            dd = dict(zip(bls, npz['vis']))
            m,g,v = Oc.redcal(dd, info, removedegen=True,maxiter=50,stepsize=.2,computeUBLFit=True,conv=1e-5,uselogcal=True)
            calparpath = os.path.dirname(os.path.realpath(__file__)) + '/testinfo/test'+str(index+1)+'_calpar.txt'
            with open(calparpath) as f:
                rawinfo = [[float(x) for x in line.split()] for line in f]
            temp = np.array(rawinfo[:-1])
            correctcalpar = (np.array(temp[:,0]) + 1.0j*np.array(temp[:,1]))
            i = g.keys()[0]
            scalar = correctcalpar[i].real / g[i].real
            for i in xrange(56):
                if not g.has_key(i): continue
                self.assertAlmostEqual(np.abs(correctcalpar[i] - g[i] * scalar), 0, 4)

    def test_logcal(self):
        m, g, v = Oc.logcal(self.unitdata, self.info2)
        nt.assert_equal(np.testing.assert_equal(g, self.unitgains), None)

    def test_lincal(self):
        m1, g1, v1 = Oc.logcal(self.unitdata, self.info2)
        m, g, v = Oc.lincal(self.unitdata, self.info2, gains=g1, vis=v1)
        nt.assert_equal(np.testing.assert_equal(g, self.unitgains), None)

    def test_redcal_xtalk(self):
        antpos = np.array([[0.,0,0],[1,0,0],[2,0,0],[3,0,0]])
        d = {(1,2): np.array([[1.]], dtype=np.complex64), (2,3): np.array([[1.+1j]], dtype=np.complex64)}
        x = {(1,2): np.array([[0.]], dtype=np.complex64), (2,3): np.array([[0.+1j]], dtype=np.complex64)}
        reds = [[(1,2),(2,3)]]
        info = Oc.RedundantInfo(); info.init_from_reds(reds, antpos)
        m,g,v = Oc.redcal(d, info, xtalk=x, uselogcal=False)
        self.assertEqual(g[1][0,0], 1.)
        self.assertEqual(g[2][0,0], 1.)
        self.assertEqual(g[3][0,0], 1.)
        #2D array testing
        d = {(1,2): np.array([[1.,2],[3.,4]],dtype=np.complex64), (2,3): np.array([[1.+1j,2+2j],[3+3j,4+4j]],dtype=np.complex64)}
        x = {(1,2): np.array([[0.,2],[2.,3]],dtype=np.complex64), (2,3): np.array([[0.+1j,1+2j],[2+3j,3+4j]],dtype=np.complex64)}
        m,g,v = Oc.redcal(d, info, xtalk=x, uselogcal=False)
        self.assertEqual(g[1][0,0], 1.)
        self.assertEqual(g[2][0,0], 1.)
        self.assertEqual(g[3][0,0], 1.)
        self.assertEqual(m['res'][(2,3)][0][0],0.)



class TestLogCalLinCalAndRemoveDegen(unittest.TestCase):
    """This test runs omnical with full complexity except thermal noise: non-trivial gains and visibilities, large firstcal phase wraps, degeneracy removal."""
    
    def removedegen2(self, info, gains, vis, gainstart):
        # divide out by gainstart (e.g. firstcal gains).    
        g,v = deepcopy(gains),deepcopy(vis)
        for ant in gains.keys():
            g[ant] /= gainstart[ant]
        
        # Calculate matrices used for projecting out degeneracies from antenna locations
        Rgains =  np.array([np.append(ai,1) for ai in info.antloc]) 
        Mgains = np.linalg.pinv(Rgains.T.dot(Rgains)).dot(Rgains.T) 
        Rvis = np.hstack((-info.ubl, np.zeros((len(info.ubl),1))))
        reds = info.get_reds()
        ntimes, nfreqs = gains.values()[0].shape
        
        for t in range(ntimes):
            for f in range(nfreqs):
                gainSols = np.array([g[ai][t,f] for ai in info.subsetant])
                visSols = np.array([vis[rg[0]][t,f] for rg in reds])
                
                #Fix amplitudes
                newGainSols = gainSols * np.exp(-1.0j * np.mean(np.angle(gainSols)))
                newGainSols = newGainSols / np.mean(np.abs(newGainSols))
                newVisSols = visSols * np.mean(np.abs(gainSols))**2 

                #Fix phases
                degenRemoved = Mgains.dot(np.angle(newGainSols))
                newGainSols = newGainSols * np.exp(-1.0j * Rgains.dot(degenRemoved))
                newVisSols = newVisSols * np.exp(-1.0j * Rvis.dot(degenRemoved))

                for i,ant in enumerate(info.subsetant): g[ant][t,f] = newGainSols[i]
                for i,rg in enumerate(reds): v[rg[0]][t,f] = newVisSols[i]    

        # multipy back in gainstart.
        for ai in g.keys():
            g[ai] *= gainstart[ai]

        return {}, g, v 

    def chisq(self, data, g, v, reds):
        return np.mean(np.array([np.abs(data[(i,j)] - np.conj(g[i])*g[j]*v[rg[0]])**2 for rg in reds for (i,j) in rg]),axis=0)

    def test_full_functionality(self):
        antpos = np.array([[ 14.60000038, -25.28794098,   1.], [ 21.89999962, -12.64397049,   1.], [ 14.60000038,  25.28794098,   1.], [-21.89999962, -12.64397049,   1.], [-14.60000038,   0.        ,   1.], [ 21.89999962,  12.64397049,   1.], [ 29.20000076,   0.        ,   1.], [-14.60000038, -25.28794098,   1.], [  0.        ,  25.28794098,   1.], [  0.        , -25.28794098,   1.], [  0.        ,   0.        ,   1.], [ -7.30000019, -12.64397049,   1.], [ -7.30000019,  12.64397049,   1.], [-21.89999962,  12.64397049,   1.], [-29.20000076,   0.        ,   1.], [ 14.60000038,   0.        ,   1.], [-14.60000038,  25.28794098,   1.], [  7.30000019, -12.64397049,   1.]])
        reds = [[(0, 8), (9, 16)], [(13, 15), (14, 17), (3, 0), (4, 1), (16, 5), (12, 6)], [(3, 17), (4, 15), (7, 0), (11, 1), (16, 2), (12, 5), (10, 6), (14, 10)], [(3, 6), (14, 5)], [(0, 9), (1, 17), (2, 8), (4, 14), (6, 15), (8, 16), (12, 13), (11, 3), (10, 4), (9, 7), (15, 10), (17, 11)], [(3, 8), (11, 2), (9, 5)], [(3, 9), (4, 17), (12, 15), (11, 0), (10, 1), (8, 5), (13, 10), (14, 11)], [(0, 13), (1, 16)], [(0, 4), (1, 12), (6, 8), (9, 14), (15, 16), (17, 13)], [(0, 5), (3, 16), (7, 12), (17, 2), (11, 8)], [(0, 10), (7, 14), (10, 16), (11, 13), (6, 2), (9, 4), (15, 8), (17, 12)], [(1, 9), (2, 12), (5, 10), (6, 17), (8, 13), (12, 14), (10, 3), (17, 7), (15, 11)], [(2, 3), (5, 7)], [(16, 17), (12, 0), (8, 1), (13, 9)], [(0, 17), (1, 15), (3, 14), (4, 13), (9, 11), (10, 12), (12, 16), (5, 2), (7, 3), (11, 4), (6, 5), (17, 10)], [(3, 15), (4, 5), (7, 1), (13, 2), (11, 6)], [(5, 15), (8, 12), (10, 11), (13, 14), (15, 17), (1, 0), (6, 1), (4, 3), (12, 4), (11, 7), (17, 9), (16, 13)], [(0, 15), (1, 5), (3, 13), (4, 16), (9, 10), (11, 12), (15, 2), (7, 4), (10, 8)], [(0, 6), (3, 12), (4, 8), (7, 10), (9, 15), (14, 16), (10, 2), (17, 5)], [(8, 17), (2, 1), (13, 7), (12, 9), (16, 11)], [(0, 2), (7, 16), (9, 8)], [(4, 6), (14, 15), (3, 1), (13, 5)], [(0, 14), (1, 13), (6, 16)], [(2, 14), (6, 7), (5, 3)], [(2, 9), (8, 7)], [(2, 4), (5, 11), (6, 9), (8, 14), (15, 7)], [(1, 14), (6, 13)], [(0, 8), (9, 16)], [(13, 15), (14, 17), (3, 0), (4, 1), (16, 5), (12, 6)], [(3, 17), (4, 15), (7, 0), (11, 1), (16, 2), (12, 5), (10, 6), (14, 10)], [(3, 6), (14, 5)], [(0, 9), (1, 17), (2, 8), (4, 14), (6, 15), (8, 16), (12, 13), (11, 3), (10, 4), (9, 7), (15, 10), (17, 11)], [(3, 8), (11, 2), (9, 5)], [(3, 9), (4, 17), (12, 15), (11, 0), (10, 1), (8, 5), (13, 10), (14, 11)], [(0, 13), (1, 16)], [(0, 4), (1, 12), (6, 8), (9, 14), (15, 16), (17, 13)], [(0, 5), (3, 16), (7, 12), (17, 2), (11, 8)], [(0, 10), (7, 14), (10, 16), (11, 13), (6, 2), (9, 4), (15, 8), (17, 12)], [(1, 9), (2, 12), (5, 10), (6, 17), (8, 13), (12, 14), (10, 3), (17, 7), (15, 11)], [(2, 3), (5, 7)], [(16, 17), (12, 0), (8, 1), (13, 9)], [(0, 17), (1, 15), (3, 14), (4, 13), (9, 11), (10, 12), (12, 16), (5, 2), (7, 3), (11, 4), (6, 5), (17, 10)], [(3, 15), (4, 5), (7, 1), (13, 2), (11, 6)], [(5, 15), (8, 12), (10, 11), (13, 14), (15, 17), (1, 0), (6, 1), (4, 3), (12, 4), (11, 7), (17, 9), (16, 13)], [(0, 15), (1, 5), (3, 13), (4, 16), (9, 10), (11, 12), (15, 2), (7, 4), (10, 8)], [(0, 6), (3, 12), (4, 8), (7, 10), (9, 15), (14, 16), (10, 2), (17, 5)], [(8, 17), (2, 1), (13, 7), (12, 9), (16, 11)], [(0, 2), (7, 16), (9, 8)], [(4, 6), (14, 15), (3, 1), (13, 5)], [(0, 14), (1, 13), (6, 16)], [(2, 14), (6, 7), (5, 3)], [(2, 9), (8, 7)], [(2, 4), (5, 11), (6, 9), (8, 14), (15, 7)], [(1, 14), (6, 13)], [(0, 8), (9, 16)], [(13, 15), (14, 17), (3, 0), (4, 1), (16, 5), (12, 6)], [(3, 17), (4, 15), (7, 0), (11, 1), (16, 2), (12, 5), (10, 6), (14, 10)], [(3, 6), (14, 5)], [(0, 9), (1, 17), (2, 8), (4, 14), (6, 15), (8, 16), (12, 13), (11, 3), (10, 4), (9, 7), (15, 10), (17, 11)], [(3, 8), (11, 2), (9, 5)], [(3, 9), (4, 17), (12, 15), (11, 0), (10, 1), (8, 5), (13, 10), (14, 11)], [(0, 13), (1, 16)], [(0, 4), (1, 12), (6, 8), (9, 14), (15, 16), (17, 13)], [(0, 5), (3, 16), (7, 12), (17, 2), (11, 8)], [(0, 10), (7, 14), (10, 16), (11, 13), (6, 2), (9, 4), (15, 8), (17, 12)], [(1, 9), (2, 12), (5, 10), (6, 17), (8, 13), (12, 14), (10, 3), (17, 7), (15, 11)], [(2, 3), (5, 7)], [(16, 17), (12, 0), (8, 1), (13, 9)], [(0, 17), (1, 15), (3, 14), (4, 13), (9, 11), (10, 12), (12, 16), (5, 2), (7, 3), (11, 4), (6, 5), (17, 10)], [(3, 15), (4, 5), (7, 1), (13, 2), (11, 6)], [(5, 15), (8, 12), (10, 11), (13, 14), (15, 17), (1, 0), (6, 1), (4, 3), (12, 4), (11, 7), (17, 9), (16, 13)], [(0, 15), (1, 5), (3, 13), (4, 16), (9, 10), (11, 12), (15, 2), (7, 4), (10, 8)], [(0, 6), (3, 12), (4, 8), (7, 10), (9, 15), (14, 16), (10, 2), (17, 5)], [(8, 17), (2, 1), (13, 7), (12, 9), (16, 11)], [(0, 2), (7, 16), (9, 8)], [(4, 6), (14, 15), (3, 1), (13, 5)], [(0, 14), (1, 13), (6, 16)], [(2, 14), (6, 7), (5, 3)], [(2, 9), (8, 7)], [(2, 4), (5, 11), (6, 9), (8, 14), (15, 7)], [(1, 14), (6, 13)], [(0, 8), (9, 16)], [(13, 15), (14, 17), (3, 0), (4, 1), (16, 5), (12, 6)], [(3, 17), (4, 15), (7, 0), (11, 1), (16, 2), (12, 5), (10, 6), (14, 10)], [(3, 6), (14, 5)], [(0, 9), (1, 17), (2, 8), (4, 14), (6, 15), (8, 16), (12, 13), (11, 3), (10, 4), (9, 7), (15, 10), (17, 11)], [(3, 8), (11, 2), (9, 5)], [(3, 9), (4, 17), (12, 15), (11, 0), (10, 1), (8, 5), (13, 10), (14, 11)], [(0, 13), (1, 16)], [(0, 4), (1, 12), (6, 8), (9, 14), (15, 16), (17, 13)], [(0, 5), (3, 16), (7, 12), (17, 2), (11, 8)], [(0, 10), (7, 14), (10, 16), (11, 13), (6, 2), (9, 4), (15, 8), (17, 12)], [(1, 9), (2, 12), (5, 10), (6, 17), (8, 13), (12, 14), (10, 3), (17, 7), (15, 11)], [(2, 3), (5, 7)], [(16, 17), (12, 0), (8, 1), (13, 9)], [(0, 17), (1, 15), (3, 14), (4, 13), (9, 11), (10, 12), (12, 16), (5, 2), (7, 3), (11, 4), (6, 5), (17, 10)], [(3, 15), (4, 5), (7, 1), (13, 2), (11, 6)], [(5, 15), (8, 12), (10, 11), (13, 14), (15, 17), (1, 0), (6, 1), (4, 3), (12, 4), (11, 7), (17, 9), (16, 13)], [(0, 15), (1, 5), (3, 13), (4, 16), (9, 10), (11, 12), (15, 2), (7, 4), (10, 8)], [(0, 6), (3, 12), (4, 8), (7, 10), (9, 15), (14, 16), (10, 2), (17, 5)], [(8, 17), (2, 1), (13, 7), (12, 9), (16, 11)], [(0, 2), (7, 16), (9, 8)], [(4, 6), (14, 15), (3, 1), (13, 5)], [(0, 14), (1, 13), (6, 16)], [(2, 14), (6, 7), (5, 3)], [(2, 9), (8, 7)], [(2, 4), (5, 11), (6, 9), (8, 14), (15, 7)], [(1, 14), (6, 13)]]
        freqs = np.linspace(.1,.2,64)
        times = np.arange(11)
        ants = np.arange(len(antpos))

        info = Oc.RedundantInfo()
        info.init_from_reds(reds, antpos)

        # Simulate unique "true" visibilities
        np.random.seed(21)
        vis_true = {}
        i = 0
        for rg in reds:
            vis_true[rg[0]] = np.array(1.0*np.random.randn(len(times),len(freqs)) + 1.0j*np.random.randn(len(times),len(freqs)), dtype=np.complex64)

        # Smulate true gains and then remove degeneracies from true gains so that removedegen will produce exact answers
        gain_true = {}
        for i in ants:
            gain_true[i] = np.array(1. + (.1*np.random.randn(len(times),len(freqs)) + .1j*np.random.randn(len(times),len(freqs))), dtype=np.complex64) 
        g0 = {i: np.ones_like(gain_true[i]) for i in ants}
        _, gain_true, _ = self.removedegen2(info, gain_true, vis_true, g0)
       
        # Generate and apply firstcal gains
        fcgains = {}
        for i in ants:
            fcspectrum = np.exp(2.0j * np.pi * 5.0 * np.random.randn() * freqs)
            fcgains[i] = np.array([fcspectrum for t in times], dtype=np.complex64)
        for i in ants: gain_true[i] *= fcgains[i]

        # Generate fake data 
        bl2ublkey = {bl: rg[0] for rg in reds for bl in rg}
        data = {}
        for rg in reds:
            for (i,j) in rg:
                data[(i,j)] = np.array(np.conj(gain_true[i]) * gain_true[j] * vis_true[rg[0]], dtype=np.complex64)

        # Run logcal, lincal, and removedegen
        m1, g1, v1 = Oc.logcal(data, info, gains=fcgains)
        m2, g2, v2 = Oc.lincal(data, info, gains=g1, vis=v1)
        _g2 = {}
        for k in g2:
            _g2[k] = g2[k]/fcgains[k]
        _, g3, v3 = Oc.removedegen(data, info, _g2, v2)
        for k in g3:
            g3[k] *= fcgains[k]
        
        #Test that lincal actually converged
        np.testing.assert_array_less(m2['iter'], 50*np.ones_like(m2['iter']))

        #Test that chisq is 0 after lincal in the gains/vis/data and in the meta
        chiSqBeforeRemoveDegen = self.chisq(data,g2,v2,reds)
        np.testing.assert_almost_equal(chiSqBeforeRemoveDegen, np.zeros_like(chiSqBeforeRemoveDegen), decimal=10)
        np.testing.assert_almost_equal(m2['chisq'], np.zeros_like(m2['chisq']), decimal=10)

        #Test that chisq is 0 after lincal and remove degen
        chiSqAfterRemoveDegen = self.chisq(data,g3,v3,reds)
        np.testing.assert_almost_equal(chiSqAfterRemoveDegen, np.zeros_like(chiSqAfterRemoveDegen), decimal=10)

        #Test that the solution has degeneracies removed properly
        Rgains =  np.array([np.append(ai,1) for ai in info.antloc]) 
        Mgains = np.linalg.pinv(Rgains.T.dot(Rgains)).dot(Rgains.T) 
        ntimes, nfreqs = g3.values()[0].shape
        for t in range(ntimes):
            for f in range(nfreqs):
                gainSols = np.array([g3[ai][t,f]/fcgains[ai][t,f] for ai in info.subsetant])
                np.testing.assert_almost_equal(np.mean(np.abs(gainSols)), 1.0, decimal=5)
                np.testing.assert_almost_equal(Mgains.dot(np.angle(gainSols)), [0.0,0.0,0.0,0.0], decimal=5)

        #Test that the correct gains and visibilities are recovered
        for ai in info.subsetant:
            np.testing.assert_array_almost_equal(g3[ai], gain_true[ai], decimal=5)
        for bl in vis_true.keys():
            np.testing.assert_array_almost_equal(v3[bl], vis_true[bl], decimal=5)




class TestRedCal(unittest.TestCase):
    #def setUp(self):
    #    self.i = Oi.RedundantInfo()
    #    self.i.fromfile_txt(redinfo_psa32)
    def tearDown(self):
        if os.path.exists(infotestpath): os.remove(infotestpath)

    def test_large_info_IO(self):
        calibrator = Oc.RedundantCalibrator(150)
        calibrator.compute_redundantinfo()
        calibrator.write_redundantinfo(infotestpath, verbose=VERBOSE)
        info2 = Oi.RedundantInfo(filename=infotestpath)
        self.assertEqual(calibrator.Info.nAntenna, info2.nAntenna)
        self.assertEqual(calibrator.Info.nBaseline, info2.nBaseline)
        self.assertEqual(calibrator.Info.get_reds(), info2.get_reds())
        os.remove(infotestpath)

    def test_logcal(self):
        #check that logcal give 0 chi2 for all 20 testinfos
        diff = np.zeros(20)
        for index in range(20):
            arrayinfopath = os.path.dirname(os.path.realpath(__file__)) + '/testinfo/test'+str(index+1)+'_array_info.txt'
            calibrator = Oc.RedundantCalibrator(56)
            calibrator.compute_redundantinfo(arrayinfopath, tol=.1)
            if False: # XXX this was to migrate files so they include bl order w/ data
                _info = calibrator.Info # XXX needs to have been initialized the old way (w/o reds)
                datapath = os.path.dirname(os.path.realpath(__file__)) + '/testinfo/test'+str(index+1)+'_data.txt'
                with open(datapath) as f:
                    rawinfo = [[float(x) for x in line.split()] for line in f]
                data = np.array([i[0] + 1.0j*i[1] for i in rawinfo[:-1]],dtype = 'complex64') #last element is empty
                data = data.reshape((1,1,len(data)))
                dd = _info.make_dd(data)
                np.savez('calib_test_data_%02d.npz' % index, bls=np.array(dd.keys()), vis=np.array(dd.values()))
            info = calibrator.Info
            npz = np.load(testdata % index)
            bls = [tuple(bl) for bl in npz['bls']]
            dd = dict(zip(bls, npz['vis']))
            data = np.array([dd[bl] if dd.has_key(bl) else dd[bl[::-1]].conj() for bl in info.bl_order()]).transpose((1,2,0))
            #data = info.order_data(dd) # order_data not native to info.RedundantInfo.
            ####do calibration################
            calibrator.removeDegeneracy = True
            calibrator.removeAdditive = False
            calibrator.keepData = True
            calibrator.keepCalpar = True
            calibrator.convergePercent = 1e-5
            calibrator.maxIteration = 50
            calibrator.stepSize = .2
            calibrator.computeUBLFit = True

            calibrator.logcal(data, np.zeros_like(data), verbose=VERBOSE)
            log = np.copy(calibrator.rawCalpar)
            ampcal = log[0,0,3:info['nAntenna']+3]
            phasecal = log[0,0,info['nAntenna']+3: info['nAntenna']*2+3]
            calpar = 10**(ampcal)*np.exp(1.0j*phasecal)
            start_ubl = 3 + 2*info['nAntenna']
            end_ubl = start_ubl + 2*len(info.ublcount)
            ublfit = log[0,0,start_ubl:end_ubl:2]+1.0j*log[0,0,start_ubl+1:end_ubl+1:2]
            ####import real calibration parameter
            calparpath = os.path.dirname(os.path.realpath(__file__)) + '/testinfo/test'+str(index+1)+'_calpar.txt'
            with open(calparpath) as f:
                rawinfo = [[float(x) for x in line.split()] for line in f]
            temp = np.array(rawinfo[:-1])
            correctcalpar = (np.array(temp[:,0]) + 1.0j*np.array(temp[:,1]))[info['subsetant']]
            ###compare calpar with correct calpar
            overallfactor = np.real(np.mean(ublfit))**0.5
            diffnorm = la.norm(calpar*overallfactor - correctcalpar)
            self.assertAlmostEqual(diffnorm, 0, 4)

    def test_lincal(self):
        fileindex = 3      #use the 3rd file to do the test, can also change this to any number from 1 to 20
        length = 100
        loglist = np.zeros(length)
        linlist = np.zeros(length)

        ####import arrayinfo################
        arrayinfopath = os.path.dirname(os.path.realpath(__file__)) + '/testinfo/test'+str(fileindex)+'_array_info.txt'
        nant = 56
        calibrator = Oc.RedundantCalibrator(nant)
        calibrator.compute_redundantinfo(arrayinfopath)
        info = calibrator.Info
        npz = np.load(testdata % (fileindex-1))
        bls = [tuple(bl) for bl in npz['bls']]
        dd = dict(zip(bls, npz['vis']))
        data = np.array([dd[bl] if dd.has_key(bl) else dd[bl[::-1]].conj() for bl in info.bl_order()]).transpose((1,2,0))
        #data = info.order_data(dd)

        ####Config parameters###################################
        needrawcal = True #if true, (generally true for raw data) you need to take care of having raw calibration parameters in float32 binary format freq x nant
        std = 0.1

        ####do calibration################
        calibrator.removeDegeneracy = True
        calibrator.removeAdditive = False
        calibrator.keepData = True
        calibrator.keepCalpar = True
        calibrator.convergePercent = 1e-5
        calibrator.maxIteration = 50
        calibrator.stepSize = .2
        calibrator.computeUBLFit = True

        for i in range(length):
            noise = (np.random.normal(scale = std, size = data.shape) + 1.0j*np.random.normal(scale = std, size = data.shape)).astype('complex64')
            ndata = data + noise
            calibrator.logcal(ndata, np.zeros_like(ndata), verbose=VERBOSE)
            calibrator.lincal(ndata, np.zeros_like(ndata), verbose=VERBOSE)

            linchi2 = (calibrator.rawCalpar[0,0,2]/(calibrator.Info['At'].shape[1] - calibrator.Info['At'].shape[0])/(2*std**2))**0.5
            logchi2 = (calibrator.rawCalpar[0,0,1]/(calibrator.Info['At'].shape[1] - calibrator.Info['At'].shape[0])/(2*std**2))**0.5
            linlist[i] = linchi2
            loglist[i] = logchi2

            # The sum of the chi^2's for all antennas should be twice the
            # calibration chi^2. Omnical uses single precision floats in C, so
            # the ratio of that sum to chi^2 must be equal to 2 to 5 decimal
            # places. That should hold in all cases.
            chi2all = calibrator.rawCalpar[0,0,2]
            chi2ant = calibrator.rawCalpar[0,0,3+2*(info.nAntenna + len(info.ublcount)):]
            np.testing.assert_almost_equal(np.sum(chi2ant)/chi2all-2, 0, 5)

        self.assertTrue(abs(np.mean(linlist)-1.0) < 0.01)        #check that chi2 of lincal is close enough to 1
        self.assertTrue(np.mean(linlist) < np.mean(loglist))     #chick that chi2 of lincal is smaller than chi2 of logcal

if __name__ == '__main__':
    unittest.main()
