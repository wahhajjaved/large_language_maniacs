import numpy as np

from linearConstraints import bspline
from linearConstraints import piecewiseBilinearAxial
from linearConstraints import baffles
from linearConstraints import cleanupConstraintMatrix

from domains import LinIneqDomain
from domains import UniformDomain
from domains import LogNormalDomain
from domains import ComboDomain

def buildDesignDomain(output='verbose'):

    lb_perc = 0.8
    ub_perc = 1.2

    # ============================================================================
    # Specify design variables
    # ============================================================================
    # The choice of design variables below has 4 control points which control the 
    # nozzle throat. Control points are duplicated at the throat, and there is one
    # on either side of the throat which helps give a smooth (and not pointed)
    # throat. The centerline has a throat as well which coincides with the major
    # axis throat. There is no throat for the minor axis. Instead, the minor axis
    # monotonically decreases.

    # ============================================================================
    # Wall design variables for free inlet
    # ============================================================================
    # # Centerline
    # WALL_COEFS1 = (0.0000, 0.0000, 0.3000, 0.5750, 1.1477, 1.1500, 1.1500, 1.1523, 1.7262, 2.0000, 2.3000, 2.3000, 
    #                0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000)
    # WALL_COEFS1_DV= (1,    1,      2,      3,      4,      5,      5,      6,      7,      0,      0,      0,     
    #                  8,    8,      8,      9,      10,     10,     10,     10,     11,     0,      0,      0)
    
    # # Major Axis
    # WALL_COEFS2= (0.0000, 0.0000, 0.3000, 0.5000, 0.7000, 0.9000, 1.1477, 1.1500, 
    #               1.1500, 1.1523, 1.4000, 1.6500, 1.9000, 2.1000, 2.3000, 2.3000, 
    #               0.3255, 0.3255, 0.3255, 0.3195, 0.3046, 0.2971, 0.2956, 0.2956, 
    #               0.2956, 0.2956, 0.3065, 0.3283, 0.3611, 0.4211, 0.4265, 0.4265)
    # WALL_COEFS2_DV= (1,   1,      2,      12,     13,     14,     15,     5,
    #                  5,   16,     17,     18,     19,     20,     0,      0,
    #                  0,   0,      0,      21,     22,     23,     24,     24,
    #                  24,  24,     25,     26,     27,     28,     0,      0)
                     
    # # Minor axis
    # WALL_COEFS3= (0.0000, 0.0000, 0.3000, 0.5500, 0.9000, 
    #               1.1500, 1.8000, 2.1000, 2.3000, 2.3000, 
    #               0.3255, 0.3255, 0.3255, 0.3195, 0.2956, 
    #               0.2750, 0.2338, 0.2167, 0.2133, 0.2133)
    # WALL_COEFS3_DV= (1,   1,      2,      29,     30,
    #                  31,  32,     33,     0,      0, 
    #                  0,   0,      0,      34,     35,  
    #                  36,  37,     38,     0,      0)

    # ============================================================================
    # Wall design variables for fixed inlet
    # ============================================================================
    # Centerline
    WALL_COEFS1 = (0.0000,   0.0000,   0.3000,   0.5750, 1.1477, 1.1500, 1.1500, 1.1523, 1.7262, 2.0000, 2.33702, 2.33702, 
                   0.099908, 0.099908, 0.099908, 0.12, 0.14, 0.14, 0.14, 0.14, 0.17, 0.19, 0.19, 0.19)
    WALL_COEFS1_DV= (0,    0,      0,      1,      2,      3,      3,      4,      5,      0,      0,      0,     
                     0,    0,      0,      6,      7,      7,      7,      7,      8,      0,      0,      0)
    
    # Major Axis
    WALL_COEFS2= (0.0000,   0.0000,   0.3000,   0.5000, 0.7000, 0.9000, 1.1477, 1.1500, 
                  1.1500,   1.1523,   1.4000,   1.6500, 1.9000, 2.1000, 2.33702, 2.33702, 
                  0.439461, 0.439461, 0.439461, 0.3195, 0.3046, 0.2971, 0.2956, 0.2956, 
                  0.2956, 0.2956, 0.3065, 0.3283, 0.3611, 0.4211, 0.92, 0.92)
    WALL_COEFS2_DV= (0,   0,      0,      9,     10,     11,     12,     3,
                     3,   13,     14,     15,     16,     17,     0,      0,
                     0,   0,      0,      18,     19,     20,     21,     21,
                     21,  21,     22,     23,     24,     25,     0,      0)
                     
    # Minor axis
    WALL_COEFS3= (0.0000,   0.0000,   0.3000,   0.5500,  0.9000, 
                  1.1500,   1.8000,   2.1000,   2.33702, 2.33702, 
                  0.439461, 0.439461, 0.439461, 0.3195,  0.2956, 
                  0.2750, 0.2338, 0.2167, 0.24, 0.24)
    WALL_COEFS3_DV= (0,   0,      0,      26,     27,
                     28,  29,     30,     0,      0, 
                     0,   0,      0,      31,     32,  
                     33,  34,     35,     0,      0)    
                     
    # Thermal layer                 
    LAYER1_THICKNESS_LOCATIONS= (0, 0.3, 0.6, 1.0)
    LAYER1_THICKNESS_ANGLES= (0, 90, 180, 270)
    LAYER1_THICKNESS_VALUES= (0.03, 0.03, 0.03, 0.03, 0.03, 0.03, 0.03, 0.03, 0.03, 
                              0.03, 0.03, 0.03, 0.03, 0.03, 0.03, 0.03)
    LAYER1_DV= (0, 1, 2, 0, 0, 0, 0, 0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 
                15, 16, 17, 18)
                
    # Inner load layer
    LAYER3_THICKNESS_LOCATIONS= (0, 0.3, 0.6, 1.0)
    LAYER3_THICKNESS_ANGLES= (0, 90, 180, 270)
    LAYER3_THICKNESS_VALUES= (0.002, 0.002, 0.002, 0.002, 0.002, 0.002, 0.002, 
                              0.002, 0.002, 0.002, 0.002, 0.002, 0.002, 0.002, 
                              0.002, 0.002)
    LAYER3_DV= (0, 1, 2, 0, 0, 0, 0, 0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 
                14, 15, 16, 17, 18)
                
    # Middle load layer
    LAYER4_THICKNESS_LOCATIONS= (0, 0.3, 0.6, 1.0)
    LAYER4_THICKNESS_ANGLES= (0, 90, 180, 270)
    LAYER4_THICKNESS_VALUES= (0.013, 0.013, 0.013, 0.013, 0.013, 0.013, 0.013, 
                              0.013, 0.013, 0.013, 0.013, 0.013, 0.013, 0.013, 
                              0.013, 0.013)
    LAYER4_DV= (0, 1, 2, 0, 0, 0, 0, 0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 
                14, 15, 16, 17, 18)
    
    # Outer load layer
    LAYER5_THICKNESS_LOCATIONS= (0, 0.3, 0.6, 1.0)
    LAYER5_THICKNESS_ANGLES= (0, 90, 180, 270)
    LAYER5_THICKNESS_VALUES= (0.002, 0.002, 0.002, 0.002, 0.002, 0.002, 0.002, 
                              0.002, 0.002, 0.002, 0.002, 0.002, 0.002, 0.002, 
                              0.002, 0.002)
    LAYER5_DV= (0, 1, 2, 0, 0, 0, 0, 0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 
                14, 15, 16, 17, 18)
                                                 
    # Baffles
    BAFFLES_LOCATION= (0, 0.2, 0.4, 0.6, 0.8)
    BAFFLES_THICKNESS= (0.01, 0.01, 0.01, 0.01, 0.01)
    BAFFLES_TRANSVERSE_EXTENT= (1.1)
    BAFFLES_DV= (0, 1, 2, 3, 4, 5, 6, 7, 8, 9)

    # Top and bottom stringer
    STRINGERS_ANGLES= (90, 270)
    STRINGERS_BREAK_LOCATIONS= (0, 0.2, 0.4, 0.6, 0.8, 1)
    STRINGERS_THICKNESS_VALUES= (0.005, 0.005, 0.005, 0.005, 0.005, 0.005,
                                 0.005, 0.005, 0.005, 0.005, 0.005, 0.005)
    STRINGERS_DV= (0, 1, 2, 3, 4, 0, 0, 0, 5, 6, 7, 8, 9, 10, 11, 12, 13, 
                   14, 15, 16)
        
    # ============================================================================
    # Build constraints & domain information
    # ============================================================================
    
    # -------------------------------- WALL --------------------------------------
    # Centerline constraints
    # For sampling purposes, we require overlap between the slope ranges on either side of the throat
    A1, b1 = bspline(WALL_COEFS1, WALL_COEFS1_DV, 5, (-0.2,0.01,-0.01,0.3), 
                     xLimits=[None,2.3], delta=0.2, output=output)
    # Major axis constraints
    A2, b2 = bspline(WALL_COEFS2, WALL_COEFS2_DV, 7, (-0.4,0.0,-0.05,1.2), 
                     xLimits=[None,2.3], delta=0.15, throatIsLowest=1, 
                     minThroat=0.2, output=output)
    # Minor axis constraints
    # Likewise for sampling here, we set max slope to 0.01, in reality this could be 0
    # For some reason the sampling does not deal well with 0 slopes
    A3, b3 = bspline(WALL_COEFS3, WALL_COEFS3_DV, 0, (-0.3,0.01,-0.3,0.01),
                     xLimits=[None,2.3], delta=0.2, minThroat=0.2133, output=output)                 
    Awall, bwall = cleanupConstraintMatrix(Alist=[A1,A2,A3],blist=[b1,b2,b3])
    inner_wall_domain = LinIneqDomain(Awall, np.squeeze(bwall))
    # Use x_wall, lb and ub below for free inlet:
    # x_wall = np.array([0., 2.11625813e-01,  4.33456653e-01,
    #      6.40008709e-01,   6.94218975e-01,   7.47699639e-01,
    #      9.63367938e-01,   0.,               0.,
    #      0.,               0.,               3.19606406e-01,
    #      4.25187066e-01,   5.26621220e-01,   6.43854797e-01,
    #      7.45326057e-01,   8.49338274e-01,   9.66198899e-01,
    #      1.06819478e+00,   1.18163314e+00,   3.25177592e-01,
    #      3.25078539e-01,   2.97088172e-01,   2.56513305e-01,
    #      2.79231344e-01,   3.10313168e-01,   3.51101683e-01,
    #      3.70116145e-01,   4.15313111e-01,   6.23135788e-01,
    #      8.29455873e-01,   1.03225119e+00,   1.24925362e+00,
    #      3.22570448e-01,   3.19918913e-01,   3.01938440e-01,
    #      2.60902178e-01,   2.19374337e-01])    
    # lb = np.hstack((-0.1,-np.inf*np.array(6*[1]),-0.05,-np.inf*np.array(30*[1]))) # centerline can move down 5 cm, back 10 cm
    # ub = np.hstack((0.1,np.inf*np.array(6*[1]),0.05,np.inf*np.array(30*[1]))) # centerline can move up 5 cm, forward 10 cm
    # Use x_wall, lb, and ub below for fixed inlet:
