#/////////////////////////////#
# - P H O T O   W I Z A R D - #
#\\\\\\\\\\\\\\\\\\\\\\\\\\\\\#

# -*- coding: utf-8 -*-

# This module contains several useful tools


import sys,re,os,numpy
from PIL import Image


class Picture:

    def __init__(self,ID,name):
        self.ID = ID
        self.History = History(ID)
        self.EXIF = {}
        self.pic = None
        if os.path.exist(name):
            try:
                self.pic = Image.open(name)
            except:
                raise NameError('PhotoWizard Error: Unable to load file')
        else:
            raise NameError('PhotoWizard Error: Unable to find file')
        if self.pic is not None :
            self.smallpic = self.pic.resize((30,30),Image.ANTIALIAS) # Makes a resized copy of the original image for optimized computing
        else :
            self.smallpic = None

        return


    def asImage(self):
        return self.pic


    def asArray(self):
        return numpy.asarray(self.pic)


    def smallAsImage(self):
        return self.smallpic


    def smallAsArray(self):
        return numpy.asarray(self.smallpic)


    def resizeSmall(self,size): # Resizes the working miniature picture according to a given relative size (range 1/100 to 100)
        if type(size) is not tuple :
            raise NameError('PhotoWizard Error: Wrong argument type, must be tuple')
        else:
            if len(size) != 2 :
                raise NameError('PhotoWizard Error: Wrong argument size, must be of length 2')
            else :
                a = 1
                b = 1
                try:
                    a = int(size[0])
                    b = int(size[1])
                except:
                    raise NameError('PhotoWizard Error: Wrong argument type, must be integers')

                if (1<100*a<100*100) and (1<=100*b<=100*100):
                    self.smallpic = tools.resize(self,(a,b))
                else:
                    raise NameError('PhotoWizard Error: Wrong argument range, must be between 1/100 and 100')
        return


    def reCompute(self): # Recompute the miniature image according to the current history
        hist = self.History.getHistory()
        for event in hist:
            action = event.getContent()
            self.smallpic = everyFunction(self,action)
            
        return


    def export(self,path):
        hist = self.History.getHistory()
        for event in hist:
            action = event.getContent()
            self.pic = everyFunction(self,action)
        self.pic.save(name)            
        return





def getInput(message): # Message is a message to display

    if sys.version_info[0] < 3 :
        string =  raw_input(str(message))
    else :
        string = input(str(message))

    if re.search(r"^[0-9A-Za-z-_. \/]{0,60}$", string) is None :
        raise NameError('PhotoWizard Error: Unexpected input')
        return
    else :
        return string




def resize(img,size): # Resizes an image to a given size and returns an Image.Image object

    if type(img) != Image.Image:
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
    return image




def everyFunction(image,action): # Maps the action in the history to the real image editing functions
    if (type(Image) is Image.Image) and (type(action) is list):
        try:
            f = action[0]
            params = action[1]
        except:
            raise NameError('PhotoWizard Error: Wrong argument format in everyFunction')
            f = ""
            params = []
        """
        if f == "":

        elif f == "":

        else:
        """

    else:
        raise NameError('PhotoWizard Error: Wrong argument type in everyFunction')

    return image




def explore(path,options): # Explores a folder


    return





def unzip(paths): # Extracts an archive file


    return





def zip(paths): # Compresses files into an archive


    return

