"path planner function"

from math import pi, copysign
from molly.Circle import Circle
from molly.Polygon import dist_on_circle
from molly.Vec2D import Vec2D

from collections import defaultdict
from heapdict import heapdict

def get_path(settings,
             polygons,
             circles,
             start_pos,
             start_heading,
             start_v,
             target_pos):
    "returns list of points from_pos to end_pos"

    start_circles = get_start_circles(start_pos,
                                      start_heading,
                                      settings.obs_min_r)

    end_circle = [Circle(target_pos, 0)]

    all_circs = settings.static_circ_obs + circles + start_circles + end_circle
    all_polys = settings.static_poly_obs + polygons

    all_tans = all_tangents(all_circs, all_polys)

    #remove tangents between the two start circles

    start_circle_tans = start_circles[0].tangent_circle(start_circles[1])

    all_tans = [tan for tan in all_tans if not tan in start_circle_tans]

    # remove tangents leading out of bounds

    all_tans = [tan for tan in all_tans if tangent_inside_bounds(settings, tan)]

    graph = build_graph(all_tans, start_pos, start_circles, settings)

    segments = a_star(graph, target_pos)

    if segments:
        traj = discretize_trajectory(segments, start_v, 0.0, settings)
    else:
        traj = ramp_down(start_pos, start_heading, start_v, settings)

    return traj

def ramp_down(start_pos, start_heading, start_v, settings):
    "simple ramp down"

    direction = start_heading.normalized()

    current_pos = start_pos
    current_v = start_v
    current_time_stamp = 0.0

    res = [(current_pos, direction * current_v, current_time_stamp)]

    while current_v > 0:
        current_pos = current_pos + direction * current_v * settings.time_resolution
        current_v = current_v - settings.max_acc * settings.time_resolution
        if current_v < 0:
            current_v = 0
        current_time_stamp = current_time_stamp + settings.time_resolution

        res.append((current_pos, direction * current_v, current_time_stamp))

    return res


def point_inside_bounds(settings, vec):
    "check if vec is inside playground"
    x_check = 0 <= vec.pos_x <= settings.width
    y_check = 0 <= vec.pos_y <= settings.height
    return x_check and y_check

def tangent_inside_bounds(settings, tan):
    "check if start and end of tangent are inside playground"
    start_check = point_inside_bounds(settings, tan.start_pos)
    end_check = point_inside_bounds(settings, tan.end_pos)
    return start_check and end_check

def circle_segment_inside_bounds(settings, seg):
    "check if circle segment doesn't leave playground"

    for tan in settings.bounds:
        intersections = seg.circle.tangent_intersection_point(tan)

        if intersections:
            for inter_point in intersections:
                vec1 = seg.end - seg.start
                vec2 = inter_point - seg.start

                if vec1.cross(vec2) * seg.orientation < 0:
                    return True

    return True

def get_start_circles(start_pos, start_heading, radius):
    "two circles for which the line defined by start_pos and start_heading \
     is tangent"

    pos_center = start_pos + start_heading.rotate(pi/2).normalized() * radius
    neg_center = start_pos + start_heading.rotate(-pi/2).normalized() * radius

    return [Circle(pos_center, radius), Circle(neg_center, radius)]

def all_tangents(circles, polygons):
    "return all valid tangents for circles and polygons"
    circle_tans = all_tangents_poly_helper([], [], polygons)

    return all_tangents_circle_helper(circle_tans, polygons, circles)

    #circle_tans = all_tangents_circle_helper([], [], circles)

    #return all_tangents_poly_helper(circle_tans, circles, polygons)

def all_tangents_circle_helper(tan_acc, checked, circles):
    "helper function for all_tangents"

    res = tan_acc

    for circle in circles:

        old_tans_filtered = [tan for tan in res
                             if not circle.intersects_tangent(tan)]

        new_candidates = [tan for old in checked
                          for tan in old.tangent_circle(circle)]

        new_tans_filtered = [tan for tan in new_candidates
                             if all(not old.intersects_tangent(tan)
                                    for old in checked)]

        res = res + old_tans_filtered + new_tans_filtered
        checked = checked + [circle]

    return res