#    x_wall = inner_wall_domain.center; # use center shape as baseline
    x_wall = np.array([0.75221887, 0.99267767, 1.06767767, 1.14267767, 
        1.36767767, 0.02749198, 0.00489532, 0.02764657, 0.46767767, 0.64267767, 
        0.81767767, 0.99267767, 1.14267767, 1.31767767, 1.49267767, 1.66767767, 
        1.84267767, 0.39142936, 0.34835519, 0.30528101, 0.26220684, 0.43315559, 
        0.60410434, 0.75606861, 0.92701736, 0.51767767, 0.74267767, 0.96767767, 
        1.19267767, 1.41767767, 0.41408206, 0.37268283, 0.33128360, 0.28988436, 
        0.24848513])
    # import sys
    # sys.stdout.write('x_wall = np.array([')
    # for i in range(len(x_wall)-1):
    #     sys.stdout.write('%0.8f, ' % x_wall[i])
    # sys.stdout.write('%0.8f])\n' % x_wall[-1])
    # print x_wall
    lb = -np.inf*np.array(35*[1])
    ub = np.inf*np.array(35*[1])
    inner_wall_domain = LinIneqDomain(Awall, np.squeeze(bwall), lb = lb, ub = ub, center = x_wall)
    
    wall_shovel_height_domain = UniformDomain(-0.15, -0.05, center = -0.1)
    wall_shovel_angle_domain = UniformDomain(5., 35., center = 20.)
                     
    # -------------------------------- THERMAL LAYER -----------------------------
    A4, b4 = piecewiseBilinearAxial(LAYER1_THICKNESS_LOCATIONS, LAYER1_THICKNESS_ANGLES,
                               LAYER1_THICKNESS_VALUES, LAYER1_DV, (-0.2,0.2), 
                               xLimits=[0.,1.], deltax=0.15, deltay=60, deltaz=0.01,
                               output=output)                          
    Athermal, bthermal = cleanupConstraintMatrix(Alist=[A4],blist=[b4])
    x_thermal = list(LAYER1_THICKNESS_LOCATIONS) + list(LAYER1_THICKNESS_ANGLES) + \
        list(LAYER1_THICKNESS_VALUES);
    x_thermal = np.array([x_thermal[i] for i in range(len(x_thermal)) if LAYER1_DV[i] != 0 ]);
    lb = np.hstack((lb_perc*x_thermal[0:2], 0.01*np.ones(16)))
    ub = np.hstack((ub_perc*x_thermal[0:2], 0.05*np.ones(16)))
    thermal_layer_domain = LinIneqDomain(Athermal, np.squeeze(bthermal), lb = lb, ub = ub, center = x_thermal)
    
    # -------------------------------- AIR GAP -----------------------------------
    air_gap_domain  = UniformDomain(0.003, 0.01, center = 0.005)
    
    # -------------------------------- INNER LOAD LAYER --------------------------
    A5, b5 = piecewiseBilinearAxial(LAYER3_THICKNESS_LOCATIONS, LAYER3_THICKNESS_ANGLES,
                               LAYER3_THICKNESS_VALUES, LAYER3_DV, (-0.2,0.2), 
                               xLimits=[0.,1.], deltax=0.15, deltay=60, deltaz=0.01,
                               output=output) 
    Aload1, bload1 = cleanupConstraintMatrix(Alist=[A5],blist=[b5])  
    x_load1 = list(LAYER3_THICKNESS_LOCATIONS) + list(LAYER3_THICKNESS_ANGLES) + \
        list(LAYER3_THICKNESS_VALUES);                       
    x_load1 = np.array([x_load1[i] for i in range(len(x_load1)) if LAYER3_DV[i] != 0 ]);  
    lb = np.hstack((lb_perc*x_load1[0:2], 0.001*np.ones(16)))
    ub = np.hstack((ub_perc*x_load1[0:2], 0.006*np.ones(16)))
    load_layer_inner_domain = LinIneqDomain(Aload1, np.squeeze(bload1), lb = lb, ub = ub, center = x_load1)
    
    # -------------------------------- MIDDLE LOAD LAYER -------------------------
    A6, b6 = piecewiseBilinearAxial(LAYER4_THICKNESS_LOCATIONS, LAYER4_THICKNESS_ANGLES,
                               LAYER4_THICKNESS_VALUES, LAYER4_DV, (-0.2,0.2), 
                               xLimits=[0.,1.], deltax=0.15, deltay=60, deltaz=0.01,
                               output=output) 
    Aload2, bload2 = cleanupConstraintMatrix(Alist=[A6],blist=[b6])  
    x_load2 = list(LAYER4_THICKNESS_LOCATIONS) + list(LAYER4_THICKNESS_ANGLES) + \
        list(LAYER4_THICKNESS_VALUES);                       
    x_load2 = np.array([x_load2[i] for i in range(len(x_load2)) if LAYER4_DV[i] != 0 ]);  
    lb = np.hstack((lb_perc*x_load2[0:2], 0.0064*np.ones(16)))
    ub = np.hstack((ub_perc*x_load2[0:2], 0.0159*np.ones(16)))
    load_layer_middle_domain = LinIneqDomain(Aload2, np.squeeze(bload2), lb = lb, ub = ub, center = x_load2)
    
    # -------------------------------- OUTER LOAD LAYER --------------------------
    A7, b7 = piecewiseBilinearAxial(LAYER5_THICKNESS_LOCATIONS, LAYER5_THICKNESS_ANGLES,
                               LAYER5_THICKNESS_VALUES, LAYER5_DV, (-0.2,0.2), 
                               xLimits=[0.,1.], deltax=0.15, deltay=60, deltaz=0.01,
                               output=output) 
    Aload3, bload3 = cleanupConstraintMatrix(Alist=[A7],blist=[b7])  
    x_load3 = list(LAYER5_THICKNESS_LOCATIONS) + list(LAYER5_THICKNESS_ANGLES) + \
        list(LAYER5_THICKNESS_VALUES);                       
    x_load3 = np.array([x_load3[i] for i in range(len(x_load3)) if LAYER5_DV[i] != 0 ]);  
    lb = np.hstack((lb_perc*x_load3[0:2], 0.001*np.ones(16)))
    ub = np.hstack((ub_perc*x_load3[0:2], 0.006*np.ones(16)))
    load_layer_outer_domain = LinIneqDomain(Aload3, np.squeeze(bload3), lb = lb, ub = ub, center = x_load3)
    
    # -------------------------------- STRINGERS ---------------------------------
    A8, b8 = piecewiseBilinearAxial(STRINGERS_BREAK_LOCATIONS, STRINGERS_ANGLES,
                                    STRINGERS_THICKNESS_VALUES, STRINGERS_DV,
                                    (-0.2,0.2), xLimits=[0.,1.], deltax=0.1,
                                    deltay=None,deltaz=None,output=output);
    Astringers, bstringers = cleanupConstraintMatrix(Alist=[A8],blist=[b8])
    x_stringers = list(STRINGERS_BREAK_LOCATIONS) + list(STRINGERS_ANGLES) + \
                  list(STRINGERS_THICKNESS_VALUES);
    x_stringers = np.array([x_stringers[i] for i in range(len(x_stringers)) if STRINGERS_DV[i] != 0]);
    lb = np.hstack((x_stringers[0:4]-0.2, 0.002*np.ones(12)));
    ub = np.hstack((x_stringers[0:4]+0.2, 0.01*np.ones(12)));
    stringers_domain = LinIneqDomain(Astringers, np.squeeze(bstringers), lb = lb, ub = ub, center = x_stringers)
    
    # -------------------------------- BAFFLES -----------------------------------
    A9, b9 = baffles(BAFFLES_LOCATION, BAFFLES_THICKNESS, 
                     BAFFLES_TRANSVERSE_EXTENT, BAFFLES_DV, 0.1, 
                     0.26, output=output);
    Abaffles, bbaffles = cleanupConstraintMatrix(Alist=[A9],blist=[b9]);
    x_baffles = list(BAFFLES_LOCATION) + list(BAFFLES_THICKNESS);
    x_baffles = np.array([x_baffles[i] for i in range(len(x_baffles)) if BAFFLES_DV[i] != 0]);
    lb = np.hstack((x_baffles[0:4]-0.15, 0.0074*np.ones(5)));
    ub = np.hstack((x_baffles[0:4]+0.15, 0.0359*np.ones(5)));
    baffles_domain = LinIneqDomain(Abaffles, np.squeeze(bbaffles), lb = lb, ub = ub, center = x_baffles)
    
    # -------------------------------- FULL CONSTRAINTS --------------------------
    
    design_domain = ComboDomain([inner_wall_domain, wall_shovel_height_domain,
                                 wall_shovel_angle_domain, thermal_layer_domain,
                                 air_gap_domain, load_layer_inner_domain, 
                                 load_layer_middle_domain, 
                                 load_layer_outer_domain, stringers_domain,
                                 baffles_domain])

    return design_domain


