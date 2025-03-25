from pyglet.gl import *
import random
import math
from itertools import chain

glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
glEnable(GL_BLEND)

drawOriginalPoints = True
drawOriginalLines = True
drawFixedWidthBorder = False
drawFixedWidthAtIntersectionBorder = False
drawVectors = False
drawEastMitrePointLines = True
drawEastMitreConstructionLines = False
drawWestMitrePointLines = True
drawWestMitreConstructionLines = False

batch = pyglet.graphics.Batch()

xMax = 600
yMax = 600

numPoints = 3
points = list()

lineWidth = 80
halfLineWidth = lineWidth/2

def printPoints(listName, pointList):
    print("Printing list: %s" % listName)
    for p in pointList:
        print(p)

def normalize(vec):
    magnitude = math.sqrt(vec[0]**2 + vec[1]**2)
    return (vec[0]/magnitude, vec[1]/magnitude)

def mag(vec):
    return math.sqrt(vec[0]**2 + vec[1]**2)

def drawVector(start, vector, col = [255,255,255], norm=False):
    v = 0
    if norm:
        v = normalize(vector)
    else:
        v = vector
    drawnLengthMultiplier = 20
    if not norm:
        drawnLengthMultiplier = 1
    batch.add(2, pyglet.gl.GL_LINES, None,
        ('v2f/static', [start[0], start[1], start[0]+v[0]*drawnLengthMultiplier, start[1]+v[1]*drawnLengthMultiplier]),
        ('c3B/static', col+col)
    )

def drawLine(start, end, col = [255, 255, 255]):
    batch.add(2, pyglet.gl.GL_LINES, None,
        ('v2f/static', [start[0], start[1], end[0], end[1]]),
        ('c3B/static', col+col)
    )


def calcLineIntersection(p1, p2, p3, p4):
    # First line: Pa = p1 + u1(p2-p1)
    # Second line: Pb = p3 + u2(p4-p3)
    # Unknowns
    denominator = ((p4[1]-p3[1])*(p2[0]-p1[0]) - (p4[0]-p3[0])*(p2[1]-p1[1]))
    if denominator == 0:
        # Use 0, 0 as an obvious diagnostic indicator that something is wrong
        return 0, 0
    u1 = ((p4[0]-p3[0])*(p1[1]-p3[1]) - (p4[1]-p3[1])*(p1[0]-p3[0]))/denominator
    # Don't even need to calculate the second, but here it is
    #u2 = ((p2[0]-p1[0])*(p1[1]-p3[1]) - (p2[1]-p1[1])*(p1[0]-p3[0]))/denominator
    x = p1[0]+(u1*(p2[0]-p1[0]))
    y = p1[1]+(u1*(p2[1]-p1[1]))
    # Notes:
    # If denominator is zero, lines are parallel
    # Intersection is for infinite lines. If line segment intersection is necessary
    #   must test if u1 and u2 are between 0 and 1.
    # This link was very helpful: http://paulbourke.net/geometry/pointlineplane/
    return x, y

