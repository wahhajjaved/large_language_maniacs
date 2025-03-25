#!/usr/bin/env python
# -*- coding: utf-8 -*-

import math
import numpy as np
import matplotlib.pyplot as plt

#何分割するか
DIV = 12
#x座標のstep
STEP = 0.01
#出力画像のサイズ（インチ）
SIZE = 9

def main():
    plt.figure(figsize=(SIZE,SIZE))
    x = np.arange(0, DIV + 1, STEP)
    y1 = np.sin(x*math.pi/DIV)
    y2 = -np.sin(x*math.pi/DIV)
    plt.plot(x, y1)
    plt.plot(x, y2)
    ex = DIV/2
    exs = np.array([ex, ex])
    eys = np.array([1, -1])
    etan = np.arctan2(eys, exs)
    er = np.sqrt(exs*exs + eys*eys)
    plt.plot(exs, eys)

    r = np.sqrt(x*x + y1*y1)
    tan1 = np.arctan2(y1, x)
    tan2 = np.arctan2(y2, x)

    for i in range(1, DIV):
        theta1 = tan1 + i*2*math.pi/DIV
        theta2 = tan2 + i*2*math.pi/DIV
        x1rot1 = r * np.cos(theta1)
        y1rot1 = x * np.sin(theta1)
        x2rot1 = r * np.cos(theta2)
        y2rot1 = x * np.sin(theta2)

        etheta = etan + i*2*math.pi/DIV
        erotx = er * np.cos(etheta)
        eroty = er * np.sin(etheta)

        plt.plot(x1rot1, y1rot1)
        plt.plot(x2rot1, y2rot1)
        plt.plot(erotx, eroty)

    plt.axis('scaled')
    plt.show()

if __name__ == '__main__':
    main()