def buildRandomDomain(output='verbose', clip = None):

    random_domains = [
    #            CMC_DENSITY, 1,
        LogNormalDomain(7.7803, 0.0182**2, clip = clip),
    #            CMC_ELASTIC_MODULUS, 1,
        LogNormalDomain(4.2047, 0.0551**2, scaling = 1e9, clip = clip),
    #            CMC_POISSON_RATIO, 1,
        UniformDomain(0.23, 0.43),
    #             CMC_THERMAL_CONDUCTIVITY, 1,
        UniformDomain(1.37, 1.45),
    #            CMC_THERMAL_EXPANSION_COEF, 1, 
        UniformDomain(0.228e-6, 0.252e-6),     
    #            CMC_PRINCIPLE_FAILURE_STRAIN, 1, 
        LogNormalDomain(-2.6694, 0.1421**2, scaling=1e-2, clip = clip),
    #            CMC_MAX_SERVICE_TEMPERATURE, 1, 
        UniformDomain(963, 983),
    #
    #
    #            GR-BMI_DENSITY, 1, 
        UniformDomain(1563, 1573), 
    #            GR-BMI_ELASTIC_MODULUS, 2,
        UniformDomain(57e9, 63e9),
        UniformDomain(57e9, 63e9),
    #            GR-BMI_SHEAR_MODULUS, 1, 
        UniformDomain(22.6e9, 24.0e9),
    #            GR-BMI_POISSON_RATIO, 1,
        UniformDomain(0.334, 0.354), 
    #            GR-BMI_MUTUAL_INFLUENCE_COEFS, 2, 
        UniformDomain(-0.1, 0.1),
        UniformDomain(-0.1, 0.1),
    #            GR-BMI_THERMAL_CONDUCTIVITY, 3,
        UniformDomain(3.208, 3.546),
        UniformDomain(3.208, 3.546),
        UniformDomain(3.243, 3.585),
    #            GR-BMI_THERMAL_EXPANSION_COEF, 3,
        UniformDomain(1.16e-6, 1.24e-6), 
        UniformDomain(1.16e-6, 1.24e-6), 
        UniformDomain(-0.04e-6, 0.04e-6),
    #            GR-BMI_LOCAL_FAILURE_STRAIN, 5,
        UniformDomain(0.675e-2, 0.825e-2, center = 0.75e-2),
        UniformDomain(-0.572e-2, -0.494e-2, center = -0.52e-2),
        UniformDomain(0.675e-2, 0.825e-2, center = 0.75e-2),
        UniformDomain(-0.572e-2, -0.494e-2, center = -0.52e-2),
        UniformDomain(0.153e-2, 0.187e-2, center = 0.17e-2),
    #            GR-BMI_MAX_SERVICE_TEMPERATURE, 1,
        UniformDomain(500, 510),
    #
    #
    #            TI-HC_DENSITY, 1, 
        UniformDomain(177.77, 181.37),
    #            TI-HC_ELASTIC_MODULUS, 1, 
        LogNormalDomain(0.6441, 0.0779**2, scaling = 1e9, clip = clip),
    #            TI-HC_POISSON_RATIO, 1, 
        UniformDomain(0.160, 0.196),
    #            TI-HC_THERMAL_CONDUCTIVITY, 1, 
        UniformDomain(0.680, 0.736),
    #            TI-HC_THERMAL_EXPANSION_COEF, 1, 
        UniformDomain(2.88e-6, 3.06e-6),
    #            TI-HC_YIELD_STRESS, 1,
        LogNormalDomain(2.5500, 0.1205**2, scaling = 1e6, clip = clip),
    #            TI-HC_MAX_SERVICE_TEMPERATURE, 1, 
        UniformDomain(745, 765),
    #
    #
    #            AIR_THERMAL_CONDUCTIVITY, 1, 
        UniformDomain(0.0320, 0.0530),
    #            PANEL_YIELD_STRESS, 1, 
        LogNormalDomain(4.3191, 0.1196**2, scaling = 1e6, clip = clip), 
    #            INLET_PSTAG, 1, 
        LogNormalDomain(11.5010, 0.0579**2, clip = clip),
    #            INLET_TSTAG, 1, 
        LogNormalDomain(6.8615, 0.0119**2, clip = clip),
    #            ATM_PRES, 1, 
        LogNormalDomain(9.8386, 0.0323**2, clip = clip),
    #            ATM_TEMP, 1, 
        LogNormalDomain(5.3781, 0.0282**2, clip = clip),
    #            HEAT_XFER_COEF_TO_ENV, 1
        LogNormalDomain(2.5090, 0.2285, clip = clip),
    ]

    return ComboDomain(random_domains)
