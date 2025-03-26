# Equivalent Width calculation on normalised spectrum

from PyQt4.QtCore import *
from PyQt4.QtGui import *

import string
import os.path
import numpy as np
import matplotlib.pyplot as plt
import scipy.stats as ss
import specdatactrl
import datarange
import xmlutil
import meanval
import exclusions
import miscutils
import ui_ewcalcdlg
import ui_ewresdlg

Plotcolours = ('black','red','green','blue','yellow','magenta','cyan')
Exclcolours = ('red','green','blue','yellow','magenta','cyan','black')

class EWResdlg(QDialog, ui_ewresdlg.Ui_ewresdlg):
    def __init__(self, parent = None):
        super(EWResdlg, self).__init__(parent)
        self.setupUi(self)

    def on_browsedir_clicked(self, b = None):
        if b is None: return
        d = QFileDialog.getExistingDirectory(self, "Select browse directory")
        if d is None: return
        self.resdir.setText(d)
        
    def on_browsefile_clicked(self, b = None):
        if b is None: return
        fname = QFileDialog.getSaveFileName(self, self.tr("Select save file"), self.resfile.text())
        if fname is None: return
        self.resfile.setText(fname)
        if len(self.resdir.text()) == 0:
            self.resdir.setText(os.path.dirname(str(fname)))       

class EWCalcDlg(QDialog, ui_ewcalcdlg.Ui_ewcalcdlg):
    
    def __init__(self, parent = None):
        super(EWCalcDlg, self).__init__(parent)
        self.setupUi(self)
        
    def initrange(self, rangefile):
        """Initialise range combo box"""
        rlist = rangefile.listranges()
        rlist.sort()
        self.peakrange.addItem("(None)", QVariant(""))
        for rnam in rlist:
            if rnam == "yrange": continue
            r = rangefile.getrange(rnam)
            self.peakrange.addItem(r.description, QVariant(rnam))

