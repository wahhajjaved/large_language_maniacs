import keras 
import numpy as np
import pandas as pd
import cv2
import os
import json
import PIL
import pdb
import argparse
import math
from shutil import rmtree
import pandas as pd

from sklearn import metrics

import keras.backend as K
from keras.utils.generic_utils import CustomObjectScope
from keras.callbacks import ProgbarLogger, TensorBoard, ReduceLROnPlateau, EarlyStopping, ModelCheckpoint
from keras.models import Model
from keras.layers import Input, Dense
from keras.optimizers import SGD
from keras.applications.inception_v3 import InceptionV3, preprocess_input as inception_pre
from keras.applications.mobilenet import MobileNet, relu6, DepthwiseConv2D, preprocess_input as mobilenet_pre
from keras.applications.resnet50 import ResNet50, preprocess_input as resnet_pre
from keras.applications.densenet import DenseNet121, preprocess_input as densnet_pre
from datagenerator import ImageDataGenerator
import tensorflow as tf

from train_one_teacher import load_filelist, AUC, mean_AUC

def load_model(model_dir):

	with open(os.path.join(model_dir, 'model_config.json'), 'r') as f:
		model_config = json.load(f)

	ckpts = [x for x in os.listdir(model_dir) if 'hdf5' in x]

	ckpts.sort()

	custom_objects = {'auc': auc, 'mauc': auc}

	if model_config['model_name'] == 'mobilenet':
		custom_objects['relu6'] = relu6
		custom_objects['DepthwiseConv2D'] = DepthwiseConv2D

	model = keras.models.load_model(os.path.join(model_dir, ckpts[-1]), custom_objects = custom_objects)

	return model, model_config


def auc(labels, predictions):
	score, up_opt = tf.metrics.auc(labels, predictions)
	K.get_session().run(tf.local_variables_initializer())
	with tf.control_dependencies([up_opt]):
		score = tf.identity(score)
	return score


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument('--model_dir', help = 'Directory to model weights and config.')
	ap.add_argument('--data_dir', help = 'Directory to the file lists and labels.')
	ap.add_argument('--image_dir', help = 'Directory to the raw images.')
	ap.add_argument('--partition_id', type = int, default = 1,
					help = 'Partition index (1-based).')
	ap.add_argument('--partition_num', type = int, default = 1,
					help = 'Number of partitions.')
	ap.add_argument('--split_name', help = "Dataset split to evaluate on. Either 'val' or 'test'.")
	ap.add_argument('--batch_size', type = int, default = 32)

	args = ap.parse_args()

	with open(os.path.join(args.data_dir, 'label_map.json'), 'r') as f:
		label_map = json.load(f)

	num_class = len(list(label_map.keys()))

	model, model_config = load_model(args.model_dir)

	model_name = model_config['model_name']

	if model_name in ['inception']:
		image_size = 299

	elif model_name in ['resnet', 'mobilenet', 'densenet']:
		image_size = 224

	preprocess_input = {
		'inception': inception_pre,
		'resnet': resnet_pre,
		'mobilenet': mobilenet_pre,
		'densenet': densnet_pre
	}

	datagen = ImageDataGenerator(preprocessing_function = preprocess_input[model_name])

	X, Y = load_filelist(args.data_dir, args.split_name, args.partition_id, args.partition_num)

	predictions = model.predict_generator(datagen.flow_from_list(x = X, directory = args.image_dir,
								batch_size = args.batch_size, target_size = (image_size, image_size),
								shuffle = False))

	labels = np.array(Y)

	auc_scores = {}

	for key, value in label_map.items():
		pred = predictions[:,int(key)]
		label = labels[:,int(key)]

		if len(np.unique(label)) == 1:
			auc_scores[value] = np.nan

		else:
			auc_scores[value] = metrics.roc_auc_score(label, pred)

	with open(os.path.join(args.model_dir, 'auc_scores.json'), 'w') as f:
		json.dump(auc_scores, f)


if __name__ == "__main__":
	main()


