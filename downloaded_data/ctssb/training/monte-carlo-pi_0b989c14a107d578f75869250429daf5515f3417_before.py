import random
import matplotlib.pyplot as plt
import numpy

def approx_pi_with_plot(n, seed = 0):
        random.seed(seed)
        inside = 0
        total = 0
        inside_x = []
        inside_y = []
        outside_x = []
        outside_y = []
        
        for i in range(n):
                x = random.random()
                y = random.random()
                dist = dist_to_origin(x, y)

                if dist <= 1:
                        inside += 1
                        inside_x.append(x)
                        inside_y.append(y)
                else:
                        outside_x.append(x)
                        outside_y.append(y)
                total += 1


        pi = 4 * inside / total

        plt.plot(inside_x, inside_y, 'bo', outside_x, outside_y, 'go')
        plt.axis([-0.03, 1.03, -0.03, 1.03])
        plt.xlabel("Pi ~ {}, Total Dots: {}, Dots Inside {}".format(pi, inside, total))
        plt.show()
        
        return pi


def approx_pi(n, seed = 0):
        random.seed(seed)
        inside = 0
        total = 0
        
        for i in range(n):
                if dist_to_origin(random.random(), random.random()) <= 1:
                        inside += 1
                total += 1

        return 4 * inside / total


#returns the distance from point (x,y) to (0,0)
def dist_to_origin(x, y):
        return (x ** 2 + y ** 2) ** 0.5


n = int(input("N: "))
seed = float(input("Seed: "))

if n <= 100000:
        print(approx_pi_with_plot(n, seed))
else:
        print(approx_pi(n, seed))