def run_ew_calc(ctrlfile, rangefile):
    """Do the business to calculate the equivalent width plots"""

    # Load up all the data (if not already)

    try:
        ctrlfile.loadfiles()
    except specdatactrl.SpecDataError as e:
        QMessageBox.warning(dlg, "Error loading files", e.args[0])
        return

    # Put up the dialog box to work out what we're doing
    
    dlg = EWCalcDlg()
    dlg.initrange(rangefile)
    
    # Loop until happy
    
    while dlg.exec_():
        selrange = dlg.peakrange.currentIndex()
        if selrange <= 0:
            QMessageBox.warning(dlg, "No range given", "You didn't give an indegrations range")
            continue
    
        halphar = rangefile.getrange(str(dlg.peakrange.itemData(selrange).toString()))
        scaling = dlg.scaling.value()
    
        skipped = 0
        elist = exclusions.Exclusions()
        datelu = dict()
    
        # Compile list of equivalent widths for each spectrum
        # Note the ones we are excluding separately
        
        for dataset in ctrlfile.datalist:
            try:
                xvalues = dataset.get_xvalues(False)
                yvalues = dataset.get_yvalues(False)
            except specdatactrl.SpecDataError as err:
                if err.args[0] == "Discounted data":
                    elist.add(dataset.modbjdate, err.args[2])
                    skipped += 1
                    continue
            har, hir = meanval.mean_value(halphar, xvalues, yvalues)
            ew = (hir - scaling * har) / har
            datelu[dataset.modbjdate] = ew
    
            # Now sort the result so we've got dates in an array with parallel ews.
    
        ds = datelu.keys()
        ds.sort()
        dates = []
        ews = []
        for d in ds:
            dates.append(d)
            ews.append(datelu[d])
    
        # Draw the histogram
        
        histfig = plt.gcf()
        histfig.canvas.set_window_title("Equivalent widths histogram")
        histews = np.array(ews)
        sexv = dlg.exclstds.value()
        if sexv != 0.0:
            lh = len(histews)
            while 1:
                hmean = np.mean(histews)
                hstd = np.std(histews)
                sel = np.abs(histews - hmean) <= sexv * hstd
                histews = histews[sel]
                nl = len(histews)
                if nl == lh: break
                lh = nl
        if dlg.gaussian.isChecked():
            plt.hist(histews, bins=dlg.histbins.value(), normed=True)
            hmean = np.mean(histews)
            hstd = np.std(histews)
            minv = np.min(histews)
            maxv = np.max(histews)
            lx = np.linspace(minv,maxv,500)
            garr = ss.norm.pdf(lx, hmean, hstd)
            plt.plot(lx, garr)
        else:
            plt.hist(histews, bins=dlg.histbins.value())
        plt.ylabel(str(dlg.histyaxis.text()))
        plt.xlabel(str(dlg.histxaxis.text()))
        plt.show()
    
        # rxarray is an array of arrays of x values for each separate day
        # ditto ryarray for y values
        
        rxarray = []
        ryarray = []
        rxvalues = []
        ryvalues = []
    
        lastdate = 1e12         # Force new date
        
        sepdays = dlg.sepdays.value()
    
        for d, v in zip(dates,ews):
            if d - lastdate > sepdays and len(rxvalues) != 0:
                # Starting new day
                rxarray.append(rxvalues)
                ryarray.append(ryvalues)
                rxvalues = []
                ryvalues = []
            rxvalues.append(d)
            ryvalues.append(v)
            lastdate = d

        # Pick up stragglers
       
        if len(rxvalues) != 0:
           rxarray.append(rxvalues)
           ryarray.append(ryvalues)
    
        colours = Plotcolours * ((len(rxarray) + len(Plotcolours) - 1) / len(Plotcolours))
        
        # Assign colours to reasons for exclusion
        
        rlist = elist.reasons()
        excolours = Exclcolours * ((len(rlist) + len(Exclcolours) - 1) / len(Exclcolours))
        rlookup = dict()
        for r, c in zip(rlist, excolours):
            rlookup[r] = c
    
        xlab = str(dlg.plotxaxis.text())
        ylab = str(dlg.plotxaxis.text())

        # Separate plots if we've asked for them and we have actually split across days
        
        sepplots = dlg.sepplot.isChecked() and len(rxarray) > 1
        
        if  sepplots:
            
            # Plot each separately, list figures in figlist
            
            figlist = []
            
            for xarr, yarr, col in zip(rxarray,ryarray,colours):
                offs = xarr[0]
                xa = np.array(xarr) - offs
                ya = np.array(yarr)
                f = plt.figure()
                figlist.append(f)
                plt.ylabel(ylab)
                plt.xlabel(xlab)
                plab = "%.1f" % xarr[0]
                plt.plot(xa,ya,col,label=plab)
                f.canvas.set_window_title("Equivalent width plot for " + plab)
                sube = elist.inrange(np.min(xarr), np.max(xarr))
                had = dict()
                for pl in sube.places():
                    xpl = pl - offs
                    reas = sube.getreason(pl)
                    creas = rlookup[reas]
                    if reas in had:
                        plt.axvline(xpl, color=creas, ls="--")
                    else:
                        had[reas] = 1
                        plt.axvline(xpl, color=creas, label=reas, ls="--")
                plt.legend()
        else:
            plotfig = plt.figure()
            plotfig.canvas.set_window_title("Equivalent width plot")
            legends = []
            lines = []
            ln = dlg.legnum.value()
            plt.ylabel(ylab)
            plt.xlabel(xlab)
            for xarr, yarr, col in zip(rxarray,ryarray,colours):
                offs = xarr[0]
                xa = np.array(xarr) - offs
                ya = np.array(yarr)
                plt.plot(xa,ya, col)
                if len(legends) < ln:
                    legends.append("%.1f" % xarr[0])
                elif  len(legends) == ln:
                    legends.append('etc...')
                sube = elist.inrange(np.min(xarr), np.max(xarr))
                for pl in sube.places():
                    xpl = pl - offs
                    reas = sube.getreason(pl)
                    creas = rlookup[reas]
                    lines.append((xpl,creas))
                plt.legend(legends)
            for xpl, creas in lines:
                plt.axvline(xpl, color=creas, ls="--")
        plt.show()
    
        resdlg = EWResdlg()
        
        # Loop until we get a sensible answer or he gives up

        while resdlg.exec_():
            resfile = string.strip(str(resdlg.resfile.text()))
            resdir = string.strip(str(resdlg.resdir.text()))
            histfile = string.strip(str(resdlg.histfile.text()))
            plotfile = string.strip(str(resdlg.plotfile.text()))
            if len(resdir) == 0 or len(histfile) == 0 or len(plotfile) == 0:
                QMessageBox.warning(resdlg, "Missing file names", "Please complete all directory and file names")
                continue
            if not miscutils.hassuffix(histfile, '.png'): histfile += '.png'
            histpath = os.path.join(resdir, histfile)
            plt.figure(histfig.number)
            plt.savefig(histpath)
            if sepplots:
                for n,f in enumerate(figlist):
                    plt.figure(f.number)
                    fn = "%s_%d.png" % (plotfile, n+1)
                    ppath = os.path.join(resdir, fn)
                    plt.savefig(ppath)
            else:
                plt.figure(plotfig.number)
                if not miscutils.hassuffix(plotfile, '.png'): plotfile += '.png'
                ppath = os.path.join(resdir, plotfile)
                plt.savefig(ppath)
            
            if len(resfile) != 0:
                nparr = np.array([dates, ews]).transpose()
                np.savetxt(resfile, nparr)
            break
    
        plt.figure(histfig.number)
        plt.close()
        if sepplots:
            for f in figlist:
                plt.figure(f.number)
                plt.close()
        else:
            plt.figure(plotfig.number)
            plt.close()
    # End of while loop for main dialog
    # End of func
