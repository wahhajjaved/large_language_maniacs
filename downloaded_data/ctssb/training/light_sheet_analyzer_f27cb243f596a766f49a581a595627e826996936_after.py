# -*- coding: utf-8 -*-
"""
Created on Thu Feb 11 15:04:31 2016

@author: kyle
"""

import os
from os.path import expanduser
import numpy as np
from qtpy import QtGui, QtWidgets, QtCore
from time import time
import global_vars as g
from process.BaseProcess import BaseProcess, SliderLabel, CheckBox, ComboBox
import pyqtgraph as pg
from window import Window
from scipy.ndimage.interpolation import zoom
import tifffile


#from skimage.transform import resize
#from spimagine import volshow




class Light_Sheet_Analyzer(BaseProcess):
    """ light_Sheet_Analyzer(nSteps, shift_factor, keepSourceWindow=False)
    Makes a 3D viewer for data acquired using a light sheet microscope.

    Parameters:
        | nSteps (int) -- How many stacks per volume
        | shift_factor (int)
    Returns:
        Volume_Viewer
    """
    def __init__(self):
        if g.settings['light_sheet_analyzer'] is None:
            s = dict()
            s['nSteps'] = 1
            s['shift_factor'] = 1
            s['triangle_scan'] = False
            g.settings['light_sheet_analyzer']=s
        super().__init__()


    def __call__(self, nSteps, shift_factor, triangle_scan, keepSourceWindow=False):
        g.settings['light_sheet_analyzer']['nSteps']=nSteps
        g.settings['light_sheet_analyzer']['shift_factor']=shift_factor
        g.settings['light_sheet_analyzer']['triangle_scan'] = triangle_scan
        g.m.statusBar().showMessage("Generating 4D movie ...")
        t = time()
        self.start(keepSourceWindow)
        A = np.copy(self.tif)
        # A = A[1:]  # Ian Parker said to hard code removal of the first frame.
        '''
        A=g.m.currentWindow.image
        nSteps=250
        shift_factor=1
        
        '''
        mt, mx, my = A.shape
        if triangle_scan:
            for i in np.arange(mt // (nSteps * 2)):
                t0 = i * nSteps * 2 + nSteps
                tf = (i + 1) * nSteps * 2
                A[t0:tf] = A[tf:t0:-1]

        mv = mt // nSteps  # number of volumes
        A = A[:mv * nSteps]
        B = np.reshape(A, (mv, nSteps, mx, my))
        B = B.swapaxes(1, 3)  # the direction we step is going to be the new y axis, whereas the old y axis will eventually become the z axis
        B = np.repeat(B, shift_factor, axis=3)  # We need to stretch the y axis pixels (which were the step size) so that one new y pixel is the same as a pixel in the x direction. Hopefully before this transformation, the step size (ums) is an integer multiple of the x pixel size (um).
        # Now our matrix is in terms of (mv, mz, mx, my).
        mv, mz, mx, my = B.shape

        mz_new, _ = zoom(B[0, :, 0, :], (1 / np.sqrt(2), 1)).shape
        C = np.zeros((mv, mz_new, mx, my), dtype=B.dtype)
        for v in np.arange(mv):
            for x in np.arange(mx):
                C[v, :, x, :] = zoom(B[v, :, x, :], (1 / np.sqrt(2), 1), order=0)  # squash the z axis pixel size by sqrt(2)
        mv, mz, mx, my = C.shape

        newy = my + mz  # because we will be shifting each x-y plane in the y direction by one pixel, the resulting size will be my plus the number of x-y planes (mz)
        D = np.zeros((mv, mz, mx, newy), dtype=A.dtype)
        shifted = 0
        for z in np.arange(mz):
            minus_z = mz - z
            shifted = minus_z
            D[:, z, :, shifted:shifted + my] = C[:, z, :, :]
        D = D[:, ::-1, :, :]  # (mv, mz, mx, my)

        g.m.statusBar().showMessage("Successfully generated movie ({} s)".format(time() - t))
        w = Window(np.squeeze(D[:,0,:,:]), name=self.oldname)
        w.volume=D

        Volume_Viewer(w)
        return 


    def closeEvent(self, event):
        self.ui.close()
        event.accept()

    def gui(self):
        s=g.settings['light_sheet_analyzer']
        self.gui_reset()
        self.nSteps = pg.SpinBox(int=True, step=1)
        self.nSteps.setMinimum(1)
        self.nSteps.setValue(s['nSteps'])
        
        self.shift_factor = pg.SpinBox(int=False, step=.1)
        self.shift_factor.setValue(s['shift_factor'])

        self.triangle_scan = CheckBox()
        self.triangle_scan.setValue(s['triangle_scan'])

        
        self.items.append({'name': 'nSteps', 'string': 'Number of steps per volume', 'object': self.nSteps})
        self.items.append({'name': 'shift_factor', 'string': 'Shift Factor', 'object': self.shift_factor})
        self.items.append({'name': 'triangle_scan', 'string': 'Trangle Scan', 'object': self.triangle_scan})
        super().gui()
        
light_sheet_analyzer = Light_Sheet_Analyzer()


class Ratio_by_baseline(BaseProcess):
    """ ratio_by_baseline(nSteps, first_volume, nVolumes, ratio_type, keepSourceWindow=False)

    Parameters:
        | nSteps (int) -- Number of steps per volume
        | first_volume (int) -- The first volume to be used in the baseline.
        | nVolumes (int) -- The number of volume to be combined in the baseline.
        | ratio_type (str) -- The method used to combine the frames in the baseline.  Either 'standard deviation' or 'average'.
    Returns:
        newWindow
    """

    def __init__(self):
        super().__init__()

    def gui(self):
        self.gui_reset()
        nSteps         = pg.SpinBox(int=True, step=1)
        first_volume   = pg.SpinBox(int=True, step=1)
        nVolumes       = pg.SpinBox(int=True, step=1)
        nVolumes.setMinimum(1)
        ratio_type = ComboBox()
        ratio_type.addItem('average')
        ratio_type.addItem('standard deviation')
        self.items.append({'name': 'nSteps',       'string': 'Number of steps per volume', 'object': nSteps      })
        self.items.append({'name': 'first_volume', 'string': 'First Volume',               'object': first_volume})
        self.items.append({'name': 'nVolumes',     'string': 'Number of Volumes',           'object': nVolumes    })
        self.items.append({'name': 'ratio_type',   'string': 'Ratio Type',                 'object': ratio_type  })
        super().gui()

    def get_init_settings_dict(self):
        s = dict()
        s['nSteps'] = 1
        s['first_volume'] = 0
        s['nVolumes'] = 1
        s['ratio_type'] = 'average'
        return s

    def __call__(self, nSteps, first_volume, nVolumes, ratio_type, keepSourceWindow=False):
        self.start(keepSourceWindow)
        A = np.copy(self.tif).astype(np.float)
        mt, mx, my = A.shape
        mv = mt // nSteps  # number of volumes
        for i in range(nSteps):
            baseline = A[i+first_volume*nSteps:nVolumes*nSteps:nSteps]
            if ratio_type == 'average':
                baseline = np.average(baseline,0)
            elif ratio_type == 'standard deviation':
                baseline = np.std(baseline,0)
            else:
                g.alert("'{}' is an unknown ratio_type.  Try 'average' or 'standard deviation'".format(ratio_type))
                return None
            A[i::nSteps] = A[i::nSteps] / baseline
        self.newtif = A
        self.newname = self.oldname + ' - Ratioed by ' + str(ratio_type)
        return self.end()


ratio_by_baseline = Ratio_by_baseline()

class Volume_Viewer(QtWidgets.QWidget):
    closeSignal=QtCore.Signal()

    def show_wo_focus(self):
        self.show()
        self.window.activateWindow()  # for Windows
        self.window.raise_()  # for MacOS

    def __init__(self,window=None,parent=None):
        super(Volume_Viewer,self).__init__(parent) ## Create window with ImageView widget
        g.m.volume_viewer=self
        window.lostFocusSignal.connect(self.hide)
        window.gainedFocusSignal.connect(self.show_wo_focus)
        self.window=window
        self.setWindowTitle('Light Sheet Volume View Controller')
        self.setWindowIcon(QtGui.QIcon('images/favicon.png'))
        self.setGeometry(QtCore.QRect(422, 35, 222, 86))
        self.layout = QtWidgets.QVBoxLayout()
        self.vol_shape=window.volume.shape
        mv,mz,mx,my=window.volume.shape
        self.currentAxisOrder=[0,1,2,3]
        self.current_v_Index=0
        self.current_z_Index=0
        self.current_x_Index=0
        self.current_y_Index=0
        self.formlayout=QtWidgets.QFormLayout()
        self.formlayout.setLabelAlignment(QtCore.Qt.AlignRight)
        self.xzy_position_label = QtWidgets.QLabel('Z position')
        self.zSlider=SliderLabel(0)
        self.zSlider.setRange(0,mz-1)
        self.zSlider.label.valueChanged.connect(self.zSlider_updated)
        self.zSlider.slider.mouseReleaseEvent=self.zSlider_release_event
        
        self.sideViewOn=CheckBox()
        self.sideViewOn.setChecked(False)
        self.sideViewOn.stateChanged.connect(self.sideViewOnClicked)
        
        self.sideViewSide = QtWidgets.QComboBox(self)
        self.sideViewSide.addItem("X")
        self.sideViewSide.addItem("Y")
        
        self.MaxProjButton = QtWidgets.QPushButton('Max Intenstiy Projection')
        self.MaxProjButton.pressed.connect(self.make_maxintensity)
        
        self.exportVolButton = QtWidgets.QPushButton('Export Volume')
        self.exportVolButton.pressed.connect(self.export_volume)
        
        self.formlayout.addRow(self.xzy_position_label,self.zSlider)
        self.formlayout.addRow('Side View On',self.sideViewOn)
        self.formlayout.addRow('Side View Side',self.sideViewSide)
        self.formlayout.addRow('', self.MaxProjButton)
        self.formlayout.addRow('', self.exportVolButton)
        
        self.layout.addWidget(self.zSlider)
        self.layout.addLayout(self.formlayout)
        self.setLayout(self.layout)
        self.setGeometry(QtCore.QRect(381, 43, 416, 110))
        self.show()

    def closeEvent(self, event):
        event.accept() # let the window close
        
    def zSlider_updated(self,z_val):
        self.current_v_Index=self.window.currentIndex
        vol=self.window.volume
        testimage=np.squeeze(vol[self.current_v_Index,z_val,:,:])
        viewRect = self.window.imageview.view.targetRect()
        self.window.imageview.setImage(testimage,autoLevels=False)
        self.window.imageview.view.setRange(viewRect, padding = 0)
        self.window.image = testimage
        
    def zSlider_release_event(self,ev):
        vol=self.window.volume
        if self.currentAxisOrder[1]==1: # 'z'
            self.current_z_Index=self.zSlider.value()
            image=np.squeeze(vol[:,self.current_z_Index,:,:])
        elif self.currentAxisOrder[1]==2: # 'x'
            self.current_x_Index=self.zSlider.value()
            image=np.squeeze(vol[:,self.current_x_Index,:,:])
        elif self.currentAxisOrder[1]==3: # 'y'
            self.current_y_Index=self.zSlider.value()
            image=np.squeeze(vol[:,self.current_y_Index,:,:])

        viewRect = self.window.imageview.view.viewRect()
        self.window.imageview.setImage(image,autoLevels=False)
        self.window.imageview.view.setRange(viewRect, padding=0)
        self.window.image = image
        self.window.imageview.setCurrentIndex(self.current_v_Index)
        self.window.activateWindow()  # for Windows
        self.window.raise_()  # for MacOS
        QtWidgets.QSlider.mouseReleaseEvent(self.zSlider.slider, ev)
    
    def sideViewOnClicked(self, checked):
        self.current_v_Index=self.window.currentIndex
        vol=self.window.volume
        if checked==2: #checked=True
            assert self.currentAxisOrder==[0,1,2,3]
            side = self.sideViewSide.currentText()
            if side=='X':
                vol=vol.swapaxes(1,2)
                self.currentAxisOrder=[0,2,1,3]
                vol=vol.swapaxes(2,3)
                self.currentAxisOrder=[0,2,3,1]
            elif side=='Y':
                vol=vol.swapaxes(1,3)
                self.currentAxisOrder=[0,3,2,1]
        else: #checked=False
            if self.currentAxisOrder == [0,3,2,1]:
                vol=vol.swapaxes(1,3)
                self.currentAxisOrder=[0,1,2,3]
            elif self.currentAxisOrder == [0,2,3,1]:
                vol=vol.swapaxes(2,3)
                vol=vol.swapaxes(1,2)
                self.currentAxisOrder=[0,1,2,3]
        if self.currentAxisOrder[1]==1: # 'z'
            idx=self.current_z_Index
            self.xzy_position_label.setText('Z position')
            self.zSlider.setRange(0,self.vol_shape[1]-1)
        elif self.currentAxisOrder[1]==2: # 'x'
            idx=self.current_x_Index
            self.xzy_position_label.setText('X position')
            self.zSlider.setRange(0,self.vol_shape[2]-1)
        elif self.currentAxisOrder[1]==3: # 'y'
            idx=self.current_y_Index
            self.xzy_position_label.setText('Y position')
            self.zSlider.setRange(0,self.vol_shape[3]-1)
        image=np.squeeze(vol[:,idx,:,:])
        self.window.imageview.setImage(image,autoLevels=False)
        self.window.volume=vol
        self.window.imageview.setCurrentIndex(self.current_v_Index)
        self.zSlider.setValue(idx)

    def make_maxintensity(self):
        vol=self.window.volume
        new_vol=np.max(vol,1)
        if self.currentAxisOrder[1]==1: # 'z'
            name='Max Z projection'
        elif self.currentAxisOrder[1]==2: # 'x'
            name = 'Max X projection'
        elif self.currentAxisOrder[1]==3: # 'y'
            name = 'Max Y projection'
        Window(new_vol, name=name)
        
    def export_volume(self):
        vol=self.window.volume
        export_path = QtWidgets.QFileDialog.getExistingDirectory(g.m, "Select a parent folder to save into.", expanduser("~"), QtWidgets.QFileDialog.ShowDirsOnly)
        export_path = os.path.join(export_path, 'light_sheet_vols')
        i=0
        while os.path.isdir(export_path+str(i)):
            i+=1
        export_path=export_path+str(i)
        os.mkdir(export_path) 
        for v in np.arange(len(vol)):
            A=vol[v]
            filename=os.path.join(export_path,str(v)+'.tiff')
            if len(A.shape)==3:
                A=np.transpose(A,(0,2,1)) # This keeps the x and the y the same as in FIJI
            elif len(A.shape)==2:
                A=np.transpose(A,(1,0))
            tifffile.imsave(filename, A)

#v=Volume_Viewer(g.m.currentWindow)


    
