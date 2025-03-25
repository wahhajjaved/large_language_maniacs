from utils import create_tree_as_extracted, surface_area_old, sort_boxes, create_tree, get_overlap_ratio, sort_boxes_only, extract_coords
import numpy as np
import time
import IEP
import itertools
from itertools import chain, islice
import networkx as nx
from collections import deque
from utils import get_set_intersection, get_intersection

class Data:
    def __init__(self, load, img_nr, prune_tree_levels, scaler, num_features=4096, overlap_gt=False, grid=False, gt=False):
        self.img_nr = img_nr
        if load.mode != 'mscoco' and load.mode != 'trancos':
            self.y = load.get_label(img_nr)
        if grid:
            self.X = load.get_grid(img_nr)
            self.levels = {0: [0], 1: [1,2], 2: range(3,7), 3: range(23,32), 4: range(7,23)}
            self.boxes = load.get_grid_coords(img_nr)
            #self.levels = {0: [0], 1: [1,2], 2: range(3,7), 3: range(7,16), 4: range(17,32)} #for count net
        else:
            self.boxes = load.get_coords(img_nr)
            print load.mode
            if load.mode == 'gt':
                gts = load.get_all_gts(img_nr)
                self.boxes = np.array(self.boxes[0])
                for gt in gts:
                    if gts[gt] != []:
                        self.boxes = np.vstack((self.boxes,np.array(gts[gt])))
                self.levels = {0:[0], 1: range(1,len(self.boxes))}
            if self.boxes != []:
                if load.mode == 'dennis':
                    self.X = load.get_features(img_nr)
                elif load.mode == 'mscoco' or load.mode == 'trancos':
                    self.X = np.zeros((5000,num_features))
                self.num_features = num_features
                if gt:
                    self.gr = load.get_gts(img_nr)
                    self.gt_f = load.get_get_features(img_nr)
                    self.levels = {0: range(len(self.gr))}
                else:
                    if num_features != 4096:
                        features_temp = []
                        for p in self.X:
                            features_temp.append(p[0:num_features])
                        self.X = np.array(features_temp)
                    if scaler != None:
                        self.X = scaler.transform(self.X)
                    #print "load", (time.time() - start)
                    start = time.time()
                    #self.tree_boxes = load.get_coords_tree(img_nr)
                    #print len(self.tree_boxes), len(self.tree_boxes[0])
                    if load.mode == 'dennis':
                        self.tree_boxes = load.get_coords_tree(img_nr)
                        self.tree_boxes,self.X = sort_boxes(self.tree_boxes, self.X)
                    elif load.mode == 'mscoco' or load.mode == 'trancos':
                        self.boxes = sort_boxes_only(self.boxes)
                        self.tree_boxes = np.array(self.boxes)

                    if overlap_gt:
                        self.y_boxes = []
                        for b_i in self.tree_boxes:
                            sum_tmp = 0.0
                            for g_i in gr:
                                sum_tmp += get_overlap_ratio(g_i, b_i)
                            self.y_boxes.append(sum_tmp)

                    #self.G, levels = create_tree_as_extracted(self.tree_boxes)
                    if load.mode == 'dennis':
                        self.G, levels = create_tree(self.tree_boxes)
                    elif load.mode == 'mscoco' or load.mode == 'trancos':
                        self.G, levels = create_tree(self.boxes)
                    #print "tree", (time.time() - start)
                    start = time.time()
                    if load.mode == 'dennis':
                        self.boxes = self.tree_boxes
                    #prune tree to only have levels which fully cover the image, tested
                    total_size = surface_area_old(self.tree_boxes, levels[0])
                    for level in levels:
                        sa = surface_area_old(self.tree_boxes, levels[level])
                        sa_co = sa/total_size
                        if sa_co != 1.0:
                            self.G.remove_nodes_from(levels[level])
                        else:
                            nr_levels_covered = level
                    levels = {k: levels[k] for k in range(0,nr_levels_covered + 1)}
                    # prune levels, speedup + performance 
                    levels_tmp = {k:v for k,v in levels.iteritems() if k<prune_tree_levels}
                    levels_gone = {k:v for k,v in levels.iteritems() if k>=prune_tree_levels}
                    self.levels = levels_tmp
                    #prune tree as well, for patches training
                    for trash_level in levels_gone.values():
                        self.G.remove_nodes_from(trash_level)

                    if load.mode == 'mscoco' or load.mode == 'trancos' or load.mode == 'gt':
                        intersection_coords = []
            #            for patch in self.G.nodes():
            #                intersection_coords.append(self.boxes[patch])

                        for level in levels:
                            intersections_level = extract_coords(self.levels[level], self.boxes)
            #                intersection_coords.extend([pruned_boxes[ll] for ll in levels[level]])
                            #for i_coo in intersection_coords:
                            intersection_coords.extend(intersections_level)
                        a = np.array(intersection_coords)
                        #print a
                        if len(a)>0:
                            unique_coords = np.unique(a.view(np.dtype((np.void, a.dtype.itemsize*a.shape[1])))).view(a.dtype).reshape(-1, a.shape[1])
                            self.boxes = np.concatenate((self.boxes,unique_coords))
                        else:
                            self.boxes = np.array(self.boxes)
                        self.tree_boxes = np.array(self.boxes)
                        #self.boxes = np.array(self.boxes)
                        
                    self.debug_tmp = []
                    for n in self.G.nodes():
                        self.debug_tmp.append(self.tree_boxes[n])
                    if load.mode == 'pascal':
                        self.lookup_coords()
                    elif load.mode == 'dennis':
                        assert self.boxes==self.tree_boxes
                        intersection_coords = load.get_intersection_coords(img_nr)
                        intersection_features = load.get_intersection_features(img_nr)
                        if scaler != None and len(intersection_features) > 0:
                            intersection_features = scaler.transform(intersection_features)
                        assert len(intersection_coords) == len(intersection_features)
                        if len(intersection_coords) > 0:
                            self.boxes = np.append(self.boxes, intersection_coords, axis=0)
                            if overlap_gt:
                                for is_i in intersection_coords:
                                    sum_tmp = 0.0
                                    for g_i in gr:
                                        sum_tmp += get_overlap_ratio(g_i, is_i)
                                    self.y_boxes.append(sum_tmp)
                                self.X = np.array(self.y_boxes) + np.random.normal(0,.1,len(self.y_boxes))
                                assert self.num_features == 1
                            else:
                                self.X = np.append(self.X, intersection_features[:,0:num_features], axis=0)
                        else:
                            if overlap_gt:
                                self.X = np.array(self.y_boxes) + np.random.normal(0,.1,len(self.y_boxes))
                                assert self.num_features == 1
                            else:
                                self.boxes = np.array(self.boxes)
                                self.X = np.array(self.X)

                    #print 'starting getting gt data'
                    #this is just for create_mats.py
                if load.mode == 'mscoco' or load.mode == 'trancos'  or load.mode == 'gt':
                    learner = IEP.IEP(1, 'learning')
                    _,function = learner.get_iep_levels(self, {})
                    flevels = []
                    for f in range(len(function)):
                        flevels.append([a[1] for a in function[f]])
                    self.box_levels = []
                    temp = []
                    temp1 = []
                    double = 0.0
                    l_boxes = len(self.boxes)
                    level_len = np.zeros(len(flevels))
                    for i in range(len(self.boxes)):
                        found = False
                        for i_l,fl in enumerate(flevels):
                            if i in fl:
                                level_len[i_l] += 1
                                if found:
                                    # append afterwards so functions and boxes are in same order
                                    double += 1
                                    #self.boxes = np.concatenate((self.boxes,self.boxes[i].reshape(1,4)), axis=0)
                                    #have to put it at the end somehow
                                    if function[i_l][fl.index(i)][0] == '+':
                                        if len(np.where((np.array(function[i_l]) == ['-',i]).all(axis=1))[0]) != len(np.where((np.array(function[i_l]) == ['+',i]).all(axis=1))[0])  and len(np.where((np.array(function[i_l]) == ['+',i]).all(axis=1))[0])>0:
                                            #temp.append([0, -1])
                                            temp.append([1,i_l])
                                            temp1.append(self.boxes[i])
                                        else:
                                            double
                                    elif function[i_l][fl.index(i)][0] == '-':
                                        if len(np.where((np.array(function[i_l]) == ['-',i]).all(axis=1))[0]) != len(np.where((np.array(function[i_l]) == ['+',i]).all(axis=1))[0])  and len(np.where((np.array(function[i_l]) == ['-',i]).all(axis=1))[0])>0:
                                            temp.append([-1,i_l])
                                            temp1.append(self.boxes[i])
                                        else:
                                            double
                                else:
                                    if function[i_l][fl.index(i)][0] == '+':
                                        if len(np.where((np.array(function[i_l]) == ['-',i]).all(axis=1))[0]) != len(np.where((np.array(function[i_l]) == ['+',i]).all(axis=1))[0]) and len(np.where((np.array(function[i_l]) == ['+',i]).all(axis=1))[0])>0:
                                            self.box_levels.append([1,i_l])
                                            #print i, i_l, np.where((np.array(function[i_l]) == ['-',i]).all(axis=1))[0], np.where((np.array(function[i_l]) == ['+',i]).all(axis=1))[0]
                                            #raw_input()
                                            found = True
                                        else:
                                            #print 'skipping', i
                                            self.box_levels.append([0, -1])
                                            found = True
                                    elif function[i_l][fl.index(i)][0] == '-':
                                        if len(np.where((np.array(function[i_l]) == ['-',i]).all(axis=1))[0]) != len(np.where((np.array(function[i_l]) == ['+',i]).all(axis=1))[0])  and len(np.where((np.array(function[i_l]) == ['-',i]).all(axis=1))[0])>0:
                                            self.box_levels.append([-1,i_l])
                                            #print i, i_l, np.where((np.array(function[i_l]) == ['-',i]).all(axis=1))[0], np.where((np.array(function[i_l]) == ['+',i]).all(axis=1))[0]
                                            #raw_input()
                                            found = True
                                        else:
                                            #print 'skipping', i
                                            self.box_levels.append([0, -1])
                                            found = True
                        if not found:
                            self.box_levels.append([0, -1])
                    #print np.array(self.box_levels).shape
                    self.box_levels.extend(temp)
                    #print np.array(self.box_levels).shape
                    #print np.array(temp1).shape,self.boxes.shape, np.array(temp).shape
                    if len(temp1)>0:
                        self.boxes = np.concatenate((self.boxes,np.array(temp1)),axis=0)
                    #print self.boxes.shape
                    #print 'double: ', double
                    #self.level_functions = get_level_functions(self.levels,self.boxes, prune_tree_levels)

                    #gts = load.get_all_gts(self.img_nr)
                    #self.gt_overlaps = np.zeros((len(self.boxes),21))
                    #for i_b,b in enumerate(self.boxes):
                    #    for i_cls,cls_ in enumerate(gts):
                    #        overlap_cls = 0.0
                    #        for gt in gts[cls_]:
                    #            overlap_cls += get_overlap_ratio(gt, b)
                    #        self.gt_overlaps[i_b,i_cls+1] = overlap_cls

        
    def lookup_coords(self):
        #have to change level indexes because of rearranging in extraction
        levels_corrected = {}
        for level in self.levels:
            levels_corrected[level] = []
            for idx in self.levels[level]:
                coord = self.tree_boxes[idx]
                new_idx = self.boxes.tolist().index(coord.tolist())
                levels_corrected[level].append(new_idx)
        self.levels = levels_corrected

