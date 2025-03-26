import numpy as np
import matplotlib.pylab as plt
import pylhef

import sys

#p = [100.,100.,100.]
#m = 173.

################################################################################
def lorentz_boost(pmom, rest_frame):

    p = rest_frame
    c = 1

    pmag = np.sqrt(p[1]**2 + p[2]**2 + p[3]**2)
    #E = np.sqrt((pmag*c)**2 + (m*c**2)**2)
    E = p[0]

    beta = pmag/E
    betaX = p[1]/E
    betaY = p[2]/E
    betaZ = p[3]/E

    gamma = np.sqrt(1 / (1-beta**2))

    x = ((gamma-1) * betaX) / beta**2
    y = ((gamma-1) * betaY) / beta**2
    z = ((gamma-1) * betaZ) / beta**2

    L = np.matrix([[gamma,      -gamma*betaX, -gamma*betaY, -gamma*betaZ],
                [-gamma*betaX,  1 + x*betaX,      x*betaY,      x*betaZ],
                [-gamma*betaY,      y*betaX,  1 + y*betaY,      y*betaZ],
                [-gamma*betaZ,      z*betaX,      z*betaY,  1 + z*betaZ]])


    # Moving particle that will be boosted
    #vector = np.matrix([E,p[1],p[1],p[2]])
    vector = np.matrix(pmom)

    boosted_vec = L*np.matrix.transpose(vector)

    return boosted_vec
################################################################################
#pmom = [200, 90,50,50]
#rest_frame = pmom
#print(lorentz_boost(pmom,rest_frame))
#exit()





lhefile = pylhef.read(sys.argv[1])

ebnv = []
esm = []

for count,event in enumerate(lhefile.events):

    if count%1000==0:
        print(count)
        #if count>1000:
            #break

    particles = event.particles

    #print("--------")
    for particle in particles:
        pid = np.abs(particle.id)
        #print(pid)
        #if pid>=11 and pid<=18:
        if pid==13:
            first,last = particle.first_mother,particle.last_mother
            if first==last and np.abs(particles[first-1].id)==6:
                p = particle.p
                Mt = particles[first-1].mass
                topp = particles[first-1].p
                boosted = lorentz_boost(p,topp)
                Ee = boosted.item(0,0)
                ebnv.append(2*Ee/Mt)
            elif first==last and np.abs(particles[first-1].id)==24:
                #print("HERE")
                p = particle.p
                W = particles[first-1]
                Wfirst = W.first_mother
                top = particles[Wfirst-1]
                topp = top.p
                Mt = top.mass
                boosted = lorentz_boost(p,topp)
                Ee = boosted.item(0,0)
                esm.append(2*Ee/Mt)



print(len(ebnv))
print(len(esm))
plt.figure()
plt.hist(ebnv,bins=50,range=(0,1),linewidth=3,fill=False,histtype='step',label='BNV',normed=True,color='r')
plt.hist(esm,bins=50,range=(0,1),linewidth=3,fill=False,histtype='step',label='SM',normed=True,color='b')
plt.xlabel(r'$2E_{\ell}/m_t$',fontsize=18)
plt.legend(loc='upper left')
plt.tight_layout()
plt.savefig('Fig1_from_paper.png')
plt.show()
