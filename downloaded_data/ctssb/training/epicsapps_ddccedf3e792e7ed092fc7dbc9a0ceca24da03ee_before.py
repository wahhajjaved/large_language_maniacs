"""
Base Image Panel to be inherited by other ImagePanels
"""

import io
import wx
import time
import numpy as np
import os
import shutil
import math
import atexit
from threading import Thread
from six import StringIO
import base64
import zmq
from PIL import Image

from epics.wx.utils import  Closure, add_button
from wxutils import MenuItem, Choice

is_wxPhoenix = 'phoenix' in wx.PlatformInfo

if is_wxPhoenix:
    Bitmap = wx.Bitmap
else:
    Bitmap = wx.BitmapFromImage


class JpegServer(object):
    def __init__(self, port=17166, delay=0.05):
        self.delay = delay
        ctx = zmq.Context()
        self.socket = ctx.socket(zmq.REP)
        self.socket.bind("tcp://*:%d" % port)
        self.data = None

    def serve(self):
        while True:
            try:
                message = self.socket.recv()
            except:
                continue
            try:
                ncols, nrows, nx = self.data.shape
            except:
                continue
            tmp = io.BytesIO()
            Image.frombytes('RGB', (nrows, ncols), self.data).save(tmp, 'JPEG')
            tmp.seek(0)
            bindat = base64.b64encode(tmp.read()).decode('utf-8')
            self.socket.send_json({'format':'jpeg', 'image':bindat,
                                   'shape': self.data.shape})
            time.sleep(self.delay)

