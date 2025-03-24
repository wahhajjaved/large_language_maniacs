#!/usr/bin/python
# Copyright 2010 Google Inc.
# Licensed under the Apache License, Version 2.0
# http://www.apache.org/licenses/LICENSE-2.0

# Google's Python Class
# http://code.google.com/edu/languages/google-python-class/

import sys
import re
import os
import shutil
import commands
import subprocess

"""Copy Special exercise
"""

# +++your code here+++
# Write functions and modify main() to call them

def get_special_paths(dirs):
    '''
    XX Gather a list of the absolute paths of the special files in all the directories.
    XX In the simplest case, just print that list (here the "." after the command is a 
    XX    single argument indicating the current directory). Print one absolute path per line.
    XX We'll assume that names are not repeated across the directories
    XX    (optional: check that assumption and error out if it's violated).
    '''
    
    # use ox.path to navigate to dir (http://docs.python.org/2/library/os.path.html)
    # use os.path.abspath(path) to get the absolute path
    #
    # use os.listdir(path) to get the files in the dir (http://docs.python.org/2/library/os.html#os.listdir)
    special_files = []
    file_list = []
    for dir in dirs:
        absolute_dir = os.path.abspath(dir)
        files = os.listdir(absolute_dir)
        for file in files:
            if file not in file_list:
                first = file.find('__')
                if first != -1:
                    second = file.find('__', first + 2)
                    if second != -1:
                        file_list.append(file)
                        special_files.append(absolute_dir + '/' + file)
                        #print absolute_dir + '/' + file
            else:
                sys.stderr.write('ERROR: File ' + file + ' is not special\n')
                sys.exit(1)
    return special_files


def copy_special_to_dir(todir, dirs):
    '''
    XX If the "--todir dir" option is present at the start of the command line, do not print anything and instead copy the files to the given directory, creating it if necessary.
    '''
    if not os.path.exists(os.path.abspath(todir)):
        os.makedirs(os.path.abspath(todir))
    files = get_special_paths(dirs)
    for file in files:
        shutil.copy(file, os.path.abspath(todir))


def copy_special_to_zip(tozip, dirs):
    '''
    XX If the "--tozip zipfile" option is present at the start of the command line,
    XX    run this command: "zip -j zipfile <list all the files>"
    XX Also print the command line you are going to do first (as shown in lecture)
    XX If the child process exits with an error code, exit with an error code and print the command's output
    XX Test this by trying to write a zip file to a directory that does not exist
    '''
    # uncertain if i'm supposed to make directories that do not exist, but the following is how i would...including get_zip_dir
    #zipdir = get_zip_dir(tozip)
    #if zipdir and not os.path.exists(zipdir): os.makedirs(zipdir)
    files = get_special_paths(dirs)
    if files:
        output_command = 'zip -j ' + tozip
        for file in files:
            output_command += ' ' + file
        print "Command I'm going to do: " + output_command
        subprocess.call(output_command, shell=True)
    else:
        sys.stderr.write('ERROR: No special files\n')
        sys.exit(1)

# see comment about uncertainty on line 74
def get_zip_dir(full_zip_filename):
    '''
    returns absolute_path
    '''
    last_slash = full_zip_filename.rfind('/')
    if last_slash == -1 or last_slash == 0:
        return None
    else:
        return os.path.abspath(full_zip_filename[ : last_slash])


def main():
  # This basic command line argument parsing code is provided.
  # Add code to call your functions below.

  # Make a list of command line arguments, omitting the [0] element
  # which is the script itself.
  args = sys.argv[1:]
  if not args:
    print "usage: [--todir dir][--tozip zipfile] dir [dir ...]";
    sys.exit(1)

  # todir and tozip are either set from command line
  # or left as the empty string.
  # The args array is left just containing the dirs.
  todir = ''
  if args[0] == '--todir':
    todir = args[1]
    del args[0:2]

  tozip = ''
  if args[0] == '--tozip':
    tozip = args[1]
    del args[0:2]

  if len(args) == 0:
    print "error: must specify one or more dirs"
    sys.exit(1)
    

  # +++your code here+++
  # Call your functions
  if todir: copy_special_to_dir(todir, args)
  if tozip: copy_special_to_zip(tozip, args)
  
if __name__ == "__main__":
  main()
