#
#  MythBox for XBMC - http://mythbox.googlecode.com
#  Copyright (C) 2010 analogue@yahoo.com
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
import copy
import logging
import odict
import os
import xbmcgui

from mythbox.mythtv.conn import inject_conn 
from mythbox.mythtv.db import inject_db 
from mythbox.mythtv.domain import RecordingSchedule
from mythbox.mythtv.enums import CheckForDupesIn, CheckForDupesUsing, EpisodeFilter, ScheduleType
from mythbox.ui.toolkit import BaseDialog, BaseWindow, window_busy, Action 
from mythbox.util import catchall_ui, lirc_hack, catchall, run_async, ui_locked, coalesce, ui_locked2

log = logging.getLogger('mythbox.ui')

ID_SCHEDULES_LISTBOX = 600
ID_REFRESH_BUTTON = 250


class SchedulesWindow(BaseWindow):
    
    def __init__(self, *args, **kwargs):
        BaseWindow.__init__(self, *args, **kwargs)
        
        self.settings = kwargs['settings']
        self.translator = kwargs['translator']
        self.platform = kwargs['platform']
        self.fanArt = kwargs['fanArt']
        self.mythChannelIconCache = kwargs['cachesByName']['mythChannelIconCache']
        
        self.schedules = []                       # [RecordingSchedule]
        self.listItemsBySchedule = odict.odict()  # {RecordingSchedule:ListItem}
        self.channelsById = None                  # {int:Channel}
        self.closed = False
        self.lastFocusId = ID_SCHEDULES_LISTBOX
        self.lastSelected = int(self.settings.get('schedules_last_selected'))
        
    @catchall
    def onInit(self):
        if not self.win:
            self.win = xbmcgui.Window(xbmcgui.getCurrentWindowId())
            self.schedulesListBox = self.getControl(ID_SCHEDULES_LISTBOX)
            self.refreshButton = self.getControl(ID_REFRESH_BUTTON)
            self.refresh()

    @catchall_ui
    @lirc_hack    
    def onClick(self, controlId):
        if controlId == ID_SCHEDULES_LISTBOX: 
            self.goEditSchedule()
        elif controlId == ID_REFRESH_BUTTON:
            self.refresh()
             
    def onFocus(self, controlId):
        self.lastFocusId = controlId
        #if controlId == ID_SCHEDULES_LISTBOX:
        #    self.lastSelected = self.schedulesListBox.getSelectedPosition()

    @catchall
    @lirc_hack            
    def onAction(self, action):
        if action.getId() in (Action.PREVIOUS_MENU, Action.PARENT_DIR):
            self.closed = True
            self.settings.put('schedules_last_selected', '%d'%self.schedulesListBox.getSelectedPosition())
            self.close()
            
    def goEditSchedule(self):
        self.lastSelected = self.schedulesListBox.getSelectedPosition()
        editScheduleDialog = ScheduleDialog(
            "mythbox_schedule_dialog.xml", 
            os.getcwd(), 
            forceFallback=True,
            schedule=self.schedules[self.schedulesListBox.getSelectedPosition()], 
            translator=self.translator,
            platform=self.platform,
            settings=self.settings,
            mythChannelIconCache=self.mythChannelIconCache)
        editScheduleDialog.doModal()
        if editScheduleDialog.shouldRefresh:
            self.refresh()
             
    @inject_db
    def cacheChannels(self):
        if not self.channelsById:
            self.channelsById = {}
            for channel in self.db().getChannels():
                self.channelsById[channel.getChannelId()] = channel
        
    @window_busy
    @inject_db
    def refresh(self):
        self.cacheChannels()
        self.schedules = self.db().getRecordingSchedules()
        self.schedules.sort(key=RecordingSchedule.title)
        self.render()
        
    @ui_locked
    def render(self):
        log.debug('Rendering....')
        self.listItemsBySchedule.clear()
        listItems = []
        
        @ui_locked2
        def buildListItems():
            for i, s in enumerate(self.schedules):
                listItem = xbmcgui.ListItem()
                self.setListItemProperty(listItem, 'title', s.title())
                self.setListItemProperty(listItem, 'scheduleType', s.formattedScheduleType())
                self.setListItemProperty(listItem, 'fullTitle', s.fullTitle())
                self.setListItemProperty(listItem, 'priority', '%s' % s.getPriority())
                self.setListItemProperty(listItem, 'channelName', s.getChannelName())
                self.setListItemProperty(listItem, 'poster', 'loading.gif')
                self.setListItemProperty(listItem, 'index', str(i+1))
                #self.setListItemProperty(listItem, 'description', s.formattedDescription())
                #self.setListItemProperty(listItem, 'airDate', s.formattedAirDateTime())
                #self.setListItemProperty(listItem, 'originalAirDate', s.formattedOriginalAirDate())
                
                try:
                    # isolate failure for schedules with a channel that may no longer exist
                    channel = self.channelsById[s.getChannelId()]
                    if channel.getIconPath():
                        channelIcon = self.mythChannelIconCache.get(channel)
                        if channelIcon:
                            self.setListItemProperty(listItem, 'channelIcon', channelIcon)
                except:
                    log.exception('context: schedule = %s' % s)
                
                listItems.append(listItem)
                self.listItemsBySchedule[s] = listItem

        buildListItems()
        self.schedulesListBox.reset()
        self.schedulesListBox.addItems(listItems)
        self.schedulesListBox.selectItem(self.lastSelected)
        self.renderPosters()

    @run_async
    @catchall
    @coalesce
    def renderPosters(self):
        for schedule in self.listItemsBySchedule.keys():
            if self.closed: 
                return
            listItem = self.listItemsBySchedule[schedule]
            try:
                try:
                    posterPath = self.fanArt.getRandomPoster(schedule)
                    if not posterPath:
                        channel =  self.channelsById[schedule.getChannelId()]
                        if channel.getIconPath():
                            posterPath = self.mythChannelIconCache.get(channel)
                except:
                    posterPath = self.platform.getMediaPath('mythbox.png')
                    log.exception('Schedule = %s' % schedule)
            finally:
                self.setListItemProperty(listItem, 'poster', posterPath)
                