def all_tangents_poly_helper(tan_acc, checked, polys):
    "helper function for all_tangents"

    res = tan_acc

    for poly in polys:

        old_tans_filtered = [tan for tan in res
                             if not poly.intersects_tangent(tan)]

        new_candidates = [tan for old in checked
                          for tan in old.tangent_polygon(poly)]

        new_candidates = new_candidates + poly.sides

        new_tans_filtered = [tan for tan in new_candidates
                             if all(not old.intersects_tangent(tan)
                                    for old in checked)]

        res = res + old_tans_filtered + new_tans_filtered
        checked = checked + [poly]

    return res

def sort_points_on_circle(points, circle):
    "sort points by their angle on the circle"

    if not points:
        return []

    reference = points[0]
    rest = points[1: len(points)]

    sorted_points = sorted(rest,
                           key=lambda p:
                           Vec2D.orientation(reference, circle.pos, p))

    return [reference] + sorted_points

def build_graph(tans, start_pos, start_circles, settings):
    "build waypoint graph"

    circle_map = defaultdict(list)

    node_map = {}

    for tan in tans:
        start = tan.start_pos
        end = tan.end_pos
        circle_map[tan.start_circle].append(start)
        circle_map[tan.end_circle].append(end)

        node_map[(start, 1)] = Node(start, 1)
        node_map[(start, -1)] = Node(start, -1)
        node_map[(end, 1)] = Node(end, 1)
        node_map[(end, -1)] = Node(end, -1)


    for circle in circle_map:
        points = circle_map.get(circle)

        for point in points:
            (pos, neg) = neighbours_on_circle(points, circle, point)

            if pos is not None:
                pos_node = node_map[(point, 1)]
                pos_neigh = node_map[(pos, 1)]
                seg = CircleSegment(point, pos, circle, 1)
                if circle_segment_inside_bounds(settings, seg):
                    pos_node.add_neigh(pos_neigh, seg)

            if neg is not None:
                neg_node = node_map[(point, -1)]
                neg_neigh = node_map[(neg, -1)]
                seg = CircleSegment(point, neg, circle, -1)
                if circle_segment_inside_bounds(settings, seg):
                    neg_node.add_neigh(neg_neigh, seg)

    for tan in tans:

        node1_in_orient = copysign(1, tan.start_orient)
        node2_in_orient = copysign(1, tan.end_orient)

        node1_in = node_map[(tan.start_pos, node1_in_orient)]
        node2_in = node_map[(tan.end_pos, node2_in_orient)]

        node1_out = node_map[(tan.start_pos, -node1_in_orient)]
        node2_out = node_map[(tan.end_pos, -node2_in_orient)]

        node1_out.add_neigh(node2_in, LineSegment(node1_out.pos, node2_in.pos))
        node2_out.add_neigh(node1_in, LineSegment(node2_out.pos, node1_in.pos))

    pos_start_circle = start_circles[0]
    neg_start_circle = start_circles[1]

    pos_start_neigh = neighbours_on_circle(circle_map[pos_start_circle],
                                           pos_start_circle,
                                           start_pos)[0]

    neg_start_neigh = neighbours_on_circle(circle_map[neg_start_circle],
                                           neg_start_circle,
                                           start_pos)[1]

    pos_neigh = node_map.get((pos_start_neigh, 1))
    neg_neigh = node_map.get((neg_start_neigh, -1))

    pos_node = Node(start_pos, 1)
    neg_node = Node(start_pos, -1)

    if pos_neigh:
        seg = CircleSegment(start_pos, pos_neigh.pos, pos_start_circle, 1)

        if circle_segment_inside_bounds(settings, seg):
            pos_node.add_neigh(pos_neigh, seg)

    if neg_neigh:
        seg = CircleSegment(start_pos, neg_neigh.pos, neg_start_circle, -1)

        if circle_segment_inside_bounds(settings, seg):
            neg_node.add_neigh(neg_neigh, seg)

    for tan in tans:
        if tan.start_pos == start_pos:
            seg = LineSegment(start_pos, tan.end_pos)
            pneigh = node_map.get((tan.end_pos, 1))
            nneigh = node_map.get((tan.end_pos, -1))
            if pneigh:
                pos_node.add_neigh(pneigh, seg)
                neg_node.add_neigh(pneigh, seg)
            if nneigh:
                pos_node.add_neigh(nneigh, seg)
                neg_node.add_neigh(nneigh, seg)

        elif tan.end_pos == start_pos:
            seg = LineSegment(start_pos, tan.start_pos)
            pneigh = node_map.get((tan.start_pos, 1))
            nneigh = node_map.get((tan.start_pos, -1))
            if pneigh:
                pos_node.add_neigh(pneigh, seg)
                neg_node.add_neigh(pneigh, seg)
            if nneigh:
                pos_node.add_neigh(nneigh, seg)
                neg_node.add_neigh(nneigh, seg)

    return [pos_node, neg_node]

