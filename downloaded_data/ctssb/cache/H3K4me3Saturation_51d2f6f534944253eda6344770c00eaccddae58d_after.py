import numpy as np
import os
import csv
import matplotlib.pyplot as plt


def genomeSize(path="./hg19_chr_sizes.txt"):
    genome = {}

    file = open(path, "r")
    for line in file.readlines():
        chrName, chrSize = line.split("\t")
        size = int(chrSize.rstrip())
        if size%10 == 0:
            size = size/10
        else:
            size = size/10+1
        genome[chrName] = np.zeros(size)
    file.close()
    return genome



class H3K4me3Saturation:
    def __init__(self, iterations):
        self.genome = genomeSize()
        self.iterations = iterations
        self.coverage = None
        self.region = None
        self.regionLength = None
        self.numberSample = None

    def initialization(self, sampleNumber):
        self.coverage = [[0] * self.iterations for i in range(sampleNumber)]
        self.region = [[0] * self.iterations for i in range(sampleNumber)]
        self.regionLength = [[0] * self.iterations for i in range(sampleNumber)]

    def saturated(self, path, sampleSequence, iteration, cutoff=0):
        file = open(path, "rb")

        for line in file.readlines():
            info = line.split("\t")
            if info[1] == "start":
                continue
            start = int(info[1])/10
            end = int(info[2])/10
            height = float(info[6])
            chrName = info[0]
            if height >= cutoff:
                if chrName in self.genome:
                    self.genome[chrName][start - 1:end] = 1
        totalCoverage = 0
        totalIsland = 0

        for value in self.genome.values():
            newCoverage = np.sum(value)
            totalCoverage += newCoverage
            if newCoverage == 0:
                continue
            else:
                sign = ((np.roll(value, 1) - value) != 0).astype(int)
                sign[0] = 0
                islandNumber = np.sum(sign)
                if value[0] == 1:
                    islandNumber+=1
                if value[-1] == 1:
                    islandNumber+=1
                totalIsland += islandNumber/2

        if totalIsland == 0:
            avgLength = 0
        else:
            avgLength = totalCoverage*1.0/totalIsland*10

        self.coverage[sampleSequence][iteration] = totalCoverage * 10
        self.region[sampleSequence][iteration] = totalIsland
        self.regionLength[sampleSequence][iteration] = avgLength


    def converge(self, prev, current, convergeCap = 10):
        prevCoverage, prevNumber = prev
        curCoverage, curNumber = current

        converge = 0
        if prevCoverage * 1.1 > curCoverage and (prevNumber * 0.9 < curNumber):
            converge += 1
        else:
            converge = 0

        return converge > convergeCap


    def reset(self):
        self.genome = genomeSize()


    def saveRefMap(self, cutoff):
        refmap = {}
        for chr, vector in self.genome.items():
            if vector[0] == 1:
                vector = np.insert(vector, 0, 0)
            if vector[-1] == 1:
                vector = np.append(vector, 0)

            # sign change mark the start of the peak and the end to the peak, the end mark is exclusive
            signchange = ((np.roll(vector, 1) - vector) != 0).astype(int)
            peaksindex = np.where(signchange == 1)[0]

            rowNumber = peaksindex.shape[0] / 2
            colNumber = 2
            peaksindex = peaksindex.reshape((rowNumber, colNumber))

            refmap[chr] = peaksindex

        output = open(str(cutoff) + "_refmap.csv", "w")
        writer = csv.writer(output)
        for chr, index in refmap.items():
            output.write(">" + chr + "\n")
            for i in range(index.shape[0]):
                writer.writerow(index[i, :])
        output.close()


    def trainMap(self, directories, cutoff=0, saveRefMap=True):
        listFiles = os.listdir(directories)

        self.numberSample = len(listFiles)

        self.initialization(self.numberSample)

        n = 0

        while n < self.iterations:
            np.random.shuffle(listFiles)
            seq = 0
            for file in listFiles:
                self.saturated(directories + '/' + file, seq, n, cutoff=cutoff)
                seq += 1

            if saveRefMap and n == 0:
                self.saveRefMap(cutoff)

            self.reset()

            n += 1

        table = np.zeros((self.numberSample, 4))
        table[:, 0] = np.arange(1, self.numberSample + 1)
        table[:, 1] = np.mean(self.coverage, axis=1)
        table[:, 2] = np.mean(self.regionLength, axis=1)
        table[:, 3] = np.mean(self.region, axis=1)

        np.savetxt(str(cutoff) + ".csv", table, delimiter=",")

