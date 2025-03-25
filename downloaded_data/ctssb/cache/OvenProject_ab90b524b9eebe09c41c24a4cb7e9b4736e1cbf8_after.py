from flask import Flask, request, session, redirect, url_for, \
     abort, render_template, flash, send_from_directory
from max31855.max31855 import MAX31855, MAX31855Error
import math
import RPi.GPIO as GPIO
from time import perf_counter
import time
import threading
#from RPLCD import CharLCD
#from RPLCD import Alignment, CursorMode, ShiftMode
#from RPLCD import cursor, cleared
import os
from werkzeug import secure_filename
import csv
import sys
from statistics import mean
from collections import deque

#Import Tunings
tuneParams = [[],[],[],[]]
with open(('/home/pi/OvenProject/data/tunefile.csv') , newline='') as csvfile:
    spamreader = csv.reader(csvfile, dialect='excel')
    next(spamreader)
    for row in spamreader:
        tuneParams[0].append(float(row[0]))
        tuneParams[1].append(float(row[1]))
        tuneParams[2].append(float(row[2]))
        tuneParams[3].append(float(row[3]))

#Flask Settings

DEBUG = True
SECRET_KEY = 'development key'
USERNAME = 'admin'
PASSWORD = 'PrISUm14'

UPLOAD_FOLDER = '/home/pi/OvenProject/data/uploads'
ALLOWED_EXTENSIONS = set(['csv'])

