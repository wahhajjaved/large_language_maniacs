#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""=================================================
@Project -> File   ：tools -> FOP.py
@IDE    : Pycharm
@Author : Qi Shuo
@Date   : 2019-6-18
@Intro  : File Operations
=================================================="""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os

import pandas as pd
import glob
import json
import logging


def get_files_from_path(path, recurse=False, full_path=True):
    """
    Get Files_Path From Input Path
    :param full_path: Full path flag
    :param path: Input Path
    :param recurse: Whether Recursive
    :return: List of Files_Path
    """
    files_path_list = []
    if not os.path.exists(path):
        return []
    for file_path in os.listdir(path):
        if not full_path:
            file_path = os.path.join(path, file_path)
        if os.path.isdir(file_path):
            if recurse:
                files_path_list += get_files_from_path(file_path, recurse=True)
            else:
                pass
        else:
            files_path_list.append(file_path)
    return files_path_list


def get_dirs_from_path(path, recurse=False):
    """
    Get Dirs_Path From Input Path
    :param path: Input Path
    :param recurse: Whether Recursive
    :return: List of Dirs_Path
    """
    dirs_path_list = []
    if not os.path.exists(path):
        return []
    for each_dir in os.listdir(path):
        dir_path = os.path.join(path, each_dir)
        if os.path.isdir(dir_path):
            dirs_path_list.append(dir_path)
            if recurse:
                dirs_path_list += get_dirs_from_path(dir_path, recurse=True)
    return dirs_path_list


def get_images_from_path(path, suffix=None):
    """
    Get images from path
    :param suffix: Image suffix list , such as : ['jpg', 'png', 'jpeg', 'JPG']
    :param path: Input path
    :return: List of images
    """
    images_path_list = []
    if suffix is None:
        suffix = ['jpg', 'png', 'jpeg', 'JPG']
    for ext in suffix:
        images_path_list.extend(glob.glob(
            os.path.join(path, '*.{}'.format(ext))))
    return images_path_list


def read_text_file_to_list(file_path, separator, op=None):
    """
    Read the file contents to list
    Split by "separator"
    Operate on each element with "op"
    :param file_path: Input File Path
    :param separator: Separator for each line
    :param op: Operations on each element
    :return: List of file
    """
    split_data_list = []
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r") as file:
        the_number_of_rows = 0
        for line in file.readlines():
            the_number_of_rows += 1
            split_data = line.strip().split(separator)
            if op is not None:
                try:
                    split_data = list(map(op, split_data))
                except Exception as e:
                    print("\033[1;33;0mERROR : {} with line {}\033[0m".format(e, the_number_of_rows))
                else:
                    pass
            split_data_list.append(split_data)
    return split_data_list


def read_excel_file_to_dict(file_path, sheet_name=None, op=None):
    """
    Read the excel file contents to dict(multi sheet)
    :param file_path: Excel file path
    :param sheet_name: Sheet name list
    :param op: Operations on each element
    :return: Dict of excel file
    """
    excel_data_dict = {}
    if not os.path.exists(file_path):
        return {}
    sheet = pd.read_excel(file_path, sheet_name=sheet_name)
    for name, value in sheet.items():
        excel_data_list = value.values.tolist()
        if op is not None:
            try:
                excel_data_list = list(map(op, excel_data_list))
            except Exception as e:
                print("\033[1;33;0mERROR : {}\033[0m".format(e))
            else:
                pass
        excel_data_dict.setdefault(name, excel_data_list)
    return excel_data_dict


def read_json_file_to_dict(file_path):
    """
    Read json file to dict
    :param file_path: Json file path
    :return: Dict of json file
    """
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r") as json_file:
        data = json_file.read()
        return json.loads(data)


def write_dict_to_json_file(in_dict, out_file_path):
    """
    Write dict to json file
    :param in_dict: Input Dict data
    :param out_file_path: Output json file path
    :return: None
    """
    with open(out_file_path, "w") as json_file:
        json_file.write(json.dumps(in_dict))


class Logger(object):

    def __init__(self, file_path, file_mode='a'):
        """
        Initialize the log class
        :param file_path: Log file path
        :param file_mode: Open File mode
        """
        logging.basicConfig(filename=file_path,
                            filemode=file_mode,
                            level=logging.INFO,
                            format='%(message)s')

    @staticmethod
    def out_print(in_list, separator=","):
        """
        Print output to file
        :param in_list: Input data list
        :param separator: Separator for each item
        :return: None
        """
        logging.info("[{}]".format(separator.join(list(map(str, in_list)))))


if __name__ == "__main__":
    print(get_images_from_path("./"))

