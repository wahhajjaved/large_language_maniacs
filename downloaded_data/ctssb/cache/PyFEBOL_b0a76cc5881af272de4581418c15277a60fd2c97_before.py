'''
filter.py

Cedrick Argueta
cdrckrgt@stanford.edu

filter stuff
'''
import numpy as np
import scipy.stats as stats

from fast_histogram import histogram2d as fhist2d

class Filter(object):
    def __init__(self):
        raise Exception("Please instantitate a specific filter!")

    def update(self):
        raise Exception("Please instantitate a specific filter!")

    def centroid(self):
        raise Exception("Please instantitate a specific filter!")

    def covariance(self):
        raise Exception("Please instantitate a specific filter!")

    def entropy(self):
        raise Exception("Please instantitate a specific filter!")

    def reset(self):
        raise Exception("Please instantitate a specific filter!")

    def getBelief(self):
        raise Exception("Please instantitate a specific filter!")

    def maxEigenvalue(self):
        raise Exception("Please instantitate a specific filter!")

    def maxProbBucket(self):
        raise Exception("Please instantitate a specific filter!")


class DiscreteFilter(Filter):
    def __init__(self, domain, buckets, sensor):
        self.domain = domain
        self.df = np.ones((buckets, buckets)) / (buckets ** 2) # buckets is num buckets per side
        self.sensor = sensor
        self.cellSize = domain.length / buckets
        self.buckets = buckets

    def getBelief(self):
        return self.df[np.newaxis, :, :] # adding a channel dimension

    def update(self, pose, obs):
        '''
        updates filter with new information (obs)
        '''

        i, j = np.where(self.df > 0) # i is for rows, j is for columns
        x = (j + 0.5) * self.cellSize
        y = (i + 0.5) * self.cellSize
        
        dfUpdate = np.zeros(self.df.shape)
        dfUpdate[i, j] = self.sensor.prob((x, y), pose, obs)
        self.df *= dfUpdate
        self.df /= np.sum(self.df)

    def centroid(self):
        centers = (np.arange(self.buckets) + 0.5) * self.cellSize

        mu_x = np.sum(np.dot(self.df.T, centers))
        mu_y = np.sum(np.dot(self.df, centers))

        return mu_x, mu_y
        
    def covariance(self):
        centers = (np.arange(self.buckets) + 0.5) * self.cellSize

        mu_x = np.sum(np.dot(self.df.T, centers))
        mu_y = np.sum(np.dot(self.df, centers))
        c_xx = np.sum(np.dot(self.df.T, centers ** 2)) - mu_x ** 2
        c_yy = np.sum(np.dot(self.df, centers ** 2)) - mu_y ** 2
        c_xy = np.sum(self.df.T * np.outer(centers, centers)) - mu_x * mu_y

        m = np.array([[c_xx+1e-15, c_xy], [c_xy, c_yy+1e-15]])
        return m

    def entropy(self):
        return stats.entropy(self.df.flatten())

    def maxEigenvalue(self):
        w, v = np.linalg.eig(self.covariance())
        return np.max(w)
    
    def maxProbBucket(self):
        return self.getBelief().max()