def createPoints():
    groupNum = 1

    # Manual points
    points.extend([(100, 400), (200, 500), (300, 400), (350,550), (375,400), (500, 400), (500, 200), (400, 200)])
    printPoints("Initial points", points)
    pointCols = [255, 0, 0] * len(points)
    if drawOriginalPoints:
        points_vertex_list = batch.add(len(points), pyglet.gl.GL_POINTS, None,
            ('v2f/static', list(chain.from_iterable(points))),
            ('c3B/static', pointCols)
        )
    if drawOriginalLines:
        lineSegmentCols = [255, 255, 0] * (len(points))
        line_segments_vertex_list = batch.add(len(points), pyglet.gl.GL_LINE_LOOP, None,
            ('v2f/static', list(chain.from_iterable(points))),
            ('c3B/static', lineSegmentCols)
        )

    # Calculate line segment normals
    lineVecs = list()
    lineNormals = list()
    intersectionNormals = list()

    # Calc line segment normals
    for pIndex in range(len(points)):
        #print("pIndex: ", pIndex)
        nextPIndex = (pIndex+1)%len(points)
        vec = (points[nextPIndex][0] - points[pIndex][0], points[nextPIndex][1] - points[pIndex][1])
        lineVecs.append(vec)
        normalVec = (-vec[1], vec[0])
        unitNormalVec = normalize(normalVec)
        lineNormals.append(unitNormalVec)
        # Visualize normal
        midpoint = (
            (points[pIndex][0] + points[nextPIndex][0])/2,
            (points[pIndex][1] + points[nextPIndex][1])/2
        )
        if drawVectors:
            drawVector(midpoint, unitNormalVec, [120,222,240])

    printPoints("line vectors", lineVecs)
    printPoints("line normals", lineNormals)

    # Calc intersection normals
    for lineIndex in range(len(lineVecs)):
        nextLineIndex = (lineIndex+1)%len(lineVecs)
        xComp = lineNormals[lineIndex][0] + lineNormals[nextLineIndex][0]
        yComp = lineNormals[lineIndex][1] + lineNormals[nextLineIndex][1]
        intersectionNormal = normalize((xComp, yComp))
        intersectionNormals.append(intersectionNormal)
        # Visualize normal
        if drawVectors:
            drawVector(points[nextLineIndex], intersectionNormal, [200,250,150])


    printPoints("intersection normals", intersectionNormals)

    # Calc points for line width border
    westBorderPoints = list()
    eastBorderPoints = list()
    for pIndex in range(len(points)):
        p = points[pIndex]
        wX = p[0]+(lineNormals[pIndex][0]*halfLineWidth)
        wY = p[1]+(lineNormals[pIndex][1]*halfLineWidth)
        westBorderPoints.append( (wX, wY) )
        westBorderPoints.append( (wX+lineVecs[pIndex][0], wY+lineVecs[pIndex][1]) )

        eX = p[0]-(lineNormals[pIndex][0]*halfLineWidth)
        eY = p[1]-(lineNormals[pIndex][1]*halfLineWidth)
        eastBorderPoints.append( (eX, eY) )
        eastBorderPoints.append( (eX+lineVecs[pIndex][0], eY+lineVecs[pIndex][1]) )
    if drawFixedWidthBorder:
        west_vertex_list = batch.add(len(westBorderPoints), pyglet.gl.GL_POINTS, None,
            ('v2f/static', list(chain.from_iterable(westBorderPoints))),
            ('c3B/static', [0, 255, 0, 100, 255, 50]*int(len(westBorderPoints)/2))
        )
        east_vertex_list = batch.add(len(eastBorderPoints), pyglet.gl.GL_POINTS, None,
            ('v2f/static', list(chain.from_iterable(eastBorderPoints))),
            ('c3B/static', [0, 0, 255, 100, 50, 255]*int(len(eastBorderPoints)/2))
        )
        west_line_vertex_list = batch.add(len(westBorderPoints), pyglet.gl.GL_LINE_LOOP, None,
            ('v2f/static', list(chain.from_iterable(westBorderPoints))),
            ('c3B/static', [0, 255, 0, 100, 255, 50]*int(len(westBorderPoints)/2))
        )
        east_line_vertex_list = batch.add(len(eastBorderPoints), pyglet.gl.GL_LINE_LOOP, None,
            ('v2f/static', list(chain.from_iterable(eastBorderPoints))),
            ('c3B/static', [0, 0, 255, 100, 50, 255]*int(len(eastBorderPoints)/2))
        )

    # Print whether line is making left or right turns
    for i in range(len(lineVecs)):
        if i == len(lineVecs)-1:
            continue
        v1 = normalize(lineVecs[i])
        v2 = normalize(lineVecs[i+1])
        position = v1[0]*v2[1] - v1[1]*v2[0]
        if (position == 0):
            #print("i=%d, straight ahead" % i)
            pass
        elif (position > 0):
            #print("i=%d, left turn" % i)
            pass
        else:
            #print("i=%d, right turn" % i)
            pass

    # Calculate intersection points for east line segments (and then west) using normal offsets from corners
    eastIntersectionPoints = list()
    westIntersectionPoints = list()
    for i in range(len(intersectionNormals)):
        nextI = (i+1)%len(intersectionNormals)
        eastIntersection = (points[nextI][0] - intersectionNormals[i][0]*halfLineWidth, points[nextI][1] - intersectionNormals[i][1]*halfLineWidth)
        eastIntersectionPoints.append(eastIntersection)
        westIntersection = (points[nextI][0] + intersectionNormals[i][0]*halfLineWidth, points[nextI][1] + intersectionNormals[i][1]*halfLineWidth)
        westIntersectionPoints.append(westIntersection)
    if drawFixedWidthAtIntersectionBorder:
        east_inters_vertex_list = batch.add(len(eastIntersectionPoints), pyglet.gl.GL_LINE_LOOP, None,
            ('v2f/static', list(chain.from_iterable(eastIntersectionPoints))),
            ('c3B/static', [255, 0, 0]*len(eastIntersectionPoints))
        )
        west_inters_vertex_list = batch.add(len(westIntersectionPoints), pyglet.gl.GL_LINE_LOOP, None,
            ('v2f/static', list(chain.from_iterable(westIntersectionPoints))),
            ('c3B/static', [200, 0, 0]*len(westIntersectionPoints))
        )

    # Loop over intersections
    # On inside of turn, find where entering/exiting lines meet, use point
    # On outside of turn...
    # * stop at same length of acute line
    # * next point is intersection normal, at dist of line width
    # * subdivide if desired
    eastPoints = list()
    eastConstructionLines = list()
    westPoints = list()
    westConstructionLines = list()
    for i in range(len(lineVecs)):
        #print("\ni = %d" % i)
        #print("ith Point: %f,%f" % (points[i][0], points[i][1]))
        prever = i-2
        prev = i-1
        current = i
        v1 = normalize(lineVecs[prever])
        v2 = normalize(lineVecs[prev])
        position = v1[0]*v2[1] - v1[1]*v2[0]
        if (position == 0):
            print("i=%d, straight ahead" % prever)
            # ignore points here... let prev vector dictate them
            continue
        elif (position > 0):
            # Left turn, west border is acute

            ## Calculate WEST acute points
            line1Norm = (lineNormals[prever][0]*halfLineWidth, lineNormals[prever][1]*halfLineWidth)
            wX1 = points[prever][0] + line1Norm[0]
            wY1 = points[prever][1] + line1Norm[1]
            # Vector from current point, into intersection
            v1 = (points[prev][0]-points[prever][0], points[prev][1]-points[prever][1])
            # Point on line parallel to line leaving intersection point
            line2Norm = (lineNormals[prev][0]*halfLineWidth, lineNormals[prev][1]*halfLineWidth)
            wX2 = points[current][0] + line2Norm[0]
            wY2 = points[current][1] + line2Norm[1]
            # Vector from point after intersection, pointing back into it
            v2 = (points[prev][0]-points[current][0], points[prev][1]-points[current][1])
            # Gives
            p1 = (wX1, wY1)
            p2 = (wX1+v1[0], wY1+v1[1])
            # and
            p3 = (wX2, wY2)
            p4 = (wX2+v2[0], wY2+v2[1])
            xInter, yInter = calcLineIntersection(p1, p2, p3, p4)
            westPoints.append((xInter, yInter))
            westConstructionLines.extend([p1, p2, p3, p4])

            ## Calculate EAST obtuse points
            # Uses point i+1 (i.e. prev) as this process is working out the termination points for the end of the prev vector
            eX1 = points[prever][0] - line1Norm[0]
            eY1 = points[prever][1] - line1Norm[1]
            #drawVector(points[prev], line1Norm)
            eX2 = points[current][0] - line2Norm[0]
            eY2 = points[current][1] - line2Norm[1]
            #drawVector(points[current], line2Norm, (50, 50, 50))
            # Gives
            p1 = (eX1, eY1)
            p2 = (eX1+v1[0], eY1+v1[1])
            # and
            p3 = (eX2, eY2)
            p4 = (eX2+v2[0], eY2+v2[1])
            xInter, yInter = calcLineIntersection(p1, p2, p3, p4)
            eastPoints.append((xInter, yInter))
            eastConstructionLines.extend([p1, p2])
        else:
            # Right turn, east border is acute

            ## Calculate EAST acute points
            # Inverted normal to get normal on east side
            line1Norm = (lineNormals[prever][0]*halfLineWidth, lineNormals[prever][1]*halfLineWidth)
            eX1 = points[prever][0]-line1Norm[0]
            eY1 = points[prever][1]-line1Norm[1]
            # Vector from current point, into intersection
            v1 = (points[prev][0]-points[prever][0], points[prev][1]-points[prever][1])
            # Point on line parallel to line leaving intersection point
            line2Norm = (lineNormals[prev][0]*halfLineWidth, lineNormals[prev][1]*halfLineWidth)
            eX2 = points[current][0]-line2Norm[0]
            eY2 = points[current][1]-line2Norm[1]
            # Vector from point after intersection, pointing back into it
            v2 = (points[prev][0]-points[current][0], points[prev][1]-points[current][1])
            # Gives
            p1 = (eX1, eY1)
            p2 = (eX1+v1[0], eY1+v1[1])
            # and
            p3 = (eX2, eY2)
            p4 = (eX2+v2[0], eY2+v2[1])
            xInter, yInter = calcLineIntersection(p1, p2, p3, p4)
            eastPoints.append((xInter, yInter))
            eastConstructionLines.extend([p1, p2, p3, p4])

            ## Calculate WEST obtuse points
            # Uses point i+1 (i.e. prev) as this process is working out the termination points for the end of the prev vector
            wX1 = points[prever][0] + line1Norm[0]
            wY1 = points[prever][1] + line1Norm[1]
            #drawVector(points[prev], line1Norm)
            wX2 = points[current][0] + line2Norm[0]
            wY2 = points[current][1] + line2Norm[1]
            #drawVector(points[current], line2Norm, (50, 50, 50))
            # Gives
            p1 = (wX1, wY1)
            p2 = (wX1+v1[0], wY1+v1[1])
            # and
            p3 = (wX2, wY2)
            p4 = (wX2+v2[0], wY2+v2[1])
            xInter, yInter = calcLineIntersection(p1, p2, p3, p4)
            westPoints.append((xInter, yInter))
            westConstructionLines.extend([p1, p2])

    if drawEastMitreConstructionLines:
        east_acute_construction_vertex_list = batch.add(len(eastConstructionLines), pyglet.gl.GL_LINES, None,
            ('v2f/static', list(chain.from_iterable(eastConstructionLines))),
            ('c3B/static', [25, 180, 60]*len(eastConstructionLines))
        )
    if drawEastMitrePointLines:
        eastMitrePointsGroup = pyglet.graphics.OrderedGroup(groupNum)
        groupNum += 1
        east_acute_vertex_list = batch.add(len(eastPoints), pyglet.gl.GL_LINE_LOOP, eastMitrePointsGroup,
            ('v2f/static', list(chain.from_iterable(eastPoints))),
            ('c3B/static', [200, 0, 0]*len(eastPoints))
        )
    if drawWestMitreConstructionLines:
        west_acute_construction_vertex_list = batch.add(len(westConstructionLines), pyglet.gl.GL_LINES, None,
            ('v2f/static', list(chain.from_iterable(westConstructionLines))),
            ('c3B/static', [25, 180, 60]*len(westConstructionLines))
        )
    if drawWestMitrePointLines:
        westMitrePointsGroup = pyglet.graphics.OrderedGroup(groupNum)
        groupNum += 1
        west_acute_vertex_list = batch.add(len(westPoints), pyglet.gl.GL_LINE_LOOP, westMitrePointsGroup,
            ('v2f/static', list(chain.from_iterable(westPoints))),
            ('c3B/static', [0, 0, 200]*len(westPoints))
        )

    # Construct wide-line triangles
    # West triangles
    westTrianglePoints = list()
    for pIndex in range(len(points)):
        westTrianglePoints.append(points[pIndex-1])
        westTrianglePoints.append(westPoints[pIndex])
    westTrianglePoints.append(points[-1])
    westTrianglePoints.append(westPoints[0])
    westPointsGroup = pyglet.graphics.OrderedGroup(groupNum)
    groupNum += 1
    col = list()
    for n in range(len(westTrianglePoints)):
        col.extend([random.randint(0,255), random.randint(0,255), random.randint(0,255)])
    west_acute_vertex_list = batch.add(len(westTrianglePoints), pyglet.gl.GL_TRIANGLE_STRIP, westPointsGroup,
        ('v2f/static', list(chain.from_iterable(westTrianglePoints))),
        ('c3B/static', col)
    )
    # East triangles
    eastTrianglePoints = list()
    for pIndex in range(len(points)):
        eastTrianglePoints.append(points[pIndex-1])
        eastTrianglePoints.append(eastPoints[pIndex])
    eastTrianglePoints.append(points[-1])
    eastTrianglePoints.append(eastPoints[0])
    eastPointsGroup = pyglet.graphics.OrderedGroup(groupNum)
    groupNum += 1
    col = list()
    for n in range(len(eastTrianglePoints)):
        col.extend([random.randint(0,255), random.randint(0,255), random.randint(0,255)])
    east_acute_vertex_list = batch.add(len(eastTrianglePoints), pyglet.gl.GL_TRIANGLE_STRIP, eastPointsGroup,
        ('v2f/static', list(chain.from_iterable(eastTrianglePoints))),
        ('c3B/static', col)
    )

class GameWindow(pyglet.window.Window):
    def __init__(self, *args, **kwargs):
        pyglet.window.Window.__init__(self, *args, **kwargs)

    def on_draw(self):
        self.clear()
        batch.draw()

    def update(self, deltaTime):
        pass

if __name__ == '__main__':
    print("Running app")
    window = GameWindow(xMax, yMax, caption="LineRenderer", resizable=True, vsync=False)
    # Pyglet FPS Overlay
    fps_display = pyglet.clock.ClockDisplay()
    # Call update 120 per second
    pyglet.clock.schedule_interval(window.update, 1/120.0)
    # Generate point data
    createPoints()
    pyglet.app.run()
    print("Ran app")