class ImagePanel_Base(wx.Panel):
    """Image Panel for FlyCapture2 camera"""

    def Start(self):
        "turn camera on"
        raise NotImplementedError('must provide Start()')

    def Stop(self):
        "turn camera off"
        raise NotImplementedError('must provide Stop()')

    def CaptureVideo(self, filename='Capture', format='MJPG', runtime=60.0):
        pass

    def SetExposureTime(self, exptime):
        "set exposure time... overwrite this!"
        raise NotImplementedError('must provide SetExposureTime()')

    def GrabWxImage(self, scale=1, rgb=True, can_skip=True):
        "grab Wx Image, with scale and rgb=True/False"
        raise NotImplementedError('must provide GrabWxImage()')

    def GrabNumpyImage(self):
        "grab Image as numpy array"
        raise NotImplementedError('must provide GrabNumpyImage()')

    def AutoSetExposureTime(self):
        """auto set exposure time"""
        raise NotImplementedError('must provide AutoSetExposure')

    def __init__(self, parent, camera_id=0, writer=None, output_pv=None,
                 leftdown_cb=None, motion_cb=None, publish_jpeg=True,
                 publish_delay=0.2, publish_port=17166, draw_objects=None,
                 zoompanel=None, **kws):

        super(ImagePanel_Base, self).__init__(parent, -1, size=(800, 600))
        self.img_w = 800.5
        self.img_h = 600.5
        self.writer = writer
        self.leftdown_cb = leftdown_cb
        self.motion_cb   = motion_cb
        self.output_pv = output_pv
        self.output_pvs = {}
        self.last_save = 0.0
        self.cam_name = '-'
        self.scale = 0.60
        self.count = 0
        self.image = None
        self.draw_objects = None
        self.zoompanel = zoompanel
        self.zoommode = 'click'
        self.SetBackgroundColour("#E4E4E4")
        self.starttime = time.clock()
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)

        self.Bind(wx.EVT_SIZE, self.onSize)
        self.Bind(wx.EVT_PAINT, self.onPaint)

        if self.leftdown_cb is not None:
            self.Bind(wx.EVT_LEFT_DOWN, self.onLeftDown)
        if self.motion_cb is not None:
            self.Bind(wx.EVT_MOTION, self.onMotion)
        self.Bind(wx.EVT_RIGHT_DOWN, self.onRightDown)
        self.fps_current = 1.0
        self.data = None
        self.data_shape = (0, 0, 0)

        self.full_image = None
        self.full_size = None
        self.build_popupmenu()

        self.publish_jpeg = publish_jpeg
        self.publisher = None
        if publish_jpeg:
            self.create_publisher(publish_delay, publish_port)

    def grab_data(self):
        self.data = self.GrabNumpyImage()
        self.last_data_time = time.time()
        return self.data

    def onSize(self, evt):
        frame_w, frame_h = evt.GetSize()
        self.scale = min(frame_w/self.img_w, frame_h/self.img_h)
        self.Refresh()
        evt.Skip()

    def onTimer(self, evt=None):
        self.Refresh()

    def onLeftDown(self, evt=None):
        """
        report left down events within image
        """
        if self.zoommode == 'click':
            self.show_zoompanel(evt.GetX(), evt.GetY())

        if self.leftdown_cb is not None:
            evt_x, evt_y = evt.GetX(), evt.GetY()
            max_x, max_y = self.full_size
            img_w, img_h = self.bitmap_size
            pan_w, pan_h = self.panel_size
            pad_w, pad_h = (pan_w-img_w)/2.0, (pan_h-img_h)/2.0

            x = int(0.5 + (evt_x - pad_w)/self.scale)
            y = int(0.5 + (evt_y - pad_h)/self.scale)
            self.leftdown_cb(x, y, xmax=max_x, ymax=max_y)


    def onMotion(self, evt=None):
        """
        report left down events within image
        """
        if self.motion_cb is None or self.full_size is None:
            return
        evt_x, evt_y = evt.GetX(), evt.GetY()
        max_x, max_y = self.full_size
        img_w, img_h = self.bitmap_size
        pan_w, pan_h = self.panel_size
        pad_w, pad_h = (pan_w-img_w)/2.0, (pan_h-img_h)/2.0

        x = int(0.5 + (evt_x - pad_w)/self.scale)
        y = int(0.5 + (evt_y - pad_h)/self.scale)
        self.motion_cb(x, y, xmax=max_x, ymax=max_y)
        if self.zoommode == 'live' and self.zoompanel is not None:
            self.show_zoompanel(evt_x, evt_y)

    def show_zoompanel(self, evt_x, evt_y):
        img_w, img_h = self.bitmap_size
        pan_w, pan_h = self.panel_size
        pad_w, pad_h = (pan_w-img_w)/2.0, (pan_h-img_h)/2.0

        x = int(0.5 + (evt_x - pad_w)/self.scale)
        y = int(0.5 + (evt_y - pad_h)/self.scale)
        self.x, self.y = x, y
        dh, dw, dc = self.data.shape
        if y > -1 and y <  dh and x > -1 and x < dw:
            if self.zoompanel is not None:
                self.zoompanel.xcen = x
                self.zoompanel.ycen = y
                self.zoompanel.Refresh()

    def build_popupmenu(self):
        self.popup_menu = popup = wx.Menu()
        MenuItem(self, popup, 'ZoomBox follows Cursor', '', self.zoom_motion_mode)
        MenuItem(self, popup, 'ZoomBox on Left Click', '',  self.zoom_click_mode)

    def zoom_motion_mode(self, evt=None):
        self.zoommode = 'live'

    def zoom_click_mode(self, evt=None):
        self.zoommode = 'click'


    def onRightDown(self, evt=None):
        wx.CallAfter(self.PopupMenu, self.popup_menu, evt.GetPosition())

    def onPaint(self, event):
        self.count += 1
        now = time.clock()
        elapsed = now - self.starttime
        if elapsed >= 2.0 and self.writer is not None:
            self.fps_current = (self.count/elapsed)
            self.writer("  %.2f fps" % (self.count/elapsed))
            self.starttime = now
            self.count = 0

        self.scale = max(self.scale, 0.05)
        # try:
        self.image = self.GrabWxImage(scale=self.scale, rgb=True)
        if self.publisher is not None:
            self.publisher.data = self.data
        # except: #  ValueError:
        #    return

        if self.image is None:
            return

        if self.full_size is None:
            img = self.GrabWxImage(scale=1.0, rgb=True)
            if img is not None:
                self.full_size = img.GetSize()

        try:
            bitmap = Bitmap(self.image)
        except ValueError:
            return
        t2 = time.clock()
        img_w, img_h = self.bitmap_size = bitmap.GetSize()
        pan_w, pan_h = self.panel_size  = self.GetSize()
        pad_w, pad_h = int(1+(pan_w-img_w)/2.0), int(1+(pan_h-img_h)/2.0)
        dc = wx.AutoBufferedPaintDC(self)

        dc.Clear()
        dc.DrawBitmap(bitmap, pad_w, pad_h, useMask=True)
        self.__draw_objects(dc, img_w, img_h, pad_w, pad_h)
        if self.zoompanel is not None:
            self.zoompanel.data = self.data
            self.zoompanel.Refresh()

    def __draw_objects(self, dc, img_w, img_h, pad_w, pad_h):
        dc.SetBrush(wx.Brush('Black', wx.BRUSHSTYLE_TRANSPARENT))
        if self.draw_objects is not None:
            for obj in self.draw_objects:
                shape = obj.get('shape', None)
                color = obj.get('color', None)
                if color is None:
                    color = obj.get('colour', 'Black')
                color = wx.Colour(*color)
                width = obj.get('width', 1.0)
                style = obj.get('style', wx.SOLID)
                args  = obj.get('args', [])
                kws   = obj.get('kws', {})

                method = getattr(dc, 'Draw%s' % (shape.title()), None)
                if shape.title() == 'Line':
                    args = [pad_w + args[0]*img_w,
                            pad_h + args[1]*img_h,
                            pad_w + args[2]*img_w,
                            pad_h + args[3]*img_h]
                elif shape.title() == 'Circle':
                    args = [pad_w + args[0]*img_w,
                            pad_h + args[1]*img_h,  args[2]*img_w]

                if method is not None:
                    dc.SetPen(wx.Pen(color, width, style))
                    method(*args, **kws)

    def create_publisher(self, delay, port):
        self.publish_jpeg = True
        self.publish_delay = delay
        self.publisher = JpegServer(port=port)
        self.jpeg_thread = Thread(target=self.publisher.serve)
        self.jpeg_thread.daemon = True
        self.jpeg_thread.start()

    def SaveImage(self, fname, filetype='jpeg'):
        """save image (jpeg) to file,
        return dictionary of image data, suitable for serialization
        """
        ftype = wx.BITMAP_TYPE_JPEG
        if filetype.lower() == 'png':
            ftype = wx.BITMAP_TYPE_PNG
        elif filetype.lower() in ('tiff', 'tif'):
            ftype = wx.BITMAP_TYPE_TIFF

        image = self.GrabWxImage(scale=1, rgb=True)
        if image is None:
            return

        width, height = image.GetSize()

        # make two device contexts -- copy bitamp to one,
        # use other for image+overlays
        dc_bitmap = wx.MemoryDC()
        dc_bitmap.SelectObject(Bitmap(image))
        dc_output = wx.MemoryDC()

        out = wx.Bitmap(width, height)
        dc_output.SelectObject(out)

        # draw image bitmap to output
        dc_output.Blit(0, 0, width, height, dc_bitmap, 0, 0)
        # draw overlays to output
        self.__draw_objects(dc_output, width, height, 0, 0)
        # save to image file
        ret = out.ConvertToImage().SaveFile(fname, ftype)
        # image.SaveFile(fname, ftype)
        return self.image2dict(image)

    def image2dict(self, img=None):
        "return dictionary of image data, suitable for serialization"
        if img is None:
            img = self.GrabWxImage(scale=1, rgb=True)
        _size = img.GetSize()
        size = (_size[0], _size[1])
        return {'image_size': size,
                'image_format': 'RGB',
                'data_format': 'base64',
                'data': base64.b64encode(img.GetData())}

