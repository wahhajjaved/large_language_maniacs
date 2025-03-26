import tensorflow as tf
import numpy as np
import cv2

class Object_Detector():
    def __init__(self, graph_path, session=None):
        self.graph_path = graph_path
        detection_graph = tf.Graph()
        with detection_graph.as_default():
            od_graph_def = tf.GraphDef()
            with tf.gfile.GFile(graph_path, 'rb') as fid:
                serialized_graph = fid.read()
                od_graph_def.ParseFromString(serialized_graph)
                tf.import_graph_def(od_graph_def, name='')

        self.detection_graph = detection_graph

        if not session:
            config = tf.ConfigProto()
            config.gpu_options.allow_growth = True
            
            session = tf.Session(graph=detection_graph, config=config)
        self.session = session

    def detect_objects_in_np(self, image_np):
        '''
        Runs the object detection on a single image or a batch of images.
        image_np can be a batch or a single image with batch dimension 1, dims:[None, None, None, 3]
        Returned boxes are top, left, bottom, right = current_bbox
        '''
        image_tensor = self.detection_graph.get_tensor_by_name('image_tensor:0')
        # Each box represents a part of the image where a particular object was detected.
        boxes = self.detection_graph.get_tensor_by_name('detection_boxes:0')
        # Each score represent how level of confidence for each of the objects.
        # Score is shown on the result image, together with the class label.
        scores = self.detection_graph.get_tensor_by_name('detection_scores:0')
        classes = self.detection_graph.get_tensor_by_name('detection_classes:0')
        num_detections = self.detection_graph.get_tensor_by_name('num_detections:0')
        # Actual detection.
        (boxes, scores, classes, num_detections) = self.session.run(
            [boxes, scores, classes, num_detections],
            feed_dict={image_tensor: image_np[:,:,:,:]})
    
        return boxes,scores,classes,num_detections

    def detect_objects_in_tf(self):
        '''
        Returns the tensor pointers for the object detection inputs and outputs
        image_tensor can be a batch or a single image with batch dimension 1, dims:[None, None, None, 3]
        Returned boxes are top, left, bottom, right = current_bbox
        '''
        image_tensor = self.detection_graph.get_tensor_by_name('image_tensor:0')
        # Each box represents a part of the image where a particular object was detected.
        boxes = self.detection_graph.get_tensor_by_name('detection_boxes:0')
        # Each score represent how level of confidence for each of the objects.
        # Score is shown on the result image, together with the class label.
        scores = self.detection_graph.get_tensor_by_name('detection_scores:0')
        classes = self.detection_graph.get_tensor_by_name('detection_classes:0')
        num_detections = self.detection_graph.get_tensor_by_name('num_detections:0')

        return image_tensor, boxes, scores, classes, num_detections