app = Flask(__name__)
app.config.from_object(__name__)
app.config.from_envvar('FLASKR_SETTINGS', silent=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


#Variable Creation

timeL = []
setPointL = []
outputL = []
tempL = []
aveTempL = deque([],10)

currentTemp = 0
initialTemp = 100
setPoint = initialTemp
output = 0
status = 0
killStatus = True
rampEnable = False

#Status:
#0 = Off
#1 = Preheat: No Program
#2 = Preheat: Ready
#3 = Running
#4 = Complete
#5 = Preheat: No 2 Part Program
#6 = Preheat: No Complex Program

#Loop for the PID controller, data logging and ramp control

class PIDloop(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
    def run(self):
        global currentTemp, output, killStatus, setPoint, tempL, outputL, status

        #Setup the output relay
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(18, GPIO.OUT)
        relay = GPIO.PWM(18, 1)
        relay.start(0)

        #Setup the thermocouple
        cs_pin = 8
        clock_pin = 11
        data_pin = 9
        units = 'f'
        thermocouple = MAX31855(cs_pin, clock_pin, data_pin, units)

        #Character LCD Setup, currently abandoned
#        c = CharLCD(0x27, numbering_mode=GPIO.BCM, rows=2, cols=16)

        #Initial loop variable setup
        killStatus = False
        firstRamp = True
        timeOldP = perf_counter()
        tempOld = thermocouple.get()
        aveTempL.append(tempOld)
        outMin = 0
        outMax = 100
        intErr = 0
        logCount = 0
        kset = 0

        #Loop
        while not(killStatus):
            timeP = perf_counter()

            #PID controller
            if (timeP-timeOldP)>1:
                timeOldP = timeP
                logCount += 1
                aveTempL.append(thermocouple.get())
                currentTemp = mean(aveTempL)
                err = setPoint - currentTemp

                #Gain scheduling
                for n in range(len(tuneParams)):
                    if err > tuneParams[0][n]:
                        kp = tuneParams[1][n]
                        ki = tuneParams[2][n]
                        kd = tuneParams[3][n]
                        if kset != n:
                            if kset < n:
                                intErr = 0
                            kset = n
                        break
                    else:
                        kp = 0
                        ki = 0
                        kd = 0

                #Integral term
                intErr += ki*err

                #Integral windup prevention
                if intErr > outMax:
                    intErr = outMax
                elif intErr < outMin:
                    intErr = outMin

                #Derivative term
                din = currentTemp - tempOld

                #Output equation
                output = kp*err + intErr - kd*din

                #Process output
                if output > outMax:
                    output = outMax
                elif output < outMin:
                    output = outMin
                relay.ChangeDutyCycle(output)

                #Character LCD update, currently abandoned
#                c.cursor_pos = (0, 0)
#                c.write_string('T:' + str(currentTemp) + ' SP:' + str(setPoint))
#                c.cursor_pos = (1, 0)
#                c.write_string('Out:' + str(output))

                tempOld = currentTemp

            #Ramp and data logging
            if rampEnable:

                #Begin run setup
                if firstRamp:
                    tmin = 0
                    logTime = 0
                    logCount = 0
                    timeOldR = perf_counter()
                    tempL.append(currentTemp)
                    outputL.append(output)
                    logFile = open('/home/pi/OvenProject/data/uploads/logfile.csv', 'a')
                    spamwriter = csv.writer(logFile, dialect='excel', quoting=csv.QUOTE_MINIMAL)
                    spamwriter.writerow(['Time', 'SP', 'Temp', 'Output'])
                    spamwriter.writerow([logTime, setPoint, currentTemp, output])
                    firstRamp = False

                #Data logging
                if logCount == 15:
                    logTime += 0.25
                    logCount = 0
                    spamwriter.writerow([logTime, setPoint, currentTemp, output])

                #setpoint update
                if (timeP-timeOldR)>60:
                    timeOldR = timeP
                    if not(abs(err)>5):
                        tmin += 1
                        tempL.append(currentTemp)
                    if len(tempL) == len(setPointL):
                        killStatus = True
                        status = 4
                        break
                    setPoint = setPointL[tmin]

        #Cleanup
        logFile.close()
        relay.stop()
#        c.close()
        GPIO.cleanup()

#Create loop
PIDloopT = PIDloop()

#Main page, renders the currently needed information
@app.route('/')
def main():
    if status == 0:
        return render_template('prerun.html')
    elif status == 1:
        return render_template('program.html')
    elif status == 2:
        return render_template('ready.html', CurrT=currentTemp, sp=setPoint)
    elif status == 3:
        return render_template('run.html', CurrT=currentTemp, sp=setPoint)
    elif status == 5:
        return render_template('program2.html')
    elif status == 6:
        return render_template('compprogram.html')
    else:
        return render_template('postrun.html')

#Enables the preheat and returns for simple programming
@app.route('/preheat', methods=['POST'])
def preheat():
    global status
    PIDloopT.start()
    flash('Preheat Enabled')
    status = 1
    return redirect(url_for('main'))

#Enables the preheat and returns for 2 step programming
@app.route('/preheat2', methods=['POST'])
def preheat2():
    global status
    PIDloopT.start()
    flash('Preheat Enabled')
    status = 5
    return redirect(url_for('main'))

#Enables the preheat and returns for complex programming
@app.route('/comppreheat', methods=['POST'])
def comppreheat():
    global status
    PIDloopT.start()
    flash('Preheat Enabled')
    status = 6
    return redirect(url_for('main'))

#Starts the run
@app.route('/startrun', methods=['POST'])
def startrun():
    global status, rampEnable
    rampEnable = True
    flash('Run Started')
    status = 3
    return redirect(url_for('main'))

#Kills the run
@app.route('/kill', methods=['POST'])
def kill():
    global status, killStatus
    killStatus = True
    flash('Run Stopped')
    status = 4
    return redirect(url_for('main'))

#Allows the uploads of tunings
@app.route('/tuning', methods=['GET', 'POST'])
def tuning():
    return render_template('tuning.html')

#Recieve program upload
@app.route('/uploadt', methods=['GET', 'POST'])
def uploadt():
    if request.method == 'POST':
        file = request.files['file']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            return redirect(url_for('tune',
                                    filename=filename))

#Sets the tuning parameters
@app.route('/tune', methods=['POST'])
def tune(filename):
    global tuneParams
    if not session.get('logged_in'):
        abort(401)
    with open(('/home/pi/OvenProject/data/uploads/' + filename) , newline='') as csvfile:
        spamreader = csv.reader(csvfile, dialect='excel', quoting=csv.QUOTE_NONNUMERIC)
        tuneFile = open('/home/pi/OvenProject/data/tunefile.csv', 'w')
        spamwriter = csv.writer(tuneFile, dialect='excel')
        spamwriter.writerow(['Err Bound', 'Kp', 'Ki', 'Kd'])
        next(spamreader)
        for row in spamreader:
            tuneParams[0].append(float(row[0]))
            tuneParams[1].append(float(row[1]))
            tuneParams[2].append(float(row[2]))
            tuneParams[3].append(float(row[3]))
            spamwriter.writerow([row[0], row[1], row[2], row[3]])
        tuneFile.close()
    flash('Tunings Updated')
    return redirect(url_for('main'))

#Sets the simple program
@app.route('/profile', methods=['POST'])
def profile():
    global status, timeL, setPointL

    #Collect form information
    runName = request.form['Name']
    holdTemp = float(request.form['HoldT'])
    holdTime = int(request.form['HoldTim'])
    heatRate = float(request.form['UR'])
    coolRate = float(request.form['DR'])
    logFile = open('/home/pi/OvenProject/data/uploads/logfile.csv', 'w')
    spamwriter = csv.writer(logFile, dialect='excel', quoting=csv.QUOTE_MINIMAL)
    spamwriter.writerow([runName])
    logFile.close()
    outputFile = open('/home/pi/OvenProject/data/schedule.txt', 'w')
    outputFile.write('Time    SP\n')
    i = 0
    setPointIter = setPoint
    timeL.append(i)
    setPointL.append(setPointIter)
    outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')

    #Write ramp up
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

    #Write ramp down
    for j in range(holdTime):
        i += 1
        setPointL.append(setPointIter)
        timeL.append(i)
        outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')

    #Write ramp down
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

#Set two step program
@app.route('/profile2', methods=['POST'])
def profile2():
    global status, timeL, setPointL

    #Collect form information
    runName = request.form['Name']
    holdTemp1 = float(request.form['HoldT1'])
    holdTime1 = int(request.form['HoldTim1'])
    heatRate1 = float(request.form['UR1'])
    holdTemp2 = float(request.form['HoldT2'])
    holdTime2 = int(request.form['HoldTim2'])
    heatRate2 = float(request.form['UR2'])
    coolRate = float(request.form['DR'])
    logFile = open('/home/pi/OvenProject/data/uploads/logfile.csv', 'w')
    spamwriter = csv.writer(logFile, dialect='excel', quoting=csv.QUOTE_MINIMAL)
    spamwriter.writerow([runName])
    logFile.close()
    outputFile = open('/home/pi/OvenProject/data/schedule.txt', 'w')
    outputFile.write('Time    SP\n')
    i = 0
    setPointIter = setPoint
    timeL.append(i)
    setPointL.append(setPointIter)
    outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')

    #Write first ramp up
    while setPointL[i] + heatRate1 < holdTemp1:
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

    #Write first hold time
    for j in range(holdTime1):
        i += 1
        setPointL.append(setPointIter)
        timeL.append(i)
        outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')

    #Write second ramp up
    while setPointL[i] + heatRate2 < holdTemp2:
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

    #Write second hold time
    for j in range(holdTime2):
        i += 1
        setPointL.append(setPointIter)
        timeL.append(i)
        outputFile.write(str(timeL[i]) + ' ' + str(setPointL[i]) + '\n')

    #Write ramp down
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

#Provide log file for download
@app.route('/download', methods=['POST'])
def download():
    return send_from_directory(app.config['UPLOAD_FOLDER'],
                               'logfile.csv')

@app.route('/downloadt', methods=['POST'])
def downloadt():
    return send_from_directory(app.config['UPLOAD_FOLDER'],
                               'tunefile.csv')

#File type checking
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS

#Recieve program upload
@app.route('/uploadp', methods=['GET', 'POST'])
def uploadp():
    if request.method == 'POST':
        file = request.files['file']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            return redirect(url_for('compprogram',
                                    filename=filename))

#Convert uploaded file to program
@app.route('/uploads/<filename>')
def compprogram(filename):
    global status, timeL, setPointL
    with open(('/home/pi/OvenProject/data/uploads/' + filename) , newline='') as csvfile:
        spamreader = csv.reader(csvfile, dialect='excel', quoting=csv.QUOTE_NONNUMERIC)
        logFile = open('/home/pi/OvenProject/data/uploads/logfile.csv', 'w')
        spamwriter = csv.writer(logFile, dialect='excel', quoting=csv.QUOTE_MINIMAL)
        spamwriter.writerow([filename])
        logFile.close()
        outputFile = open('/home/pi/OvenProject/data/schedule.txt', 'w')
        outputFile.write('Time    SP\n')
        for row in spamreader:
            setPointL.append(row[1])
            timeL.append(int(row[0]))
            outputFile.write(str(int(row[0])) + ' ' + str(row[1]) + '\n')
    outputFile.close()
    status = 2
    flash('Temperature Profile Updated')
    return redirect(url_for('main'))

def restart_program():
    """Restarts the current program.
    Note: this function does not return. Any cleanup action (like
    saving data) must be done before calling this function."""
    python = sys.executable
    os.execl(python, python, * sys.argv)

#Kill the program
@app.route('/end', methods=['POST'])
def end():
    GPIO.cleanup()
    restart_program()

#Login for tuning change
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

#Logout of tuning
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('You were logged out')
    return redirect(url_for('main'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=True)
