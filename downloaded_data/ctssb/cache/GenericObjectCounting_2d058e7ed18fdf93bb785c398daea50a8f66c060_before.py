import os
import Data
import numpy as np
import pandas as pd
import pickle
from scipy.misc import imread
from utils import extract_coords
#import sys
#sys.path.append('/var/scratch/tstahl/source')
#from pycocotools.coco import COCO
#import random
#import cv2


class Input:
    def __init__(self, mode, category, number_of_levels):
        self.mode = mode
        self.category = category
        if self.mode == 'grid':
            self.coord_path = 'bla'
            self.label_path = 'bla'
            self.feature_path = 'bla'
        elif self.mode == 'mscoco':
            self.coord_path = '/var/node436/local/tstahl/mscoco/SS_Boxes/%s.txt'
            self.label_path = 'bla'
            self.feature_path = 'bla'
            self.coco_train_set = COCO('/var/node436/local/tstahl/annotations/instances_train2014.json')
            self.coco_val_set = COCO('/var/node436/local/tstahl/annotations/instances_train2014.json')
            cats = self.coco_train_set.loadCats(self.coco_train_set.getCatIds())
            self.classes = [cat['name'] for cat in cats]
            print self.classes
        elif self.mode == 'trancos':
            self.coord_path = '/var/node436/local/tstahl/TRANCOS_v3/TRANCOS/SS_Boxes'
            self.label_path = 'bla'
            self.feature_path = 'bla'
        elif self.mode == 'blob':
            self.training_numbers = [1,2,3,5,6,7]
            self.val_numbers = [4,8]
        else:
            if self.mode == 'pascal':
                self.coord_path =  '/var/node436/local/tstahl/new_Resnet_features/2nd/coords/1-%s.csv'
                self.label_path =  '/var/node436/local/tstahl/Coords_prop_windows/Labels/Labels/%s_%s_partial.txt'
                self.feature_path = '/var/node436/local/tstahl/new_Resnet_features/2nd/1-%s.csv'
                self.coord_tree_path = '/var/node436/local/tstahl/Coords_prop_windows/%s.txt'
                self.scaler_category_path = '/var/node436/local/tstahl/models/scaler_%s_pascal.p'%(category)
            elif self.mode == 'dennis' or self.mode == 'gt':
                self.coord_path =  '/var/node436/local/tstahl/Coords_prop_windows/%s.txt'
                self.coord_tree_path = '/var/node436/local/tstahl/Coords_prop_windows/%s.txt'
                self.label_path =  '/var/node436/local/tstahl/Coords_prop_windows/Labels/Labels/%s_%s_partial.txt'
                self.feature_path = '/var/node436/local/tstahl/Features_prop_windows/SS_Boxes/%s.txt'
                self.intersection_feature_path = '/var/node436/local/tstahl/Features_prop_windows/Features_upper/sheep_%s_fully_cover_tree.txt'
                self.intersection_coords_path = '/var/node436/local/tstahl/Features_prop_windows/upper_levels/sheep_%s_fully_cover_tree.txt'
                self.scaler_path = '/var/node436/local/tstahl/models/scaler_dennis.p'
                self.scaler_category_path = '/var/node436/local/tstahl/models/scaler_%s_dennis.p'%(category)
                self.classifier_path = '/var/node436/local/tstahl/models/classifier_%s.p'%(category)
                self.classes = ['aeroplane', 'bicycle', 'bird', 'boat',
           'bottle', 'bus', 'car', 'cat', 'chair',
           'cow', 'diningtable', 'dog', 'horse',
           'motorbike', 'person', 'pottedplant',
            'sheep', 'sofa', 'train', 'tvmonitor']
                self.test_numbers, training_numbers_tmp = self.get_training_numbers()
                self.training_numbers, self.val_numbers = self.get_val_numbers(training_numbers_tmp)
            #self.category_train, self.category_val = self.get_category_imgs()
            #self.category_train_with_levels, self.category_val_with_levels = self.get_samples_with_number_of_levels(number_of_levels)

    def get_all_labels(self, img_nr, mode):
        all_labels = [0.0]
        if self.mode == 'dennis':
            cat = self.category
            for class_ in self.classes:
                self.category = class_
                l = self.get_label(img_nr)
                all_labels.append(l)
            self.category = cat
        elif self.mode == 'mscoco':
            for class_ in self.classes:
                if mode == 'train':
                    ann_id = self.coco_train_set.getAnnIds(imgIds=img_nr,catIds=self.coco_train_set.getCatIds(catNms=[class_]), iscrowd=None)
                    annos = self.coco_train_set.loadAnns(ann_id)
                elif mode == 'test':
                    ann_id = self.coco_val_set.getAnnIds(imgIds=img_nr,catIds=self.coco_train_set.getCatIds(catNms=[class_]), iscrowd=None)
                    annos = self.coco_val_set.loadAnns(ann_id)
                all_labels.append(len(annos))

        elif self.mode == 'trancos':
            with open('/var/node436/local/tstahl/TRANCOS_v3/images/image-%s-%s.txt'%(i_mode,format(img_nr, "06d"))) as f:
                for i, l in enumerate(f):
                    pass
            return np.array([i + 1])
        return np.array(all_labels)

    def get_all_gts(self, img_nr):
        all_gts = {}
        if self.mode == 'dennis':
            cat = self.category
            for i_c,class_ in enumerate(self.classes):
                self.category = class_
                l = self.get_gts(img_nr)
                all_gts[i_c] = l
            self.category = cat
        elif self.mode == 'mscoco':
            for i_c,class_ in enumerate(self.classes):
                ann_id = self.coco_set.getAnnIds(imgIds=img_nr,catIds=self.coco_set.getCatIds(catNms=[class_]), iscrowd=None)
                annos = self.coco_set.loadAnns(ann_id)
                all_gts[i_c] = len(annos)
        return all_gts
        
	#old
