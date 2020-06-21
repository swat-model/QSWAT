# -*- coding: utf-8 -*-
'''
/***************************************************************************
 QSWAT
                                 A QGIS plugin
 Create SWAT inputs
                              -------------------
        begin                : 2014-07-18
        copyright            : (C) 2014 by Chris George
        email                : cgeorge@mcmaster.ca
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
'''
# Import the PyQt and QGIS libraries
from PyQt5.QtCore import * # @UnusedWildImport
from PyQt5.QtGui import * # @UnusedWildImport
from PyQt5.QtWidgets import * # @UnusedWildImport
from qgis.core import * # @UnusedWildImport
import os.path

# Import the code for the dialog
try:
    from .parametersdialog import ParametersDialog  # @UnresolvedImport
    from .QSWATUtils import QSWATUtils  # @UnresolvedImport
except ImportError:
    # for convert from Arc and to plus
    from parametersdialog import ParametersDialog
    from QSWATUtils import QSWATUtils

class Parameters:
    
    """Collect QSWAT parameters (location of SWAT editor and MPI) from user and save."""
    
    # TODO: the .exe file names and directories need changing when running on Linux
    _SWATEDITOR = 'SwatEditor.exe'
    _SWATEDITORDEFAULTDIR = 'C:\\SWAT\\SWATEditor'
    #TODO: interrogate editor for this
    _SWATEDITORVERSION = '2012.10.19'
    _MPIEXEC = 'mpiexec.exe'
    _MPIEXECDEFAULTDIR = 'C:\\Program Files\\Microsoft MPI\\Bin'
    _TAUDEMDIR = 'TauDEM5Bin'
    _TAUDEMHELP = 'TauDEM_Tools.chm'
    _SWATGRAPH = 'SWATGraph'
    _DBDIR = 'Databases'
    _DBPROJ = 'QSWATProj2012.mdb'
    # TODO: the reference database is the official one with crop table extended for global landuses
    _DBREF = 'QSWATRef2012.mdb'
    # TODO: this is a later driver; don't know how common it is
    # _ACCESSSTRING = 'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ='
    _ACCESSSTRING = 'DRIVER={Microsoft Access Driver (*.mdb)};DBQ='
    _TABLESOUT = 'TablesOut'
    _ANIMATION = 'Animation'
    _PNG = 'Png'
    _STILLBASE = 'still.gif'
    _STILLJPG = 'still.jpg'
    _STILLPNG = 'still.png'
    _TXTINOUT = 'TxtInOut'
    _SSURGODB = 'SWAT_US_SSURGO_Soils.mdb'
    _SSURGOWater = 377988
    _USSOILDB = 'SWAT_US_Soils.mdb'
    _CIO = 'file.cio'
    _OUTPUTDB = 'SWATOutput.mdb'
    _SUBS = 'subs'
    _RIVS = 'rivs'
    _HRUS = 'hrus'
    _SUBS1 = 'subs1'
    _RIV1 = 'riv1'
    _HRU0 = 'hru0'
    _HRUS1 = 'hrus1'
    _HRUS2 = 'hrus2'
    _HRUSRASTER = 'hrus.tif'
    _HRUSCSV = 'hrus.csv'
    
    _TOPOREPORT = 'TopoRep.txt'
    _TOPOITEM = 'Elevation'
    _BASINREPORT = 'LanduseSoilSlopeRepSwat.txt'
    _BASINITEM = 'Landuse and Soil'
    _HRUSREPORT = 'HruLanduseSoilSlopeRepSwat.txt'
    _ARCHRUSREPORT = 'HRULandUseSoilsReport.txt'
    _ARCBASINREPORT = 'LandUseSoilsReport.txt'
    _HRUSITEM = 'HRUs'
    
    _USECSV = 'Use csv file'
    
    _LANDUSE = 'LANDUSE'
    _SOIL = 'SOIL'
    _SLOPEBAND = 'SLOPE_BAND'
    _AREA = 'AREA (ha)'
    _PERCENT = '%SUBBASIN'
    
    _SQKM = 'sq. km'
    _HECTARES = 'hectares'
    _SQMETRES = 'sq. metres'
    _SQMILES = 'sq. miles'
    _ACRES = 'acres'
    _SQFEET = 'sq. feet'
    _METRES = 'metres'
    _FEET = 'feet'
    _CM = 'centimetres'
    _MM = 'millimetres'
    _INCHES = 'inches'
    _YARDS = 'yards'
    _DEGREES = 'degrees'
    _UNKNOWN = 'unknown'
    _FEETTOMETRES = 0.3048
    _CMTOMETRES = 0.01
    _MMTOMETRES = 0.001
    _INCHESTOMETRES = 0.0254
    _YARDSTOMETRES = 0.91441
    _SQMILESTOSQMETRES = 2589988.1
    _ACRESTOSQMETRES = 4046.8564
    _SQMETRESTOSQFEET = 10.763910
    
    ## maximum number of features for adding Reach and Watershed table data to riv1 and subs1 files
    _RIV1SUBS1MAX = 1000
    
    ## nearness threshold: proportion of size of DEM cell used to determine if two stream points should be considered to join
    # too large a threshold and very short stream segments can apparently be circular
    # too small and connected stream segments can appear to be disconnected
    _NEARNESSTHRESHOLD = 0.1
    
    # landuses for which we use just one SSURGO soil and where we make the slope at most _WATERMAXSLOPE 
    _WATERLANDUSES = {'WATR', 'WETN', 'WETF'}
    _WATERMAXSLOPE = 0.005
    
    def __init__(self, gv):
        """Initialise class variables."""
        
        settings = QSettings()
        ## SWAT Editor directory
        self.SWATEditorDir = settings.value('/QSWAT/SWATEditorDir', Parameters._SWATEDITORDEFAULTDIR)
        ## mpiexec directory
        self.mpiexecDir = settings.value('/QSWAT/mpiexecDir', Parameters._MPIEXECDEFAULTDIR)
        ## number of MPI processes
        self.numProcesses = settings.value('/QSWAT/NumProcesses', '')
        self._gv = gv
        self._dlg = ParametersDialog()
        self._dlg.setWindowFlags(self._dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        if self._gv:
            self._dlg.move(self._gv.parametersPos)
            ## flag showing if batch run
            self.isBatch = self._gv.isBatch
        else:
            self.isBatch = False
        
    def run(self):
        """Run the form."""
        self._dlg.checkUseMPI.stateChanged.connect(self.changeUseMPI)
        if os.path.isdir(self.mpiexecDir):
            self._dlg.checkUseMPI.setChecked(True)
        else:
            self._dlg.checkUseMPI.setChecked(False)
        self._dlg.MPIBox.setText(self.mpiexecDir)
        self._dlg.editorBox.setText(self.SWATEditorDir)
        self._dlg.editorButton.clicked.connect(self.chooseEditorDir)
        self._dlg.MPIButton.clicked.connect(self.chooseMPIDir)
        self._dlg.cancelButton.clicked.connect(self._dlg.close)
        self._dlg.saveButton.clicked.connect(self.save)
        self._dlg.exec_()
        if self._gv:
            self._gv.parametersPos = self._dlg.pos()
        
    def changeUseMPI(self):
        """Enable form to allow MPI setting."""
        if self._dlg.checkUseMPI.isChecked():
            self._dlg.MPIBox.setEnabled(True)
            self._dlg.MPIButton.setEnabled(True)
            self._dlg.MPILabel.setEnabled(True)
        else:
            self._dlg.MPIBox.setEnabled(False)
            self._dlg.MPIButton.setEnabled(False)
            self._dlg.MPILabel.setEnabled(False)
        
    def save(self):
        """Save parameters and close form."""
        SWATEditorDir = self._dlg.editorBox.text()
        if SWATEditorDir == '' or not os.path.isdir(SWATEditorDir):
            QSWATUtils.error('Please select the SWAT editor directory', self.isBatch)
            return
        editor = Parameters._SWATEDITOR
        SWATEditorPath = QSWATUtils.join(SWATEditorDir, editor)
        if not os.path.exists(SWATEditorPath):
            QSWATUtils.error('Cannot find the SWAT editor {0}'.format(SWATEditorPath), self.isBatch)
            return
        dbProjTemplate =  QSWATUtils.join(QSWATUtils.join(SWATEditorDir, Parameters._DBDIR), Parameters._DBPROJ)
        if not os.path.exists(dbProjTemplate):
            QSWATUtils.error('Cannot find the default project database {0}'.format(dbProjTemplate), self.isBatch)
            return
        dbRefTemplate =  QSWATUtils.join(QSWATUtils.join(SWATEditorDir, Parameters._DBDIR), Parameters._DBREF)
        if not os.path.exists(dbRefTemplate):
            QSWATUtils.error('Cannot find the SWAT parameter database {0}'.format(dbRefTemplate), self.isBatch)
            return
        TauDEMDir = QSWATUtils.join(SWATEditorDir, Parameters._TAUDEMDIR)
        if not os.path.isdir(TauDEMDir):
            QSWATUtils.error('Cannot find the TauDEM directory {0}'.format(TauDEMDir), self.isBatch)
            return   
        if self._dlg.checkUseMPI.isChecked():
            mpiexecDir = self._dlg.MPIBox.text()
            if mpiexecDir == '' or not os.path.isdir(mpiexecDir):
                QSWATUtils.error('Please select the MPI bin directory', self.isBatch)
                return
            mpiexec = Parameters._MPIEXEC
            mpiexecPath = QSWATUtils.join(mpiexecDir, mpiexec)
            if not os.path.exists(mpiexecPath):
                QSWATUtils.error('Cannot find mpiexec program {0}'.format(mpiexecPath), self.isBatch)
                return
        # no problems - save parameters
        if self._gv:
            self._gv.dbProjTemplate = dbProjTemplate
            self._gv.dbRefTemplate = dbRefTemplate
            self._gv.TauDEMDir = TauDEMDir
            self._gv.mpiexecPath = mpiexecPath if self._dlg.checkUseMPI.isChecked() else ''
            self._gv.SWATEditorPath = SWATEditorPath
        settings = QSettings()
        settings.setValue('/QSWAT/SWATEditorDir', SWATEditorDir)
        if self._dlg.checkUseMPI.isChecked():
            settings.setValue('/QSWAT/mpiexecDir', mpiexecDir)
            if self.numProcesses == '': # no previous setting
                settings.setValue('/QSWAT/NumProcesses', '8')
        else:
            if self.numProcesses == '': # no previous setting
                settings.setValue('/QSWAT/NumProcesses', '0')
            self.numProcesses = '0'
        self._dlg.close()
            
    def chooseEditorDir(self):
        """Choose SWAT Editor directory."""
        title = QSWATUtils.trans('Select SWAT Editor directory')
        if self._dlg.editorBox.text() != '':
            startDir = os.path.split(self._dlg.editorBox.text())[0]
        elif os.path.isdir(self.SWATEditorDir):
            startDir = os.path.split(self.SWATEditorDir)[0]
        else:
            startDir = None
        dlg = QFileDialog(None, title)
        if startDir:
            dlg.setDirectory(startDir)
        dlg.setFileMode(QFileDialog.Directory)
        if dlg.exec_():
            dirs = dlg.selectedFiles()
            SWATEditorDir = dirs[0]
            self._dlg.editorBox.setText(SWATEditorDir)
            self.SWATEditorDir = SWATEditorDir
            
    def chooseMPIDir(self):
        """Choose MPI directory."""
        title = QSWATUtils.trans('Select MPI bin directory')
        if self._dlg.MPIBox.text() != '':
            startDir = os.path.split(self._dlg.MPIBox.text())[0]
        elif os.path.isdir(self.mpiexecDir):
            startDir = os.path.split(self.mpiexecDir)[0]
        else:
            startDir = None
        dlg = QFileDialog(None, title)
        if startDir:
            dlg.setDirectory(startDir)
        dlg.setFileMode(QFileDialog.Directory)
        if dlg.exec_():
            dirs = dlg.selectedFiles()
            mpiexecDir = dirs[0]
            self._dlg.MPIBox.setText(mpiexecDir)
            self.mpiexecDir = mpiexecDir
            
            
