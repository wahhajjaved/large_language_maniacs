

def KAUSTColor(color):
    # this returns the colors of KAUST logo
    # input parameter the name of the color
    # blue, orange, green, yellow, grey
    chart = {'blue': (46,141,150), 'orange': (231,113,33), 'green': (117,199,25), 'yellow': (246,183,31), 'grey': (128,118,111)}
    try:
        rv = chart[color]
    except KeyError:
        rv = chart['grey']
    return [a/255.0 for a in rv]



    