#    def get_intersection_features(self, img_nr):
#        assert self.mode == 'dennis'
#        features = []
#        f = open(self.intersection_feature_path%(format(img_nr, "06d")), 'r')
#        for i,line in enumerate(f):
#            str_ = line.rstrip('\n').split(',')  
#            ff = []
#            for s in str_:
#               ff.append(float(s))
#            features.append(ff)
#        return features

    def get_samples_with_number_of_levels(self, number_of_levels):
        imgs_with_levels_train = []
        imgs_with_levels_val = []
        for im in self.category_train:
            d = Data.Data(self, im, number_of_levels, None, 4096)
            if len(d.levels) >= number_of_levels:
                imgs_with_levels_train.append(im)
        for im in self.category_val:
            d = Data.Data(self, im, number_of_levels, None, 4096)
            if len(d.levels) >= number_of_levels:
                imgs_with_levels_val.append(im)
        return imgs_with_levels_train, imgs_with_levels_val


    def get_gts(self, img_nr):
        gr = []
        if os.path.isfile('/var/node436/local/tstahl/GroundTruth/%s/%s.txt'%(self.category,format(img_nr, "06d"))):
            gr = pd.read_csv('/var/node436/local/tstahl/GroundTruth/%s/%s.txt'%(self.category,format(img_nr, "06d")), header=None, delimiter=",").values
        return gr


    def get_get_features(self, img_nr):
        gr_f = []
        if os.path.isfile('/var/node436/local/tstahl/Features_groundtruth/Features_ground_truth/%s/%s.txt'%(self.category,format(img_nr, "06d"))):
            gr_f = pd.read_csv('/var/node436/local/tstahl/Features_groundtruth/Features_ground_truth/%s/%s.txt'%(self.category,format(img_nr, "06d")), header=None, delimiter=",").values
        return gr_f



    def get_intersection_features(self, img_nr):
	if os.stat(self.intersection_feature_path%(format(img_nr, "06d"))).st_size > 0:
		if os.path.isfile(self.intersection_feature_path%(format(img_nr, "06d"))):
		    ret = pd.read_csv(self.intersection_feature_path%(format(img_nr, "06d")), header=None, delimiter=",").values
		    return ret
		else:
		     print 'warning ' + self.intersection_feature_path%(format(img_nr, "06d")) + 'does not exist'
		     exit()   
	else:
		return []
    
    def get_scaler(self):
        if os.path.isfile(self.scaler_path):
            with open(self.scaler_path, 'rb') as handle:
                scaler = pickle.load(handle)
                return scaler
        else:
            return []
         
    def get_scaler_category(self):
    	if os.path.isfile(self.scaler_category_path):
    		with open(self.scaler_category_path, 'rb') as handle:
    		    scaler = pickle.load(handle)
    	else:
    		scaler = []
        return scaler
         
    def get_classifier(self):
         with open(self.classifier_path, 'rb') as handle:
            classifier = pickle.load(handle)
         return classifier
         
        
    def get_intersection_coords(self, img_nr):
        assert self.mode == 'dennis'
        coords = []
        f_c = open(self.intersection_coords_path%(format(img_nr, "06d")), 'r')
        for i,line in enumerate(f_c):
            str_ = line.rstrip('\n').split(',')
            cc = []
            for s in str_:
               cc.append(float(s))
            coords.append(cc)
        return coords
        
        
    def get_category_imgs(self):
        tr_images = []
        te_images = []
        for img in self.training_numbers:
            y = self.get_label(img)
            if y > 0:
                tr_images.append(img)
        for img in self.val_numbers:
            y = self.get_label(img)
            if y > 0:
                te_images.append(img)
        return tr_images, te_images
                
    def get_training_numbers(self):     
        if self.mode == 'pascal' or self.mode == 'dennis' or self.mode == 'gt':
            file = open('/var/scratch/tstahl/IO/test.txt')
            test_imgs = []
            train_imgs = []
            for line in file:
                test_imgs.append(int(line))
            for i in range(1,9963):
                if i not in test_imgs:
                    train_imgs.append(i)
            return test_imgs, train_imgs
        
    def get_val_numbers(self, train_imgs):
        if self.mode == 'pascal' or self.mode == 'dennis' or self.mode == 'gt':
            file = open('/var/scratch/tstahl/IO/val.txt', 'r')
            eval_images = []
            for line in file:
                im_nr = int(line)
                eval_images.append(im_nr)
            return [x for x in train_imgs if x not in eval_images], eval_images
    
    def get_coords(self, img_nr):
        if self.mode == 'dennis':
            if os.path.isfile(self.coord_path%(format(img_nr, "06d"))):
                ret = np.loadtxt(self.coord_path%(format(img_nr, "06d")), delimiter=',')
                return ret
        elif self.mode == 'mscoco':
            if os.path.isfile(self.coord_path%(format(img_nr, "012d"))):
                ret = np.loadtxt(self.coord_path%(format(img_nr, "012d")), delimiter=',')
                if isinstance(ret[0], np.float64):
                    return np.array([ret])
                else:
                    return ret
            else:
                print img_nr,
                return []

    def get_coords_tree(self, img_nr):
        if os.path.isfile(self.coord_tree_path%(format(img_nr, "06d"))):
            ret = np.loadtxt(self.coord_tree_path%(format(img_nr, "06d")), delimiter=',')
            if isinstance(ret[0], np.float64):
                return np.array([ret])
            else:
                return ret
            
      
	#old      
