'''
Authors: D. Knowles, B. McBride, T. Miller

Prereqs:
python 3
sudo apt install python3-tk
pip3 install Pillow, opencv-python, ttkthemes, imutils
'''

'''
TODO:

All:
    *possible threading behind the scenese to autosize other tabs
    use consistent naming patterns
    change gui into multiple tabs/classes
    change text font, size, color, etc.
Tab0:
    add error handling if entries aren't in the right format
    add error handling if not connected to correct wifi
Tab1:
    Don't crop if you single click
    If you try to crop off the picture have it go to edge of picture
    Add zooming feature
    Add panning feature
    Fix resizing
Tab2
    Change crop picture only if focus is not on the entry widget
    Change disable color
    Disable other Characteristics for emergent
    Resize compass
    Verify rotating picture based on yaw angle
Tab3:
    Fix resizing issues
    Disable radiobuttons for N/A images
    Connect radiobuttons with choosing
    Change color of labels
    Change col 6 labels according to choice
    Change submission if there is user input
    Change stickness of corresponding labels
    Add functionality to choose certain aspect
    Add functionalty to delete a classification
Tab4:
    create everything



KNOWN BUGS:
    Weird exit is bound to an event (doesn't do anything) when rerun in iPython3
    When you click on the 2nd tab right at the beginning, and then use the left/intruder_height
        buttons, it moves one tab, then unbinds like it's supposed to.
'''

import tkinter as tk
from tkinter import ttk
from ttkthemes import ThemedStyle
from PIL import Image,ImageTk
import PIL
import cv2
import numpy as np
import time
from lib import client_rest
import time
import sys
import scipy.stats
import imutils


