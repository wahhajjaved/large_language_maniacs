#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May 15 22:03:26 2017

@author: kasparov092
"""
import cv2
import numpy as np
import os
import Util as utl

def select_frame_from_video(video_path, selected_frame, output_path):
    vidcap = cv2.VideoCapture(video_path)
    success,image = vidcap.read()
    count = 0;
    
    while success:
        count += 1
        
        if count == selected_frame:
            fileName = video_path[video_path.rfind('/')+1:video_path.rfind('.')];
            category_name = video_path.split('/')
            category_name = category_name[len(category_name)-2]

            full_folder_path = output_path+category_name+'/'+fileName
            full_file_path = full_folder_path+'/{:06}'.format(count)+".jpg"

            if not os.path.exists(full_folder_path):
                if not os.path.exists(output_path+category_name+'/'):
                    os.mkdir(output_path+category_name+'/')
                os.mkdir(full_folder_path+'/')
            
            cv2.imwrite(full_file_path, image)    # save frame as JPEG file
            break;
            
        success, image = vidcap.read()

#-----------------------------------------------------------------------------------------------

def select_all_frames_from_video(video_path, output_path):
    video_name = utl.get_file_name_from_path_without_extention(video_path)
    video_category = utl.get_direct_folder_containing_file(video_path)

    save_frame_path = os.path.join(output_path, video_category, video_name )

    vidcap = cv2.VideoCapture(video_path)
    success, image = vidcap.read()
    count = 0;

    if not os.path.exists(output_path + video_category + '/'):
        os.mkdir(output_path + '/' + video_category + '/')

    if not os.path.exists(save_frame_path):
        os.mkdir(save_frame_path)

    while success:
        count += 1
        save_frame_full_path = save_frame_path + '/{:06}'.format(count) + ".jpg"
        cv2.imwrite(save_frame_full_path, image)  # save frame as JPEG file
        success, image = vidcap.read()

#-----------------------------------------------------------------------------------------------

#select_frame_from_video('/home/kasparov092/sources/c3d/data/UCF-101/ApplyEyeMakeup/v_ApplyEyeMakeup_g01_c01.avi',
#                        1,
#                        '/home/kasparov092/Desktop/UCF101_Frames/')