class ScheduleDialog(BaseDialog):
    """Create new and edit existing recording schedules"""
        
    def __init__(self, *args, **kwargs):
        BaseDialog.__init__(self, *args, **kwargs)
        # Leave passed in schedule untouched; work on a copy of it 
        # in case the user cancels the operation.
        self.schedule = copy.copy(kwargs['schedule'])
        self.translator = kwargs['translator']
        self.platform = kwargs['platform']
        self.settings = kwargs['settings']
        self.mythChannelIconCache = kwargs['mythChannelIconCache']
        self.shouldRefresh = False
        
    @catchall
    def onInit(self):
        #log.debug('onInit %s' % self.win)
        #log.debug('dlg id = %s' % xbmcgui.getCurrentWindowDialogId())
        self.win = xbmcgui.Window(xbmcgui.getCurrentWindowId())
        
        self.enabledCheckBox = self.getControl(212)
        self.autoCommFlagCheckBox = self.getControl(205)
        self.autoExpireCheckBox = self.getControl(207)
        self.autoTranscodeCheckBox = self.getControl(218)
        self.recordNewExpireOldCheckBox = self.getControl(213) 
        
        self.saveButton = self.getControl(250)
        self.deleteButton = self.getControl(251)
        self.cancelButton = self.getControl(252)
        
        self._updateView()

    def onFocus(self, controlId):
        pass
        
    @catchall_ui 
    @lirc_hack
    def onAction(self, action):
        if action.getId() in (Action.PREVIOUS_MENU, Action.PARENT_DIR):
            self.close() 

    @catchall_ui
    @lirc_hack    
    @inject_conn
    def onClick(self, controlId):
        log.debug('onClick %s ' % controlId)
        source = self.getControl(controlId)
        s = self.schedule
        
        if controlId == 201: self._chooseFromList(ScheduleType.long_translations, 'Record When', 'scheduleType', s.setScheduleType)
        
        elif controlId == 202:
            priority = self._enterNumber('Recording Priority', s.getPriority(), -99, 99)
            s.setPriority(priority)
            self.setWindowProperty('priority', str(priority))
        
        elif self.autoCommFlagCheckBox == source: 
            s.setAutoCommFlag(self.autoCommFlagCheckBox.isSelected())
        
        elif self.autoExpireCheckBox == source: 
            s.setAutoExpire(self.autoExpireCheckBox.isSelected())
        
        elif self.enabledCheckBox == source: 
            s.setEnabled(self.enabledCheckBox.isSelected())
        
        elif self.autoTranscodeCheckBox == source: 
            s.setAutoTranscode(self.autoTranscodeCheckBox.isSelected())
        
        elif self.recordNewExpireOldCheckBox == source: 
            s.setRecordNewAndExpireOld(self.recordNewExpireOldCheckBox.isSelected())    
        
        elif controlId == 203: self._chooseFromList(CheckForDupesUsing.translations, 'Check for Duplicates Using', 'checkForDupesUsing', s.setCheckForDupesUsing)            
        elif controlId == 204: self._chooseFromList(CheckForDupesIn.translations, 'Check for Duplicates In', 'checkForDupesIn', s.setCheckForDupesIn)
        elif controlId == 208: self._chooseFromList(EpisodeFilter.translations, 'Episode Filter', 'episodeFilter', s.setEpisodeFilter)
            
        elif controlId == 206:
            maxEpisodes = self._enterNumber('Keep At Most - Episodes', s.getMaxEpisodes(), 0, 99)
            s.setMaxEpisodes(maxEpisodes)
            self.setWindowProperty('maxEpisodes', ('%d Episode(s)' % maxEpisodes, 'All Episodes')[maxEpisodes == 0])

        elif controlId == 209:
            minutes = self._enterNumber('Start Recording Early - Minutes', s.getStartOffset(), 0, 60) 
            s.setStartOffset(minutes)
            self.setWindowProperty('startEarly', ('%d minute(s) early' % minutes, 'On time')[minutes == 0]) 

        elif controlId == 210:
            minutes = self._enterNumber('End Recording Late - Minutes', s.getEndOffset(), 0, 60) 
            s.setEndOffset(minutes)
            self.setWindowProperty('endLate', ('%d minute(s) late' % minutes, 'On time')[minutes == 0])
            
        elif self.saveButton == source:
            log.debug("Save button clicked")
            self.conn().saveSchedule(self.schedule)
            self.shouldRefresh = True
            self.close()
            
        elif self.deleteButton == source:
            log.debug('Delete button clicked')
            self.conn().deleteSchedule(self.schedule)
            self.shouldRefresh = True
            self.close()
            
        elif self.cancelButton == source:
            log.debug("Cancel button clicked")
            self.close()

    def _updateView(self):
        s = self.schedule
        
        if s.getScheduleId() is None:
            self.setWindowProperty('heading', 'New Recording Schedule')
            self.deleteButton.setEnabled(False)
        else:
            self.setWindowProperty('heading', 'Edit Recording Schedule')

        logo = 'mythbox-logo.png'    
        try:
            if s.getIconPath() and self.mythChannelIconCache.get(s):
                logo = self.mythChannelIconCache.get(s)
        except:
            log.exception('setting channel logo in schedules dialog box')
        self.setWindowProperty('channel_logo', logo)
        
        self.setWindowProperty('channel', s.getChannelNumber())
        self.setWindowProperty('station', s.station())    
        
        # TODO: Find root cause
        try:
            self.setWindowProperty('startTime', s.formattedTime())
        except:
            log.exception("HACK ALERT: s.formattedTime() blew up. Known issue.")
            self.setWindowProperty('startTime', 'Unknown')
            
        self.setWindowProperty('title', s.title())    
        self.setWindowProperty('startDate', s.formattedStartDate())    
        self.setWindowProperty('scheduleType', s.formattedScheduleTypeDescription())
        self.setWindowProperty('priority', str(s.getPriority()))

        self.autoCommFlagCheckBox.setLabel('Auto-flag Commercials')
        self.autoCommFlagCheckBox.setSelected(s.isAutoCommFlag())
        
        self.autoExpireCheckBox.setLabel('Auto-expire')
        self.autoExpireCheckBox.setSelected(s.isAutoExpire())
        
        self.setWindowProperty('checkForDupesUsing', self.translator.get(CheckForDupesUsing.translations[s.getCheckForDupesUsing()]))
        self.setWindowProperty('checkForDupesIn', self.translator.get(CheckForDupesIn.translations[s.getCheckForDupesIn()]))
        self.setWindowProperty('episodeFilter', self.translator.get(EpisodeFilter.translations[s.getEpisodeFilter()])) 
        
        self.enabledCheckBox.setSelected(s.isEnabled())
        self.autoTranscodeCheckBox.setSelected(s.isAutoTranscode())
        self.recordNewExpireOldCheckBox.setSelected(s.isRecordNewAndExpireOld())
        
        self.setWindowProperty('maxEpisodes', ('%d Episode(s)' % s.getMaxEpisodes(), 'All Episodes')[s.getMaxEpisodes() == 0])
        self.setWindowProperty('startEarly', ('%d minute(s) early' % s.getStartOffset(), 'On time')[s.getStartOffset() == 0])
        self.setWindowProperty('endLate', ("%d minute(s) late" % s.getEndOffset(), 'On time')[s.getEndOffset() == 0])
            
    def _chooseFromList(self, translations, title, property, setter):
        """
        Boiler plate code that presents the user with a dialog box to select a value from a list.
        Once selected, the setter method on the Schedule is called to reflect the selection.
        
        @param translations: odict of {enumerated type:translation index}
        @param title: Dialog box title
        @param property: Window property name 
        @param setter: method on Schedule to 'set' selected item from chooser
        """
        pickList = self.translator.toList(translations)
        selected = xbmcgui.Dialog().select(title, pickList)
        if selected >= 0:
            self.setWindowProperty(property, pickList[selected])
            setter(translations.keys()[selected])
            
    def _enterNumber(self, heading, current, min=None, max=None):
        """
        Prompt user to enter a valid number with optional min/max bounds.
        
        @param heading: Dialog title as string
        @param current: current value as int
        @param min: Min value of number as int
        @param max: Max value of number as int
        @return: entered number as int
        """
        value = xbmcgui.Dialog().numeric(0, heading, str(current))
        if value == str(current):
            return current
        
        result = int(value)
        
        if min is not None and result < min:
            xbmcgui.Dialog().ok('Error', 'Value must be between %d and %d' % (min, max))
            result = current
            
        if max is not None and result > max:
            xbmcgui.Dialog().ok('Error', 'Value must be between %d and %d' % (min, max))
            result = current
            
        return result             