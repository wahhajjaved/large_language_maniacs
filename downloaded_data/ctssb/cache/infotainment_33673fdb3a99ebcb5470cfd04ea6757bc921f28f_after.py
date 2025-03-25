from PyQt5.QtCore import QUrl, QObject, QVariant, QRunnable, QCoreApplication, QThreadPool
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtGui import QColor
from PyQt5.QtQuick import QQuickView
import os
import sys
import signal
import time
import threading
from UpdateThread import UpdateThread

def handler(signum, frame):
    print("ayyyy")
    sys.exit()

signal.signal(signal.SIGINT, handler)

class MainApplication(QQuickView):  
    GOOD = 0
    BAD = 1
    WARN = 2

    fuelRed = ["fuel_r1","fuel_r2"]
    fuelYellow = ["fuel_y1","fuel_y2","fuel_y3","fuel_y4","fuel_y5","fuel_y6","fuel_y7","fuel_y8"]
    fuelGreen = ["fuel_g1","fuel_g2","fuel_g3","fuel_g4","fuel_g5","fuel_g6","fuel_g7","fuel_g8","fuel_g9","fuel_g10","fuel_g11","fuel_g12","fuel_g13","fuel_g14","fuel_g15","fuel_g16","fuel_g17","fuel_g18","fuel_g19","fuel_g20"]

    socRed = ["fuel_r1","soc_r2"]
    socYellow = ["soc_y1","soc_y2","soc_y3","soc_y4","soc_y5","soc_y6","soc_y7","soc_y8"]
    socGreen = ["soc_g1","soc_g2","soc_g3","soc_g4","soc_g5","soc_g6","soc_g7","soc_g8","soc_g9","soc_g10","soc_g11","soc_g12","soc_g13","soc_g14","soc_g15","soc_g16","soc_g17","soc_g18","soc_g19","soc_g20"]

    def __init__(self,parent=None):
        super(MainApplication, self).__init__(parent)
        #self.resize(1200, 900) # TODO update to get screen size for full
        
        self.setSource(QUrl.fromLocalFile(os.path.join(os.path.dirname(__file__),'qml/Display_rev_1.qml')))
        self.setupUpdateThread()  
        self.qml = self.rootObject()
       


    def updateTachNeedle(self, tachRPM):
        # TODO angle is 270 degrees around tach, use mousePressEvent to get position then work around, i know its dusty but its ok
        # TODO update to allow input to be RPM vs Degrees
        
        # Gotta fix this

        goToAngle = (tachRPM*-0.02)
        # +1.3077
        self.qml.setProperty("tachNeedleAngle", QVariant(int(goToAngle)))

    def updateSpeed(self, pSPEED):  
        self.qml.setProperty("speed", QVariant(str(pSPEED)))


    def updateESS_SOC(self, pESS_SOC):
        #Pass in the SOC percent, this will do the rest
        for i in range(0,20):
            if(pESS_SOC>(i*5)):
                self.qml.setProperty("soc_"+str((i+1)*5), QVariant(1))
            else:
                self.qml.setProperty("soc_"+str((i+1)*5), QVariant(0))
        #Pass in the soc percent, this will do the rest for soc 
        #and target soc soc_y1
        def turn_off(pBar_array):
            for bar in pBar_array:
                self.qml.setProperty(bar, QVariant(0))

        if(pESS_SOC<=10):
            turn_off(socGreen)
            turn_off(socYellow)
            counter = 0
            for bar in socRed:
                if(pESS_SOC>counter):
                    self.qml.setProperty(bar, QVariant(1))
                else:
                    self.qml.setProperty(bar, QVariant(0))
                counter+=5

        if(pESS_SOC>10 and pESS_SOC<=40):
            turn_off(socGreen)
            turn_off(socRed)
            counter = 0
            for bar in socYellow:
                if(pESS_SOC>counter):
                    self.qml.setProperty(bar, QVariant(1))
                else:
                    self.qml.setProperty(bar, QVariant(0))
                counter+=5

        if(pESS_SOC>40):
            turn_off(socRed)
            turn_off(socYellow)
            counter = 0
            for bar in socGreen:
                if(pESS_SOC>counter):
                    self.qml.setProperty(bar, QVariant(1))
                else:
                    self.qml.setProperty(bar, QVariant(0))
                counter+=5

    def updateGear(self, pGEAR):  
        self.qml.setProperty("gear", QVariant(str(pGEAR)))

    def updateSHIFT(self, pShift):
        if(pShift==1):
            self.qml.setProperty("tach_shift", QVariant(1))
            self.qml.setProperty("tach", QVariant(0))
        if(pShift==0):
            self.qml.setProperty("tach_shift", QVariant(0))
            self.qml.setProperty("tach", QVariant(1))

    def updateFUEL(self, pFUEL):
        #Pass in the fuel percent, this will do the rest for fuel 
        #and target fuel fuel_y1
        def turn_off(pBar_array):
            for bar in pBar_array:
                self.qml.setProperty(bar, QVariant(0))

        if(pFUEL<=10):
            turn_off(fuelGreen)
            turn_off(fuelYellow)
            counter = 0
            for bar in fuelRed:
                if(pFUEL>counter):
                    self.qml.setProperty(bar, QVariant(1))
                else:
                    self.qml.setProperty(bar, QVariant(0))
                counter+=5

        if(pFUEL>10 and pFUEL<=40):
            turn_off(fuelGreen)
            turn_off(fuelRed)
            counter = 0
            for bar in fuelYellow:
                if(pFUEL>counter):
                    self.qml.setProperty(bar, QVariant(1))
                else:
                    self.qml.setProperty(bar, QVariant(0))
                counter+=5

        if(pFUEL>40):
            turn_off(fuelRed)
            turn_off(fuelYellow)
            counter = 0
            for bar in fuelGreen:
                if(pFUEL>counter):
                    self.qml.setProperty(bar, QVariant(1))
                else:
                    self.qml.setProperty(bar, QVariant(0))
                counter+=5
        if(pFUEL<CAN_Main.current_target_fuel):
            roundedFUEL = int(pFUEL) - int(pFUEL) % 5
            roundedTARGET = int(CAN_Main.current_target_fuel) - int(CAN_Main.current_target_fuel) % 5
            for num in range(0,19):
                if(num>roundedFUEL/5 and num<=roundedTARGET/5):
                    self.qml.setProperty("fuel_b"+(num+1), QVariant(1))
                else:
                    self.qml.setProperty("fuel_b"+(num+1), QVariant(0))



    def updateMOTOR_TEMP_HACK(self, pDEGREES): 
        self.qml.setProperty("temp_text_text", QVariant(str(pDEGREES)))

    def updateMOTOR_TEMP(self, pMOTOR_TEMP): 
        if(pMOTOR_TEMP==self.GOOD): #GOOD
            self.qml.setProperty("temp_text_color", QVariant("#00FF00"))
        #    self.qml.setProperty("tempC", QVariant("#00FF00"))
        if(pMOTOR_TEMP==self.BAD): #BAD
            self.qml.setProperty("temp_text_color", QVariant("#FF0000"))
        #    self.qml.setProperty("tempC", QVariant("#FF0000"))     
        if(pMOTOR_TEMP==self.WARN): #WARN
            self.qml.setProperty("temp_text_color", QVariant("#FFFF00"))
        #    self.qml.setProperty("tempC", QVariant("#FFFF00"))
    '''
    Need:
    RPM
    speed
    ess soc
    gear
    shift

    target fuel
    fuel
    engine temp

    warn motor temp
    warn fuel low
    war ess over temp
    warn CAN down
    warn charging
    warn power on

    '''
    def updateMOTOR_OVER_TEMP(self, pSTATUS):
        if(pMOTOR_TEMP==self.GOOD): #GOOD
            self.qml.setProperty("motor_temp_red", QVariant(0)) 
            self.qml.setProperty("motor_temp_yellow", QVariant(0))
        if(pSTATUS==self.BAD): #BAD
            self.qml.setProperty("motor_temp_red", QVariant(1)) 
            self.qml.setProperty("motor_temp_yellow", QVariant(0))  
        if(pSTATUS==self.WARN): #WARN
            self.qml.setProperty("motor_temp_red", QVariant(0)) 
            self.qml.setProperty("motor_temp_yellow", QVariant(1))

    def updateFUEL_LOW(self, pSTATUS):
        if(pSTATUS==self.GOOD): #GOOD
            self.qml.setProperty("fuel_red", QVariant(0))
        if(pSTATUS==self.BAD): #BAD
            self.qml.setProperty("fuel_red", QVariant(1))

    def updateESS_TEMP(self, pESS_TEMP): 
        if(pESS_TEMP==self.GOOD): #GOOD
            self.qml.setProperty("ess_temp_red", QVariant(0))
        if(pESS_TEMP==self.BAD): #BAD
            self.qml.setProperty("ess_temp_red", QVariant(1))
 
    def updateCAN_DOWN(self, pCAN_Status):
        if(pCAN_Status==self.GOOD): #GOOD
            self.qml.setProperty("can_red", QVariant(0))
        if(pCAN_Status==self.BAD): #BAD
            self.qml.setProperty("can_red", QVariant(1))

    def updateCHARGING(self, pCHARGE_STATUS):
        if(pCHARGE_STATUS==self.GOOD): #GOOD
            self.qml.setProperty("power_on", QVariant(0))
        if(pCHARGE_STATUS==self.BAD): #BAD
            self.qml.setProperty("power_on", QVariant(1))
    
    def updateMOTOR_ON(self, pMOTOR_STATUS):
        if(pMOTOR_STATUS==self.GOOD): #GOOD
            self.qml.setProperty("can_red", QVariant(0))
        if(pMOTOR_STATUS==self.BAD): #BAD
            self.qml.setProperty("can_red", QVariant(1))

    def updateGLV_SOC(self, pGLV_SOC): 
        if(pGLV_SOC==self.GOOD): #GOOD
            self.qml.setProperty("glv_soc_red", QVariant(0))
        if(pGLV_SOC==self.BAD): #BAD
            self.qml.setProperty("glv_soc_red", QVariant(1))

    def mousePressEvent(self, QMouseEvent):
        # Used for finding mouse postions, strictly testing
        print(QMouseEvent.pos()) 
   
    def setupUpdateThread(self):  
        self.updateThread = UpdateThread()  
        
        # Connect our update function to the progress signal of the update thread  
        self.updateThread.speed.connect(self.updateSpeed)
        self.updateThread.gear.connect(self.updateGear)
        self.updateThread.temp_text.connect(self.updateMOTOR_TEMP_HACK)

        self.updateThread.shift.connect(self.updateSHIFT)
        
        self.updateThread.glv_soc.connect(self.updateGLV_SOC)
        self.updateThread.motor_temp.connect(self.updateMOTOR_OVER_TEMP)
        self.updateThread.ess_temp.connect(self.updateESS_TEMP)
        self.updateThread.charging.connect(self.updateCHARGING)
        self.updateThread.fuel_low.connect(self.updateFUEL_LOW)
        self.updateThread.CAN_down.connect(self.updateCAN_DOWN)
        self.updateThread.motor_on.connect(self.updateMOTOR_ON)
        
        self.updateThread.tachNeedle.connect(self.updateTachNeedle)
        
        self.updateThread.ess_soc.connect(self.updateESS_SOC)
        self.updateThread.fuel.connect(self.updateFUEL)
  
        if not self.updateThread.isRunning():
            # If the thread has not been started let's kick it off  
            self.updateThread.start()  
  
if __name__ == '__main__':  
    print("YOU HAVE 1 SECOND!") 
    time.sleep(1) 
    app = QGuiApplication(sys.argv)  
    win = MainApplication()  
    win.show()  
    app.processEvents()
    sys.exit(app.exec_())