LEFT = wx.ALIGN_LEFT|wx.EXPAND

class ConfPanel_Base(wx.Panel):
    def __init__(self, parent,  center_cb=None,
                 image_panel=None, xhair_cb=None,
                 size=(300, 350), **kws):
        self.lens_choices = None
        if 'lens_choices' in kws:
             self.lens_choices = kws.pop('lens_choices')
        self.lens_default = None
        if 'lens_default' in kws:
             self.lens_default = kws.pop('lens_default')
        super(ConfPanel_Base, self).__init__(parent, -1, size=size)
        self.image_panel = image_panel
        self.center_cb = center_cb
        self.xhair_cb = xhair_cb

        self.wids = wids = {}
        self.sizer = wx.GridBagSizer(10, 4)
        self.sizer.SetVGap(3)
        self.sizer.SetHGap(5)

        self.sel_pixel = self.txt(' ', size=200)
        self.cen_dist = self.txt(' ', size=200)
        self.cur_pixel = self.txt(' ', size=200)
        self.img_size  = self.txt(' ', size=140)
        self.img_size_shown = False
        self.show_xhair = False

    def txt(self, lab, size=150, height=-1):
        return wx.StaticText(self, label=lab, size=(size, height), style=LEFT)

    def on_selected_pixel(self, x, y, xmax, ymax, cam_calibx=1.0, cam_caliby=1.0):
        if x > 0 and x < xmax and y > 0 and y < ymax:
            dx = abs(cam_calibx*(x-xmax/2.0))
            dy = abs(cam_caliby*(y-ymax/2.0))
            self.sel_pixel.SetLabel("(%i, %i)" % (x, y))
            self.cen_dist.SetLabel("(%.1f, %.1f)" % (dx, dy))

    def show_position_info(self, row=0):
        img_label = self.txt("Image Size:")
        sel_label = self.txt("Selected Pixel:")
        cen_label = self.txt("Distance to Center(um):")
        ctr_button = add_button(self, "Bring Selected Pixel to Center",
                                action=self.onBringToCenter, size=(250, -1))

        sizer = self.sizer
        sizer.Add(img_label,      (row,   0), (1, 1), LEFT)
        sizer.Add(self.img_size,  (row,   1), (1, 2), LEFT)
        row += 1
        sizer.Add(sel_label,      (row, 0), (1, 1), LEFT)
        sizer.Add(self.sel_pixel, (row, 1), (1, 2), LEFT)
        row += 1
        sizer.Add(cen_label,      (row, 0), (1, 1), LEFT)
        sizer.Add(self.cen_dist,  (row, 1), (1, 2), LEFT)
        row += 1
        sizer.Add(ctr_button,     (row, 0), (1, 2), wx.ALIGN_LEFT)
        self.choice_lens = None
        if self.lens_choices is not None and len(self.lens_choices) > 1:
            lenses = ['%ix' % i for i in self.lens_choices]
            ldef = '%ix' % self.lens_default
            default = 1
            if ldef in lenses:
                  default = lenses.index(ldef)
            self.choice_lens = Choice(self, choices=lenses, default=default,
                                       size=(100, -1))
            row += 1
            _label = self.txt("Current Lens:")
            sizer.Add(_label,            (row, 0), (1, 1), wx.ALIGN_LEFT)
            sizer.Add(self.choice_lens,  (row, 1), (1, 2), wx.ALIGN_LEFT)

        return row+1

    def onStart(self, event=None, **kws):
        pass

    def onStop(self, event=None, **kws):
        pass

    def onBringToCenter(self, event=None,  **kws):
        if self.center_cb is not None:
            self.center_cb(event=event, **kws)

        if self.image_panel is not None:
            zoompanel = getattr(self.image_panel, 'zoompanel', None)
            if zoompanel is not None:
                mx, my = self.image_panel.full_size
                zoompanel.xcen = int(mx/2.0)
                zoompanel.ycen = int(my/2.0)
                zoompanel.Refresh()

    def onToggleCrosshair(self, event=None,  **kws):
        self.show_xhair = not self.show_xhair
        if self.xhair_cb is not None:
            self.xhair_cb(event=event, show=self.show_xhair, **kws)


