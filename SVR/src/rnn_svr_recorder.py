'''
Created on Jan 7, 2018
To do list:
Try cython or swap to C++ to read faster. Program slowing because of GIL.
@author: James
'''

# RNN tutorial
# https://github.com/mrubash1/RNN-Tutorial
# https://svds.com/tensorflow-rnn-tutorial/
# should also check this
# https://www.swharden.com/wp/2016-07-31-real-time-audio-monitor-with-pyqt/

import time
import serial
import wave
import struct
import sys
import re
import csv, codecs, io
import os
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from scipy.io import wavfile
from scipy.signal import resample
import textract

from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import QThread, QMutex, pyqtSignal, pyqtSlot,QObject
from PyQt5.QtWidgets import (QApplication, QWidget, QMainWindow, QAction, qApp,
                              QDesktopWidget, QPushButton, QToolTip, QMessageBox,
                              QMenu, QTextEdit)

import pyqtgraph
import ui_main

serialBufferSize = 10000
dataHighSpeedCount = 0;
average_Voltage = 0
tempRecording = []
mutex = QtCore.QMutex()
completeMutex = QtCore.QMutex()
recordingMutex = QtCore.QMutex()
complete = False
recording = False
resetFlag = False
inputText = ""
bookTextTemp = ""
wavStringTemp = ""

userName = "James"
bookName = "Twilight"
currentDirectory = os.getcwd()
# Checks if directories exist, make them if they don't.
finalDirectoryManual = os.path.join(currentDirectory, r'data/{}/manual'.format(userName))
if not os.path.exists(finalDirectoryManual):
    os.makedirs(finalDirectoryManual)

finalDirectoryBook = os.path.join(currentDirectory, r'data/{}/{}'.format(userName, bookName))
if not os.path.exists(finalDirectoryBook):
    os.makedirs(finalDirectoryBook)



# Connect to serial port
try:
    # Change the string to whatever serial port your Arduino is connected to on the bottom right corner in the Arduino sketch
    arduino = serial.Serial("COM3", 115200, timeout=0.5)
except:
    print('Please check the port')
    sys.exit(1)


###############################################################################
#    svrRingBuffer
#        General ring buffer for int or float.  Made because Python array allocation
#        took too long.
###############################################################################
class svrRingBuffer():
    ####################
    #    __init__
    #        Initializes ring buffer with given buffer size and data type.
    #        Return: None
    ####################
    def __init__(self, bufferSize, dataType):
        if(dataType == "int"):
            self.buffer = np.zeros(bufferSize, dtype = "int")
        elif(dataType == "float"):
            self.buffer = np.zeros(bufferSize, dtype = "float")
        else:
            print("Invalid data type")
            sys.exit(1)
        self.index = 0
        self.readIndex = 0
    
    ####################
    #    writeData
    #        Writes ones int or float, depending on initialized type.
    #        Return: None
    ####################    
    def writeData(self, x):
        if self.index + x.size > self.buffer.size:
            self.buffer[:self.buffer.size - self.index] = x[x.size - (self.buffer.size - self.index):x.size]
            self.buffer[self.buffer.size - (x.size - (self.buffer.size - self.index)):self.buffer.size] = x[:x.size - (self.buffer.size - self.index)]
            self.index = (x.size - (self.buffer.size - self.index))
        elif self.index + x.size > 2*self.buffer.size:
            print("wtf dude")
        else:
            self.buffer[self.buffer.size - x.size - self.index:self.buffer.size - self.index] = x
            self.index += x.size
    
    ####################
    #    readData
    #        Reads top of ring buffer.
    #        Return: int or float
    ####################            
    def readData(self):
        self.indexTemp = self.index
        self.buffer = np.roll(self.buffer, self.index)
        self.index = 0
        return self.buffer[:self.indexTemp]
    
    ####################
    #    theWholeTruth
    #        Debug function, returns entire buffer.
    #        Return: int or float array
    ####################    
    def theWholeTruth(self):
        return self.buffer
    
    ####################
    #    theWholeRolledTruth
    #        Rolls the buffer, then returns the entire buffer.
    #        Return: int or float array
    ####################    
    def theWholeRolledTruth(self):
        self.buffer = np.roll(self.buffer, self.index)
        self.index = 0
        return self.buffer

