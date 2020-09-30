# For Args
import sys
import numpy as np
from scipy.signal import find_peaks
import time

# for GUI 
from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
# For graphs
from pyqtgraph import PlotWidget, plot
import pyqtgraph as pg

from rtlsdr import RtlSdr
from matplotlib import mlab as mlab


# Supported gain values (29): 0.0 0.9 1.4 2.7 3.7 7.7 8.7 12.5 14.4 15.7 16.6 19.7 20.7 22.9 25.4 28.0 29.7 32.8 33.8 36.4 37.2 38.6 40.2 42.1 43.4 43.9 44.5 48.0 49.6
pg.setConfigOptions(antialias=True)
pg.setConfigOption('background', '#000000')
pg.setConfigOption('foreground', '#aaaaaa')
class SDRThread(QThread):
    signal = pyqtSignal(object)
    def __init__(self,sample_rate = 2.4e6,center_freq = 100.0e6,freq_correction = 60, gain = 33.8, chunks = 1024):
        QThread.__init__(self)
    
        self.sdr = RtlSdr()
        # configure device
        self.sdr.sample_rate = sample_rate  # Hz
        self.sdr.center_freq = center_freq  # Hz
        self.sdr.freq_correction = freq_correction   # PPM
        self.sdr.gain = gain # dB
        self.CHUNK = chunks
    
    def __del__(self):
        self.wait()
        self.sdr.cancel_read_async()

    def sdr_tune(self,cf):
        self.sdr.center_freq = cf  # Hz

    def sdr_gain(self,gain=33.8):
        self.sdr.gain = gain


    def run(self):
        self.sdr.read_samples_async(self.sdr_async_callback,self.CHUNK,None)

    def sdr_async_callback(self,iq,ctx):
        power, _ = mlab.psd(iq, NFFT=self.CHUNK, Fs=self.sdr.sample_rate, scale_by_freq=False)
        self.signal.emit(np.sqrt(power))

