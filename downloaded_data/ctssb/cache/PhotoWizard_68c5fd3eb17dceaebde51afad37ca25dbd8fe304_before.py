#/////////////////////////////#
# - P H O T O   W I Z A R D - #
#\\\\\\\\\\\\\\\\\\\\\\\\\\\\\#

# -*- coding: utf-8 -*-

# This module contains several useful tools


import sys,re,os,numpy
sys.path.insert(0,'utils')
from scipy import ndimage
from history import History,Event
from PIL import Image
from config import *




def getChannel(image,channel): # Channel can be H, S, V, R, G, B or ALL - Note: if BW, should use V or ALL?
 
    if isinstance(image,Image.Image) and (type(channel) is str):
        if len(channel) == 1:
            if channel == 'H':
                image = image.convert('HSV')
                image = numpy.asarray(image,dtype=numpy.uint8)
                image = [image[:,:,0]]
            elif channel == 'S':
                image = image.convert('HSV')
                image = numpy.asarray(image,dtype=numpy.uint8)
                image = [image[:,:,1]]
            elif channel == 'V':
                image = image.convert('HSV')
                image = numpy.asarray(image,dtype=numpy.uint8)
                image = [image[:,:,2]]
            elif channel == 'R':
                image = image.convert('RGB')
                image = numpy.asarray(image,dtype=numpy.uint8)
                image = [image[:,:,0]]
            elif channel == 'G':
                image = image.convert('RGB')
                image = numpy.asarray(image,dtype=numpy.uint8)
                image = [image[:,:,1]]
            elif channel == 'B' :
                image = image.convert('RGB')
                image = numpy.asarray(image,dtype=numpy.uint8)
                image = [image[:,:,2]]
            else:
                raise NameError('PhotoWizard Error: unexpected argument in getChannel')
        elif len(channel) == 3:
            if channel == 'ALL':
                image = image.convert('RGB')
                image = numpy.asarray(image,dtype=numpy.uint8)
                image = [image[:,:,0],image[:,:,1],image[:,:,2]]
            else:
                raise NameError('PhotoWizard Error: unexpected argument in getChannel')
        else:
            raise NameError('PhotoWizard Error: unexpected argument in getChannel')
    else:
        raise NameError('PhotoWizard Error: Wrong argument type in getChannel')

    return image



def recompose(image,channel,matrices): # Recomposes the image after modifications on one or several of its channels
    #print(isinstance(image,Image.Image),type(channel) is str,type(matrices) is list)
    if (isinstance(image,Image.Image)) and (type(channel) is str) and (type(matrices) is list):
       
        if len(matrices) == len(channel):

            if len(channel) == 1 :
                
                try:
                    matrices = numpy.asarray(matrices[0],dtype=numpy.uint8)
                except:
                    raise NameError('PhotoWizard Error: Wrong argument type in recompose - 2')

                if channel == 'R':
                    img = image.convert('RGB')
                    img = numpy.asarray(img,dtype=numpy.uint8)
                    img.setflags(write=True)
                    img[:,:,0] = matrices
                    image = Image.fromarray(img,'RGB')
                elif channel == 'G':
                    img = image.convert('RGB')
                    img = numpy.asarray(img,dtype=numpy.uint8)
                    img.setflags(write=True)
                    img[:,:,1] = matrices
                    image = Image.fromarray(img,'RGB')
                elif channel == 'B':
                    img = image.convert('RGB')
                    img = numpy.asarray(img,dtype=numpy.uint8)
                    img.setflags(write=True)
                    img[:,:,2] = matrices
                    image = Image.fromarray(img,'RGB')
                elif channel == 'H':
                    img = image.convert('HSV')
                    img = numpy.asarray(img,dtype=numpy.uint8)
                    img.setflags(write=True)
                    img[:,:,0] = matrices
                    image = Image.fromarray(img,'HSV')
                    #image = image.convert('RGB') # We convert this to back to RGB mode for easier handling
                elif channel == 'S':
                    img = image.convert('HSV')
                    img = numpy.asarray(img,dtype=numpy.uint8)
                    img.setflags(write=True)
                    img[:,:,1] = matrices
                    image = Image.fromarray(img,'HSV')
                    #image = image.convert('RGB')
                elif channel == 'V':
                    img = image.convert('HSV')
                    img = numpy.asarray(img,dtype=numpy.uint8)
                    img.setflags(write=True)
                    img[:,:,2] = matrices
                    image = Image.fromarray(img,'HSV')
                    #image = image.convert('RGB')
                else:
                    raise NameError('PhotoWizard Error: unexpected argument in recompose')  

            elif len(channel) == 3:
                if channel == 'ALL': 
                    matrices2 = []
                    try:
                        matrices2.append(numpy.asarray(matrices[0],dtype=numpy.uint8))
                        matrices2.append(numpy.asarray(matrices[1],dtype=numpy.uint8))
                        matrices2.append(numpy.asarray(matrices[2],dtype=numpy.uint8))
                    except:
                        raise NameError('PhotoWizard Error: Wrong argument type in recompose - 3')

                    img = image.convert('RGB')
                    img = numpy.asarray(img,dtype=numpy.uint8)
                    img.setflags(write=True)
                    img[:,:,0] = matrices2[0]
                    img[:,:,1] = matrices2[1]
                    img[:,:,2] = matrices2[2]
                    image = Image.fromarray(img,'RGB')

                else:
                    raise NameError('PhotoWizard Error: unexpected argument in recompose')
            else:
                raise NameError('PhotoWizard Error: unexpected argument in recompose')
        else:
            raise NameError('PhotoWizard Error: arugments length mismatch in recompose')
    else:
        raise NameError('PhotoWizard Error: Wrong argument type in recompose - 1')

    return image