class GuiClass(tk.Frame):
    """
    Graphical User Interface for 2019 AUVSI competition
    Tab 0: Setting for setting up the server_error
    Tab 1: Pull raw images and submit cropped images
    Tab 2: Pull cropped iamges and submit classification for images
    Tab 3: Display results for manual and autonomous classification

    @type tk.Frame: nothing
    @param tk.Frame: nothing
    """
    def __init__(self,master=None):
        """
        initialization for Gui Class

        @rtype:  None
        @return: None
        """


        tk.Frame.__init__(self,master=None)
        self.master = master # gui master handle
        try:
            self.master.attributes('-zoomed', True) # maximizes screen
        except (Exception) as e:
            w, h = root.winfo_screenwidth(), root.winfo_screenheight()
            root.geometry("%dx%d+0+0" % (w, h))
        self.master.title("BYU AUVSI COMPETITION 2019")

        self.n = ttk.Notebook(self.master) # create tabs
        self.n.pack(fill=tk.BOTH, expand=1) # expand across space
        tk.Grid.rowconfigure(self.master,0,weight=1)
        tk.Grid.columnconfigure(self.master,0,weight=1)

        # itialize variables
        #self.default_host = '192.168.1.48'
        self.default_host = '127.0.0.1'
        self.default_port = '5000'
        self.default_idnum = 50
        self.default_debug = False
        self.imageID = 0
        self.interface = client_rest.ImagingInterface(host=self.default_host,port=self.default_port,numIdsStored=self.default_idnum,isDebug=self.default_debug)
        self.initialized = False
        self.pingServer()
        self.draw_np = np.copy(self.org_np)
        self.img_im = self.np2im(self.draw_np)
        self.crop_preview_im = self.img_im.copy()
        self.crop_preview_tk = self.im2tk(self.crop_preview_im)
        self.img_tk = self.im2tk(self.img_im)
        self.org_width,self.org_height = self.img_im.size
        self.crop_preview_width,self.crop_preview_height = self.img_im.size
        self.resize_counter_tab0 = time.time()
        self.resize_counter_tab1 = time.time()
        self.resize_counter_tab2 = time.time()
        self.resize_counter_tab3 = time.time()
        self.cropped = False
        self.cropped_im = self.np2im(self.cropped_np)
        self.cropped_width,self.cropped_height = self.cropped_im.size
        self.cropped_tk = self.im2tk(self.cropped_im)
        # Tab 1 variables
        self.t1_functional = False
        # Tab 2 variables
        self.t2_functional = False # prevent
        # Tab 3 variables
        self.t3_total_targets  = 0
        self.t3_current_target = 1


        '''
        # new radiobutton Style
        s = ttk.Style()
        s.configure('Centered.TRadiobutton',width=30,justify=tk.CENTER)
        s.configure('Centered.TRadiobutton',justify=tk.CENTER)
        '''

        # Tab 0: SETTINGS ------------------------------------------------------
        self.tab0 = ttk.Frame(self.n)
        self.n.add(self.tab0, text='Settings')
        for x in range(6):
            tk.Grid.columnconfigure(self.tab0,x,weight=1)
        for y in range(10):
            tk.Grid.rowconfigure(self.tab0,y,weight=1)
        # Column One
        self.t0c1l1 = ttk.Label(self.tab0, anchor=tk.CENTER, text='                               ')
        self.t0c1l1.grid(row=0,column=0,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t0c1l2 = ttk.Label(self.tab0, anchor=tk.CENTER, text='                               ')
        self.t0c1l2.grid(row=0,column=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)

        # Column Two
        #self.t0sep12 = ttk.Separator(self.tab0, orient=tk.VERTICAL)
        #self.t0sep12.grid(row=0, column=2, rowspan=10,sticky=tk.N+tk.S+tk.E+tk.W, pady=5)
        self.logo_np = self.get_image('assets/logo.png')
        self.logo_im = self.np2im(self.logo_np)
        self.logo_width,self.logo_height = self.logo_im.size
        self.logo_tk = self.im2tk(self.logo_im)

        self.t0c2i1 = ttk.Label(self.tab0, anchor=tk.CENTER,image=self.logo_tk)
        self.t0c2i1.image = self.logo_tk
        self.t0c2i1.grid(row=0,column=2,rowspan=5,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t0c2l1 = ttk.Label(self.tab0, anchor=tk.E, text='Host:')
        self.t0c2l1.grid(row=5,column=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t0c2host = tk.StringVar()
        self.t0c2host.set(self.default_host)
        self.t0c2l2 = ttk.Entry(self.tab0,textvariable=self.t0c2host)
        self.t0c2l2.grid(row=5,column=3,sticky=tk.N+tk.S+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t0c2l3 = ttk.Label(self.tab0, anchor=tk.E, text='Port:')
        self.t0c2l3.grid(row=6,column=2,sticky=tk.N+tk.E+tk.S+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t0c2port = tk.StringVar()
        self.t0c2port.set(self.default_port)
        self.t0c2l4 = ttk.Entry(self.tab0,textvariable=self.t0c2port)
        self.t0c2l4.grid(row=6,column=3,sticky=tk.N+tk.S+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t0c2l5 = ttk.Label(self.tab0, anchor=tk.E, text='Number of IDs Stored:')
        self.t0c2l5.grid(row=7,column=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t0c2ids = tk.StringVar()
        self.t0c2ids.set(self.default_idnum)
        self.t0c2l6 = ttk.Entry(self.tab0,textvariable=self.t0c2ids)
        self.t0c2l6.grid(row=7,column=3,sticky=tk.N+tk.S+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t0c2l7 = ttk.Label(self.tab0, anchor=tk.E, text='Debug Mode:')
        self.t0c2l7.grid(row=8,column=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t0c2debug = tk.IntVar()
        self.t0c2l8 = ttk.Radiobutton(self.tab0,text='True',value=0,variable=self.t0c2debug)
        self.t0c2l8.grid(row=8,column=3,sticky=tk.N+tk.S+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t0c2l8b = ttk.Radiobutton(self.tab0,text='False',value=1,variable=self.t0c2debug)
        self.t0c2l8b.grid(row=8,column=3,sticky=tk.N+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        if not self.default_debug:
            self.t0c2debug.set(1)
        self.t0c2l9 = ttk.Button(self.tab0, text="Apply Settings",command=self.updateSettings)
        self.t0c2l9.grid(row=9,column=2,columnspan=2,sticky=tk.N+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        # Column Three
        #self.t0sep23 = ttk.Separator(self.tab0, orient=tk.VERTICAL)
        #self.t0sep23.grid(row=0, column=4, rowspan=10,sticky=tk.N+tk.S+tk.E+tk.W, pady=5)
        self.t0c3l1 = ttk.Label(self.tab0, anchor=tk.CENTER, text='                                   ')
        self.t0c3l1.grid(row=0,column=4,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t0c3l2 = ttk.Label(self.tab0, anchor=tk.CENTER, text='                                   ')
        self.t0c3l2.grid(row=0,column=5,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)

        # TAB 1: CROPPING ------------------------------------------------------
        self.tab1 = ttk.Frame(self.n)
        self.n.add(self.tab1, text='Cropping')
        # Allows everthing to be resized
        tk.Grid.rowconfigure(self.tab1,0,weight=7)
        tk.Grid.rowconfigure(self.tab1,1,weight=1)
        tk.Grid.columnconfigure(self.tab1,0,weight=7)
        tk.Grid.columnconfigure(self.tab1,1,weight=1)

        self.t1c1i1 = ttk.Label(self.tab1, anchor=tk.CENTER,image=self.img_tk)
        self.t1c1i1.image = self.img_tk
        self.t1c1i1.grid(row=0,column=0,rowspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t1c1i1.bind("<Button-1>",self.mouse_click)
        self.t1c1i1_width = self.t1c1i1.winfo_width()
        self.t1c1i1_height = self.t1c1i1.winfo_height()

        self.crop_preview_img_ratio = 1/7.
        self.t1c2i1 = ttk.Label(self.tab1, anchor=tk.CENTER,image=self.crop_preview_tk)
        self.t1c2i1.image = self.crop_preview_tk
        self.t1c2i1.grid(row=0,column=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        #self.t1c2i1_width = self.t1c2i1.winfo_width()
        #self.t1c2i1_height = self.t1c2i1.winfo_height()

        self.t1c2b1 = ttk.Button(self.tab1, text="Submit Crop",command=self.submitCropped)
        self.t1c2b1.grid(row=1,column=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)



        # TAB 2: CLASSIFICATION ------------------------------------------------
        self.tab2 = ttk.Frame(self.n)   # second page
        self.n.add(self.tab2, text='Classification')

        for x in range(16):
            tk.Grid.columnconfigure(self.tab2,x,weight=1)
        for y in range(50):
            tk.Grid.rowconfigure(self.tab2,y,weight=1)

        # Column One
        self.t2c1title = ttk.Label(self.tab2, anchor=tk.CENTER, text='                  ')
        self.t2c1title.grid(row=0,column=0,columnspan=4,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)

        # Column Two
        self.t2sep12 = ttk.Separator(self.tab2, orient=tk.VERTICAL)
        self.t2sep12.grid(row=0, column=4, rowspan=50,sticky=tk.N+tk.S+tk.E+tk.W, pady=5)
        self.t2c2title = ttk.Label(self.tab2, anchor=tk.CENTER, text='Classification')
        self.t2c2title.grid(row=0,column=4,columnspan=8,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)

        self.t2c2i1 = ttk.Label(self.tab2, anchor=tk.CENTER,image=self.cropped_tk)
        self.t2c2i1.image = self.cropped_tk
        self.t2c2i1.grid(row=2,column=4,rowspan=38,columnspan=8,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)

        self.t2c2l1 = ttk.Label(self.tab2, anchor=tk.CENTER, text='Shape')
        self.t2c2l1.grid(row=40,column=4,columnspan=2,rowspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        shape_options = ('circle','semicircle','quarter_circle','triangle','square','rectangle','trapezoid','pentagon','hexagon','heptagon','octagon','star','cross')
        self.t2c2l2_var = tk.StringVar(self.master)
        self.t2c2l2 = ttk.OptionMenu(self.tab2,self.t2c2l2_var,shape_options[0],*shape_options)
        self.t2c2l2.grid(row=42,column=4,columnspan=2,rowspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t2c2l3 = ttk.Label(self.tab2, anchor=tk.CENTER, text='Alphanumeric')
        self.t2c2l3.grid(row=40,column=6,columnspan=2,rowspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t2c2l4_var = tk.StringVar(self.master)
        alphanumericValidateCommand = self.register(self.alphanumericValidate)
        self.t2c2l4 = ttk.Entry(self.tab2,textvariable=self.t2c2l4_var,validate=tk.ALL,validatecommand=(alphanumericValidateCommand, '%d','%P'))
        self.t2c2l4.grid(row=42,column=6,columnspan=2,rowspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t2c2l5 = ttk.Label(self.tab2, anchor=tk.CENTER, text='Orientation')
        self.t2c2l5.grid(row=40,column=8,columnspan=4,rowspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        orientation_options = ('N','NE','E','SE','S','SW','W','NW')
        self.t2c2l6_var = tk.StringVar(self.master)
        self.t2c2l6 = ttk.OptionMenu(self.tab2,self.t2c2l6_var,orientation_options[0],*orientation_options)
        self.t2c2l6.grid(row=42,column=8,columnspan=4,rowspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t2c2l9 = ttk.Label(self.tab2, anchor=tk.CENTER, text='Background Color')
        self.t2c2l9.grid(row=44,column=4,columnspan=2,rowspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        color_options = ('white','black','gray','red','blue','green','yellow','purple','brown','orange')
        self.t2c2l10_var = tk.StringVar(self.master)
        self.t2c2l10 = ttk.OptionMenu(self.tab2,self.t2c2l10_var,color_options[0],*color_options)
        self.t2c2l10.grid(row=46,column=4,columnspan=2,rowspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t2c2l11 = ttk.Label(self.tab2, anchor=tk.CENTER, text='Alphanumeric Color')
        self.t2c2l11.grid(row=44,column=6,columnspan=2,rowspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t2c2l12_var = tk.StringVar(self.master)
        self.t2c2l12 = ttk.OptionMenu(self.tab2,self.t2c2l12_var,color_options[0],*color_options)
        self.t2c2l12.grid(row=46,column=6,columnspan=2,rowspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t2c2l13 = ttk.Label(self.tab2, anchor=tk.CENTER, text='Target Type')
        self.t2c2l13.grid(row=44,column=8,columnspan=2,rowspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t2c2l14_var = tk.StringVar(self.master)
        target_options = ('standard','emergent','off-axis')
        self.t2c2l14 = ttk.OptionMenu(self.tab2,self.t2c2l14_var,target_options[0],*target_options)
        self.t2c2l14.grid(row=46,column=8,columnspan=2,rowspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t2c2l14_var.trace("w",self.disableEmergentDescription)

        self.t2c2l15 = ttk.Label(self.tab2, anchor=tk.CENTER, text='Emergent Description')
        self.t2c2l15.grid(row=44,column=10,columnspan=2,rowspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t2c2l16_var = tk.StringVar()
        self.t2c2l16_var.set("")
        self.t2c2l16 = ttk.Entry(self.tab2,textvariable=self.t2c2l16_var)
        self.t2c2l16.grid(row=46,column=10,columnspan=2,rowspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t2c2l17 = ttk.Button(self.tab2, text="Submit Classification",command=self.submitClassification)
        self.t2c2l17.grid(row=48,column=4,columnspan=8,rowspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.disableEmergentDescription()

        # Column Three
        self.t2sep23 = ttk.Separator(self.tab2, orient=tk.VERTICAL)
        self.t2sep23.grid(row=0, column=12, rowspan=50,sticky=tk.N+tk.S+tk.E+tk.W, pady=5)
        self.t2c3title = ttk.Label(self.tab2, anchor=tk.CENTER, text='                      ')
        self.t2c3title.grid(row=0,column=12,columnspan=4,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        t2c2i1_np = self.get_image('assets/compass.jpg')
        self.t2c3i1_im = self.np2im(t2c2i1_np)
        self.t2c3i1_default_width,self.t2c3i1_default_height = self.t2c3i1_im.size
        self.t2c3i1_tk = self.im2tk(self.t2c3i1_im)
        # place image
        self.t2c3i1 = ttk.Label(self.tab2, anchor=tk.CENTER,image=self.t2c3i1_tk)
        self.t2c3i1.image = self.t2c3i1_tk
        self.t2c3i1.grid(row=2,column=12,rowspan=38,columnspan=4,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)




        # TAB 3: MANUAL TARGET SUBMISSION ------------------------------------------------
        self.tab3 = ttk.Frame(self.n)
        self.n.add(self.tab3, text='Manual Target Submission')

        for x in range(12):
            tk.Grid.columnconfigure(self.tab3,x,weight=1)
        for y in range(21):
            tk.Grid.rowconfigure(self.tab3,y,weight=1)

        self.t3_default_np = self.get_image('assets/noClassifiedTargets.jpg')
        self.t3_default_im = self.np2im(self.t3_default_np)
        self.t3_default_width,self.t3_default_height = self.t3_default_im.size
        self.t3_default_tk = self.im2tk(self.t3_default_im)

        # Title
        self.t3titleA = ttk.Label(self.tab3, anchor=tk.CENTER, text='Target #')
        self.t3titleA.grid(row=0,column=4,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3titleB = ttk.Label(self.tab3, anchor=tk.CENTER, text=self.t3_current_target)
        self.t3titleB.grid(row=0,column=5,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3titleC = ttk.Label(self.tab3, anchor=tk.CENTER, text='Out of')
        self.t3titleC.grid(row=0,column=6,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3titleD = ttk.Label(self.tab3, anchor=tk.CENTER, text=self.t3_total_targets)
        self.t3titleD.grid(row=0,column=7,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)

        # Column One
        self.t3c1title = ttk.Label(self.tab3, anchor=tk.CENTER, text='Pic 1')
        self.t3c1title.grid(row=1,column=0,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c1i1_im = self.t3_default_im.copy()
        self.t3c1i1_tk = self.im2tk(self.t3c1i1_im)
        self.t3c1i1_org_width,self.t3c1i1_org_height = self.t3c1i1_im.size
        self.t3c1i1 = ttk.Label(self.tab3, anchor=tk.CENTER,image=self.t3c1i1_tk)
        self.t3c1i1.image = self.t3c1i1_tk
        self.t3c1i1.grid(row=3,column=0,rowspan=1,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        # Characteristics
        self.submissionImage = tk.IntVar()
        self.t3c1r4 = tk.Radiobutton(self.tab3,value=1,variable=self.submissionImage)
        self.t3c1r4.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c1r4.grid(row=4,column=0,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c1ar5 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Shape:")
        self.t3c1ar5.grid(row=5,column=0,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c1br5 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c1br5.grid(row=5,column=1,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c1ar7 = ttk.Label(self.tab3, anchor=tk.S, text="Background Color:")
        self.t3c1ar7.grid(row=7,column=0,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c1br7 = ttk.Label(self.tab3, anchor=tk.S, text="N/A")
        self.t3c1br7.grid(row=7,column=1,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.submissionBackgroundColor = tk.IntVar()
        self.t3c1r8 = tk.Radiobutton(self.tab3,value=1,variable=self.submissionBackgroundColor)
        self.t3c1r8.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c1r8.grid(row=8,column=0,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c1ar9 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Alphanumeric:")
        self.t3c1ar9.grid(row=9,column=0,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c1br9 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c1br9.grid(row=9,column=1,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c1ar11 = ttk.Label(self.tab3, anchor=tk.S, text="Alphanumeric Color:")
        self.t3c1ar11.grid(row=11,column=0,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c1br11 = ttk.Label(self.tab3, anchor=tk.S, text="N/A")
        self.t3c1br11.grid(row=11,column=1,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.submissionAlphanumericColor = tk.IntVar()
        self.t3c1r12 = tk.Radiobutton(self.tab3,value=1,variable=self.submissionAlphanumericColor)
        self.t3c1r12.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c1r12.grid(row=12,column=0,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c1ar13 = ttk.Label(self.tab3, anchor=tk.S, text="Orientation:")
        self.t3c1ar13.grid(row=13,column=0,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c1br13 = ttk.Label(self.tab3, anchor=tk.S, text="N/A")
        self.t3c1br13.grid(row=13,column=1,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.submissionOrientation = tk.IntVar()
        self.t3c1r14 = tk.Radiobutton(self.tab3,value=1,variable=self.submissionOrientation)
        self.t3c1r14.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c1r14.grid(row=14,column=0,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c1ar15 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Target Type:")
        self.t3c1ar15.grid(row=15,column=0,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c1br15 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c1br15.grid(row=15,column=1,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c1ar17 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Description:")
        self.t3c1ar17.grid(row=17,column=0,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c1ar18 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c1ar18.grid(row=18,column=0,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.submissionDescription = tk.IntVar()
        self.t3c1r19 = tk.Radiobutton(self.tab3,value=1,variable=self.submissionDescription)
        self.t3c1r19.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c1r19.grid(row=19,column=0,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)



        # Column Two
        self.t3c2title = ttk.Label(self.tab3, anchor=tk.CENTER, text='Pic 2')
        self.t3c2title.grid(row=1,column=2,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2i1_im = self.t3_default_im.copy()
        self.t3c2i1_tk = self.im2tk(self.t3c2i1_im)
        self.t3c2i1_org_width,self.t3c2i1_org_height = self.t3c2i1_im.size
        self.t3c2i1 = ttk.Label(self.tab3, anchor=tk.CENTER,image=self.t3c2i1_tk)
        self.t3c2i1.image = self.t3c2i1_tk
        self.t3c2i1.grid(row=3,column=2,rowspan=1,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        # Characteristics
        self.t3c2r4 = tk.Radiobutton(self.tab3,value=2,variable=self.submissionImage)
        self.t3c2r4.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c2r4.grid(row=4,column=2,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2ar5 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Shape:")
        self.t3c2ar5.grid(row=5,column=2,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2br5 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c2br5.grid(row=5,column=3,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2ar7 = ttk.Label(self.tab3, anchor=tk.S, text="Background Color:")
        self.t3c2ar7.grid(row=7,column=2,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2br7 = ttk.Label(self.tab3, anchor=tk.S, text="N/A")
        self.t3c2br7.grid(row=7,column=3,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2r8 = tk.Radiobutton(self.tab3,value=2,variable=self.submissionBackgroundColor)
        self.t3c2r8.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c2r8.grid(row=8,column=2,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2ar9 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Alphanumeric:")
        self.t3c2ar9.grid(row=9,column=2,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2br9 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c2br9.grid(row=9,column=3,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2ar11 = ttk.Label(self.tab3, anchor=tk.S, text="Alphanumeric Color:")
        self.t3c2ar11.grid(row=11,column=2,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2br11 = ttk.Label(self.tab3, anchor=tk.S, text="N/A")
        self.t3c2br11.grid(row=11,column=3,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2r12 = tk.Radiobutton(self.tab3,value=2,variable=self.submissionAlphanumericColor)
        self.t3c2r12.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c2r12.grid(row=12,column=2,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2ar13 = ttk.Label(self.tab3, anchor=tk.S, text="Orientation:")
        self.t3c2ar13.grid(row=13,column=2,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2br13 = ttk.Label(self.tab3, anchor=tk.S, text="N/A")
        self.t3c2br13.grid(row=13,column=3,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2r14 = tk.Radiobutton(self.tab3,value=2,variable=self.submissionOrientation)
        self.t3c2r14.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c2r14.grid(row=14,column=2,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2ar15 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Target Type:")
        self.t3c2ar15.grid(row=15,column=2,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2br15 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c2br15.grid(row=15,column=3,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2ar17 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Description:")
        self.t3c2ar17.grid(row=17,column=2,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2ar18 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c2ar18.grid(row=18,column=2,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c2r19 = tk.Radiobutton(self.tab3,value=2,variable=self.submissionDescription)
        self.t3c2r19.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c2r19.grid(row=19,column=2,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)


        # Column Three
        self.t3c3title = ttk.Label(self.tab3, anchor=tk.CENTER, text='Pic 3')
        self.t3c3title.grid(row=1,column=4,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3i1_im = self.t3_default_im.copy()
        self.t3c3i1_tk = self.im2tk(self.t3c3i1_im)
        self.t3c3i1_org_width,self.t3c3i1_org_height = self.t3c3i1_im.size
        self.t3c3i1 = ttk.Label(self.tab3, anchor=tk.CENTER,image=self.t3c3i1_tk)
        self.t3c3i1.image = self.t3c3i1_tk
        self.t3c3i1.grid(row=3,column=4,rowspan=1,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        # Characteristics
        self.t3c3r4 = tk.Radiobutton(self.tab3,value=3,variable=self.submissionImage)
        self.t3c3r4.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c3r4.grid(row=4,column=4,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3ar5 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Shape:")
        self.t3c3ar5.grid(row=5,column=4,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3br5 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c3br5.grid(row=5,column=5,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3ar7 = ttk.Label(self.tab3, anchor=tk.S, text="Background Color:")
        self.t3c3ar7.grid(row=7,column=4,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3br7 = ttk.Label(self.tab3, anchor=tk.S, text="N/A")
        self.t3c3br7.grid(row=7,column=5,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3r8 = tk.Radiobutton(self.tab3,value=3,variable=self.submissionBackgroundColor)
        self.t3c3r8.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c3r8.grid(row=8,column=4,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3ar9 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Alphanumeric:")
        self.t3c3ar9.grid(row=9,column=4,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3br9 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c3br9.grid(row=9,column=5,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3ar11 = ttk.Label(self.tab3, anchor=tk.S, text="Alphanumeric Color:")
        self.t3c3ar11.grid(row=11,column=4,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3br11 = ttk.Label(self.tab3, anchor=tk.S, text="N/A")
        self.t3c3br11.grid(row=11,column=5,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3r12 = tk.Radiobutton(self.tab3,value=3,variable=self.submissionAlphanumericColor)
        self.t3c3r12.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c3r12.grid(row=12,column=4,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3ar13 = ttk.Label(self.tab3, anchor=tk.S, text="Orientation:")
        self.t3c3ar13.grid(row=13,column=4,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3br13 = ttk.Label(self.tab3, anchor=tk.S, text="N/A")
        self.t3c3br13.grid(row=13,column=5,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3r14 = tk.Radiobutton(self.tab3,value=3,variable=self.submissionOrientation)
        self.t3c3r14.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c3r14.grid(row=14,column=4,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3ar15 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Target Type:")
        self.t3c3ar15.grid(row=15,column=4,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3br15 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c3br15.grid(row=15,column=5,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3ar17 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Description:")
        self.t3c3ar17.grid(row=17,column=4,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3ar18 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c3ar18.grid(row=18,column=4,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c3r19 = tk.Radiobutton(self.tab3,value=3,variable=self.submissionDescription)
        self.t3c3r19.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c3r19.grid(row=19,column=4,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)


        # Column Four
        self.t3c4title = ttk.Label(self.tab3, anchor=tk.CENTER, text='Pic 4')
        self.t3c4title.grid(row=1,column=6,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4i1_im = self.t3_default_im.copy()
        self.t3c4i1_tk = self.im2tk(self.t3c4i1_im)
        self.t3c4i1_org_width,self.t3c4i1_org_height = self.t3c4i1_im.size
        self.t3c4i1 = ttk.Label(self.tab3, anchor=tk.CENTER,image=self.t3c4i1_tk)
        self.t3c4i1.image = self.t3c4i1_tk
        self.t3c4i1.grid(row=3,column=6,rowspan=1,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        # Characteristics
        self.t3c4r4 = tk.Radiobutton(self.tab3,value=4,variable=self.submissionImage)
        self.t3c4r4.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c4r4.grid(row=4,column=6,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4ar5 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Shape:")
        self.t3c4ar5.grid(row=5,column=6,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4br5 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c4br5.grid(row=5,column=7,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4ar7 = ttk.Label(self.tab3, anchor=tk.S, text="Background Color:")
        self.t3c4ar7.grid(row=7,column=6,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4br7 = ttk.Label(self.tab3, anchor=tk.S, text="N/A")
        self.t3c4br7.grid(row=7,column=7,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4r8 = tk.Radiobutton(self.tab3,value=4,variable=self.submissionBackgroundColor)
        self.t3c4r8.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c4r8.grid(row=8,column=6,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4ar9 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Alphanumeric:")
        self.t3c4ar9.grid(row=9,column=6,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4br9 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c4br9.grid(row=9,column=7,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4ar11 = ttk.Label(self.tab3, anchor=tk.S, text="Alphanumeric Color:")
        self.t3c4ar11.grid(row=11,column=6,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4br11 = ttk.Label(self.tab3, anchor=tk.S, text="N/A")
        self.t3c4br11.grid(row=11,column=7,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4r12 = tk.Radiobutton(self.tab3,value=4,variable=self.submissionAlphanumericColor)
        self.t3c4r12.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c4r12.grid(row=12,column=6,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4ar13 = ttk.Label(self.tab3, anchor=tk.S, text="Orientation:")
        self.t3c4ar13.grid(row=13,column=6,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4br13 = ttk.Label(self.tab3, anchor=tk.S, text="N/A")
        self.t3c4br13.grid(row=13,column=7,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4r14 = tk.Radiobutton(self.tab3,value=4,variable=self.submissionOrientation)
        self.t3c4r14.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c4r14.grid(row=14,column=6,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4ar15 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Target Type:")
        self.t3c4ar15.grid(row=15,column=6,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4br15 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c4br15.grid(row=15,column=7,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4ar17 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Description:")
        self.t3c4ar17.grid(row=17,column=6,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4ar18 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c4ar18.grid(row=18,column=6,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c4r19 = tk.Radiobutton(self.tab3,value=4,variable=self.submissionDescription)
        self.t3c4r19.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c4r19.grid(row=19,column=6,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)



        # Column Five
        self.t3c5title = ttk.Label(self.tab3, anchor=tk.CENTER, text='Pic 5')
        self.t3c5title.grid(row=1,column=8,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5i1_im = self.t3_default_im.copy()
        self.t3c5i1_tk = self.im2tk(self.t3c5i1_im)
        self.t3c5i1_org_width,self.t3c5i1_org_height = self.t3c5i1_im.size
        self.t3c5i1 = ttk.Label(self.tab3, anchor=tk.CENTER,image=self.t3c5i1_tk)
        self.t3c5i1.image = self.t3c5i1_tk
        self.t3c5i1.grid(row=3,column=8,rowspan=1,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        # Characteristics
        self.t3c5r4 = tk.Radiobutton(self.tab3,value=5,variable=self.submissionImage)
        self.t3c5r4.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c5r4.grid(row=4,column=8,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5ar5 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Shape:")
        self.t3c5ar5.grid(row=5,column=8,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5br5 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c5br5.grid(row=5,column=9,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5ar7 = ttk.Label(self.tab3, anchor=tk.S, text="Background Color:")
        self.t3c5ar7.grid(row=7,column=8,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5br7 = ttk.Label(self.tab3, anchor=tk.S, text="N/A")
        self.t3c5br7.grid(row=7,column=9,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5r8 = tk.Radiobutton(self.tab3,value=5,variable=self.submissionBackgroundColor)
        self.t3c5r8.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c5r8.grid(row=8,column=8,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5ar9 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Alphanumeric:")
        self.t3c5ar9.grid(row=9,column=8,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5br9 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c5br9.grid(row=9,column=9,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5ar11 = ttk.Label(self.tab3, anchor=tk.S, text="Alphanumeric Color:")
        self.t3c5ar11.grid(row=11,column=8,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5br11 = ttk.Label(self.tab3, anchor=tk.S, text="N/A")
        self.t3c5br11.grid(row=11,column=9,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5r12 = tk.Radiobutton(self.tab3,value=5,variable=self.submissionAlphanumericColor)
        self.t3c5r12.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c5r12.grid(row=12,column=8,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5ar13 = ttk.Label(self.tab3, anchor=tk.S, text="Orientation:")
        self.t3c5ar13.grid(row=13,column=8,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5br13 = ttk.Label(self.tab3, anchor=tk.S, text="N/A")
        self.t3c5br13.grid(row=13,column=9,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5r14 = tk.Radiobutton(self.tab3,value=5,variable=self.submissionOrientation)
        self.t3c5r14.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c5r14.grid(row=14,column=8,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5ar15 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Target Type:")
        self.t3c5ar15.grid(row=15,column=8,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5br15 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c5br15.grid(row=15,column=9,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5ar17 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Description:")
        self.t3c5ar17.grid(row=17,column=8,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5ar18 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c5ar18.grid(row=18,column=8,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c5r19 = tk.Radiobutton(self.tab3,value=5,variable=self.submissionDescription)
        self.t3c5r19.configure(foreground="#5c616c",background="#f5f6f7",highlightthickness=0,anchor=tk.N)
        self.t3c5r19.grid(row=19,column=8,columnspan=2,sticky=tk.N+tk.E+tk.W+tk.S,padx=5,pady=5,ipadx=5,ipady=5)


        # Column Six
        self.t3sep56 = ttk.Separator(self.tab3, orient=tk.VERTICAL)
        self.t3sep56.grid(row=1, column=10, rowspan=20,sticky=tk.N+tk.S+tk.E+tk.W, pady=5)
        self.t3c6title = ttk.Label(self.tab3, anchor=tk.CENTER, text='To Submit')
        self.t3c6title.grid(row=1,column=10,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c6i1_im = self.t3_default_im.copy()
        self.t3c6i1_tk = self.im2tk(self.t3c6i1_im)
        self.t3c6i1_org_width,self.t3c6i1_org_height = self.t3c6i1_im.size
        self.t3c6i1 = ttk.Label(self.tab3, anchor=tk.CENTER,image=self.t3c6i1_tk)
        self.t3c6i1.image = self.t3c6i1_tk
        self.t3c6i1.grid(row=3,column=10,rowspan=1,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        # Characteristics
        self.t3c6ar5 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Shape:")
        self.t3c6ar5.grid(row=5,column=10,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c6br5 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c6br5.grid(row=5,column=11,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c6ar7 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Background Color:")
        self.t3c6ar7.grid(row=7,column=10,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c6br7 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c6br7.grid(row=7,column=11,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c6ar9 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Alphanumeric:")
        self.t3c6ar9.grid(row=9,column=10,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c6br9 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c6br9.grid(row=9,column=11,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c6ar11 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Alphanumeric Color:")
        self.t3c6ar11.grid(row=11,column=10,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c6br11 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c6br11.grid(row=11,column=11,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c6ar13 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Orientation:")
        self.t3c6ar13.grid(row=13,column=10,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c6br13 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c6br13.grid(row=13,column=11,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c6ar15 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Target Type:")
        self.t3c6ar15.grid(row=15,column=10,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c6br15 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c6br15.grid(row=15,column=11,columnspan=1,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c6ar17 = ttk.Label(self.tab3, anchor=tk.CENTER, text="Description:")
        self.t3c6ar17.grid(row=17,column=10,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        self.t3c6ar18 = ttk.Label(self.tab3, anchor=tk.CENTER, text="N/A")
        self.t3c6ar18.grid(row=18,column=10,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)
        # Submit button
        self.t3c6b1 = ttk.Button(self.tab3, text="Submit Target",command=self.submitTarget)
        self.t3c6b1.grid(row=20,column=10,columnspan=2,sticky=tk.N+tk.S+tk.E+tk.W,padx=5,pady=5,ipadx=5,ipady=5)




        # TAB 4: AUTONOMOUS TARGET SUBMISSION ------------------------------------------------
        self.tab4 = ttk.Frame(self.n)
        self.n.add(self.tab4, text='Autonomous Target Submission')

        # Done with initialization
        self.initialized = True

        # KEY BINDINGS ------------------------------------------------------------
        self.master.bind("<<NotebookTabChanged>>",self.tabChanged)



    def get_image(self,path):
        """
        Reads in an image from folder on computer

        @type  path: file path
        @param path: the file path to where the image is located

        @rtype:  Numpy image array
        @return: Numpy array of selected image
        """
        image_np = cv2.imread(path)
        image_np = cv2.cvtColor(image_np,cv2.COLOR_BGR2RGB)
        return image_np

    def np2im(self,image):
        """
        Converts from numpy array to PIL image
        @type image: Numpy image array
        @param image: Numpy array of selected image

        @rtype:  PIL image
        @return: PIL image of numpy array
        """
        image_im = Image.fromarray(image)
        return image_im

    def im2tk(self,image):
        """
        Converts from PIL image to TK image
        @type image: PIL image
        @param image: PIL image of numpy array

        @rtype:  TK image
        @return: TK image of PIL image
        """
        image_tk = ImageTk.PhotoImage(image)
        return image_tk

    def mouse_click(self,event):
        """
        Saves pixel location of where on the image the mouse clicks
        @type  event: event
        @param event: mouse event

        @rtype:  None
        @return: None
        """
        #print(event.x,event.y)
        self.t1c1i1.bind("<ButtonRelease-1>",self.mouse_release)
        self.t1c1i1.bind("<Motion>",self.mouse_move)
        self.offset_x = int((self.t1c1i1_width - self.t1c1i1_img_width )/2.0)
        self.offset_y = int((self.t1c1i1_height - self.t1c1i1_img_height)/2.0)
        self.x0 = event.x - self.offset_x
        self.y0 = event.y - self.offset_y

    def mouse_move(self,event):
        """
        Gets pixel location of where the mouse is moving and show rectangle for crop preview
        @type  event: event
        @param event: mouse event

        @rtype:  None
        @return: None
        """
        self.t1c1i1.bind("<ButtonRelease-1>",self.mouse_release)
        self.x1 = event.x - self.offset_x
        self.y1 = event.y - self.offset_y
        disp_width,disp_height = self.resized_im.size
        sr = (self.org_width/disp_width + self.org_height/disp_height)/2.0
        self.draw_np = np.copy(self.org_np)
        cv2.rectangle(self.draw_np,(int(sr*self.x0),int(sr*self.y0)),(int(sr*self.x1),int(sr*self.y1)),(255,0,0),2)
        self.img_im = self.np2im(self.draw_np)
        self.resized_im = self.resizeIm(self.img_im,self.org_width,self.org_height,self.t1c1i1_width,self.t1c1i1_height)
        self.img_tk = self.im2tk(self.resized_im)
        self.t1c1i1.configure(image=self.img_tk)

    def mouse_release(self,event):
        """
        Saves pixel location of where the mouse clicks and creates crop preview
        @type  event: event
        @param event: mouse event

        @rtype:  None
        @return: None
        """
        if self.cropped:
            self.undoCrop()
        self.t1c1i1.unbind("<Motion>")
        self.t1c1i1.unbind("<ButtonRelease-1>")
        self.x1 = event.x - self.offset_x
        self.y1 = event.y - self.offset_y
        disp_width,disp_height = self.resized_im.size
        sr = (self.org_width/disp_width + self.org_height/disp_height)/2.0
        self.draw_np = np.copy(self.org_np)
        cv2.rectangle(self.draw_np,(int(sr*self.x0),int(sr*self.y0)),(int(sr*self.x1),int(sr*self.y1)),(255,0,0),2)
        self.img_im = self.np2im(self.draw_np)
        self.resized_im = self.resizeIm(self.img_im,self.org_width,self.org_height,self.t1c1i1_width,self.t1c1i1_height)
        self.img_tk = self.im2tk(self.resized_im)
        self.t1c1i1.configure(image=self.img_tk)
        # Crop Image
        self.cropImage(int(sr*self.x0),int(sr*self.y0),int(sr*self.x1),int(sr*self.y1))
        self.cropped = True

    def close_window(self,event):
        """
        Closes gui safely
        @type  event: event
        @param event: ESC event

        @rtype:  None
        @return: None
        """
        self.master.destroy()
        sys.exit()

    def resizeEventTab0(self,event=None):
        """
        Resizes picture on Tab0
        @type  event: event
        @param event: resize window event

        @rtype:  None
        @return: None
        """
        if self.initialized and (time.time()-self.resize_counter_tab0) > 0.050:
            if self.t0c2i1.winfo_width() > 1:
                self.resize_counter_tab0 = time.time()
                self.master.update()
                t0c2i1_width = self.t0c2i1.winfo_width()
                t0c2i1_height = self.t0c2i1.winfo_height()
                logoW, logoH = self.logo_im.size
                self.logo_resized_im = self.resizeIm(self.logo_im, logoW, logoH, t0c2i1_width, t0c2i1_height)
                self.logo_tk = self.im2tk(self.logo_resized_im)
                self.t0c2i1.configure(image=self.logo_tk)

    def resizeEventTab1(self,event=None):
        """
        Resizes pictures on Tab1
        @type  event: event
        @param event: resize window event

        @rtype:  None
        @return: None
        """
        if self.initialized and (time.time()-self.resize_counter_tab1) > 0.050:
            if self.t1c1i1.winfo_width() > 1:
                self.resize_counter_tab1 = time.time()
                self.master.update()
                # main image
                self.t1c1i1_width = self.t1c1i1.winfo_width()
                self.t1c1i1_height = self.t1c1i1.winfo_height()
                self.resized_im = self.resizeIm(self.img_im,self.org_width,self.org_height,self.t1c1i1_width,self.t1c1i1_height)
                self.t1c1i1_img_width,self.t1c1i1_img_height = self.resized_im.size
                self.img_tk = self.im2tk(self.resized_im)
                self.t1c1i1.configure(image=self.img_tk)
                # cropped image
                #self.t1c2i1_width = self.t1c2i1.winfo_width()
                #self.t1c2i1_height = self.t1c2i1.winfo_height()
                self.crop_preview_resized_im = self.resizeIm(self.crop_preview_im,self.crop_preview_width,self.crop_preview_height,self.t1c1i1_width*self.crop_preview_img_ratio,self.t1c1i1_height*self.crop_preview_img_ratio)
                #self.t1c2i1_width,self.t1c2i1_height = self.crop_resized_im.size
                self.crop_preview_tk = self.im2tk(self.crop_preview_resized_im)
                self.t1c2i1.configure(image=self.crop_preview_tk)

    def resizeEventTab2(self,event=None):
        """
        Resizes picture on Tab2
        @type  event: event
        @param event: resize window event

        @rtype:  None
        @return: None
        """
        if self.initialized and (time.time()-self.resize_counter_tab2) > 0.050:
            if self.t2c2i1.winfo_width() > 1:
                self.resize_counter_tab2 = time.time()
                self.master.update()
                self.t2c2i1_width = self.t2c2i1.winfo_width()
                self.t2c2i1_height = self.t2c2i1.winfo_height()
                self.cropped_resized_im = self.resizeIm(self.cropped_im,self.cropped_width,self.cropped_height,self.t2c2i1_width,self.t2c2i1_height)
                self.cropped_tk = self.im2tk(self.cropped_resized_im)
                self.t2c2i1.configure(image=self.cropped_tk)
                # resize compass
                '''
                self.t2c3i1_width = self.t2c3i1.winfo_width()
                self.t2c3i1_height = self.t2c3i1.winfo_height()
                resized_im = self.resizeIm(self.t2c3i1_im,self.t2c3i1_default_width,self.t2c3i1_default_height,self.t2c3i1_width,self.t2c3i1_height)
                self.t2c3i1_tk = self.im2tk(resized_im)
                self.t2c3i1.configure(image=self.t2c3i1_tk)
                '''

    def resizeEventTab3(self,event=None):
        """
        Resizes picture on Tab3
        @type  event: event
        @param event: resize window event

        @rtype:  None
        @return: None
        """
        if self.initialized and (time.time()-self.resize_counter_tab3) > 0.050:
            if self.t3c1i1.winfo_width() > 1:
                self.resize_counter_tab3 = time.time()
                self.master.update()
                # Col 1 Image
                self.t3c1i1_width = self.t3c1i1.winfo_width()
                self.t3c1i1_height = self.t3c1i1.winfo_height()
                resized_im = self.resizeIm(self.t3c1i1_im,self.t3c1i1_org_width,self.t3c1i1_org_height,self.t3c1i1_width,self.t3c1i1_height)
                self.t3c1i1_tk = self.im2tk(resized_im)
                self.t3c1i1.configure(image=self.t3c1i1_tk)
                # Col 2 Image
                self.t3c2i1_width = self.t3c2i1.winfo_width()
                self.t3c2i1_height = self.t3c2i1.winfo_height()
                resized_im = self.resizeIm(self.t3c2i1_im,self.t3c2i1_org_width,self.t3c2i1_org_height,self.t3c2i1_width,self.t3c2i1_height)
                self.t3c2i1_tk = self.im2tk(resized_im)
                self.t3c2i1.configure(image=self.t3c2i1_tk)
                # Col 3 Image
                self.t3c3i1_width = self.t3c3i1.winfo_width()
                self.t3c3i1_height = self.t3c3i1.winfo_height()
                resized_im = self.resizeIm(self.t3c3i1_im,self.t3c3i1_org_width,self.t3c3i1_org_height,self.t3c3i1_width,self.t3c3i1_height)
                self.t3c3i1_tk = self.im2tk(resized_im)
                self.t3c3i1.configure(image=self.t3c3i1_tk)
                # Col 4 Image
                self.t3c4i1_width = self.t3c4i1.winfo_width()
                self.t3c4i1_height = self.t3c4i1.winfo_height()
                resized_im = self.resizeIm(self.t3c4i1_im,self.t3c4i1_org_width,self.t3c4i1_org_height,self.t3c4i1_width,self.t3c4i1_height)
                self.t3c4i1_tk = self.im2tk(resized_im)
                self.t3c4i1.configure(image=self.t3c4i1_tk)
                # Col 5 Image
                self.t3c5i1_width = self.t3c5i1.winfo_width()
                self.t3c5i1_height = self.t3c5i1.winfo_height()
                resized_im = self.resizeIm(self.t3c5i1_im,self.t3c5i1_org_width,self.t3c5i1_org_height,self.t3c5i1_width,self.t3c5i1_height)
                self.t3c5i1_tk = self.im2tk(resized_im)
                self.t3c5i1.configure(image=self.t3c5i1_tk)
                # Col 6 Image
                self.t3c6i1_width = self.t3c6i1.winfo_width()
                self.t3c6i1_height = self.t3c6i1.winfo_height()
                resized_im = self.resizeIm(self.t3c6i1_im,self.t3c6i1_org_width,self.t3c6i1_org_height,self.t3c6i1_width,self.t3c6i1_height)
                self.t3c6i1_tk = self.im2tk(resized_im)
                self.t3c6i1.configure(image=self.t3c6i1_tk)




    def resizeIm(self,image,image_width,image_height,width_restrict,height_restrict):
        """
        Resizes PIL image according to given bounds
        @type  image: PIL image
        @param image: PIL image that you want to crop

        @type  image_width: integer
        @param image_width: the original image width in pixels

        @type  image_height: integer
        @param image_height: the original image height in pixels

        @type  width_restrict: integer
        @param width_restrict: the width in pixels of restricted area

        @type  height_restrict: integer
        @param height_restrict: the height in pixels of restricted area

        @rtype:  PIL image
        @return: Resized PIL image
        """
        ratio_h = height_restrict/image_height
        ratio_w = width_restrict/image_width
        if ratio_h <= ratio_w:
            resized_im = image.resize((int(image_width*ratio_h), int(image_height*ratio_h)), Image.ANTIALIAS)
        else:
            resized_im = image.resize((int(image_width*ratio_w), int(image_height*ratio_w)), Image.ANTIALIAS)
        return(resized_im)

    def cropImage(self,x0,y0,x1,y1):
        """
        Crops raw image
        @type  x0: integer
        @param x0: pixel x location of first click

        @type  y0: integer
        @param y0: pixel y location of first click

        @type  x1: integer
        @param x1: pixel x location of second click

        @type  y1: integer
        @param y1: pixel y location of second click

        @rtype:  None
        @return: None
        """
        if x0 < x1:
            self.cx0 = x0
            self.cx1 = x1
        else:
            self.cx0 = x1
            self.cx1 = x0
        if y0 < y1:
            self.cy0 = y0
            self.cy1 = y1
        else:
            self.cy0 = y1
            self.cy1 = y0
        self.crop_preview_im = self.crop_preview_im.crop((self.cx0,self.cy0,self.cx1,self.cy1))
        self.crop_preview_width,self.crop_preview_height = self.crop_preview_im.size
        self.crop_preview_resized_im = self.resizeIm(self.crop_preview_im,self.crop_preview_width,self.crop_preview_height,self.t1c1i1_width*self.crop_preview_img_ratio,self.t1c1i1_height*self.crop_preview_img_ratio)
        self.crop_preview_tk = self.im2tk(self.crop_preview_resized_im)
        self.t1c2i1.configure(image=self.crop_preview_tk)

    def undoCrop(self,event=None):
        """
        Undoes crop and resets the raw image

        @type  event: event
        @param event: Ctrl + Z event

        @rtype:  None
        @return: None
        """
        self.draw_np = np.copy(self.org_np)
        self.img_im = self.np2im(self.draw_np)
        self.resized_im = self.resizeIm(self.img_im,self.org_width,self.org_height,self.t1c1i1_width,self.t1c1i1_height)
        self.img_tk = self.im2tk(self.resized_im)
        self.t1c1i1.configure(image=self.img_tk)
        self.crop_preview_im = self.img_im.copy()
        self.crop_preview_width,self.crop_preview_height = self.crop_preview_im.size
        self.crop_preview_resized_im = self.resizeIm(self.crop_preview_im,self.crop_preview_width,self.crop_preview_height,self.t1c1i1_width*self.crop_preview_img_ratio,self.t1c1i1_height*self.crop_preview_img_ratio)
        self.crop_preview_tk = self.im2tk(self.crop_preview_resized_im)
        self.t1c2i1.configure(image=self.crop_preview_tk)
        #self.t2c2i1.configure(image=self.crop_preview_tk)

    def nextRaw(self,event):
        """
        Requests and displays next raw image

        @type  event: event
        @param event: Right arrow event

        @rtype:  None
        @return: None
        """
        self.pingServer()
        if self.serverConnected:
            time0 = time.time()
            query = self.interface.getNextRawImage()
            if query == None:
                self.t1_functional = False
                self.noNextRaw()
            else:
                self.t1_functional = True
                self.imageID = query[1]
                self.org_np = np.array(query[0]) #self.get_image('frame0744.jpg')
            time1 = time.time()
            self.draw_np = np.copy(self.org_np)
            self.img_im = self.np2im(self.draw_np)
            self.crop_preview_im = self.img_im.copy()
            self.org_width,self.org_height = self.img_im.size
            self.crop_preview_width,self.crop_preview_height = self.crop_preview_im.size
            self.cropped = False
            self.resized_im = self.resizeIm(self.img_im,self.org_width,self.org_height,self.t1c1i1_width,self.t1c1i1_height)
            self.img_tk = self.im2tk(self.resized_im)
            self.t1c1i1.configure(image=self.img_tk)
            self.crop_preview_resized_im = self.resizeIm(self.crop_preview_im,self.crop_preview_width,self.crop_preview_height,self.t1c1i1_width*self.crop_preview_img_ratio,self.t1c1i1_height*self.crop_preview_img_ratio)
            self.crop_preview_tk = self.im2tk(self.crop_preview_resized_im)
            self.t1c2i1.configure(image=self.crop_preview_tk)
            time2 = time.time()
            print("server request = ",time1-time0,"gui = ",time2-time1)

    def previousRaw(self,event):
        """
        Requests and displays previous raw image

        @type  event: event
        @param event: Left arrow event

        @rtype:  None
        @return: None
        """
        self.pingServer()
        if self.serverConnected:
            time0 = time.time()
            query = self.interface.getPrevRawImage()
            if query == None:
                self.noPreviousRaw()
                self.t1_functional = False
            else:
                self.t1_functional = True
                self.imageID = query[1]
                self.org_np = np.array(query[0]) #self.get_image('frame0744.jpg')
            time1 = time.time()
            self.draw_np = np.copy(self.org_np)
            self.img_im = self.np2im(self.draw_np)
            self.crop_preview_im = self.img_im.copy()
            self.crop_preview_tk = self.im2tk(self.crop_preview_im)
            self.org_width,self.org_height = self.img_im.size
            self.crop_preview_width,self.crop_preview_height = self.img_im.size
            self.cropped = False
            self.resized_im = self.resizeIm(self.img_im,self.org_width,self.org_height,self.t1c1i1_width,self.t1c1i1_height)
            self.img_tk = self.im2tk(self.resized_im)
            self.t1c1i1.configure(image=self.img_tk)
            self.crop_preview_resized_im = self.resizeIm(self.crop_preview_im,self.crop_preview_width,self.crop_preview_height,self.t1c1i1_width*self.crop_preview_img_ratio,self.t1c1i1_height*self.crop_preview_img_ratio)
            self.crop_preview_tk = self.im2tk(self.crop_preview_resized_im)
            self.t1c2i1.configure(image=self.crop_preview_tk)
            time2 = time.time()
            print("server request = ",time1-time0,"gui = ",time2-time1)


    def submitCropped(self,event=None):
        """
        Submits cropped image to server

        @type  event: event
        @param event: Enter press or button press event

        @rtype:  None
        @return: None
        """
        if self.t1_functional:
            self.interface.postCroppedImage(self.imageID,self.crop_preview_im,[self.cx0,self.cy0],[self.cx1,self.cy1])
            (self.cx0,self.cy0,self.cx1,self.cy1)


    def nextCropped(self,event):
        """
        Requests and displays next cropped image

        @type  event: event
        @param event: Right arrow event

        @rtype:  None
        @return: None
        """
        print("focus is on: ",self.tab2.focus_get())
        self.pingServer()
        if self.serverConnected:
            time0 = time.time()
            query = self.interface.getNextCroppedImage()
            if query == None:
                self.t2_functional = False
                self.noNextCropped()
            else:
                self.t2_functional = True
                self.imageID = query[1]
                self.cropped_np = np.array(query[0])
                yaw_angle = self.getYawAngle(self.imageID)
                self.cropped_np = imutils.rotate_bound(self.cropped_np,yaw_angle)
            time1 = time.time()
            self.cropped_im = self.np2im(self.cropped_np)
            self.cropped_width,self.cropped_height = self.cropped_im.size
            self.cropped_resized_im = self.resizeIm(self.cropped_im,self.cropped_width,self.cropped_height,self.t2c2i1_width,self.t2c2i1_height)
            self.cropped_tk = self.im2tk(self.cropped_resized_im)
            self.t2c2i1.configure(image=self.cropped_tk)
            time2 = time.time()
            print("server request = ",time1-time0,"gui = ",time2-time1)

    def previousCropped(self,event):
        """
        Requests and displays previous cropped image

        @type  event: event
        @param event: Left arrow event

        @rtype:  None
        @return: None
        """
        self.pingServer()
        if self.serverConnected:
            time0 = time.time()
            query = self.interface.getPrevCroppedImage()
            if query == None:
                self.t2_functional = False
                self.noPreviousCropped()
            else:
                self.t2_functional = True
                self.imageID = query[1]
                self.cropped_np = np.array(query[0])
                yaw_angle = self.getYawAngle(self.imageID)
                self.cropped_np = imutils.rotate_bound(self.cropped_np,yaw_angle)
            time1 = time.time()
            self.cropped_im = self.np2im(self.cropped_np)
            self.cropped_width,self.cropped_height = self.cropped_im.size
            self.cropped_resized_im = self.resizeIm(self.cropped_im,self.cropped_width,self.cropped_height,self.t2c2i1_width,self.t2c2i1_height)
            self.cropped_tk = self.im2tk(self.cropped_resized_im)
            self.t2c2i1.configure(image=self.cropped_tk)
            time2 = time.time()
            print("server request = ",time1-time0,"gui = ",time2-time1)


    def submitClassification(self,event=None):
        """
        Submits classification of image to server

        @type  event: event
        @param event: Enter press event

        @rtype:  None
        @return: None
        """
        if self.t2_functional:
            shape = self.t2c2l2_var.get()
            alphanumeric = self.t2c2l4.get()
            orientation = self.t2c2l6_var.get()
            background_color = self.t2c2l10_var.get()
            alpha_color = self.t2c2l12_var.get()
            type = self.t2c2l14_var.get()
            description = self.t2c2l16_var.get()
            classification = client_rest.Classification(self.imageID,type,orientation,shape,background_color,alphanumeric,alpha_color,"unsubmitted",description)
            self.interface.postClass(classification)

    def tabChanged(self,event):
        """
        Performs the correct keybindings when you move to a new tab of the gui

        @type  event: event
        @param event: Tab changed event

        @rtype:  None
        @return: None
        """
        active_tab = self.n.index(self.n.select())
        if active_tab == 0:
            self.resizeEventTab0()
            self.master.unbind("<Right>")
            self.master.unbind("<Left>")
            self.master.unbind("<d>")
            self.master.unbind("<a>")
            self.master.bind("<Configure>",self.resizeEventTab0)
            self.master.unbind("<Control-z>")
            self.master.bind("<Return>",self.updateSettings)
            self.master.bind("<Escape>",self.close_window)
        if active_tab == 1:
            self.resizeEventTab1()
            self.master.bind("<Right>",self.nextRaw)
            self.master.bind("<Left>",self.previousRaw)
            self.master.unbind("<d>")
            self.master.unbind("<a>")
            self.master.bind("<Configure>",self.resizeEventTab1)
            self.master.bind("<Control-z>",self.undoCrop)
            self.master.bind("<Return>",self.submitCropped)
            self.master.bind("<Escape>",self.close_window)
        elif active_tab == 2:
            self.resizeEventTab2()
            self.master.bind("<Right>",self.nextCropped)
            self.master.bind("<Left>",self.previousCropped)
            self.master.unbind("<d>")
            self.master.unbind("<a>")
            self.master.bind("<Configure>",self.resizeEventTab2)
            self.master.unbind("<Control-z>")
            self.master.bind("<Return>",self.submitClassification)
            self.master.bind("<Escape>",self.close_window)
        elif active_tab == 3:
            self.resizeEventTab3()
            self.master.bind("<Right>",self.nextClassified)
            self.master.bind("<Left>",self.previousClassified)
            self.master.unbind("<d>")
            self.master.unbind("<a>")
            self.master.bind("<Configure>",self.resizeEventTab3)
            self.master.unbind("<Control-z>")
            self.master.bind("<Return>",self.submitTarget)
            self.master.bind("<Escape>",self.close_window)
            self.updateManualSubmissionTab()
        elif active_tab == 4:
            self.master.unbind("<Right>")
            self.master.unbind("<Left>")
            self.master.unbind("<d>")
            self.master.unbind("<a>")
            self.master.unbind("<Configure>")
            self.master.unbind("<Control-z>")
            self.master.unbind("<Return>",self.submitTarget)
            self.master.bind("<Escape>",self.close_window)

        self.master.focus_set()

    def updateSettings(self,event=None):
        """
        Attempts to connect to server when settings are changed

        @type  event: event
        @param event: Enter press or button press event

        @rtype:  None
        @return: None
        """
        host_new = self.t0c2host.get()
        port_new = self.t0c2port.get()
        ids_new = int(self.t0c2ids.get())
        debug_new = not(self.t0c2debug.get())
        self.interface = client_rest.ImagingInterface(host=host_new,port=port_new,numIdsStored=ids_new,isDebug=debug_new)
        self.pingServer()
        # Tab 1
        self.draw_np = np.copy(self.org_np)
        self.img_im = self.np2im(self.draw_np)
        self.cropped_im = self.np2im(self.cropped_np)
        self.cropped_width,self.cropped_height = self.cropped_im.size
        self.crop_preview_im = self.img_im.copy()
        self.org_width,self.org_height = self.img_im.size
        self.crop_preview_width,self.crop_preview_height = self.crop_preview_im.size
        if self.initialized and self.t1c1i1.winfo_width() > 1:
            self.resized_im = self.resizeIm(self.img_im,self.org_width,self.org_height,self.t1c1i1_width,self.t1c1i1_height)
            self.img_tk = self.im2tk(self.resized_im)
            self.crop_preview_resized_im = self.resizeIm(self.crop_preview_im,self.crop_preview_width,self.crop_preview_height,self.t1c1i1_width*self.crop_preview_img_ratio,self.t1c1i1_height*self.crop_preview_img_ratio)
            self.crop_preview_tk = self.im2tk(self.crop_preview_resized_im)
            self.cropped_resized_im = self.resizeIm(self.cropped_im,self.cropped_width,self.cropped_height,self.t2c2i1_width,self.t2c2i1_height)
            self.cropped_tk = self.im2tk(self.cropped_resized_im)
        else:
            self.cropped_tk = self.im2tk(self.cropped_im)
            self.img_tk = self.im2tk(self.img_im)
            self.crop_preview_tk = self.im2tk(self.crop_preview_im)
        self.t1c1i1.configure(image=self.img_tk)
        self.t1c2i1.configure(image=self.crop_preview_tk)
        self.t2c2i1.configure(image=self.cropped_tk)


    def pingServer(self):
        """
        Checks if server is correctly connected

        @rtype:  None
        @return: None
        """
        self.serverConnected = self.interface.ping()
        if self.serverConnected:
            self.org_np = self.get_image('assets/instructions.jpg')
            self.cropped_np = self.get_image('assets/classify_instructions.jpg')
        else:
            self.org_np = self.get_image('assets/server_error.jpg')
            self.cropped_np = self.get_image('assets/server_error.jpg')

    def noNextRaw(self):
        """
        Checks if server is correctly connected

        @rtype:  None
        @return: None
        """
        self.serverConnected = self.interface.ping()
        if self.serverConnected:
            self.org_np = self.get_image('assets/noNextRaw.jpg')
        else:
            self.org_np = self.get_image('assets/server_error.jpg')

    def noPreviousRaw(self):
        """
        Checks if server is correctly connected

        @rtype:  None
        @return: None
        """
        self.serverConnected = self.interface.ping()
        if self.serverConnected:
            self.org_np = self.get_image('assets/noPreviousRaw.jpg')
        else:
            self.org_np = self.get_image('assets/server_error.jpg')

    def noNextCropped(self):
        """
        Checks if server is correctly connected

        @rtype:  None
        @return: None
        """
        self.serverConnected = self.interface.ping()
        if self.serverConnected:
            self.cropped_np = self.get_image('assets/noNextCropped.jpg')
        else:
            self.cropped_np = self.get_image('assets/server_error.jpg')

    def noPreviousCropped(self):
        """
        Checks if server is correctly connected

        @rtype:  None
        @return: None
        """
        self.serverConnected = self.interface.ping()
        if self.serverConnected:
            self.cropped_np = self.get_image('assets/noPreviousCropped.jpg')
        else:
            self.cropped_np = self.get_image('assets/server_error.jpg')

    def disableEmergentDescription(self,*args):
        """
        Disables emergent discription unless emergent target selected

        @rtype:  None
        @return: None
        """
        if self.t2c2l14_var.get() == 'emergent':
            self.t2c2l16.configure(state=tk.NORMAL)
        else:
            self.t2c2l16_var.set("")
            self.t2c2l16.configure(state=tk.DISABLED)


    def alphanumericChanged(self,*args):
        """
        Fixes if you entered something wrong

        @rtype:  None
        @return: None
        """
        input = self.t2c2l4.get()
        if len(input) != 1:
            print("INPUT ERROR!")

    def alphanumericValidate(self,type, entry):
        """
        Fixes alphanumeric if you entered something wrong

        @rtype:  None
        @return: None
        """
        if type == '1':
        # runs if you try to insert something
            if len(entry) == 1 and (entry.isdigit() or entry.isalpha()):
                if entry.isupper():
                    return True
                else:
                    self.t2c2l4_var.set(entry.upper())
                    return True
            else:
                return False
        else:
            return True

    def updateManualSubmissionTab(self):
        self.serverConnected = self.interface.ping()
        if self.serverConnected:
            self.pendingList = self.interface.getPendingSubmissions()

            if len(self.pendingList) == 0:
                self.t3c1i1_im = self.t3_default_im.copy()
                self.t3c1i1_tk = self.im2tk(self.t3c1i1_im)
                self.t3c1i1_org_width,self.t3c1i1_org_height = self.t3c1i1_im.size
                self.t3c1i1.configure(image=self.t3c1i1_tk)
                self.t3c2i1_im = self.t3_default_im.copy()
                self.t3c2i1_tk = self.im2tk(self.t3c2i1_im)
                self.t3c2i1_org_width,self.t3c2i1_org_height = self.t3c2i1_im.size
                self.t3c2i1.configure(image=self.t3c2i1_tk)
                self.t3c3i1_im = self.t3_default_im.copy()
                self.t3c3i1_tk = self.im2tk(self.t3c3i1_im)
                self.t3c3i1_org_width,self.t3c3i1_org_height = self.t3c3i1_im.size
                self.t3c3i1.configure(image=self.t3c3i1_tk)
                self.t3c4i1_im = self.t3_default_im.copy()
                self.t3c4i1_tk = self.im2tk(self.t3c4i1_im)
                self.t3c4i1_org_width,self.t3c4i1_org_height = self.t3c4i1_im.size
                self.t3c4i1.configure(image=self.t3c4i1_tk)
                self.t3c5i1_im = self.t3_default_im.copy()
                self.t3c5i1_tk = self.im2tk(self.t3c5i1_im)
                self.t3c5i1_org_width,self.t3c5i1_org_height = self.t3c5i1_im.size
                self.t3c5i1.configure(image=self.t3c5i1_tk)
                self.t3c6i1_im = self.t3_default_im.copy()
                self.t3c6i1_tk = self.im2tk(self.t3c6i1_im)
                self.t3c6i1_org_width,self.t3c6i1_org_height = self.t3c6i1_im.size
                self.t3c6i1.configure(image=self.t3c6i1_tk)
                self.t3c1br5.configure(text="N/A")
                self.t3c1br7.configure(text="N/A")
                self.t3c1br9.configure(text="N/A")
                self.t3c1br11.configure(text="N/A")
                self.t3c1br13.configure(text="N/A")
                self.t3c1br15.configure(text="N/A")
                self.t3c1ar18.configure(text="N/A")
                self.t3c6br5.configure(text="N/A")
                self.t3c6br7.configure(text="N/A")
                self.t3c6br9.configure(text="N/A")
                self.t3c6br11.configure(text="N/A")
                self.t3c6br13.configure(text="N/A")
                self.t3c6br15.configure(text="N/A")
                self.t3c6ar18.configure(text="N/A")
                self.resizeEventTab3()
            else:
                self.t3_total_targets = len(self.pendingList)
                self.t3titleD.configure(text=self.t3_total_targets)
                self.t3titleB.configure(text=self.t3_current_target)
                pics = len(self.pendingList[self.t3_current_target-1])
                self.target_id = self.pendingList[self.t3_current_target-1][0].target
                if pics > 5:
                    pics = 5
                # Because of the preceeding if/else statement there will always be at least 1 pic
                query = self.interface.getCroppedImage(self.pendingList[self.t3_current_target-1][0].crop_id)
                self.t3c1i1_im = query[0]
                yaw_angle = self.getYawAngle(query[1])
                self.t3c1i1_im = self.t3c1i1_im.rotate(yaw_angle,expand=1)
                self.t3c1i1_org_width,self.t3c1i1_org_height = self.t3c1i1_im.size
                self.t3c1i1_tk = self.im2tk(self.t3c1i1_im)
                self.t3c1i1.configure(image=self.t3c1i1_tk)
                self.t3c1br5.configure(text=self.pendingList[self.t3_current_target-1][0].shape)
                self.t3c1br7.configure(text=self.pendingList[self.t3_current_target-1][0].background_color)
                self.t3c1br9.configure(text=self.pendingList[self.t3_current_target-1][0].alphanumeric)
                self.t3c1br11.configure(text=self.pendingList[self.t3_current_target-1][0].alphanumeric_color)
                self.t3c1br13.configure(text=self.pendingList[self.t3_current_target-1][0].orientation)
                self.t3c1br15.configure(text=self.pendingList[self.t3_current_target-1][0].type)
                self.t3c1ar18.configure(text=self.pendingList[self.t3_current_target-1][0].description)
                self.pending_bg_color = [self.pendingList[self.t3_current_target-1][0].background_color]
                self.pending_alpha_color = [self.pendingList[self.t3_current_target-1][0].alphanumeric_color]
                self.pending_orientation = [self.pendingList[self.t3_current_target-1][0].orientation]
                self.pending_description = [self.pendingList[self.t3_current_target-1][0].description]

                if pics > 1:
                    query = self.interface.getCroppedImage(self.pendingList[self.t3_current_target-1][1].crop_id)
                    print("query")
                    self.t3c2i1_im = query[0]
                    yaw_angle = self.getYawAngle(query[1])
                    self.t3c2i1_im = self.t3c2i1_im.rotate(yaw_angle,expand=1)
                    self.t3c2i1_org_width,self.t3c2i1_org_height = self.t3c2i1_im.size
                    self.t3c2i1_tk = self.im2tk(self.t3c2i1_im)
                    self.t3c2i1.configure(image=self.t3c2i1_tk)
                    self.t3c2br5.configure(text=self.pendingList[self.t3_current_target-1][1].shape)
                    self.t3c2br7.configure(text=self.pendingList[self.t3_current_target-1][1].background_color)
                    self.t3c2br9.configure(text=self.pendingList[self.t3_current_target-1][1].alphanumeric)
                    self.t3c2br11.configure(text=self.pendingList[self.t3_current_target-1][1].alphanumeric_color)
                    self.t3c2br13.configure(text=self.pendingList[self.t3_current_target-1][1].orientation)
                    self.t3c2br15.configure(text=self.pendingList[self.t3_current_target-1][1].type)
                    self.t3c2ar18.configure(text=self.pendingList[self.t3_current_target-1][1].description)
                    self.pending_bg_color.append(self.pendingList[self.t3_current_target-1][1].background_color)
                    self.pending_alpha_color.append(self.pendingList[self.t3_current_target-1][1].alphanumeric_color)
                    self.pending_orientation.append(self.pendingList[self.t3_current_target-1][1].orientation)
                    self.pending_description.append(self.pendingList[self.t3_current_target-1][1].description)
                else:
                    self.t3c2i1_im = self.t3_default_im.copy()
                    self.t3c2i1_org_width,self.t3c2i1_org_height = self.t3c2i1_im.size
                    self.t3c2i1_tk = self.im2tk(self.t3c2i1_im)
                    self.t3c2i1.configure(image=self.t3c2i1_tk)
                    self.t3c2br5.configure(text="N/A")
                    self.t3c2br7.configure(text="N/A")
                    self.t3c2br9.configure(text="N/A")
                    self.t3c2br11.configure(text="N/A")
                    self.t3c2br13.configure(text="N/A")
                    self.t3c2br15.configure(text="N/A")
                    self.t3c2ar18.configure(text="N/A")
                if pics > 2:
                    query = self.interface.getCroppedImage(self.pendingList[self.t3_current_target-1][2].crop_id)
                    self.t3c3i1_im = query[0]
                    yaw_angle = self.getYawAngle(query[1])
                    self.t3c3i1_im = self.t3c3i1_im.rotate(yaw_angle,expand=1)
                    self.t3c3i1_org_width,self.t3c3i1_org_height = self.t3c3i1_im.size
                    self.t3c3i1_tk = self.im2tk(self.t3c3i1_im)
                    self.t3c3i1.configure(image=self.t3c3i1_tk)
                    self.t3c3br5.configure(text=self.pendingList[self.t3_current_target-1][2].shape)
                    self.t3c3br7.configure(text=self.pendingList[self.t3_current_target-1][2].background_color)
                    self.t3c3br9.configure(text=self.pendingList[self.t3_current_target-1][2].alphanumeric)
                    self.t3c3br11.configure(text=self.pendingList[self.t3_current_target-1][2].alphanumeric_color)
                    self.t3c3br13.configure(text=self.pendingList[self.t3_current_target-1][2].orientation)
                    self.t3c3br15.configure(text=self.pendingList[self.t3_current_target-1][2].type)
                    self.t3c3ar18.configure(text=self.pendingList[self.t3_current_target-1][2].description)
                    self.pending_bg_color.append(self.pendingList[self.t3_current_target-1][2].background_color)
                    self.pending_alpha_color.append(self.pendingList[self.t3_current_target-1][2].alphanumeric_color)
                    self.pending_orientation.append(self.pendingList[self.t3_current_target-1][2].orientation)
                    self.pending_description.append(self.pendingList[self.t3_current_target-1][2].description)
                else:
                    self.t3c3i1_im = self.t3_default_im.copy()
                    self.t3c3i1_org_width,self.t3c3i1_org_height = self.t3c3i1_im.size
                    self.t3c3i1_tk = self.im2tk(self.t3c3i1_im)
                    self.t3c3i1.configure(image=self.t3c3i1_tk)
                    self.t3c3br5.configure(text="N/A")
                    self.t3c3br7.configure(text="N/A")
                    self.t3c3br9.configure(text="N/A")
                    self.t3c3br11.configure(text="N/A")
                    self.t3c3br13.configure(text="N/A")
                    self.t3c3br15.configure(text="N/A")
                    self.t3c3ar18.configure(text="N/A")
                if pics > 3:
                    query = self.interface.getCroppedImage(self.pendingList[self.t3_current_target-1][3].crop_id)
                    self.t3c4i1_im = query[0]
                    yaw_angle = self.getYawAngle(query[1])
                    self.t3c4i1_im = self.t3c4i1_im.rotate(yaw_angle,expand=1)
                    self.t3c4i1_org_width,self.t3c4i1_org_height = self.t3c4i1_im.size
                    self.t3c4i1_tk = self.im2tk(self.t3c4i1_im)
                    self.t3c4i1.configure(image=self.t3c4i1_tk)
                    self.t3c4br5.configure(text=self.pendingList[self.t3_current_target-1][3].shape)
                    self.t3c4br7.configure(text=self.pendingList[self.t3_current_target-1][3].background_color)
                    self.t3c4br9.configure(text=self.pendingList[self.t3_current_target-1][3].alphanumeric)
                    self.t3c4br11.configure(text=self.pendingList[self.t3_current_target-1][3].alphanumeric_color)
                    self.t3c4br13.configure(text=self.pendingList[self.t3_current_target-1][3].orientation)
                    self.t3c4br15.configure(text=self.pendingList[self.t3_current_target-1][3].type)
                    self.t3c4ar18.configure(text=self.pendingList[self.t3_current_target-1][3].description)
                    self.pending_bg_color.append(self.pendingList[self.t3_current_target-1][3].background_color)
                    self.pending_alpha_color.append(self.pendingList[self.t3_current_target-1][3].alphanumeric_color)
                    self.pending_orientation.append(self.pendingList[self.t3_current_target-1][3].orientation)
                    self.pending_description.append(self.pendingList[self.t3_current_target-1][3].description)
                else:
                    self.t3c4i1_im = self.t3_default_im.copy()
                    self.t3c4i1_org_width,self.t3c4i1_org_height = self.t3c4i1_im.size
                    self.t3c4i1_tk = self.im2tk(self.t3c4i1_im)
                    self.t3c4i1.configure(image=self.t3c4i1_tk)
                    self.t3c4br5.configure(text="N/A")
                    self.t3c4br7.configure(text="N/A")
                    self.t3c4br9.configure(text="N/A")
                    self.t3c4br11.configure(text="N/A")
                    self.t3c4br13.configure(text="N/A")
                    self.t3c4br15.configure(text="N/A")
                    self.t3c4ar18.configure(text="N/A")
                if pics > 4:
                    query = self.interface.getCroppedImage(self.pendingList[self.t3_current_target-1][4].crop_id)
                    self.t3c5i1_im = query[0]
                    yaw_angle = self.getYawAngle(query[1])
                    self.t3c5i1_im = self.t3c5i1_im.rotate(yaw_angle,expand=1)
                    self.t3c5i1_org_width,self.t3c5i1_org_height = self.t3c5i1_im.size
                    self.t3c5i1_tk = self.im2tk(self.t3c5i1_im)
                    self.t3c5i1.configure(image=self.t3c5i1_tk)
                    self.t3c5br5.configure(text=self.pendingList[self.t3_current_target-1][4].shape)
                    self.t3c5br7.configure(text=self.pendingList[self.t3_current_target-1][4].background_color)
                    self.t3c5br9.configure(text=self.pendingList[self.t3_current_target-1][4].alphanumeric)
                    self.t3c5br11.configure(text=self.pendingList[self.t3_current_target-1][4].alphanumeric_color)
                    self.t3c5br13.configure(text=self.pendingList[self.t3_current_target-1][4].orientation)
                    self.t3c5br15.configure(text=self.pendingList[self.t3_current_target-1][4].type)
                    self.t3c5ar18.configure(text=self.pendingList[self.t3_current_target-1][4].description)
                    self.pending_bg_color.append(self.pendingList[self.t3_current_target-1][4].background_color)
                    self.pending_alpha_color.append(self.pendingList[self.t3_current_target-1][4].alphanumeric_color)
                    self.pending_orientation.append(self.pendingList[self.t3_current_target-1][4].orientation)
                    self.pending_description.append(self.pendingList[self.t3_current_target-1][4].description)
                else:
                    self.t3c5i1_im = self.t3_default_im.copy()
                    self.t3c5i1_org_width,self.t3c5i1_org_height = self.t3c5i1_im.size
                    self.t3c5i1_tk = self.im2tk(self.t3c5i1_im)
                    self.t3c5i1.configure(image=self.t3c5i1_tk)
                    self.t3c5br5.configure(text="N/A")
                    self.t3c5br7.configure(text="N/A")
                    self.t3c5br9.configure(text="N/A")
                    self.t3c5br11.configure(text="N/A")
                    self.t3c5br13.configure(text="N/A")
                    self.t3c5br15.configure(text="N/A")
                    self.t3c5ar18.configure(text="N/A")
                # Possible Submission
                self.t3c6i1_im = self.t3c1i1_im.copy()
                self.t3c6i1_org_width,self.t3c6i1_org_height = self.t3c6i1_im.size
                self.t3c6i1_tk = self.im2tk(self.t3c6i1_im)
                self.t3c6i1.configure(image=self.t3c6i1_tk)
                self.t3c6br5.configure(text=self.pendingList[self.t3_current_target-1][0].shape)
                self.t3c6br7.configure(text=self.findMostCommonValue(self.pending_bg_color))
                self.t3c6br9.configure(text=self.pendingList[self.t3_current_target-1][0].alphanumeric)
                self.t3c6br11.configure(text=self.findMostCommonValue(self.pending_alpha_color))
                self.t3c6br13.configure(text=self.findMostCommonValue(self.pending_orientation))
                self.t3c6br15.configure(text=self.pendingList[self.t3_current_target-1][0].type)
                self.t3c6ar18.configure(text=self.findMostCommonValue(self.pending_description))

                for ii in range(5):
                    self.resizeEventTab3()



        else:
            error_np = self.get_image('assets/server_error.jpg')
            error_im = self.np2im(error_np)
            self.t3c1i1_im = error_im.copy()
            self.t3c1i1_tk = self.im2tk(self.t3c1i1_im)
            self.t3c1i1_org_width,self.t3c1i1_org_height = self.t3c1i1_im.size
            self.t3c1i1.configure(image=self.t3c1i1_tk)
            self.t3c2i1_im = error_im.copy()
            self.t3c2i1_tk = self.im2tk(self.t3c2i1_im)
            self.t3c2i1_org_width,self.t3c2i1_org_height = self.t3c2i1_im.size
            self.t3c2i1.configure(image=self.t3c2i1_tk)
            self.t3c3i1_im = error_im.copy()
            self.t3c3i1_tk = self.im2tk(self.t3c3i1_im)
            self.t3c3i1_org_width,self.t3c3i1_org_height = self.t3c3i1_im.size
            self.t3c3i1.configure(image=self.t3c3i1_tk)
            self.t3c4i1_im = error_im.copy()
            self.t3c4i1_tk = self.im2tk(self.t3c4i1_im)
            self.t3c4i1_org_width,self.t3c4i1_org_height = self.t3c4i1_im.size
            self.t3c4i1.configure(image=self.t3c4i1_tk)
            self.t3c5i1_im = error_im.copy()
            self.t3c5i1_tk = self.im2tk(self.t3c5i1_im)
            self.t3c5i1_org_width,self.t3c5i1_org_height = self.t3c5i1_im.size
            self.t3c5i1.configure(image=self.t3c5i1_tk)
            self.t3c6i1_im = error_im.copy()
            self.t3c6i1_tk = self.im2tk(self.t3c6i1_im)
            self.t3c6i1_org_width,self.t3c6i1_org_height = self.t3c6i1_im.size
            self.t3c6i1.configure(image=self.t3c6i1_tk)
            self.resizeEventTab3()

    def nextClassified(self,event):
        """
        Goes to next classified target group

        @type  event: event
        @param event: Right arrow event

        @rtype:  None
        @return: None
        """
        #self.updateManualSubmissionTab()
        self.serverConnected = self.interface.ping()
        if self.serverConnected:
            if self.t3_current_target < len(self.pendingList):
                self.t3_current_target += 1
            elif len(self.pendingList) == 0:
                self.t3_current_target = 0
            else:
                pass
        self.updateManualSubmissionTab()

    def previousClassified(self,event):
        """
        Goes to previous classified target group

        @type  event: event
        @param event: Right arrow event

        @rtype:  None
        @return: None
        """
        #self.updateManualSubmissionTab()
        self.serverConnected = self.interface.ping()
        if self.serverConnected:
            if self.t3_current_target > 1:
                self.t3_current_target -= 1
            elif len(self.pendingList) == 0:
                self.t3_current_target = 0
            else:
                pass
        self.updateManualSubmissionTab()


    def submitTarget(self,event=None):
        """
        Submits Target to server

        @type  event: event
        @param event: Enter press or button press event

        @rtype:  None
        @return: None
        """
        self.interface.postSubmitTargetById(self.target_id,True)
        print(self.target_id)
        self.updateManualSubmissionTab()

    def findMostCommonValue(self, classifications):
        """
        Calculate the most common value in a specified column (useful for all the enum columns)

        @type classifications: list of value lists (ie: from a cursor.fetchall())
        @param classifications: database rows to use to calculate the average
        @type clmnNun: int
        @param clmnNum: Integer of the column to access in each row to get values for avg calculation
        """

        # dictionary keeps track of how many times we've seen a particular column value
        # EX: {
        #       "red": 2,
        #        "white": 1}
        valueCounts = {}
        # for each classification in our list of classifications
        # a classification here is a list
        for classification in classifications:
            if classification is not None:
                # if the value at the classification has not been added to our dictionary yet
                if classification not in valueCounts:
                    valueCounts[classification] = 0
                valueCounts[classification] += 1 # increment the particular value in the dict

        if valueCounts: # if the dictionary isnt empty
            mostCommon = max(valueCounts, key=valueCounts.get)
            return mostCommon
        return None # if there are no values for this particular field, return None

    def getYawAngle(self,imageID):
        info = self.interface.getImageInfo(imageID)
        image_state = self.interface.getStateByTs(info.time_stamp)
        if image_state == None:
            #yaw_angle = 0.0
            yaw = np.random.uniform(0,360)
        else:
            yaw = image_state.yaw
        return(yaw)


if __name__ == "__main__":
    root = tk.Tk()
    style = ThemedStyle(root)
    style.set_theme("arc")
    gui = GuiClass(root)
    try:
        gui.mainloop()
    except KeyboardInterrupt:
        root.destroy()
        sys.exit()