###############################################################################
#    WavWriteThread
#        Thread to write files while serial thread continues to read.
###############################################################################
class WavWriteThread(QtCore.QThread):
    ####################
    #    __init__
    #        Initialization
    #        Return: None
    ####################
    def __init__(self, dataBuffer, fcount, validDataIndex):
        QThread.__init__(self)
        self.dataBuffer = dataBuffer
        self.fcount = fcount
        self.validDataIndex = validDataIndex
        self.exiting = False
        self.currentTime = time.strftime("%m%d%Y-%H%M%S",time.localtime())  # Do not put this in def run, will crash code. MAGIC
    
    ####################
    #    __del__
    #        Delete Thread
    #        Return: None
    ####################
    def __del__(self):
        self.exiting = True
        self.wait()
    
    ####################
    #    run
    #        Main wav write thread.
    #        Return: None
    ####################
    def run(self):
        data = []
        currentTab = form.tabWidget.currentIndex()
        
        if currentTab == 0:
            finalDirectory = finalDirectoryManual
        else:
            finalDirectory = finalDirectoryBook

        np.savetxt("{}/{}-{}.csv".format(finalDirectory, userName, self.currentTime), self.dataBuffer[:self.validDataIndex], delimiter=",")
        fname = ("{}/{}-{}.csv".format(finalDirectory, userName, self.currentTime))
        for time, value in csv.reader(open(fname, 'U'), delimiter=','):
            try:
                data.append(float(value))#Here you can see that the time column is skipped
            except ValueError:
                pass # Just skip it
    
        arr = np.array(data)#Just organize all your samples into an array
        arr = arr * (5.0 / 1023.0) - average_Voltage
        # Normalize data
        arr /= np.max(np.abs(arr)) #Divide all your samples by the max sample value
        filename_head, extension = fname.rsplit(".", 1)        
        data_resampled = resample( arr, len(data) )
        wavfile.write("{}/{}-{}.wav".format(finalDirectory, userName, self.currentTime), 4000, data_resampled) #resampling at 16khz
        print ("Wav file written successfully !")

        if currentTab == 0:
            text_file = open("{}/{}-{}.txt".format(finalDirectory, userName, self.currentTime), "w", encoding='utf8')
            global inputText
            text_file.write(inputText)
            text_file.close()
            inputText = ""
        else:
            text_file = open("{}/{}-{}.txt".format(finalDirectory, userName, self.currentTime), "w", encoding='utf8')
            global bookTextTemp
            dummy = bookTextTemp
            text_file.write(bookTextTemp)
            text_file.close()
            form.c.doneBookWriting.emit()
        print ("Transcription file written successfully !")
        global wavStringTemp
        wavStringTemp = "{}/{}-{}.wav".format(finalDirectory, userName, self.currentTime)
        form.wavSignal.wavReady.emit()
        self.__del__()

###############################################################################
#    SerialReadThread
#        Thread to read serial.
###############################################################################
class SerialReadThread(QtCore.QThread):
    ####################
    #    __init__
    #        Initialization
    #        Return: None
    ####################
    def __init__(self):
        QThread.__init__(self)
        self.exiting = False
         
    ####################
    #    __del__
    #        Delete Thread
    #        Return: None
    ####################
    def __del__(self):
        completeMutex.lock()
        global complete
        complete = True
        completeMutex.unlock()
        self.exiting = True
        self.wait()
    
    ####################
    #    run
    #        Main serial read thread loop.
    #        Return: None
    ####################
    def run(self):
        recordCount = 0
        fileCount = 0
        timeZero = 0
        timeCurrent = 0
        timeFromZero = 0
        loopCount = 0
        takingTooLongCount = 0;
        data = np.zeros([1])
        writeBuffer = np.zeros((100000,2), dtype = int)
        while True:
            for line in arduino:
                t1=time.clock()
                if arduino.inWaiting() > 0:
                    
                    dummydata = line      # Debug variable to see serial data sent
                    t2 = time.clock()
                    data[0] = dummydata.rstrip()
                    while Is_Number(data) != True:      # Necessary to check since first serial data sent is not always valid
                        loopCount += 1
                        dummydata = line
                        data[0] = dummydata.rstrip()
                    
                    mutex.lock()
                    global dataHighSpeed

                    dataHighSpeed.writeData(data)

                    mutex.unlock()
                    
                    recordingMutex.lock()
                    
                    if recording == True:
                        if recordCount == 0:
                            timeZero = time.clock()      
                            writeBuffer[recordCount:recordCount + 1] = (0, data[0])
                            #row = [0, data[0]]
                            #writer.writerow(row)
                            recordCount += 1
                        else:
                            timeCurrent = time.clock()
                            timeFromZero = timeCurrent - timeZero
                            writeBuffer[recordCount:recordCount + 1] = (timeFromZero*1000000, data[0])
                            recordCount += 1
                    else:
                        global resetFlag
                        if resetFlag == True:
                            resetFlag = False
                            timeZero = 0
                            timeCurrent = 0
                            timeFromZero = 0
                            writeBuffer = np.zeros((100000,2), dtype = int)
                            recordCount = 0
                        elif recordCount != 0:
                            timeZero = 0
                            timeCurrent = 0
                            timeFromZero = 0
                            self.wavThread = WavWriteThread(writeBuffer, fileCount, recordCount)
                            self.wavThread.start()
                            writeBuffer = np.zeros((100000,2), dtype = int)
                            recordCount = 0
                            fileCount += 1
                        else:
                            pass
                    recordingMutex.unlock()  
                                        
                    print("update took {:0.03f} ms, arduino read took {:0.03f} ms, {:d} loops".format((time.clock()-t1)*1000, (t2-t1)*1000, takingTooLongCount))
                    if (time.clock()-t1)*1000 >= 0.03:
                        takingTooLongCount = 0
                    takingTooLongCount += 1   
                    loopCount = 0
                    completeMutex.lock()
                    if complete == True:
                        completeMutex.unlock()
                        return
                    completeMutex.unlock()

