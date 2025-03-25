from flask import Flask, request, session, redirect, url_for, \
     abort, render_template, flash
from max31855.max31855 import MAX31855, MAX31855Error
import math
import RPi.GPIO as GPIO
from time import perf_counter
import time
import threading
from RPLCD import CharLCD
from RPLCD import Alignment, CursorMode, ShiftMode
from RPLCD import cursor, cleared


#Import Tunings

tuneFile = open('data/tunings.txt', 'r')
kpt = tuneFile.readline()
kit = tuneFile.readline()
kdt = tuneFile.readline()
kpt = kpt.rstrip('\n')
kit = kit.rstrip('\n')
kdt = kdt.rstrip('\n')
kpt = kpt.lstrip('kp=')
kit = kit.lstrip('ki=')
kdt = kdt.lstrip('kd=')
tuneFile.close()

kp = float(kpt)
ki = float(kit)
kd = float(kdt)


#Flask Settings

DEBUG = True
SECRET_KEY = 'development key'
USERNAME = 'admin'
PASSWORD = 'default'

app = Flask(__name__)
app.config.from_object(__name__)
app.config.from_envvar('FLASKR_SETTINGS', silent=True)


#Variable Creation

timeL = []
setPointL = []
outputL = []
tempL = []

currentTemp = 0
initialTemp = 100
setPoint = initialTemp
output = 0
status = 0
killStatus = True

#Status:
#0 = Off
#1 = Preheat: No Program
#2 = Preheat: Ready
#3 = Running
#4 = Complete
#6 = Preheat: No 2 Part Program

#Control Loop