def getInput(message): # Gets input from user - message is a message to display
    
    if type(message) is str :

        if sys.version_info[0] < 3 :
            string =  raw_input(str(message))
        else :
            string = input(str(message))
    else:
        raise NameError('PhotoWizard Error: Wrong argument type in getInput')

    if re.search(r"^[0-9A-Za-z-_. \/]{0,60}$", string) is None :
        raise NameError('PhotoWizard Error: Unexpected input')
        return
    else :
        return string


def parseInput(string,expected): # Parses a string input to find the corresponding objects - expect is a list of expected types such as : [list,str,int,float]
    if type(string) is str and type(expected) is list:
        #print(string,expected)
        s = string.split(' ')
        stringFormated = []
        if len(s) == 2:
            if s[1] == '-h' or s[1] == '--help':
                print(helpm.help(s[0],LANG))
                return stringFormated

        if len(s) == len(expected):
            try :
                for i in range(0,len(s)):
                    if expected[i] is str:
                        tmp = str(s[i])
                    elif expected[i] is int:
                        tmp = int(s[i])
                    elif expected[i] is list:
                        tmp = str(s[i])
                        if tmp[0] == '[' and tmp[len(tmp)-1] == ']':
                            tmp = tmp[1:len(tmp)-1]
                            tmp = tmp.split(',')
                            tmp = numpy.asarray(tmp,dtype=numpy.float32)
                            tmp = list(tmp)
                        else:
                            raise NameError('PhotoWizard Error: Unable to parse delimiters in parseInput')
                    elif expected[i] is tuple:
                        tmp = str(s[i])
                        if tmp[0] == '(' and tmp[len(tmp)-1] == ')':
                            tmp = tmp[1:len(tmp)-1]
                            tmp = tmp.split(',')
                            tmp.numpy.asarray(tmp,dtype=numpy.asarray.float32)
                            tmp = tuple(tmp)
                        else:
                            raise NameError('PhotoWizard Error: Unable to parse delimiters in parseInput')

                    elif expected[i] is float:
                        tmp = float(s[i])
                    else:
                        raise NameError('PhotoWizard Error: Unsupported type in parseInput')
                    stringFormated.append(tmp)
            except Exception as e:
                print(e)
                raise NameError('PhotoWizard Error: Wrong argument type in parseInput - 2')
        else:
            raise NameError('PhotoWizard Error: arguments length mismatch in parseInput')
    else:
        raise NameError('PhotoWizard Error: Wrong argument type in parseInput - 1')
    return stringFormated



def resize(img,size): # Resizes an image to a given size and returns an Image.Image object
    if not isinstance(img, Image.Image):
        try:
            img = str(img)
            img = openf(img)
        except:
            raise NameError('PhotoWizard Error: Unable to load the object')
            img = None
    try:
        W = int(size[0])
        H = int(size[1])
    except:
        raise NameError('PhotoWizard Error: Wrong size format')
        W = 0
        H = 0
        
    img = img.resize((W,H),Image.ANTIALIAS)

    return img



def crop(image,parameters): # Crops an image
    
    if (isinstance(image,Image.Image) and (type(parameters) is tuple) and (len(parameters)==4)):
        try:
            coord = (int(parameters[0]),int(parameters[1]),int(parameters[2]),int(parameters[3]))
            if (min(coord)>=0 and coord[2]<= image.size[0] and coord[3] <= image.size[1]):
                image = image.crop(coord)
            else:
                raise NameError('PhotoWizard Error: Unexpected values in crop')
        except:
            raise NameError('PhotoWizard Error: Wrong argument format in crop or picture is too small')
    else:
        raise NameError('PhotoWizard Error: Wrong argument type in crop')
    
    return image





def explore(path,options): # Explores a folder

    return



def unzip(paths): # Extracts an archive file
    # See zipfile @https://docs.python.org/3/library/zipfile.html
    return



def zip(paths): # Compresses files into an archive
    # See: zipfile @https://docs.python.org/3/library/zipfile.html
    return