class Tracker():
    def __init__(self):
        self.active_actors = []
        self.inactive_actors = []
        self.actor_no = 0
        self.frame_history = []
        self.timesteps = 32

    def update_tracker(self, detection_info, frame):
        # filter out non-persons or less than threshold
        score_th = 0.30

        boxes, scores, classes, num_detections = detection_info
        indices = np.logical_and(scores > score_th, classes == 1)
        filtered_boxes, filtered_scores = boxes[indices], scores[indices]

        IoU_th = 0.4
        matched_indices = []
        lost_actors = []
        for aa in range(len(self.active_actors)):
            current_actor = self.active_actors[aa]
            IoUs = []
            for bb in range(filtered_boxes.shape[0]):
                cur_box = filtered_boxes[bb]
                IoU = IoU_box(cur_box, current_actor['all_boxes'][-1])
                IoUs.append(IoU)
            
            if np.max(IoUs) > IoU_th:
                # update current actor
                matched_idx = np.argmax(IoUs)
                matched_indices.append(matched_idx)
                current_actor['all_boxes'].append(filtered_boxes[matched_idx])
                current_actor['all_scores'].append(filtered_scores[matched_idx])
                current_actor['length'] += 1
            else:
                lost_actors.append(aa)
                self.inactive_actors.append(current_actor)
        
        # remove unmatched actors
        for ii in sorted(lost_actors, reverse=True):
            del self.active_actors[ii]

        # add new detected actors
        for bb in range(filtered_boxes.shape[0]):
            if bb in matched_indices:
                continue
            
            actor_info = {}
            actor_info['all_boxes'] = [filtered_boxes[bb]]
            actor_info['all_scores'] = [filtered_scores[bb]]
            actor_info['length'] = 1
            actor_info['actor_id'] = self.actor_no
            self.actor_no += 1
            self.active_actors.append(actor_info)

        if len(self.frame_history) == 32:
            del self.frame_history[0]
            self.frame_history.append(frame)
        else:
            self.frame_history.append(frame)
        
    def crop_person_tube(self, actor_id, box_size=(400,400)):
        actor_info = [act for act in self.active_actors if act['actor_id'] == actor_id][0]
        boxes = actor_info['all_boxes']
        if actor_info['length'] < self.timesteps:
            recent_boxes = boxes
            index_offset = (self.timesteps - actor_info['length']) // 2 
        else:
            recent_boxes = boxes[-self.timesteps:]
            index_offset = 0
        H,W,C = self.frame_history[-1].shape
        mid_box = recent_boxes[len(recent_boxes)//2]
        # top, left, bottom, right = mid_box
        # edge = max(bottom - top, right - left) / 2.
        edge, norm_roi = generate_edge_and_normalized_roi(mid_box)

        tube = np.zeros([self.timesteps] + list(box_size) + [3])
        for rr in range(len(recent_boxes)):
            cur_box = recent_boxes[rr]
            # zero pad so that we dont have to worry about edge cases
            cur_frame = self.frame_history[rr]
            padsize = int(edge * max(H,W))
            cur_frame = np.pad(cur_frame, [(padsize,padsize),(padsize,padsize), (0,0)], 'constant')

            top, left, bottom, right = cur_box
            cur_center = (top+bottom)/2., (left+right)/2.
            top, bottom = cur_center[0] - edge, cur_center[0] + edge
            left, right = cur_center[1] - edge, cur_center[1] + edge

            top_ind, bottom_ind = int(top * H)+padsize, int(bottom * H)+padsize
            left_ind, right_ind = int(left * W)+padsize, int(right * W)+padsize
            cur_image_crop = cur_frame[top_ind:bottom_ind, left_ind:right_ind]
            tube[rr+index_offset,:,:,:] = cv2.resize(cur_image_crop, box_size)

        return tube, norm_roi

def generate_edge_and_normalized_roi(mid_box):
    top, left, bottom, right = mid_box

    edge = max(bottom - top, right - left) / 2. * 1.5 # change this to change the size of the tube

    cur_center = (top+bottom)/2., (left+right)/2.
    context_top, context_bottom = cur_center[0] - edge, cur_center[0] + edge
    context_left, context_right = cur_center[1] - edge, cur_center[1] + edge

    normalized_top = (top - context_top) / (2*edge)
    normalized_bottom = (bottom - context_top) / (2*edge)

    normalized_left = (left - context_left) / (2*edge)
    normalized_right = (right - context_left) / (2*edge)

    norm_roi = [normalized_top, normalized_left, normalized_bottom, normalized_right]

    return edge, norm_roi




        

def IoU_box(box1, box2):
    '''
    returns intersection over union
    '''
    top1, left1, bottom1, right1 = box1
    top2, left2, bottom2, right2 = box2
    
    left_int = max(left1, left2)
    top_int = max(top1, top2)
 
    right_int = min(right1, right2)
    bottom_int = min(bottom1, bottom2)
 
    areaIntersection = max(0, right_int - left_int) * max(0, bottom_int - top_int)
 
    area1 = (right1 - left1) * (bottom1 - top1)
    area2 = (right2 - left2) * (bottom2 - top2)
     
    IoU = areaIntersection / float(area1 + area2 - areaIntersection)
    return IoU     

OBJECT_STRINGS = \
{1: {'id': 1, 'name': u'person'},
 2: {'id': 2, 'name': u'bicycle'},
 3: {'id': 3, 'name': u'car'},
 4: {'id': 4, 'name': u'motorcycle'},
 5: {'id': 5, 'name': u'airplane'},
 6: {'id': 6, 'name': u'bus'},
 7: {'id': 7, 'name': u'train'},
 8: {'id': 8, 'name': u'truck'},
 9: {'id': 9, 'name': u'boat'},
 10: {'id': 10, 'name': u'traffic light'},
 11: {'id': 11, 'name': u'fire hydrant'},
 13: {'id': 13, 'name': u'stop sign'},
 14: {'id': 14, 'name': u'parking meter'},
 15: {'id': 15, 'name': u'bench'},
 16: {'id': 16, 'name': u'bird'},
 17: {'id': 17, 'name': u'cat'},
 18: {'id': 18, 'name': u'dog'},
 19: {'id': 19, 'name': u'horse'},
 20: {'id': 20, 'name': u'sheep'},
 21: {'id': 21, 'name': u'cow'},
 22: {'id': 22, 'name': u'elephant'},
 23: {'id': 23, 'name': u'bear'},
 24: {'id': 24, 'name': u'zebra'},
 25: {'id': 25, 'name': u'giraffe'},
 27: {'id': 27, 'name': u'backpack'},
 28: {'id': 28, 'name': u'umbrella'},
 31: {'id': 31, 'name': u'handbag'},
 32: {'id': 32, 'name': u'tie'},
 33: {'id': 33, 'name': u'suitcase'},
 34: {'id': 34, 'name': u'frisbee'},
 35: {'id': 35, 'name': u'skis'},
 36: {'id': 36, 'name': u'snowboard'},
 37: {'id': 37, 'name': u'sports ball'},
 38: {'id': 38, 'name': u'kite'},
 39: {'id': 39, 'name': u'baseball bat'},
 40: {'id': 40, 'name': u'baseball glove'},
 41: {'id': 41, 'name': u'skateboard'},
 42: {'id': 42, 'name': u'surfboard'},
 43: {'id': 43, 'name': u'tennis racket'},
 44: {'id': 44, 'name': u'bottle'},
 46: {'id': 46, 'name': u'wine glass'},
 47: {'id': 47, 'name': u'cup'},
 48: {'id': 48, 'name': u'fork'},
 49: {'id': 49, 'name': u'knife'},
 50: {'id': 50, 'name': u'spoon'},
 51: {'id': 51, 'name': u'bowl'},
 52: {'id': 52, 'name': u'banana'},
 53: {'id': 53, 'name': u'apple'},
 54: {'id': 54, 'name': u'sandwich'},
 55: {'id': 55, 'name': u'orange'},
 56: {'id': 56, 'name': u'broccoli'},
 57: {'id': 57, 'name': u'carrot'},
 58: {'id': 58, 'name': u'hot dog'},
 59: {'id': 59, 'name': u'pizza'},
 60: {'id': 60, 'name': u'donut'},
 61: {'id': 61, 'name': u'cake'},
 62: {'id': 62, 'name': u'chair'},
 63: {'id': 63, 'name': u'couch'},
 64: {'id': 64, 'name': u'potted plant'},
 65: {'id': 65, 'name': u'bed'},
 67: {'id': 67, 'name': u'dining table'},
 70: {'id': 70, 'name': u'toilet'},
 72: {'id': 72, 'name': u'tv'},
 73: {'id': 73, 'name': u'laptop'},
 74: {'id': 74, 'name': u'mouse'},
 75: {'id': 75, 'name': u'remote'},
 76: {'id': 76, 'name': u'keyboard'},
 77: {'id': 77, 'name': u'cell phone'},
 78: {'id': 78, 'name': u'microwave'},
 79: {'id': 79, 'name': u'oven'},
 80: {'id': 80, 'name': u'toaster'},
 81: {'id': 81, 'name': u'sink'},
 82: {'id': 82, 'name': u'refrigerator'},
 84: {'id': 84, 'name': u'book'},
 85: {'id': 85, 'name': u'clock'},
 86: {'id': 86, 'name': u'vase'},
 87: {'id': 87, 'name': u'scissors'},
 88: {'id': 88, 'name': u'teddy bear'},
 89: {'id': 89, 'name': u'hair drier'},
 90: {'id': 90, 'name': u'toothbrush'}}
