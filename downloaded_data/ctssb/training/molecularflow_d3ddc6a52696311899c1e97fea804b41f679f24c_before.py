import time
import numpy as np
from scipy import constants
import random as rnd
from . import elbow
from . import simulation


def runSimulation(A, B, Q=0.01, Z=28, T=300, N=50000, gridSize=0.25, dt=0.0025,
                  pulse=0, steps=0, MAX_COLLISIONS=50, sampleMB=False,
                  filename=None):
    kOverM = constants.k / (Z * constants.value('atomic mass constant'))

    # Define the problem domain
    offset = np.array([-1, -1, -1])
    dimensions = np.array([A + 1, B + 1, 2])
    nArr, grid, nPoints = simulation.cubeGrid(dimensions, offset, gridSize,
                                              steps, dt)

    isSteadyState = steps == 0

    # Number of transmitted particles
    nB = 0
    nRejected = 0

    print('Computing with A={0}, B={1}, N={2}'.format(A, B, N))

    timestamp = time.time()

    for i in range(N):
        p, s = elbow.newParticle(A)
        v = simulation.mbSpeed(T, kOverM, sampleMB)
        remainder = dt * rnd.random()
        currentStep = 0

        for j in range(MAX_COLLISIONS):
            distance, idx, pNew, sNew = elbow.nextCollision(p, s, A, B)
            vNew = simulation.mbSpeed(T, kOverM, sampleMB)

            # Stop if the particle was rejected
            if idx == -1:
                nRejected += 1
                break

            remainder, currentStep = simulation.traceSegment(
                distance, remainder, gridSize, dt, p, s, v, nArr, offset,
                nPoints, steps, currentStep, isSteadyState
            )

            # Break out if the particle has exited
            if idx == 0:
                break
            elif idx == 1:
                nB += 1
                break

            if not isSteadyState and currentStep >= steps:
                break

            p, s, v = pNew, sNew, vNew

    nArr *= Q*dt / (N * gridSize**3 * T * constants.k)
    Pr = nB / (N - nRejected)

    print('Simulation finished in {0} seconds.'
          .format(round(time.time() - timestamp)))

    # For the steady state calculation, the transmission probability is also
    # meaningful
    if isSteadyState:
        print('{0} particles transmitted, {1} particles rejected'
              .format(nB, nRejected))
        print('Transmission probability Pr = ' + str(Pr))

    # Save the computation results to a file
    if filename is not None:
        if isSteadyState:
            # Steady state results to a single file
            np.savez(filename, X=grid[0], Y=grid[1], Z=grid[2], C=nArr[0],
                     Pr=np.array([Pr]))
        else:
            # For time dependent save each timestep into separate files
            for k in range(steps):
                field = np.sum(nArr[max(k + 1 - pulse, 0): k + 1], axis=0)
                np.savez(filename + '.' + str(k),
                         X=grid[0], Y=grid[1], Z=grid[2], C=field)

        print('Results saved to ' + filename)

    return Pr, grid, nArr