###############################################################################
#    CommunicateBookWritingDone
#        Signal to communicate through pyqt that it is done writing text from
#        the book.
###############################################################################
class CommunicateBookWritingDone(QObject):
    doneBookWriting = pyqtSignal()

###############################################################################
#    CommunicateSpectro
#        Signal to communicate through pyqt that we can make the spectrogram
#        now.
###############################################################################
class CommunicateSpectro(QObject):
    wavReady = pyqtSignal()

###############################################################################
#    ExampleApp
#        Main application class
###############################################################################
class ExampleApp(QMainWindow, ui_main.Ui_MainWindow):
    ####################
    #    __init__
    #        Initialization
    #        Return: None
    ####################
    def __init__(self, parent=None):
        global average_Voltage
        average_Voltage = Calibration_Zero_Average()
        # I'm not gonna explain the regex, it'll take way too long.
        # Just treat it as magic, or read the link I guess
        # https://regex101.com/r/nG1gU7/27
        regex = r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s"
        subst = "\\n"
        self.text = textract.process("Books/twilight1.epub")
        self.text = self.text.decode("utf-8")
        self.text = self.text.replace('\n','')
        self.text = re.sub(regex, subst, self.text, 0, re.MULTILINE)
        self.parsedText = []
        
        #for line in self.text:
        #Split Paragraph on basis of '.' or ? or !.
        #for l in re.split(r"\.|\?|\!", self.text):
        for l in re.split(r"\n", self.text):
            #Split line into list using space.
            #self.parsedText.append(l.split(" "))
            self.parsedText.append(l)
            
        del self.parsedText[0]        
        
        # Do not set for more points
        self.bufferSize = 1000
        self.X = np.arange(self.bufferSize)
        self.yBuffer = svrRingBuffer(self.bufferSize, "float")
        self.tempData = np.zeros(self.bufferSize)
        #self.Y = [0] * 100
        pyqtgraph.setConfigOption('background', 'w') #before loading widget
        super(ExampleApp, self).__init__(parent)
        #self.setStyleSheet("QMainWindow {background: 'black';}")
        self.setupUi(self)
        
        self.mRecordBtn.clicked.connect(self.RecordToggle)
        self.rRecordBtn.clicked.connect(self.RecordToggle)
        
        self.mResetBtn.clicked.connect(self.ResetRecording)
        self.rResetBtn.clicked.connect(self.ResetRecording)
        
        self.mRecordBtn.setEnabled(False)
        self.mResetBtn.setEnabled(False)
        
        self.textConfirmBtn.clicked.connect(self.textConfirm)
        
        self.skipBtn.clicked.connect(self.skipSentence)
        self.backBtn.clicked.connect(self.goBackASentence)
        
        # Tab 3
        self.opConfirmBtn.clicked.connect(self.optionsConfirm)
        self.usernameInput.setText(userName)
        self.bookNameInput.setText(bookName)
        
        self.bookSentenceIndex = 0
        try:
            with open("save.txt") as f:
                readTemp = f.read()
                if not readTemp:
                    pass
                else:
                    self.bookSentenceIndex = int(readTemp)
        except FileNotFoundError:
            print("No save") 
        
        self.bookText.setText(str(self.parsedText[self.bookSentenceIndex]))
        global bookTextTemp
        bookTextTemp = str(self.parsedText[self.bookSentenceIndex])
        self.c = CommunicateBookWritingDone()
        self.c.doneBookWriting.connect(self.skipSentence)
        self.wavSignal = CommunicateSpectro()
        self.wavSignal.wavReady.connect(self.printSpectro)
             
        self.grPlot.plotItem.showGrid(True, True, 0.7)
        self.grPlot.setYRange(average_Voltage - 6, average_Voltage )
        self.grPlot.setLabels(left = ("Voltage", "V"), bottom = ("Time", "s"),
                              title = ("Real-time Voltage Data"))
        
        self.thread = SerialReadThread()
        self.thread.start()
        
        self.update()
    
    ####################
    #    update
    #        Updates UI
    #        Return: None
    ####################
    def update(self):     
        mutex.lock()
        global dataHighSpeed
        tempData = dataHighSpeed.readData()
        mutex.unlock()
        
        tempData = tempData * (5.0 / 1023.0) - average_Voltage
        self.yBuffer.writeData(tempData)
        C=pyqtgraph.hsvColor(hue = 0, sat=0.9, val = 1, alpha = 0.7)
        pen=pyqtgraph.mkPen(color=C,width=4)
        self.grPlot.plot(self.X[:200],self.yBuffer.theWholeRolledTruth()[:self.bufferSize - 200 - 1:-1],pen=pen,clear=True)
        QtCore.QTimer.singleShot(100, self.update) # DO NOT LOWER THIS OR IT WILL CRASH! THIS IS A MAGIC NUMBER! You can increase it though.
    
    ####################
    #    RecordToggle
    #        Function for record button, to toggle recording on or off.
    #        Return: None
    ####################
    def RecordToggle(self):
        recordingMutex.lock()
        global recording
        recording = not recording
        if recording == True:
            recordingMutex.unlock()
            self.mRecordBtn.setText("Stop")
            self.rRecordBtn.setText("Stop")
            if self.tabWidget.currentIndex() == 0:
                self.tabWidget.setTabEnabled(1, False)
            else:
                self.tabWidget.setTabEnabled(0, False)
        else:
            recordingMutex.unlock()
            self.mRecordBtn.setText("Record")
            self.rRecordBtn.setText("Record")
            if self.tabWidget.currentIndex() == 0:
                self.tabWidget.setTabEnabled(1, True)
            else:
                self.tabWidget.setTabEnabled(0, True)
    
    ####################
    #    ResetRecording
    #        Function for reset button, pressing it resets recording.
    #        Return: None
    ####################
    def ResetRecording(self):
        recordingMutex.lock()
        global recording
        if recording == True:
            recording = False
            global resetFlag
            resetFlag = True
            recordingMutex.unlock()
            self.mRecordBtn.setText("Record")
            self.rRecordBtn.setText("Record")
            if self.tabWidget.currentIndex() == 0:
                self.tabWidget.setTabEnabled(1, True)
            else:
                self.tabWidget.setTabEnabled(0, True)
        else:
            recordingMutex.unlock()
            
    ####################
    #    textConfirm
    #        Function for text confirm button, pressing confirms text input.
    #        Return: None
    ####################
    def textConfirm(self):
        global inputText
        if not self.textEdit.toPlainText():
            inputText = ""
            self.statusBar().showMessage("Don't lie to me, I know it's empty.")
            self.mRecordBtn.setEnabled(False)
            self.mResetBtn.setEnabled(False)
        else:
            inputText = self.textEdit.toPlainText()
            self.statusBar().showMessage("Text confirmed, good to go.")
            self.mRecordBtn.setEnabled(True)
            self.mResetBtn.setEnabled(True)
            
    ####################
    #    skipSentence
    #        Function for skip button, pressing it skips the sentence to the
    #        next sentence in the book.
    #        Return: None
    ####################
    def skipSentence(self):
        global bookTextTemp
        if self.bookSentenceIndex < (len(self.parsedText) - 1):
            self.bookSentenceIndex += 1
            bookTextTemp = str(self.parsedText[self.bookSentenceIndex])
            self.bookText.setText(str(self.parsedText[self.bookSentenceIndex]))
            self.statusBar().showMessage("")
        else:
            self.statusBar().showMessage("You're done reading.")
        
    ####################
    #    goBackASentence
    #        Function for back button, pressing it makes it go back to the
    #        previous sentence in the book.
    #        Return: None
    ####################
    def goBackASentence(self):
        global bookTextTemp
        if self.bookSentenceIndex > 0:
            self.bookSentenceIndex -= 1
            bookTextTemp = str(self.parsedText[self.bookSentenceIndex])
            self.bookText.setText(str(self.parsedText[self.bookSentenceIndex]))
        else:
            self.statusBar().showMessage("You're already at the beginning of the book.")
    
    ####################
    #    printSpectro
    #        Function to print a spectrogram in the widget.
    #        Return: None
    ####################
    def printSpectro(self):
        sample_rate, samples = wavfile.read(wavStringTemp)
        frequencies, times, spectogram = signal.spectrogram(samples, sample_rate)
        self.fftPlot.axes.pcolormesh(times, frequencies, spectogram)
        self.fftPlot.axes.set_xlim(times[0], times[len(times) - 1])
        self.fftPlot.axes.set_ylabel('Frequency (Hz)')
        self.fftPlot.axes.set_xlabel('Time (s)')
        self.fftPlot.draw()
    
    ####################
    #    optionsConfirm
    #        Function for options confirm button, confirms options.
    #        Return: None
    ####################
    def optionsConfirm(self):
        if (not self.usernameInput.text()) and (not self.bookNameInput.text()):
            self.statusBar().showMessage("Don't lie to me, I know it's all empty.")
        elif not self.usernameInput.text():
            self.statusBar().showMessage("Seriously, give me your name.")
        elif not self.bookNameInput.text():
            self.statusBar().showMessage("I'll just randomly name the folder if you don't give me the name of the book.")
        else:
            global userName
            global bookName
            global finalDirectoryManual
            global finalDirectoryBook
            userName = self.usernameInput.text()
            bookName = self.bookNameInput.text()
            
            finalDirectoryManual = os.path.join(currentDirectory, r'data/{}/manual'.format(userName))
            if not os.path.exists(finalDirectoryManual):
                os.makedirs(finalDirectoryManual)
            
            finalDirectoryBook = os.path.join(currentDirectory, r'data/{}/{}'.format(userName, bookName))
            if not os.path.exists(finalDirectoryBook):
                os.makedirs(finalDirectoryBook)
            
            self.statusBar().showMessage("Options changed")
    
    ####################
    #    closeEvent
    #        When close button(top right X) is pressed, checks if you are sure
    #        you want to quit.
    #        Return: None
    ####################
    def closeEvent(self, event):
        reply = QMessageBox.question(self, 'Message',"Are you sure to quit?", 
             QMessageBox.Yes |QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.thread.__del__()
            arduino.close()
            with open("save.txt", "w") as f:
                f.write("{}".format(self.bookSentenceIndex))
            event.accept()
        else:
            event.ignore()   


####################
#    write_wave
#    write wave function from
#    https://stackoverflow.com/questions/41209733/csv-to-wav-python
#    Author: Gab55
#    Return: None
####################
def write_wav(data, filename, framerate, amplitude):
    wavfile = wave.open(filename,'w')
    nchannels = 1
    sampwidth = 2
    framerate = framerate
    nframes = len(data)
    comptype = "NONE"
    compname = "not compressed"
    wavfile.setparams((nchannels,
                        sampwidth,
                        framerate,
                        nframes,
                        comptype,
                        compname))
    frames = []
    for s in data:
        mul = int(s * amplitude)
        frames.append(struct.pack('h', mul))

    frames = ''.join(frames)
    wavfile.writeframes(frames)
    wavfile.close()
    print("%s written" %(filename)) 

####################
#    Is_Number
#    Self explanatory
#    Return: Float
####################
def Is_Number(x):
    try:
        float(x)
        return True
    except ValueError:
        return False

####################
#    Calculate_Average_Voltage
#    Self explanatory
#    Return: Float
####################
def Calculate_Average_Voltage(x):
    Average_Voltage = sum(x)/len(x)
    return Average_Voltage

####################
#    Calibration_Zero_Average
#    Calculates the average voltage of 1000 samples, zeroes the voltage
#    to that average.
#    Return: Float
####################
def Calibration_Zero_Average():
    #dataArray = [0] * 1000
    dataArray = np.zeros(serialBufferSize)
    for x in range(serialBufferSize):
        dummydata = arduino.readline()      # Debug variable to see serial data sent
        data = dummydata.rstrip()
        while Is_Number(data) != True:      # Necessary to check since first serial data sent is not always valid
            dummydata = arduino.readline()
            data = dummydata.rstrip()
        
        dataArray[x] = data
    
    dataArray = dataArray * (5.0 / 1023.0)
    return Calculate_Average_Voltage(dataArray)
 

dataHighSpeed = svrRingBuffer(serialBufferSize, "int")
    
if __name__ == "__main__":
    app = QApplication(sys.argv)
    form = ExampleApp()
    form.show()
    form.showMaximized()
    app.exec_()
    print("DONE")