def neighbours_on_circle(points, circle, pos):
    "get oriented angle of points on circle and return (min, max)"

    max_val = 0
    min_val = 2 * pi
    max_pt = None
    min_pt = None

    vec1 = pos - circle.pos

    # pos is only a neighbour if it appears more than once in points list
    self_count = 0
    for point in points:
        if point == pos:
            self_count += 1
    self_ignore = self_count <= 1

    for point in points:

        if point == pos and self_ignore:
            continue

        angle = vec1.oriented_angle(point - circle.pos)

        if angle < min_val:
            min_val = angle
            min_pt = point

        if angle > max_val:
            max_val = angle
            max_pt = point

    return (min_pt, max_pt)

def a_star(start_nodes, end_pos):
    "standard A* implementation"

    visited = set()
    parents = {}
    queue = heapdict()
    g_score = {}
    f_score = {}

    for node in start_nodes:
        g_score[node] = 0
        f_score[node] = g_score[node] + (end_pos - node.pos).length()
        queue[node] = f_score[node]

    while queue:
        current = queue.popitem()[0]
        visited.add(current)

        if current.pos == end_pos:
            res = []
            curr = current
            parent = parents.get(curr)
            while parent:
                res.append(parent.segment_to_neighbour(curr))
                curr = parent
                parent = parents.get(curr)

            res.reverse()

            return res

        for neigh in current.neighbours():

            if neigh in visited:
                continue

            tentative_g_score = g_score[current] + \
                                current.dist_to_neighbour(neigh)

            if (not neigh in queue) or (g_score[neigh] < tentative_g_score):
                parents[neigh] = current
                g_score[neigh] = tentative_g_score
                f_score[neigh] = g_score[neigh] + (end_pos - neigh.pos).length()
                queue[neigh] = f_score[neigh]

    return []

def discretize_trajectory(segments, v_start, v_end, settings):
    "discretize trajectory formed by segments"

    traj_length = 0
    for seg in segments:
        traj_length = traj_length + seg.length()

    acc_until_dist = 0
    decc_from_dist = 0

    t_adj = abs(v_start - v_end)/settings.max_acc
    d_adj = min(v_start, v_end)*t_adj + 0.5 * settings.max_acc * t_adj * t_adj

    t_acc = (settings.max_v - v_start)/settings.max_acc
    d_acc = v_start * t_acc + 0.5 * settings.max_acc * t_acc * t_acc

    t_dec = (settings.max_v - v_end)/settings.max_acc
    d_decc = v_end * t_dec + 0.5 * settings.max_acc * t_dec * t_dec

    if d_adj > traj_length:
        if v_start < v_end:
            acc_until_dist = traj_length
            decc_from_dist = traj_length + 1
            # Cannot accelerate to end-velocity"
        else:
            acc_until_dist = 0
            decc_from_dist = traj_length
            # Cannot decelerate to end-velocity
    elif t_acc + t_dec > traj_length:
        d_tmp = (traj_length - d_adj)/2
        acc_until_dist = d_tmp
        decc_from_dist = d_tmp
    else:
        acc_until_dist = d_acc
        decc_from_dist = traj_length - d_decc

    current_d = 0
    current_t = 0
    current_v = v_start
    res = []
    for seg in segments:
        res = res + discretize_segment(seg,
                                       current_d,
                                       current_t,
                                       current_v,
                                       acc_until_dist,
                                       decc_from_dist,
                                       settings)
        (_, speed, _, time_stamp) = res[-1]
        current_d = current_d + seg.length()
        current_t = time_stamp
        current_v = speed.length()

    return res

