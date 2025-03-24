# From an input file, outputs:
# <filenum>_QueueLengthsPerTimestep.txt, with the timestep, the lane number, and the calculated queue length and size.
# <filenum>_QueueLengthAverage.txt, with each lane number, and the average calculated queue length and size over the
#       simulation duration. Timesteps with 0 vehicles are not counted.
#  Appends to QueueLengthTotals.txt the filenumber, followed by average calculated queue length and size.

def leadingInt(s):
    out = 0
    index = 0
    while s[index].isdigit():
        index += 1

    if index == 0:
        return -1
    return s[:index]

def QueueLengthFromPosition(fileName):
    fileNum = leadingInt(fileName)
    laneCount = {}
    laneLengthTotal = {}
    laneSizeTotal = {}

    with open(fileName, 'rt') as inFile, open(fileNum + '_QueueLengthsPerTimestep.txt', 'wt') as queueLengths, open(fileNum + '_QueueLengthsAverage.txt', 'wt') as queueAverages, open('QueueLengthTotals.txt','a') as queueTotals:
        next(inFile)    #Skip header
        curTime = 1.0   #Start on Timestep 1
        lanes = {}  #Dict from lane to list of positions on that lane in each timestep
        for row in inFile:
            if row.strip(): #Skip blank rows
                row = row.split()
                time = float(row[1])
                lane = row[4]
                pos =  float(row[5])
                if time != curTime: #If we've just finished a timestep
                    curTime = time
                    for curLane in lanes:
                        distanceSet = lanes[curLane]    #
                        if len(distanceSet) > 1:    #If the's more than 1 vehicle on the lane
                            distanceSet.sort(reverse=True)  #Order vehicles, [0] being the leader
                            front = 0
                            back = 1
                            while back < len(distanceSet) and distanceSet[front] - distanceSet[back] < 10.0: #While the next vehicle is within 10 meters of its leader
                                front += 1
                                back += 1
                            queueSize = back    #back is the number of vehicles in the queue
                            queueLength = distanceSet[0] - distanceSet[queueSize - 1]
                            queueLengths.write(str(time) + " " + curLane + " " + str(queueLength) + " " + str(queueSize) + "\n")
                        else:
                            queueSize = 1   #if only 1 vehicle on lane, queue size is 1 and length is 0
                            queueLength = 0.0
                        if curLane not in laneCount:    #Check if this lane has been seen yet
                            laneCount[curLane] = 0
                            laneLengthTotal[curLane] = 0.0
                            laneSizeTotal[curLane] = 0
                        laneCount[curLane] += 1         #Add this queue data to the lane's totals
                        laneLengthTotal[curLane] += queueLength
                        laneSizeTotal[curLane] += queueSize

                    lanes = {}  #Clear the lane dict for each timestep

                if lane not in lanes:
                    lanes[lane] = []
                lanes[lane].append(pos) #Append the vehicle's position to the lane's list of positions

        totalLength = 0.0
        totalSize = 0
        count = 0
        for key in laneCount:
            queueAverages.write(key + " " + str(laneLengthTotal[key]/laneCount[key]) + " " + str(laneSizeTotal[key]/laneCount[key]) + "\n")   #Write per-lane averages
            count += laneCount[key]
            totalLength += laneLengthTotal[key]
            totalSize += laneSizeTotal[key] #And add to the total data collection

        totalLength /= count
        totalSize /= count
        print(str(fileName) + " " + str(totalLength) + " " + str(totalSize))
        queueTotals.write(str(fileNum) + " " + str(totalLength) + " " + str(totalSize) + "\n")