class PIDloop(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
    def run(self):
        global currentTemp, output, killStatus
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(18, GPIO.OUT)
        relay = GPIO.PWM(18, 0.5)
        relay.start(0)
        cs_pin = 8
        clock_pin = 11
        data_pin = 9
        units = 'f'
        thermocouple = MAX31855(cs_pin, clock_pin, data_pin, units)
        c = CharLCD(0x27, numbering_mode=GPIO.BCM, rows=2, cols=16)
        killStatus = False
        timeOldP = perf_counter()
        tempOld = thermocouple.get()
        outMin = 0
        outMax = 0
        intErr = 0
        while not(killStatus):
            timeP = perf_counter()
            if (timeP-timeOldP)>1:
                timeOldP = timeP
                currentTemp = thermocouple.get()
                Trj = thermocouple.get_rj()
                if currentTemp < (Trj-10): break
                err = setPoint - currentTemp
                intErr += ki*err
                if intErr > outMax:
                    intErr = outMax
                elif intErr < outMin:
                    intErr = outMin
                din = currentTemp - tempOld
                output = kp*err + intErr - kd*din
                if output > outMax:
                    output = outMax
                elif output < outMin:
                    output = outMin
                relay.ChangeDutyCycle(output)
                c.cursor_pos = (1, 1)
                c.write_string('T:' + str(currentTemp) + ' SP:' + str(setPoint))
                c.cursor_pos = (2, 1)
                c.write_string('Out:' + str(output))
                tempOld = currentTemp
        relay.stop()
        c.close()
        GPIO.cleanup()


#Program Loop

class RampLoop(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
    def run(self):
        global status, killStatus, tempL, outputL, setPoint
        tmin = 0
        timeOldR = perf_counter()
        tempL.append(currentTemp)
        outputL.append(output)
        while not(killStatus):
            timeR = perf_counter()
            if (timeR-timeOldR)>60:
                timeOldR = timeR
                tmin += 1
                tempL.append(currentTemp)
                outputL.append(output)
                if len(tempL) == len(setPointL):
                    killStatus = True
                    status = 4
                    break
                setPoint = setPointL[tmin]


PIDloopT = PIDloop()
RampLoopT = RampLoop()


@app.route('/')
def main():
    if status == 0:
        return render_template('prerun.html')
    elif status == 1:
        return render_template('program.html')
    elif status == 2:
        return render_template('ready.html', CurrT=currentTemp)
    elif status == 3:
        return render_template('run.html', CurrT=currentTemp)
    elif status == 5:
        return render_template('program2.html')
    else:
        return render_template('postrun.html')

@app.route('/preheat', methods=['POST'])
def preheat():
    global status
    PIDloopT.start()
    flash('Preheat Enabled')
    status = 1
    return redirect(url_for('main'))

@app.route('/preheat2', methods=['POST'])
def preheat():
    global status
    PIDloopT.start()
    flash('Preheat Enabled')
    status = 5
    return redirect(url_for('main'))

@app.route('/startrun', methods=['POST'])
def startrun():
    global status
    flash('Run Started')
    status = 3
    return redirect(url_for('main'))

@app.route('/kill', methods=['POST'])
def kill():
    global status, killStatus
    killStatus = True
    flash('Run Stopped')
    status = 0
    return redirect(url_for('main'))

@app.route('/tune', methods=['POST'])
def tune():
    global kp, ki, kd
    if not session.get('logged_in'):
        abort(401)
    kp = float(request.form['kp'])
    ki = float(request.form['ki'])
    kd = float(request.form['kd'])
    tuneFile = open('data/tunings.txt', 'w')
    tuneFile.write(('kp=' + str(kp) + '\nki=' + str(ki) + '\nkd=' + str(kd) + '\n'))
    tuneFile.close()
    flash('Tunings Updated')
    return redirect(url_for('main'))

@app.route('/profile', methods=['POST'])
def profile():
    global status, timeL, setPointL
    runName = request.form['Name']
    holdTemp = float(request.form['HoldT'])
    holdTime = int(request.form['HoldTim'])
    heatRate = float(request.form['UR'])
    coolRate = float(request.form['DR'])
    outputFile = open('schedule.txt', 'w')
    outputFile.write('Time      SP\n')
    i = 0
    setPointIter = setPoint
    timeL.append(i)
    setPointL.append(setPointIter)
    outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')
    while setPointL[i] + heatRate < holdTemp:
        i += 1
        setPointIter += heatRate
        setPointL.append(setPointIter)
        timeL.append(i)
        outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')
    else:
        i += 1
        setPointIter = holdTemp
        setPointL.append(setPointIter)
        timeL.append(i)
        outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')
    for j in range(holdTime):
        i += 1
        setPointL.append(setPointIter)
        timeL.append(i)
        outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')
    while setPointL[i] > initialTemp:
        i += 1
        setPointIter -= coolRate
        setPointL.append(setPointIter)
        timeL.append(i)
        outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')
    outputFile.close()
    status = 2
    flash('Temperature Profile Updated')
    return redirect(url_for('main'))

@app.route('/profile2', methods=['POST'])
def profile2():
    global status, timeL, setPointL
    runName = request.form['Name']
    holdTemp1 = float(request.form['HoldT'])
    holdTime1 = int(request.form['HoldTim'])
    heatRate1 = float(request.form['UR'])
    holdTemp2 = float(request.form['HoldT'])
    holdTime2 = int(request.form['HoldTim'])
    heatRate2 = float(request.form['UR'])
    coolRate = float(request.form['DR'])
    outputFile = open('schedule.txt', 'w')
    outputFile.write('Time      SP\n')
    i = 0
    setPointIter = setPoint
    timeL.append(i)
    setPointL.append(setPointIter)
    outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')
    while setPointL[i] + heatRate1 < holdTemp:
        i += 1
        setPointIter += heatRate1
        setPointL.append(setPointIter)
        timeL.append(i)
        outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')
    else:
        i += 1
        setPointIter = holdTemp1
        setPointL.append(setPointIter)
        timeL.append(i)
        outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')
    for j in range(holdTime1):
        i += 1
        setPointL.append(setPointIter)
        timeL.append(i)
        outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')
    while setPointL[i] + heatRate2 < holdTemp:
        i += 1
        setPointIter += heatRate2
        setPointL.append(setPointIter)
        timeL.append(i)
        outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')
    else:
        i += 1
        setPointIter = holdTemp2
        setPointL.append(setPointIter)
        timeL.append(i)
        outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')
    for j in range(holdTime2):
        i += 1
        setPointL.append(setPointIter)
        timeL.append(i)
        outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')
    while setPointL[i] > initialTemp:
        i += 1
        setPointIter -= coolRate
        setPointL.append(setPointIter)
        timeL.append(i)
        outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')
    outputFile.close()
    status = 2
    flash('Temperature Profile Updated')
    return redirect(url_for('main'))

@app.route('/login', methods=['GET','POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form['username'] != app.config['USERNAME']:
            error = 'Invalid Username'
        elif request.form['password'] != app.config['PASSWORD']:
            error = 'Invalid Password'
        else:
            session['logged_in'] = True
            flash('You were logged in')
            return redirect(url_for('main'))
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('You were logged out')
    return redirect(url_for('main'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)