def discretize_segment(segment,
                       d_travelled,
                       time_stamp,
                       v_init,
                       acc_until,
                       dec_from,
                       settings):
    "discretize a segment"

    current_pos = segment.start
    current_v = v_init
    current_speed_vector = segment.tan(segment.start) * v_init
    current_time_stamp = time_stamp
    current_d_travelled = d_travelled
    d_remaining = segment.length()

    if current_d_travelled < acc_until:
        current_acc = settings.max_acc
    elif current_d_travelled > dec_from:
        current_d_travelled = -settings.max_acc
    else:
        current_acc = 0
        
    current_acc_vector = segment.tan(current_pos) * current_acc
    current_acc_vector = current_acc_vector + \
                         segment.radial_acc(current_pos, current_v)

    res = []

    res.append((current_pos,
                current_speed_vector,
                current_acc_vector,
                current_time_stamp))

    delta_t = settings.time_resolution

    while d_remaining > 0:

        delta_dist = (current_v * delta_t)

        if delta_dist > d_remaining:
            delta_t = d_remaining / current_v
            delta_dist = d_remaining
        else:
            delta_t = settings.time_resolution

        current_pos = segment.next_pos(current_pos, delta_dist)
        current_d_travelled = current_d_travelled + delta_dist

        if current_d_travelled < acc_until:
            current_v = current_v + settings.max_acc * delta_t
            current_acc = settings.max_acc
        elif current_d_travelled < dec_from:
            current_v = settings.max_v
            current_acc = 0
        else:
            current_v = current_v - settings.max_acc * delta_t
            current_acc = - settings.max_acc
            if current_v < 0:
                return res

        current_speed_vector = segment.tan(current_pos) * current_v

        current_acc_vector = segment.tan(current_pos) * current_acc
        current_acc_vector = current_acc_vector + \
                             segment.radial_acc(current_pos, current_v)

        current_time_stamp = current_time_stamp + delta_t

        d_remaining = d_remaining - delta_dist

        res.append((current_pos,
                    current_speed_vector,
                    current_acc_vector,
                    current_time_stamp))

    return res


class Node(object):
    "node of waypoint graph"

    def __init__(self, pos, orient):
        self.pos = pos
        self.orient = orient
        self.segment_map = {}
        self.neighs = []

    def add_neigh(self, neigh, seg):
        "add segment to node"
        self.neighs.append(neigh)
        self.segment_map[neigh] = seg

    def dist_to_neighbour(self, neigh):
        "distance to neigh"
        return self.segment_map.get(neigh).length()

    def neighbours(self):
        "neighbours of self"
        return self.neighs

    def segment_to_neighbour(self, neigh):
        "segment connecting self to neigh"
        return self.segment_map.get(neigh)

class LineSegment(object):
    "simple line segment"

    def __init__(self, start, end):
        self.start = start
        self.end = end

    def __str__(self):
        return "LineSegment: {start} -> {end}".format(start=(str(self.start)),
                                                      end=(str(self.end)))

    def length(self):
        "length of segment"
        return (self.end - self.start).length()

    def tan(self, pos):
        "tangent on segment at pos"
        return (self.end - self.start).normalized()

    def radial_acc(self, pos, speed):
        "centripetal acceleration at pos with given speed"
        return Vec2D()

    def next_pos(self, pos, dist):
        "point on segment with dist to pos"
        return pos + (self.tan(pos) * dist)


class CircleSegment(object):
    "circle segment"

    def __init__(self, start, end, circle, orientation):
        self.start = start
        self.end = end
        self.circle = circle
        self.orientation = orientation

    def __str__(self):
        return "CircleSegment: {start} -> {end} on {circle} with orient {o}" \
                .format(start=(str(self.start)),
                        end=(str(self.end)),
                        circle=(str(self.circle)),
                        o=str(self.orientation))

    def length(self):
        "length of segment"
        return dist_on_circle(self.start, self.end, self.circle, self.orientation)

    def tan(self, pos):
        "tangent on segment at pos"
        return self.circle.tangent_vector(pos, self.orientation).normalized()

    def radial_acc(self, pos, speed):
        "centripetal acceleration at pos with given speed"

        res = (self.circle.pos - pos).normalized()

        acc = (speed * speed) / self.circle.radius

        return res * acc

    def next_pos(self, pos, dist):
        "point on segment with dist to pos"
        angle = (dist / self.circle.radius)
        if self.orientation < 0:
            angle = -angle
        return pos.rotate(angle, self.circle.pos)