class ParticleFilter(Filter):
    '''
    simple particle filter with simple resampling, performed according to effective N updates
    '''
    def __init__(self, domain, buckets, sensor, maxStep, nb_particles):
        self.domain = domain
        self.buckets = buckets
        self.sensor = sensor
        self.maxStep = maxStep
        self.cellSize = domain.length / buckets
        self.nb_particles = nb_particles
        self.x_particles = np.random.uniform(0, domain.length, self.nb_particles)
        self.dx_particles = np.random.uniform(-self.maxStep, self.maxStep, self.nb_particles)
        self.y_particles = np.random.uniform(0, domain.length, self.nb_particles)
        self.dy_particles = np.random.uniform(-self.maxStep, self.maxStep, self.nb_particles)
        self.weights = np.ones(self.nb_particles) / self.nb_particles
        self.belief = np.ones((self.buckets, self.buckets)) / (self.buckets ** 2)
        self.belief = self.belief[np.newaxis, :, :]
        self.transformedBelief = np.ones((self.buckets, self.buckets)) / (self.buckets ** 2)
        self.transformedBelief = self.transformedBelief[np.newaxis, :, :]

    def getTransformedBelief(self):
        '''
        returns belief matrix centered on the drone pose and rotated according to pose
        '''
        return self.transformedBelief

    def _udpateTransformedBelief(self, pose):
        origin_length = 0.5 * self.domain.length
        x, y, heading = pose
        # get particles relative to seeker position
        x_relative = self.x_particles - x
        y_relative = self.y_particles - y

        # rotate particles according to seeker heading
        theta = np.radians(heading)
        c, s = np.cos(theta), np.sin(theta)
        R = np.array([[c, -s], [s, c]])
        x_relative, y_relative = np.dot(R, np.asarray([x_relative, y_relative]))

        # discretize particles into matrix for neural net
        x_relative, y_relative =  np.clip(x_relative, 0, self.domain.length), np.clip(y_relative, 0, self.domain.length)
        f = fhist2d(x_relative, y_relative, bins=self.buckets, range=[[0, self.domain.length + 1], [0, self.domain.length + 1]], weights=self.weights)
        f = f[np.newaxis, :, :] # add channel dimension
        assert np.all(np.isfinite(f)), 'belief matrix contains nan values. filter: {}, weights: {}'.format(f, self.weights)
        if np.all(f == 0):
            print('all entries in belief matrix 0! this happens when belief is concentrated outside the search domain')
            f = (np.ones((self.buckets, self.buckets)) / (self.buckets ** 2))[np.newaxis, :, :]
            self.weights = np.ones(self.nb_particles) / self.nb_particles
        self.transformedBelief = f


    def getBelief(self):
        '''
        returns the true belief, centered at (half domain, half domain)
        '''
        return self.belief

    def _updateBelief(self):
        # discretize belief for input into neural net
        # particles will sometimes move past the end of the search domain.
        # this poses an issue for us: if all particles move out of the domain,
        # the belief we have of the domain is 0 everywhere.
        # even if that doesn't happen, belief won't sum to one if any particle is
        # outside the search domain.
        # for belief updates, we will clip the particles to the edge of the domain, 
        # regardless of where the particle actually is.
        x_particles, y_particles =  np.clip(self.x_particles, 0, self.domain.length), np.clip(self.y_particles, 0, self.domain.length)
        f = fhist2d(x_particles, y_particles, bins=self.buckets, range=[[0, self.domain.length + 1], [0, self.domain.length + 1]], weights=self.weights)
        f = f[np.newaxis, :, :] # add channel dimension
        assert np.all(np.isfinite(f)), 'belief matrix contains nan values. filter: {}, weights: {}'.format(f, self.weights)
        if np.all(f == 0):
            print('all entries in belief matrix 0! this happens when belief is concentrated outside the search domain')
            f = (np.ones((self.buckets, self.buckets)) / (self.buckets ** 2))[np.newaxis, :, :]
            self.weights = np.ones(self.nb_particles) / self.nb_particles
        self.belief = f

    def _predictParticles(self, nb_act_repeat=1):
        '''
        during particle filter updates, we need a certain amount of variance
        to combat particle deprivation. how much noise is good?
        '''
        self.dx_particles += np.random.randn(self.nb_particles) * 0.05
        self.dy_particles += np.random.randn(self.nb_particles) * 0.05

        self.x_particles += nb_act_repeat * self.dx_particles + np.random.randn(self.nb_particles) * 1.0 # noisy prediction
        self.y_particles += nb_act_repeat * self.dy_particles + np.random.randn(self.nb_particles) * 1.0
 
        # self.x_particles = np.clip(self.x_particles, 0, self.domain.length)
        # self.y_particles = np.clip(self.y_particles, 0, self.domain.length)

        self.dx_particles = np.clip(self.dx_particles, -self.maxStep, self.maxStep)
        self.dy_particles = np.clip(self.dy_particles, -self.maxStep, self.maxStep)
        
    def _updateParticles(self, pose, obs):
        prob = self.sensor.prob((self.x_particles, self.y_particles), pose, obs)
        self.weights *= prob
        self.weights = np.nan_to_num(self.weights) # we get problems with nan with larger numbers of particles
        self.weights += 1.e-300 # when numbers get too small, they become nan. then we convert nan to 0 and add a small number
        self.weights /= self.weights.sum()
        # if np.all(self.weights == 0):
        #     print('all weights 0! x, y: {}, {}'.format(self.x_particles, self.y_particles))
        #     self.weights = np.ones(self.nb_particles) / self.nb_particles
        assert not np.all(self.weights == 0), 'all weights 0! x, y: {}, {}'.format(self.x_particles, self.y_particles)
        assert np.all(np.isfinite(self.weights)), 'weights contains nan values: weights: {}, prob: {}'.format(self.weights, prob)

    def _stratifiedResample(self):
        positions = (np.random.rand(self.nb_particles) + range(self.nb_particles)) / self.nb_particles
        cumsum = np.cumsum(self.weights)
        idxs = np.zeros(self.nb_particles, dtype=int)
        i, j = 0, 0
        while i < self.nb_particles: # for all subdivisions
            # short circuit j, since sometimes our floating points get too close to 1.0
            if (j == self.nb_particles - 1) or (positions[i] < cumsum[j]): 
                idxs[i] = j # choose this particle in subdivision
                i += 1 # move index to next subdivision
            else: # move onto next particle in subdivision
                j += 1
        self.x_particles = self.x_particles[idxs]
        self.y_particles = self.y_particles[idxs]
        self.dx_particles = self.dx_particles[idxs]
        self.dy_particles = self.dy_particles[idxs]
        self.weights = np.ones(self.nb_particles) / self.nb_particles

    def _resampleParticles(self):
        # if ((1. / np.sum(np.square(self.weights))) < (self.nb_particles / 2)):
        self._stratifiedResample()

    def update(self, pose, obs, nb_act_repeat=1):
        self._predictParticles(nb_act_repeat)
        self._updateParticles(pose, obs)
        self._resampleParticles()
        self._updateBelief()
        self._updateTransformedBelief(pose)

    def entropy(self):
        f = self.getBelief()
        return stats.entropy(f.flatten()) 

    def centroid(self):
        mean_x = np.average(self.x_particles, weights=self.weights)
        mean_y = np.average(self.y_particles, weights=self.weights)
        return mean_x, mean_y
    
    def mean_velocity(self):
        mean_dx = np.average(self.dx_particles, weights=self.weights)
        mean_dy = np.average(self.dy_particles, weights=self.weights)
        return mean_dx, mean_dy

    def covariance(self):
        f = self.getBelief().squeeze(0)
        centers = (np.arange(self.buckets) + 0.5) * self.cellSize

        mu_x = np.sum(np.dot(f.T, centers))
        mu_y = np.sum(np.dot(f, centers))
        c_xx = np.sum(np.dot(f.T, centers ** 2)) - mu_x ** 2
        c_yy = np.sum(np.dot(f, centers ** 2)) - mu_y ** 2
        c_xy = np.sum(f.T * np.outer(centers, centers)) - mu_x * mu_y

        m = np.array([[c_xx+1e-15, c_xy], [c_xy, c_yy+1e-15]])
        return m
    
    def maxEigenvalue(self):
        w, v = np.linalg.eig(self.covariance())
        return np.max(w)
    
    def maxProbBucket(self):
        return self.getBelief().max()