class MainWindow(QtWidgets.QMainWindow):
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        uic.loadUi("MainApp.ui", self)

        # Variables for UI and SDR
        self.center_freq = 100.0e6
        self.band_width = 2.4e6
        self.CHUNK = 512
        self.PPM = 60

        self.isPeaks = False
        self.counter = 0
        self.tmp = 0
        self.history_length = 128

        #self.PSD = np.arange(-1,2)
        #self.freq = np.arange(-1,2)*self.band_width/2.0 + self.center_freq
        self.freq = np.linspace(-self.band_width/2,self.band_width/2,self.CHUNK) + self.center_freq
        self.data = np.random.rand(self.CHUNK)*0.000001

        self.history = np.empty(shape=(self.history_length, self.CHUNK))

        self.sdrThread = SDRThread(
            sample_rate = self.band_width,
            center_freq = self.center_freq,
            freq_correction = self.PPM,
            gain = 33.8,
            chunks = self.CHUNK
        )
        self.sdrThread.start()

        self.waterfallView.plot()

        self.waterfallView.setLabel("bottom", "Frequency", units="Hz")
        self.waterfallView.setLabel("left", "Time")
        self.waterfallView.setLimits(xMin=self.freq[0],xMax=self.freq[-1],yMin=-self.history_length,yMax=0)

        #self.waterfallView.setYRange(self.history_length, 0)
        #self.waterfallView.setLimits(yMax=self.history_length,yMin=0)
        #self.waterfallView.showButtons()
        
        # We need to construct image for waterfall
        self.img_waterfall = pg.ImageItem()
        self.waterfallView.addItem(self.img_waterfall)

        
        """
        grad = QtGui.QLinearGradient(0, 0, 0, 0.000004)
        grad.setColorAt(0.000007, pg.mkColor('#000000'))
        grad.setColorAt(0.000005, pg.mkColor('b'))
        brush = QtGui.QBrush(grad)
        """
        self.spectrumView.setLimits(xMin=self.freq[0],xMax=self.freq[-1])
        self.curve = self.spectrumView.plot(x = self.freq,
                                            y = self.data,
                                            pen = 'w',
                                            fillLevel = -8,
                                            fillBrush = (55,155,255,100),
                                            padding = 0.0,
                                            autoRange=False)

        self.curve.setPen((255,255,195,90), width=1)

        self.curvePeaks = self.spectrumView.plot(self.freq,self.freq*0, pen=None, symbol='d',symbolBrush=(215,155,255,200))

        self.spectrumView.setLabel("left", "Power", units="dB")
        self.spectrumView.setLimits(yMin=-4,yMax=-1)
        self.spectrumView.setLogMode(x=None, y=True)
        self.spectrumView.showGrid(x=True, y=None, alpha=0.8)
        self.spectrumView.setLabel("bottom", "Frequency", units="Hz")
        self.spectrumView.showButtons()

         # Create crosshair
        self.vLine = pg.InfiniteLine(angle=90, movable=False, pen='#aaaabb')
        self.vLine.setZValue(1000)

        self.hLine = pg.InfiniteLine(angle=0, movable=False, pen='#aaaabb')
        self.hLine.setZValue(1000)

        self.spectrumView.addItem(self.vLine, ignoreBounds=True)
        self.spectrumView.addItem(self.hLine, ignoreBounds=True)

        self.vLine2 = pg.InfiniteLine(angle=90, movable=False, pen='#aaaabb')
        self.vLine2.setZValue(1000)

        self.waterfallView.addItem(self.vLine2,ignoreBounds=True)

        # Link ranges and focus of spectrum and waterfall
        self.spectrumView.setXLink(self.waterfallView)
        self.sdrThread.signal.connect(self.updateData)

        # User interactions on plot
        self.mouseProxy = pg.SignalProxy(self.spectrumView.scene().sigMouseMoved,
                                         rateLimit=60,
                                         slot=self.mouse_moved)
        self.spectrumView.scene().sigMouseClicked.connect(self.mouse_clicked)
        
        # Gradient color level selector
        self.histogram_layout = pg.GraphicsLayoutWidget()
        self.verticalLayout.addWidget(self.histogram_layout)

        self.histogram = pg.HistogramLUTItem(fillHistogram=False)
        self.histogram_layout.addItem(self.histogram)
        # Load a predefined gradient. Currently defined gradients are: 
        self.gradient_presets = ['thermal', 'flame', 'yellowy', 'bipolar', 'spectrum', 'cyclic', 'greyclip', 'grey']
        self.histogram.gradient.loadPreset(self.gradient_presets[1])
        #self.histogram.setHistogramRange(-50, 0)
        self.histogram.setLevels(1.0e-4, 0.008)
        self.histogram.setHistogramRange(1.0e-4, 1.0e-2, padding=0.1)
        
        # Lables
        self.lblFreq.setText(str(self.center_freq))

        #
        self.spinBoxFrequency.setValue(self.center_freq)
        self.spinBoxFrequency.valueChanged.connect(self.sdrSetFrequency)
        
        # GUI Timer Threads for plots 
        self.render_timer = QTimer()
        self.render_timer.setInterval(50)
        self.render_timer.timeout.connect(self.render)
        self.render_timer.start()

        # GUI Timer Threads for waterfall rolling data
        self.data_roll_timer = QTimer()
        self.data_roll_timer.setInterval(50)
        self.data_roll_timer.timeout.connect(self.rollData)
        self.data_roll_timer.start()

        # averaging filter for psd
        self.doubleSpinBoxAlfa.setValue(0.9)
        self.comboBoxGain.currentIndex=21

    def updateData(self,data):
        self.data = data*(1.0-self.doubleSpinBoxAlfa.value())+self.data*(self.doubleSpinBoxAlfa.value())
        """
        if(self.counter%1==0):
            self.history = np.roll(self.history, -1, axis=0)
            self.history[-1] = data
        """

    def rollData(self):
        self.history = np.roll(self.history, -1, axis=0)
        self.history[-1] = self.data

    def render(self):
        try:
            self.counter += 1
            self.curve.setData(self.freq,self.data,autoLevels=True, autoRange=False)
            idx, _ = find_peaks(self.data,distance=50)
            self.curvePeaks.setData(self.freq[idx],self.data[idx])
            self.spectrumView.enableAutoRange(axis='y', enable=False)


            # scale waterfall image only once
            if(self.counter==1):
                    self.img_waterfall.scale((self.freq[-1] - self.freq[0]) / self.CHUNK, 1)
                    self.histogram.setImageItem(self.img_waterfall)

            self.img_waterfall.setImage(self.history.T,levels=self.histogram.getLevels())                
            self.img_waterfall.setPos(self.freq[0],-self.history_length)

        except Exception as e:
            raise(e)

    def sdrSetFrequency(self):
        self.center_freq = self.spinBoxFrequency.value()
        self.freq = np.linspace(-self.band_width/2,self.band_width/2,self.CHUNK) + self.center_freq
        self.spectrumView.setLimits(xMin=self.freq[0],xMax=self.freq[-1])
        self.waterfallView.setLimits(xMin=self.freq[0],xMax=self.freq[-1])
        
        self.sdrThread.sdr_tune(self.center_freq)

    def mouse_clicked(self,evt):
        self.center_freq=round(self.tmp/10e3)*10e3
        self.spinBoxFrequency.setValue(self.center_freq)

        


    def mouse_moved(self, evt):
        """Update crosshair when mouse is moved"""
        pos = evt[0]

        if self.spectrumView.sceneBoundingRect().contains(pos):
            mousePoint = self.spectrumView.plotItem.vb.mapSceneToView(pos)
            # I think i should just update the variables and set GUI values in timer thread
            self.vLine.setPos( round(mousePoint.x()/5e3)*5e3 )
            self.vLine2.setPos(round(mousePoint.x()/5e3)*5e3 )
            self.hLine.setPos( (mousePoint.y()) )
            self.tmp=mousePoint.x()
            self.lblFreq.setText( f'{round(mousePoint.x()/1e6,3)} MHz, {round(mousePoint.y(),3)}' )

    """
    self.rangeChanged = pg.SignalProxy(self.spectrumView.sigXRangeChanged, rateLimit=10, slot=self.range_changed)

    def range_changed(self,evt):
        xmin,xmax=evt[1]
    """
    

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    app.exec_()