class ZoomPanel(wx.Panel):
    def __init__(self, parent, imgsize=200, size=(400, 400), **kws):
        super(ZoomPanel, self).__init__(parent, size=size)
        self.imgsize = max(10, imgsize)
        self.SetBackgroundColour("#CCBBAAA")
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetSize(size)
        self.data = None
        self.scale = 1.0
        # print("ZoomPanel ", imgsize, size)
        self.xcen = self.ycen = self.x = self.y = 0
        self.Bind(wx.EVT_PAINT, self.onPaint)

    def onPaint(self, evt=None):
        data, xcen, ycen = self.data, self.xcen, self.ycen
        if data is None or xcen is None or ycen is None:
            return

        # print("ZoomPanel onPaint ", data.shape)
        h, w, x = data.shape

        if ycen < self.imgsize/2.0:
            hmin, hmax = 0, self.imgsize
        elif ycen > h - self.imgsize/2.0:
            hmin, hmax = h-self.imgsize, h
        else:
            hmin = int(ycen-self.imgsize/2.0)
            hmax = int(ycen+self.imgsize/2.0)
        if xcen < self.imgsize/2.0:
            wmin, wmax = 0, self.imgsize
        elif xcen > w - self.imgsize/2.0:
            wmin, wmax = w-self.imgsize, w
        else:
            wmin = int(xcen-self.imgsize/2.0)
            wmax = int(xcen+self.imgsize/2.0)

        data = data[hmin:hmax, wmin:wmax, :]
        dshape = data.shape
        if len(dshape) == 3:
            hs, ws, nc = data.shape
        else:
            hs, ws = data.shape
        self.lims = (hmin, wmin)
        if len(dshape) == 3:
            rgb = data
        else:
            rgb = np.zeros((self.imgsize, self.imgsize, 3), dtype='float')
            rgb[:, :, 0] = rgb[:, :, 1] = rgb[:, :, 2] = data
        fh, fw = self.GetSize()
        scale = max(0.10, min(0.98*fw/(ws+0.1), 0.98*fh/(hs+0.1)))
        self.scale = scale

        image = wx.Image(self.imgsize, self.imgsize, rgb.flatten())
        image = image.Scale(int(scale*ws), int(scale*hs))
        bitmap = wx.Bitmap(image)
        bw, bh = bitmap.GetSize()
        pad_w, pad_h = int(1+(fw-bw)/2.0), int(1+(fh-bh)/2.0)
        self.pad = pad_h, pad_w
        dc = wx.AutoBufferedPaintDC(self)
        dc.Clear()
        dc.DrawBitmap(bitmap, pad_w, pad_h, useMask=True)
