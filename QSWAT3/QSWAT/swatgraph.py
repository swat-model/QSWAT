'''
Created on Dec 30, 2015

@author: Chris George
/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 '''
try:
    from qgis.PyQt.QtCore import Qt, QObject, QSettings
    #from qgis.PyQt.QtGui import *  # @UnusedWildImport
    from qgis.PyQt.QtWidgets import QApplication, QFileDialog, QMessageBox, QTableWidgetItem
except:
    from PyQt5.QtCore import Qt, QObject, QSettings
    from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox, QTableWidgetItem    

import sys
import os
import csv
from datetime import datetime, timedelta
import math
import numpy as np
from numpy.polynomial import Polynomial
# import seaborn as sns
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1.axes_divider import HBoxDivider
import mpl_toolkits.axes_grid1.axes_size as Size
# from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import (
    FigureCanvasQTAgg as FigureCanvas,
    NavigationToolbar2QT as NavigationToolbar)
import traceback

try:
    from .graphdialog import GraphDialog  # @UnresolvedImport @UnusedImport
except:
    # stand alone version
    from graphdialog1 import GraphDialog  # @UnresolvedImport @Reimport

# basic matplotlib colours
colours = ['b', 'g', 'r', 'm', 'y', 'c', 'k'] 

class SWATGraph(QObject):
    """Display SWAT result data as line graph, bar chart, flow duration curve, scatter plot or box plot."""
    
    def __init__(self, csvFile, plotType):
        """Initialise class variables."""
        QObject.__init__(self)
        self._dlg = GraphDialog()
        self._dlg.setWindowFlags(self._dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        ## csv file of results
        self.csvFile = csvFile
        ## Plot type: 1 for line graph or bar chart, 2 flor flow duration curve, 3 for scatter plot, 4 for box plot
        self.plotType = plotType
        ## canvas for displaying matplotlib figure
        self.canvas = None
        ## matplotlib tool bar
        self.toolbar = None
        ## matplotlib axes
        self.ax1 = None
        ## matplotlib figure
        self.fig = None
        
    def run(self):
        """Initialise form and run on initial csv file."""
        self._dlg.plotType.clear()
        self._dlg.plotType.addItem('Line graph/bar chart')
        self._dlg.plotType.addItem('Flow/load duration curve')
        self._dlg.plotType.addItem('Scatter plot')
        self._dlg.plotType.addItem('Box plot')
        if self.plotType in range(1,5):
            self._dlg.plotType.setCurrentIndex(self.plotType - 1)
        if self.plotType == 3:  # scatter plot
            # increase the height from default 600 to 900
            size = self._dlg.size()
            newHeight = int(size.height() * 1.5)
            self._dlg.resize(size.width(), newHeight)
        self._dlg.chartLabel.setVisible(self.plotType==1)
        self._dlg.lineOrBar.setVisible(self.plotType==1)
        self._dlg.lineOrBar.clear()
        self._dlg.lineOrBar.addItem('Line graph')
        self._dlg.lineOrBar.addItem('Bar chart')
        self._dlg.lineOrBar.setCurrentIndex(0)
        self._dlg.plotType.currentIndexChanged.connect(self.updateGraph)
        self._dlg.newFile.clicked.connect(self.getCsv)
        self._dlg.updateButton.clicked.connect(self.updateGraph)
        self._dlg.closeForm.clicked.connect(self.closeFun)
        self.readCsv()
        self._dlg.exec_()
        
    def addmpl(self):
        """Add graph defined in self.fig."""
        self.canvas = FigureCanvas(self.fig)
        # graphvl is the QVBoxLayout instance added to the graph widget.
        # Needed to make self.fig expand to fill graph widget.
        self._dlg.graphvl.addWidget(self.canvas)
        self.canvas.draw()
        self.toolbar = NavigationToolbar(self.canvas, 
                self._dlg.graph, coordinates=True)
        self._dlg.graphvl.addWidget(self.toolbar)
        
    def rmmpl(self):
        """Remove current graph if any."""
        try:
            self._dlg.graphvl.removeWidget(self.canvas)
            self.canvas.close()
            self._dlg.graphvl.removeWidget(self.toolbar)
            self.toolbar.close()
            self.ax1 = None
            return
        except Exception:
            # no problem = may not have been a graph
            return
        
    @staticmethod
    def trans(msg):
        """Translate message."""
        return QApplication.translate("SWATGraph", msg)
        
    @staticmethod
    def error(msg):
        """Report msg as an error."""
        msgbox = QMessageBox()
        msgbox.setWindowTitle('SWATGraph')
        msgbox.setIcon(QMessageBox.Critical)
        msgbox.setText(SWATGraph.trans(msg))
        msgbox.exec_()
        return
    
    def getCsv(self):
        """Ask user for csv file."""
        settings = QSettings()
        if settings.contains('/QSWAT/LastInputPath'):
            path = settings.value('/QSWAT/LastInputPath')
        else:
            path = ''
        filtr = self.trans('CSV files (*.csv);;All files (*.*)')
        csvFile, _ = QFileDialog.getOpenFileName(None, 'Open csv file', path, filtr)
        if csvFile is not None and csvFile != '':
            settings.setValue('/QSWAT/LastInputPath', os.path.dirname(csvFile))
            self.csvFile = csvFile
            self.readCsv()
        
    def readCsv(self):
        """Read current csv file (if any)."""
        # csvFile may be none if run from command line
        if not self.csvFile or self.csvFile == '':
            return
        if not os.path.exists(self.csvFile):
            self.error('Error: Cannot find csv file {0}'.format(self.csvFile))
            return
        """Read csv file into table; create statistics (coefficients); draw graph."""
        # clear graph
        self.rmmpl()
        # clear table
        self._dlg.table.clear()
        for i in range(self._dlg.table.columnCount()-1, -1, -1):
            self._dlg.table.removeColumn(i)
        self._dlg.table.setColumnCount(0)
        self._dlg.table.setRowCount(0)
        row = 0
        numCols = 0
        with open(self.csvFile, 'r', newline='') as csvFil:
            reader = csv.reader(csvFil)
            for line in reader:
                try:
                    # use headers in first line
                    if row == 0:
                        numCols = len(line)
                        for i in range(numCols):
                            self._dlg.table.insertColumn(i)
                        self._dlg.table.setHorizontalHeaderLabels(line)
                    else:
                        self._dlg.table.insertRow(row-1)
                        for i in range(numCols):
                            try:
                                val = line[i].strip()
                            except Exception:
                                self.error('Error: could not read file {0} at line {1} column {2}: {3}'.format(self.csvFile, row+1, i+1, traceback.format_exc()))
                                return
                            item = QTableWidgetItem(val)
                            self._dlg.table.setItem(row-1, i, item)
                    row = row + 1
                except Exception:
                    self.error('Error: could not read file {0} at line {1}: {2}'.format(self.csvFile, row+1, traceback.format_exc()))
                    return
        if row == 1:
            self.error('There is no data to plot in {0}'.format(self.csvFile))
            return
        # columns are too narrow for headings
        self._dlg.table.resizeColumnsToContents()
        # rows are too widely spaced vertically
        self._dlg.table.resizeRowsToContents()
        self.writeStats()
        self.updateGraph()
        
    @staticmethod
    def makeFloat(s):
        """Parse string s as float and return; return nan on failure."""
        try:
            return float(s)
        except Exception:
            return float('nan')
        
    def updateGraph(self):
        """Redraw graph according to current plotType and lineOrBar setting."""
        self.plotType = self._dlg.plotType.currentIndex() + 1
        self._dlg.chartLabel.setVisible(self.plotType==1)
        self._dlg.lineOrBar.setVisible(self.plotType==1)
        style = 'bar' if self._dlg.lineOrBar.currentText() == 'Bar chart' else 'line'
        self.drawGraph(style)
        
    @staticmethod
    def shiftDates(dates, shift):
        """Add shift (number of days) to each date in dates."""
        delta = timedelta(days=shift)
        return [x + delta for x in dates]
    
    @staticmethod
    def getDateFormat(date):
        """
        Return date strptime format string from example date, plus basic width for drawing bar charts.
    
        Basic width is how matplotlib divides the date axis: number of days in the time unit
        Assumes date has one of 3 formats:
        yyyy: annual: return %Y and 12
        yyyy/m or yyyy/mm: monthly: return %Y/%m and 30
        yyyyddd: daily: return %Y%j and 24
        """
        if date.find('/') > 0:
            return '%Y/%m', 30
        length = len(date)
        if length == 4:
            return '%Y', 365
        if length == 7:
            return '%Y%j', 1
        SWATGraph.error('Cannot parse date {0}'.format(date))
        return '', 1
    
        
    def drawGraph(self, style):
        """Draw graph as line or bar chart according to style."""
        # preserve title and xlabel if they exist
        # in order to replace them when updating graph
        try:
            title = self.ax1.get_title()
        except Exception:
            title = ''
        self.rmmpl()
        self.fig, self.ax1 = plt.subplots()
        self.fig.subplots_adjust(left=0.05)
        self.fig.subplots_adjust(right=0.95)
        if self.plotType not in {3,4} : # no legend with scatter or box plot, otherwise make space below
            self.fig.subplots_adjust(bottom=0.3)
        tkw = dict(size=4, width=1.5)
        plots = []
        if self.plotType == 1:  # line graph or bar chart
            colToTwin, twins = self.makeYAxes()
            #print('colToTwin: {0}'.format(colToTwin))
            #print('Twins: {0}'.format(twins.keys()))
            numPlots = self._dlg.table.columnCount() - 1
            rng = range(self._dlg.table.rowCount())
            fmt, widthBase = self.getDateFormat(str(self._dlg.table.item(0, 0).text()).strip())
            if fmt == '':
                # could not parse
                return
            xVals = [datetime.strptime(str(self._dlg.table.item(i, 0).text()).strip(), fmt) for i in rng]
            for col in range(1, numPlots+1):
                yVals = [self.makeFloat(self._dlg.table.item(i, col).text()) for i in rng]
                colour = self.getColour(col)
                h = self._dlg.table.horizontalHeaderItem(col).text()
                indx = colToTwin.get(col, -1)
                if indx < 0:  # axis on left
                    if not 'observed' in h:
                        self.ax1.set_ylabel(h.split('-')[3])
                        self.ax1.yaxis.label.set_color(colour)
                        self.ax1.tick_params(axis='y', colors=colour, **tkw)
                        self.ax1.tick_params(axis='x', **tkw)
                else:
                    twins[indx].set_ylabel(h.split('-')[3])
                    twins[indx].yaxis.label.set_color(colour)
                    twins[indx].tick_params(axis='y', colors=colour, **tkw)
                if style == 'line':
                    if indx < 0:  # axis on left
                        p, = self.ax1.plot(xVals, yVals, colour, label=h)
                    else:
                        p, = twins[indx].plot(xVals, yVals, colour, label=h)
                        #print('Ylim for index {0}: {1}'.format(indx, twins[indx].get_ylim()))
                else:
                    # width of bars in days.  
                    # adding 1 to divisor gives space of size width between each date's group
                    width = float(widthBase) / (numPlots+1)
                    mid = numPlots / 2
                    shift = width * (col - 1 - mid)
                    xValsShifted = xVals if shift == 0 else self.shiftDates(xVals, shift)
                    if indx < 0:  # axis on left
                        p = self.ax1.bar(xValsShifted, yVals, width, color=colour, linewidth=0, label=h)
                    else:
                        p = twins[indx].bar(xValsShifted, yVals, width, color=colour, linewidth=0, label=h)
                plots.append(p)
        elif self.plotType == 2:  # flow duration curve
            colToTwin, twins = self.makeYAxes()
            numPlots = self._dlg.table.columnCount() - 1
            timeLen = self._dlg.table.rowCount()
            rng = range(timeLen)
            exceedence = np.arange(1.0, timeLen + 1) / timeLen
            exceedence *= 100
            for col in range(1, numPlots+1):
                yVals = sorted([self.makeFloat(self._dlg.table.item(i, col).text()) for i in rng], reverse=True)
                colour = self.getColour(col)
                h = self._dlg.table.horizontalHeaderItem(col).text()
                indx = colToTwin.get(col, -1)
                if indx < 0:  # axis on left
                    p, = self.ax1.plot(exceedence, yVals, colour, label=h)
                    if not 'observed' in h:
                        self.ax1.set_ylabel(h.split('-')[3])
                        self.ax1.yaxis.label.set_color(colour)
                        self.ax1.tick_params(axis='y', colors=colour, **tkw)
                        self.ax1.tick_params(axis='x', **tkw)
                else:
                    p, = twins[indx].plot(exceedence, yVals, colour, label=h)
                    twins[indx].set_ylabel(h.split('-')[3])
                    twins[indx].yaxis.label.set_color(colour)
                    twins[indx].tick_params(axis='y', colors=colour, **tkw)
                plots.append(p)
        elif self.plotType == 3:  # scatter plot
            rng = range(self._dlg.table.rowCount())
            xVals = np.array([self.makeFloat(self._dlg.table.item(i, 1).text()) for i in rng])
            yVals = np.array([self.makeFloat(self._dlg.table.item(i, 2).text()) for i in rng])
            self.ax1.scatter(xVals, yVals, marker=".")
            # Fit linear regression via least squares with numpy.polyfit
            # It returns intercept (a) and slope (b)
            # deg=1 means linear fit (i.e. polynomial of degree 1)
            # use convert to retain unscaled domain
            a, b = Polynomial.fit(xVals, yVals, deg=1).convert().coef
            # Create sequence of 2 numbers from min to max: only need 2 for straight line
            xseq = np.linspace(np.nanmin(xVals), np.nanmax(xVals), num=2)
            #print('Minimum {0:.2F} and maximum {1:.2F}; intercept {2:.2F}, slope {3:.2F}'.format(np.amin(xVals), np.amax(xVals), a, b))
            # Plot regression line
            self.ax1.plot(xseq, a + b * xseq, color="k", lw=1);
        elif self.plotType == 4:  # box plot
            variables, colToIndex, count = self.organiseBoxSubplots()
            #print('variables: {0}'.format(variables))
            #print('colToIndex: {0}'.format(colToIndex))
            #print('count: {0}'.format(count))
            numPlots = len(count)
            rng = range(self._dlg.table.rowCount())
            gs_kw = dict(width_ratios=[count[index] for index in count], height_ratios=[1])
            self.fig, axs = plt.subplots(1, numPlots, gridspec_kw=gs_kw)
            self.fig.subplots_adjust(left=0.05)
            self.fig.subplots_adjust(right=0.95)
            llDict = dict()  # list of list of values for each index
            labelsDict = dict()  # list of labels for each index
            for col in range(1, self._dlg.table.columnCount()):
                if col not in colToIndex:
                    # allow for observed in first column error
                    continue
                index = colToIndex[col]
                vals = [self.makeFloat(self._dlg.table.item(i, col).text()) for i in rng]
                val2 = sorted([v for v in vals if not math.isnan(v)])
                minn = val2[0]
                maxx = val2[-1]
                median = SWATGraph.percentile(val2, 0.5)
                Q1 = SWATGraph.percentile(val2, 0.25)
                Q3 = SWATGraph.percentile(val2, 0.75)
                msg = ('{0}: min: {1:.2F}, max: {2:.2F}, median: {3:.2F}, Q1: {4:.2F}, Q3: {5:.2F}'.format(self._dlg.table.horizontalHeaderItem(col).text(), minn, maxx, median, Q1, Q3))
                self._dlg.coeffs.append(SWATGraph.trans(msg))
                ll = llDict.setdefault(index, []) 
                ll.append(vals)
                labels = labelsDict.setdefault(index, [])
                labels.append(self._dlg.table.horizontalHeaderItem(col).text())
            for indx, ll in llDict.items():
                # convert inputs to numpy 2D array
                npArray = np.asarray(ll).T
                # axs is not an array if only 1 subplot
                ax = axs[indx] if len(count) > 1 else axs
                p = ax.boxplot(npArray, labels=labelsDict[indx])
                ax.grid(True)
                #SWATGraph.colourBoxplot(p, self.getColour(indx))
            # cannot get this to give other than a very spread layout with narrow boxplots
            #plt.tight_layout(w_pad=-0.5)
        # reinstate title and labels
        if title != '':
            self.ax1.set_title(title)
        if self.plotType == 1:  # line or bar
            self.ax1.set_xlabel('Date')
        elif self.plotType == 2:  # flow duration
            self.ax1.set_xlabel('Exceedance (%)')
        elif self.plotType == 3:  # scatter plot
            self.ax1.set_xlabel(self._dlg.table.horizontalHeaderItem(1).text())
            self.ax1.set_ylabel(self._dlg.table.horizontalHeaderItem(2).text())
        if self.plotType != 4:
            self.ax1.grid(True)
        if self.plotType in {1,2}:  # line or bar, or flow duration
            legendCols = min(7, self._dlg.table.columnCount() - 1)
            self.ax1.legend(handles=plots, bbox_to_anchor=(1.0 + 0.07 * len(twins), -0.3), ncol=legendCols, fontsize='small')
        self.addmpl()
        
    def makeYAxes(self):
        """Make extra y-axes on right if more than one variable is used."""
        variables = []
        colToTwin = dict()  # map of column number in table to twin index used for extra y-axis
        twins = dict()  # map of twin index to twinx
        for col in range(1, self._dlg.table.columnCount()):
            h = self._dlg.table.horizontalHeaderItem(col).text()
            if 'observed' in h:
                # assume matches previous variable
                continue
            var = h.split('-')[3]
            try:
                indx = variables.index(var)
                if indx > 0:  # indx zero means we use first y-axis, on left
                    colToTwin[col] = indx 
            except:  # var not in variables
                variables.append(var)
                if len(variables) > 1:
                    colToTwin[col] = len(variables) - 1
        if len(variables) > 1:
            numAxes = len(variables) - 1
            adj = 0.95 - 0.05 * numAxes
            #print('Adjustment: {0}'.format(adj))
            self.fig.subplots_adjust(right=adj)
            for i in range(1, numAxes + 1):
                twins[i] = self.ax1.twinx()
                if i > 1:
                    # offset the second and later right spines
                    # spines.right syntax only in matplotlib >= 3.4.0
                    twins[i].spines['right'].set_position(("axes", 1 + 0.1 * (i - 1)))
                twins[i].set_ylabel(var)
        return colToTwin, twins
    
    def organiseBoxSubplots(self):
        """Make a collection of indexes of box subplots by collecting boxplots sharing the same variable."""
        variables = dict()  # map of variable name to index
        colToIndex = dict()  # map of column number to index
        count = dict()  # count of boxes for each index
        nextIndex = 0
        for col in range(1, self._dlg.table.columnCount()):
            h = self._dlg.table.horizontalHeaderItem(col).text()
            if 'observed' in h:
                # assume it belongs with previous column in table
                if col == 1:
                    SWATGraph.error('Observed values must immediately follow a column assumed to have the same type of values.  Ignoring the observed column.')
                    continue
                else:
                    index = colToIndex[col - 1]
                    colToIndex[col] = index
                    variables['observed'] = index
                    count[index] += 1
            else:
                var = h.split('-')[3]
                index = variables.get(var, -1)
                if index < 0:
                    variables[var] = nextIndex
                    colToIndex[col] = nextIndex
                    count[nextIndex] = 1
                    nextIndex += 1
                else:
                    colToIndex[col] = index
                    count[index] += 1
        return variables, colToIndex, count
                
    @staticmethod
    def percentile(N, percent):
        """
        Find the percentile of a sorted list of values.
    
        N - is a list of values. Note N MUST BE already sorted.
        percent - a float value from 0.0 to 1.0.
    
        return - the percentile of the values
        """
        if not N:
            return None
        k = (len(N)-1) * percent
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return N[int(k)]
        d0 = N[int(f)] * (c-k)
        d1 = N[int(c)] * (k-f)
        return d0+d1
        
    @staticmethod
    def make_heights_equal(fig, rect, ax1, ax2, pad):
        # pad in inches
        divider = HBoxDivider(
            fig, rect,
            horizontal=[Size.AxesX(ax1), Size.Fixed(pad), Size.AxesX(ax2)],
            vertical=[Size.AxesY(ax1), Size.Scaled(1), Size.AxesY(ax2)])
        ax1.set_axes_locator(divider.new_locator(0))
        ax2.set_axes_locator(divider.new_locator(2))

         
    def getColour(self, col):
        """Colour to use for coloumn in table."""
        # column indexess run 1 to n, since first is date
        # cannot imagine more than 7 (numColours), but use shades of grey if necessary
        numColours = len(colours)         
        return colours[col-1] if col <= len(colours) else str(float((col - numColours)/(self._dlg.table.columnCount() - numColours)))
    
    @staticmethod 
    def colourBoxplot(p, colour):
        """Colour component lines of boxplot."""
        for l in p['boxes']:
            l.set(color=colour)
        for l in p['medians']:
            l.set(color=colour)
        for l in p['whiskers']:
            l.set(color=colour)
        for l in p['caps']:
            l.set(color=colour)
    
    def closeFun(self):
        """Close dialog."""
        self._dlg.close()
        
    def writeStats(self):
        """Write Pearson and Nash coefficients."""
        numCols = self._dlg.table.columnCount()
        numRows = self._dlg.table.rowCount()
        self._dlg.coeffs.clear()
        for i in range(1, numCols):
            for j in range(i+1, numCols):
                self.pearson(i, j, numRows)
        for i in range(1, numCols):
            for j in range(i+1, numCols):
                self.nash(i, j, numRows)
        
    def multiSums(self, idx1, idx2, N):
        """Return various sums for two series, only including points where both are numbers, plus count of such values."""
        s1 = 0
        s2 = 0
        s11 = 0
        s22 = 0
        s12 = 0
        count = 0
        for i in range(N):
            val1 = self.makeFloat(self._dlg.table.item(i, idx1).text())
            val2 = self.makeFloat(self._dlg.table.item(i, idx2).text())
            # ignore missing values
            if not (math.isnan(val1) or math.isnan(val2)):
                s1 += val1
                s2 += val2
                s11 += val1 * val1
                s22 += val2 * val2
                s12 += val1 * val2
                count = count + 1
        return (s1, s2, s11, s22, s12, count)
        
        
    def sum1(self, idx1, idx2, N):
        """Return sum for series1, only including points where both are numbers, plus count of such values.""" 
        s1 = 0
        count = 0
        for i in range(N):
            val1 = self.makeFloat(self._dlg.table.item(i, idx1).text())
            val2 = self.makeFloat(self._dlg.table.item(i, idx2).text())
            # ignore missing values
            if not (math.isnan(val1) or math.isnan(val2)):
                s1 += val1
                count = count + 1
        return (s1, count)
        
    def pearson(self, idx1, idx2, N):
        """Calculate and display R2 and Pearson correlation coefficients for pair of plots."""
        s1, s2, s11, s22, s12, count = self.multiSums(idx1, idx2, N)
        if count == 0: return
        sqx = (count * s11) - (s1 * s1)
        sqy = (count * s22) - (s2 * s2)
        sxy = (count * s12) - (s1 * s2)
        deno = math.sqrt(sqx * sqy)
        if deno == 0: return
        rho = sxy / deno
        if count < N:
            extra = ' (using {0!s} of {1!s} values)'.format(count , N)
        else:
            extra = ''
        msg = 'Series1: ' + self._dlg.table.horizontalHeaderItem(idx1).text() + \
            '  Series2: ' + self._dlg.table.horizontalHeaderItem(idx2).text() + '  R2 = {0:.2f} (Pearson Correlation Coefficient = {1:.2f}){2}'.format(rho * rho, rho, extra)
        self._dlg.coeffs.append(SWATGraph.trans(msg))

    def nash(self, idx1, idx2, N):
        """Calculate and display Nash-Sutcliffe efficiency coefficients for pair of plots."""
        s1, count = self.sum1(idx1, idx2, N)
        if count == 0: return
        mean = s1 / count
        num = 0
        deno = 0
        for i in range(N):
            val1 = self.makeFloat(self._dlg.table.item(i, idx1).text())
            val2 = self.makeFloat(self._dlg.table.item(i, idx2).text())
            # ignore missing values
            if not (math.isnan(val1) or math.isnan(val2)):
                diff12 = val1 - val2
                diff1m = val1 - mean
                num += diff12 * diff12
                deno += diff1m * diff1m
        if deno == 0: return
        result = 1 - (num / deno)
        if count < N:
            extra = ' (using {0!s} of {1!s} values)'.format(count , N)
        else:
            extra = ''
        msg = 'Series1: ' + self._dlg.table.horizontalHeaderItem(idx1).text() + \
            '  Series2: ' + self._dlg.table.horizontalHeaderItem(idx2).text() + '   Nash-Sutcliffe Efficiency Coefficient = {0:.2f}{1}'.format(result, extra)
        self._dlg.coeffs.append(SWATGraph.trans(msg))

if __name__ == '__main__':
    ## QApplication object needed 
    app = QApplication(sys.argv)
    if len(sys.argv) > 1:
        ## csv file argument
        csvFile = sys.argv[1]
    else:
        csvFile = None
    if len(sys.argv) > 2:
        ## plot type
        plotType = int(sys.argv[2])
    else:
        plotType = 1 # line graph or bar chart
    ## main program
    main = SWATGraph(csvFile, plotType)
    main.run()
    
