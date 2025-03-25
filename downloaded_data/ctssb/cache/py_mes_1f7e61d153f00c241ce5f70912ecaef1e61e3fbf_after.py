#!/usr/bin/env python

import math

class Mes:
    def __init__(self, bitmap, n):
        self.bitmap = bitmap
        self.n = n
        self.pixels_per_x = (bitmap.width-1)  / (n+1)
        self.pixels_per_y = (bitmap.height-1) / (n+1)
        self.matrix = bitmap.as_matrix()
    
    def bitmap_value(self, x, y):
        '''
        returns bitmap value for real coordinates of pixels (calculated as weighted sum of neighbors) using bilinear interpolation
        '''
        
        a = self.matrix[math.floor(x)  , math.floor(y)  ]
        b = self.matrix[math.floor(x)+1, math.floor(y)  ]
        c = self.matrix[math.floor(x)+1, math.floor(y)+1]
        d = self.matrix[math.floor(x)  , math.floor(y)+1]
        
        dx = x - math.floor(x)
        dy = y - math.floor(y)
        
        return a*(1.0-dx)*(1.0-dy) + b*dx*(1.0-dy) + c*dx*dy + d*(1.0-dx)*dy
    
    def bitmap_derivative_x(self, x, y):
        a = self.matrix[math.floor(x)  , math.floor(y)  ]
        b = self.matrix[math.floor(x)+1, math.floor(y)  ]
        
        return b-a

    def bitmap_derivative_y(self, x, y):
        a = self.matrix[math.floor(x)  , math.floor(y)  ]
        b = self.matrix[math.floor(x)  , math.floor(y)+1]
        
        return b-a
        
    
    def ij_to_abcd(self, i,j):
        return [self.pixels_per_x*i,self.pixels_per_x*(i+1),self.pixels_per_y*j,self.pixels_per_y*(j+1)]
        
