import wx
import sys
from subprocess import *


class MainFrame(wx.Frame):

    def __init__(self):
        wx.Frame.__init__(self, None, -1, title='Select Language', style=wx.SYSTEM_MENU | wx.CAPTION | wx.CLOSE_BOX | wx.CLIP_CHILDREN)
        self.SetSizer(wx.GridBagSizer())
        self.LanguageSelector = wx.ComboBox(self, -1)
        self.Ok = wx.Button(self, wx.ID_OK, 'Ok')
        self.GetSizer().Add(wx.StaticText(self, -1, 'Choose the language for desktop:'), (0, 0), (1, 1), wx.ALIGN_LEFT | wx.ALL, 5)
        self.GetSizer().Add(self.LanguageSelector, (1, 0), (1, 1), wx.EXPAND | wx.ALL, 5)
        self.GetSizer().Add(wx.StaticLine(self, -1), (2, 0), (1, 1), wx.EXPAND | wx.ALL, 2)
        self.GetSizer().Add(self.Ok, (3, 0), (1, 1), wx.ALL | wx.ALIGN_RIGHT, 5)
        self.Bind(wx.EVT_BUTTON, self.OnClick)
        self.SetSize((350, 145))
        self.GetSizer().AddGrowableCol(0)
        self.InitLanguages()
        self.Center()
        self.Show()

    def InitLanguages(self):
        process = Popen(['locale', '-a'], stdout=PIPE)
        (output, err) = process.communicate()
        exit_code = process.wait()
        locales = output.split('\n')
        for locale in locales:
            self.LanguageSelector.Append(locale)

    def OnClick(self, event):
        process = Popen(['sudo', './changelocale.sh', self.LanguageSelector.GetValue()], stdout=PIPE)
        (output, err) = process.communicate()
        exit_code = process.wait()
        exit(0)

app = wx.App()
MainFrame()
app.MainLoop()