#    def get_coords_tree(self, img_nr):
#        if os.path.isfile(self.coord_tree_path%(format(img_nr, "06d"))):
#            f = open(self.coord_tree_path%(format(img_nr, "06d")), 'r')
#        else:
#            print 'warning, no ' + self.coord_tree_path%(format(img_nr, "06d"))
#            exit()
#        boxes = []
#        for line in f:
#            tmp = line.split(',')
#            coord = []
#            for s in tmp:
#                coord.append(float(s))
#            boxes.append(coord)
#        return boxes
        
    def get_features(self, img_nr):
        if os.path.isfile(self.feature_path%(format(img_nr, "06d"))):
            #ret = np.loadtxt(self.feature_path%(format(img_nr, "06d")), delimiter=',')
            ret = pd.read_csv(self.feature_path%(format(img_nr, "06d")), header=None, delimiter=",").values
            #ret = np.loadtxt(self.feature_path%(format(img_nr, "06d")), delimiter=',')
            #print len(ret)
            #if isinstance(ret[0], np.float64):
            #    return np.array([ret])
            #else:
            return ret
        else:
             print 'warning ' + self.feature_path%(format(img_nr, "06d")) + 'does not exist'
             exit()
        

    def get_label(self, img_nr):
        if os.path.isfile(self.label_path%(format(img_nr, "06d"),self.category)):
            file = open(self.label_path%(format(img_nr, "06d"),self.category), 'r')
        else:
            print 'warning ' + (self.label_path%(format(img_nr, "06d"),self.category)) + ' does not exist '
            exit()
        line = file.readline()
        tmp = line.split()[0]
        label = float(tmp)
        return label

    def get_coords_blob(self, img_nr):
        if os.path.isfile('/var/node436/local/tstahl/Dummy/%s.txt'%(format(img_nr, "02d"))):
            ret = np.loadtxt('/var/node436/local/tstahl/Dummy/%s.txt'%(format(img_nr, "02d")), delimiter=',')
            if isinstance(ret[0], np.float64):
                return np.array([ret])
            else:
                return ret

    def get_label_blob(self, img_nr):
        if img_nr == 1:
            return 1
        elif img_nr == 2:
            return 2
        elif img_nr == 3:
            return 3
        elif img_nr == 4:
            return 5
        elif img_nr == 5:
            return 5
        elif img_nr == 6:
            return 7
        elif img_nr == 7:
            return 7
        elif img_nr == 8:
            return 9

    def get_features_blob(self, img_nr, boxes):
        im = imread('/var/node436/local/tstahl/Dummy/%s.png'%(format(img_nr, "02d")), mode='L')
        #im = cv2.imread('/var/node436/local/tstahl/Dummy/%s.png'%(format(img_nr, "02d")), 0)
        #assert np.array_equal(im[:,:,0], im[:,:,1])
        #assert np.array_equal(im[:,:,1], im[:,:,2])
        #im = im[:,:,0]
        #im = 255 - im
        #x = [x0, x1, x2]
        #x0 = average intensity value in the bounding box.
        #x1 = width of the boundig box
        #x2 = height of the bounding box. 
        features = []
        for box in boxes:
            cropped = im[box[1]:box[1]+box[3], box[0]:box[0]+box[2]]
            ff = []
            ff.append(np.sum(cropped))
            ff.append(box[0]+box[2])
            ff.append(box[1]+box[3])
            # adding Gaussian noise with a sigma of 10
            features.append(np.array(ff) + np.random.normal(10,1,3))
        return np.array(features)

    def get_intersections_blob(self, levels, boxes):
        intersection_coords = []
        for level_numbers in levels.values():
            intersection_coords.extend(extract_coords(level_numbers, boxes))
        return np.array(intersection_coords)

    def get_grid(self, img_nr):
        feat = self.get_features(img_nr)[0]
        for grid in ['12','22','44']:
            if os.path.isfile('/var/node436/local/tstahl/Hard_partitioned_Features/new_Features/%sx%s.txt'%(grid,format(img_nr, "06d"))):
                ret = np.loadtxt('/var/node436/local/tstahl/Hard_partitioned_Features/new_Features/%sx%s.txt'%(grid,format(img_nr, "06")), delimiter=',')
                feat = np.vstack((feat,ret))
        if os.path.isfile('/var/node436/local/tstahl/Hard_partitioned_Features/%s3x3.txt'%(format(img_nr, "06d"))):
            ret = np.loadtxt('/var/node436/local/tstahl/Hard_partitioned_Features/%s3x3.txt'%(format(img_nr, "06d")), delimiter=',')
            feat = np.vstack((feat,ret))
        return feat

    def get_grid_coords(self, img_nr):
        grid_coords = get_coords(self, img_nr)[0]
        #full,1x2,2x2,3x3,4x4
        for grid in ['1x2','2x2','3x3','4x4']:
            if os.path.isfile('/var/node436/local/tstahl/Hard_partitioned_Coords/%s%s.txt'%(format(img_nr, "06d"),grid)):
                ret = np.loadtxt('/var/node436/local/tstahl/Hard_partitioned_Coords/%s%s.txt'%(format(img_nr, "06"),grid), delimiter=',')
                feat = np.vstack((feat,ret))
            else:
                print 'grid coords not found for ', img_nr
                exit()