def get_level_functions(levels,coords, tree_size):
  #get level_function
  # format for each level: 1 row plus patches, one row - patches, i hope 100 terms is enough
  level_functions = np.zeros((tree_size * 2, 1000))
  for i_level in range(len(levels)):
    counter_plus = 0
    counter_minus = 0
    sets = levels[i_level]
    level_coords = []
    for i in levels[i_level]:
          level_coords.append(coords[i])
    combinations = list(itertools.combinations(sets, 2))
    overlaps = nx.Graph()
    for comb in combinations:
          set_ = []
          for c in comb:
              set_.append(coords[c])
          I = get_set_intersection(set_)
          if I != []:
              overlaps.add_edges_from([comb])
    index = {}
    nbrs = {}
    for u in overlaps:
        index[u] = len(index)
        # Neighbors of u that appear after u in the iteration order of G.
        nbrs[u] = {v for v in overlaps[u] if v not in index}


    queue = deque(([u], sorted(nbrs[u], key=index.__getitem__)) for u in overlaps)
    # Loop invariants:
    # 1. len(base) is nondecreasing.
    # 2. (base + cnbrs) is sorted with respect to the iteration order of G.
    # 3. cnbrs is a set of common neighbors of nodes in base.
    while queue:
        base, cnbrs = map(list, queue.popleft())
        I = [0,0,1000,1000]
        for c in base:
            if I != []:
               I = get_intersection(coords[c], I)
        if I != [] and I[1] != I[3] and I[0]!=I[2]:
              if I in np.array(coords):
                 ind = [list(c) for c in coords].index(I)
                 if len(base)%2==1:
                    level_functions[2*i_level,counter_plus] = ind
                    counter_plus += 1
                    if counter_plus > 999:
                        print 'more than 1000 terms'
                        exit()
                 elif len(base)%2==0:
                    level_functions[2*i_level+1,counter_minus] = ind
                    counter_minus += 1
                    if counter_minus > 999:
                        print 'more than 1000 terms'
                        exit()

              else:
                 print 'IEP: intersection not found', I
                 exit()
        for i, u in enumerate(cnbrs):
            # Use generators to reduce memory consumption.
            queue.append((chain(base, [u]),
                          filter(nbrs[u].__contains__,
                                 islice(cnbrs, i + 1, None))))
  return level_functions                