def loadXMD(path): # loads an eXternal MetaData file which basically contains a copy of the history
    try:
        f0 = open(str(path))
        f = f0.read()
        f = f.split('<EVENT>')
        f1 = f[1:len(f)-1]
        events = {}
        for event in f1:
            a = event.split('<label>')
            label = str(a[1])
            #print('Label: ',label)
            b = event.split('<request>')
            request = str(b[1])
            #print('Request: ',request)
            c = event.split('<id>')
            ID = int(c[1])
            #print('ID: ',ID)
            d = event.split('<previous>')
            try:
                previous = int(d[1])
            except:
                previous = None
            #print('Previous: ',previous)
            events[ID] = Event(ID,previous,request,label)
            #print('Event created.\n')
        current = f[len(f)-1]
        current = current.split('<current>')
        current = int(current[1])
        #print('Current State: ',current)
        f0.close()
    except Exception as e:
        print(e)
        raise NameError('PhotoWizard Error: Unable to open XMD file')

    return events,current



def saveXMD(path,history): # Saves the XMD file

    if type(path) is str and isinstance(history,History):
        try:
            f = ['<XMD FILE>']
            events = history.getEvents()
            for elt in events:
                event = events[elt]
                label = '<label>'+str(event.getLabel())+'<label>'
                request = '<request>'+str(event.getContent())+'<request>'
                ID = '<id>'+str(event.getID())+'<id>'
                previous = '<previous>'+str(event.getPrevious())+'<previous>'
                f.append('<EVENT>'+label+request+ID+previous)
            f.append('<EVENT>'+'<current>'+str(history.getCurrentState())+'<current>')
            f = '\n'.join(f)
            f0 = open(str(path),'w')
            f0.write(f)
            f0.close()
        except Exception as e:
            print(e)
            raise NameError('PhotoWizard Error: Unable to save XMD file')
    else:
        raise NameError('PhotoWizard Error: Wrong argument type in saveXMD')
            
    return



def rotate(img,theta): # Rotates a 2D matrix by an angle theta in degrees
    if (type(theta) is int) and (isinstance(img,Image.Image)):
        
        img = img.convert('RGB')
        img = numpy.asarray(img,dtype=numpy.uint8)
        img = ndimage.interpolation.rotate(img,theta)
        image = Image.fromarray(img,'RGB')

        """
        # PIL Library
        a = numpy.amin(mat)
        b = numpy.amax(mat)
        mat2 = (mat-a)*255/(b-a)
        mat2 = numpy.array(mat2,dtype=numpy.uint8)
        mat2 = Image.fromarray(mat2)
        mat2.rotate(theta)
        mat2 = numpy.asarray(mat2,dtype=mat.dtype)
        mat = mat2*(b-a)/255+a        
        """

    else:
        raise NameError('PhotoWizard Error: Wrong argument type in rotate function')

    return image

#
#def cubicSpline(Xref,Yref,matrix,Xnew,Ynew): # Interpolation of a 2D matrix using cubic interpolation
#
#    f = interpolate.interp2d(Xref,Yref,matrix,'cubic')
#
#    matrix = f(Xnew,Ynew)
#
#    return matrix
#
#
#
#
#
#def rotate(mat,theta): # Rotates a 2D matrix mat by an angle theta in radians
#    if (type(theta) is int) and (type(mat) is numpy.array):
#        # First, we calculate the rotation matrix
#        #rotation = numpy.asarray([[math.cos(theta) -math.sin(theta)],[math.sin(theta) math.cos(theta)]],dtype=numpy.float32)
#        a = mat.shape[0]
#        b = mat.shape[1]
#
#        # Then we compute the old and new coordinates of the values to interpolate, thanks to the rotation matrix
#        """
#        coordinates = numpy.zeros((a,b,2),dtype=numpy.float32)
#        newCoordinates = numpy.array(coordinates)
#        for i in range(1,a):
#            y = (i-a/2)
#            for j in range(1,b):
#                x = (j-b/2)
#                coordinates[,i-1,j-1] = [x,y]
#                XY = numpy.array([[x],[y]],dtype=numpy.float32)
#                XY = numpy.multiply(rotation,XY)
#                newCoordinates[,i-1,j-1] = [XY[0],XY[1]]
#        """
#        Ycoord = numpy.zeros((1,a))
#        Xcoord = numpy.zeros((1,b))
#        
#        for i in range(1,a):
#            Ycoord[i-1] = (i-a/2)
#        for j in range(1,b):
#            Xcoord[j-1] = (j-b/2)
#        Xnew = numpy.multiply(Xcoord,numpy.asarray([math.cos(theta)]))
#        Ynew = numpy.multiply(Ycoord,numpy.asarray([math.sin(theta)]))
#
#        # Now we can interpolate the matrix at the new coordinates
#        mat = cubicSpline(Xcoord,Ycoord,mat,Xnew,Ynew)
#        
#    else:
#        raise NameError('PhotoWizard Error: Wrong argument type in rotate function')
#
#    return mat
#
