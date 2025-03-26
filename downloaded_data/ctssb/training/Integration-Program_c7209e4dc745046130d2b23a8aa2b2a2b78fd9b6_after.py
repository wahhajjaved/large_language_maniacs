#Written by: Omar Ali <Omarh90@gmail.com>

def curve(x_mV, el, sen, audit=False):

    """
    3rd and 4th order inverse polynomials generated from CNS Instrument.
    Coefficient ID: 25034055
    
    Calculates concentration of element for respective element peak
    (either C, N, or S) based on peak area, sample weight, and
    calibration correction factor.

    y = a + bx + cx^2 + dx^3 + ex^4, for x >= highconc_lowerlim, and
    y = a + bx + cx^2 + dx^3         for x <  highconc_lowerlim,

    where x = peak area in V*sec, and y = mg element in sample. Note that in 
    order to match the CNS software calculation, this calibration does not use
    the convention of abscissa for concentration, and ordinate for signal.
    
    Note 'a' term corresponds to intercept, and 'e' to 4th order coefficient,
    to stay consistent with CNS software nomenclature.

    ____________________________________________________________________________
    Parameters:
 
     * x_mV: (float) Area under curve in mV*sec. (Note: calibration calculated
           in V*sec, but instrument displays area count in mV*sec.)

     * el: (str) Element of peak selected for integration. Order and timing of peak
           on chart indicates which element (either C, N, or S).  

     * sen: (bool) "Sensitive" or "Insensitive" analysis mode on instrument.
           Typically C is run in sensitive mode, N and S insensitive.

     * audit: (bool) for audit = True, returns calibration parameters for report.

    Returns:
    
     * y: (float) Amount of selected element in sample (in mg), for audit = False

     * cal_audit: (list, len=6) For audit = True, returns calibration information:
           coefficents, calibration range, calibration date, and calibration ID for report.

           * cal_audit[0] = (y,x,el) (float, float, str)
           * cal_audit[1] = (a,b,c,d,e) (float)
           * cal_audit[2] = (upper_range, lower_range, n (polynomial order)) (int)
           * cal_audit[3] = cal_date (str)
           * cal_audit[4] = cal_ID (str)
           * cal_audit[5] = errormessage (str)
     
    """

    #Calibration ranges for high and low concentration calibration curves (quartic and cubic, respectively).
    highconc_upperlim_C, highconc_lowerlim_C = 311355, 6465
    lowconc_upperlim_C, lowconc_lowerlim_C = 6465, 458
    highconc_upperlim_N, highconc_lowerlim_N = 403059, 7779
    lowconc_upperlim_N, lowconc_lowerlim_N = 7779, 795
    highconc_upperlim_S, highconc_lowerlim_S = 164214, 6900
    lowconc_upperlim_S, lowconc_lowerlim_S = 6900, 574

    #Defines coefficients for calibration.
    a, b, c, d, e = 0, 0, 0, 0, 0
    high_lim, low_lim = 0, 0
    cal_date = ''
    cal_ID = 25034055
    errormessage=""

    #Carbon calibration curve:
    if el == 'C':
        if sen == False:
            if x_mV >= highconc_lowerlim_C:
                #Forth order 'Insensitive' calibration coefficients for Carbon.
                a, b, c, d, e = -2.855261*10**-2, 5.950209*10**-1, 2.345126*10**-4, -3.624688*10**-7, 2.083684*10**-10
                high_lim, low_lim = highconc_upperlim_C, highconc_lowerlim_C
                n=4
                if x_mV > highconc_upperlim_C:
                    errormessage = 'Outside of calibration range (C conc. too high).'
            else:
                #Third order 'Insensitive' calibration coefficients for Carbon.
                a, b, c, d = -6.350634*10**-2, 6.753878*10**-1, -3.047112*10**-2, 3.023291*10**-3
                high_lim, low_lim = lowconc_upperlim_C, lowconc_lowerlim_C
                n=3
                if x_mV < lowconc_lowerlim_C:
                    errormessage = 'Outside of calibration range (C conc. too low).'

    #Nitrogen calibration curve:
    if el == 'N':
        if sen == True:
            if x_mV >= highconc_lowerlim_N:
                #Forth order 'Sensitive' calibration coefficients for Nitrogen.
                a, b, c, d, e = 5.367576*10**-2, 1.393439*10**-1,  2.390824*10**-5, -7.546750*10**-8, 1.059858*10**-10
                high_lim, low_lim = highconc_upperlim_N, highconc_lowerlim_N
                n=4
                if x_mV > highconc_upperlim_N:
                    errormessage = 'Outside of calibration range (N conc. too high).'
            else:
                #Third order 'Sensitive' calibration coefficients for Nitrogen.
                a, b, c, d = -1.405304*10**-2, 1.608039*10**-1, -4.025931*10**-3, 2.631854*10**-4
                high_lim, low_lim = lowconc_upperlim_N, lowconc_lowerlim_N
                n=3
                if x_mV < lowconc_lowerlim_N:
                    errormessage = 'Outside of calibration range (N conc. too low).'

    #Sulfur calibration curve:
    if el == 'S':
        if sen == True:
            if x_mV >= highconc_lowerlim_S:
                #Forth order 'Sensitive' calibration coefficients for Sulfur.
                a, b, c, d, e = -3.012942*10**-2, 1.155174*10**-1, -8.512391*10**-5, 3.150013*10**-7, 9.708221*10**-11
                high_lim, low_lim = highconc_upperlim_S, highconc_lowerlim_S
                n=4
                if x_mV > highconc_upperlim_S:
                    errormessage = 'Outside of calibration range (S conc. too high).'
            else:
                #Third order 'Sensitive' calibration coefficients for Nitrogen.
                a, b, c, d = 2.839449*10**-3, 1.093653*10**-1, 1.589169*10**-3, -1.871188*10**-4
                high_lim, low_lim = lowconc_upperlim_S, lowconc_lowerlim_S
                n=3
                if x_mV < lowconc_lowerlim_S:
                    errormessage = 'Outside of calibration range (S conc. too low).'

    #Converts area from mV*sec to V*sec
    x = x_mV/1000 

    #Inverted forth order calibration curve. 3rd order (e.g. e=0) for low concentration results.
    y = a + b*x + c*x**2 + d*x**3 + e*x**4
    if errormessage:
        print(errormessage)
        
    if audit == False:
        return y;
    else:
        cal_audit = list(((y, x, el), (a, b, c, d, e),(high_lim, low_lim, n), (str(cal_date), str(cal_ID)), errormessage))
        return cal_audit;
