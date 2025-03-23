#!/usr/bin/env python
 
import os
import sys
import platform
import argparse
 
import PySide
from PySide.QtGui import QApplication, QMainWindow, QTextEdit,\
                         QPushButton,  QMessageBox, QInputDialog

sys.path.append('./libs')

__version__ = '0.1.0'
from score_ui  import Ui_MainWindow
from score_lib import Player, Course, Walk, WipConfig
 
class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.config = WipConfig()
        print "Wib:" + self.config.get('wip', 'course_type')
        self.course = Course(self.config.get('wip', 'default_course'))
        self.pebble = False
        self.walk = Walk(self.course)
        self.player = Player();
        self.player.set_name('ez')
        self.walk.set_player(self.player)
        self.setupUi(self)
        # Hard coding debug! Wonder how long time this one will last.
        # Still here, new version.
        if os.uname()[4] != 'x86_64':
            self.showFullScreen()
        self.actionChoose_course.triggered.connect(self.show_course_picker)
        self.actionSave_course.triggered.connect(self.save_course)
        self.actionConnect.triggered.connect(self.connect_pebble)
        self.actionAbout.triggered.connect(self.about)        
        self.Plus.clicked.connect(self.plus)        
        self.Minus.clicked.connect(self.minus)        
        self.Next.clicked.connect(self.next)        
        self.Done.clicked.connect(self.done)        
        self.Previous.clicked.connect(self.previous)        
        self.Throws.display(0)
        self.Done.setEnabled(True)

    def set_pebble(self, pebble):
        self.pebble = pebble
        if self.pebble:
            def music_control_handler(endpoint, resp):
                if resp == "PLAYPAUSE":
                    self.next()
                    #print 'PLAYPAUSE!'
                elif resp == "PREVIOUS":
                    self.minus()
                    #print 'PREVIOUS!'
                elif resp == "NEXT":
                    self.plus()
                    #print 'NEXT!'

            self.pebble.get_pebble().register_endpoint("MUSIC_CONTROL", music_control_handler)
            #print 'waiting for control events'

    def redraw(self):
        bnum = self.walk.get_basket()
        par = self.course.get_par(bnum)
        btxt = str(self.course.get_name()) +  " - Basket " + str(bnum) + " - Par " + str(par)
        self.Basketnum.setText(btxt)
        self.Playername.setText("Player 1")
        throws = self.walk.get_throws()
        self.Throws.display(throws)
        total = self.walk.get_result()
        totaltxt = "Total:\t" + str(total['score']) + "\nPar:\t" + str(total['par']) + "\n"
        totaltxt += "Res:\t" + str(total['result'])
        totaltxt += "  (FH:" + str(total['res_first']) + " / "
        totaltxt += str(total['par_first']) + " )"
        totaltxt += " (SH:" + str(total['res_second']) + " / "
        totaltxt += str(total['par_second']) + " )"
        self.Total.setText(totaltxt)
        if self.walk.is_done():
            self.Done.setText('Done')
        else:
            self.Done.setText('Save')
        # print "Pebble:" + str(self.pebble)
        if self.pebble:
            btxt = "Basket " + str(bnum)
            rtxt = "Res:\t" + str(total['result']) + "\nPar:\t" + str(total['par']) + "\n"
            self.pebble.update_screen(btxt, throws, rtxt)

    def next(self):
        self.walk.next_basket()
        self.redraw()
       
    def previous(self):
        self.walk.previous_basket()
        self.redraw()
       
    def plus(self):
        self.walk.add_throw(1)
        self.redraw()
       
    def minus(self):
        self.walk.subtract_throw(1)
        self.redraw()
       
    def done(self):
        saveScore(self.walk)
        total = self.walk.get_score_total()
        txt = "have saved?, Total:" + str(total['score'] + " Par:" + total['par'])
        QMessageBox.about(self, "Done!", txt)

    def show_course_picker(self):
        course_list = self.config.get_course_list()
        coursename, ok = QInputDialog.getItem(self, 'Course name', 
            'Which course?', course_list, editable = False)
        if ok:
            print "Got name:" + coursename
            self.course.load(coursename)
            self.redraw()

    def save_course(self):
        coursename, ok = QInputDialog.getText(self, 'Course name', 
            'Which course?')
        if ok and coursename:
            print "Got name:" + coursename
            self.walk.saveScoreAsCourse(coursename)
            self.redraw()

    def show_name_input_dialog(self):
        text, ok = QInputDialog.getText(self, 'Player name', 
            'Enter your name:')
        if ok:
            print "Got name:" + text

    def connect_pebble(self):
        from pebble_buttons import PebbleButtons
        pebble_id = self.config.get('pebble','pebble_id')
        lightblue = self.config.get('pebble','lightblue')
        if pebble_id is None and "PEBBLE_ID" in os.environ:
            pebble_id = os.environ["PEBBLE_ID"]
        pebble = PebbleButtons(pebble_id, lightblue, False)
        self.set_pebble(pebble)

    def show_file_dialog(self):
        fname, _ = QFileDialog.getOpenFileName(self, 'Open file', './')
        f = open(fname, 'r')

    def show_gpl(self):
        '''Read and display GPL licence.'''
        self.textEdit.setText(open('COPYING.txt').read())
       
    def about(self):
        '''Popup a box with about message.'''
        QMessageBox.about(self, "About the Golf scor app",
                """<b> About this program </b> v %s
               <p>Copyright 2013 Thomas Lundquist</p>
               <p>All rights reserved in accordance with
               GPL v2 or later - NO WARRANTIES!</p>
               <p>The GUI part of this app was cooked from Joe Biggs 
                PySide examples.
               <p>Python %s -  PySide version %s - Qt version %s on %s""" % \
                (__version__, platform.python_version(), PySide.__version__,\
                 PySide.QtCore.__version__, platform.system()))      
       
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Scorecard for your golf round')
    parser.add_argument('--pebble', help='Turn on Pebble support', action='store_true')
    parser.add_argument('--pebble_id', type=str, help='the last 4 digits of the target Pebble\'s MAC address. \nNOTE: if \
                        --lightblue is set, providing a full MAC address (ex: "A0:1B:C0:D3:DC:93") won\'t require the pebble \
                        to be discoverable and will be faster')
    parser.add_argument('--lightblue', action="store_true", help='use LightBlue bluetooth API')
    args = parser.parse_args()
    config = WipConfig()

    if args.pebble_id:
        config.set('pebble', 'pebble_id', args.pebble_id)
    if args.lightblue:
        config.set('pebble', 'lightblue', True)
    config.save_config()

    app = QApplication(sys.argv)
    frame = MainWindow()
    if args.pebble:
        frame.connect_pebble()

    frame.redraw()
    frame.show()
    app.exec_()

