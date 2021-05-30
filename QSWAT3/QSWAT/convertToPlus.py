'''
Created on April 1, 2018

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
 
from qgis.PyQt.QtCore import QObject, QSettings, Qt
# from PyQt5.QtGui import QIcon
from qgis.PyQt.QtWidgets import QApplication, QInputDialog, QMessageBox, QFileDialog
from qgis.core import QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY, QgsProject, QgsRasterLayer
import os
import shutil
import glob
import pyodbc
import csv
import sqlite3
import numpy
import datetime
import time
import traceback
import subprocess

from convertdialog import ConvertDialog  # @UnresolvedImport


class ConvertToPlus(QObject):
    """Convert ArcSWAT project to QSWAT project."""
    
    _fullChoice = 0
    _noGISChoice = 1
    
    def __init__(self):
        """Initialise class variables."""
        QObject.__init__(self)
        ## plugin directory
        self.pluginDir = os.path.dirname(__file__)
        ## QSWATPlus project directory
        self.projDirNew = ''
        ## QSWATPlus project name
        self.projNameNew = ''
        ## QSWAT project directory
        self.projDirOld = ''
        ## QSWAT project name
        self.projNameOld = ''
        ## QSWATPlus project file
        self.projFileNew = ''
        ## relative path of DEM from old project
        self.demFile = ''
        ## landuse lookup table
        self.landuseLookup = ''
        ## soil lookup table
        self.soilLookup = ''
        ## soils used in model (no GIS option only)
        self.usedSoils = set()
        ## use STATSGO?
        self.useSTATSGO = False
        ## use SSURGO?
        self.useSSURGO = False
        ## wgn stations stored as station id -> (lat, long)
        self.wgnStations = dict()
        self._dlg = ConvertDialog()
        self._dlg.setWindowFlags(self._dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint & Qt.WindowMinimizeButtonHint)
        self._dlg.fullButton.clicked.connect(self.getChoice)
        self._dlg.noGISButton.clicked.connect(self.getChoice)
        ## choice of conversion
        self.choice = ConvertToPlus._fullChoice
        ## transform to project projection from lat-long
        self.transformFromDeg = None
        ## transform from project projection to lat-long
        self.transformToLatLong = None
        
    def run(self):
        """Run the conversion."""
        settings = QSettings()
        if settings.contains('/QSWAT/LastInputPath'):
            path = settings.value('/QSWAT/LastInputPath')
        else:
            path = ''
        title = u'Select existing QSWAT project file'
        filtr = 'QGIS project files (*.qgs)'
        projFileOld, _ = QFileDialog.getOpenFileName(None, title, path, filtr)
        if not projFileOld:
            return
        # convert to string from QString
        projFileOld = str(projFileOld)
        projParentOld, projFileName = os.path.split(projFileOld)
        self.projNameOld = os.path.splitext(projFileName)[0]
        # get location and name of new project
        while True:
            title = u'Select a parent directory to hold the new QSWATPlus project'
            projParentNew = QFileDialog.getExistingDirectory(None, title, projParentOld)
            if not projParentNew:
                return
            absOld = os.path.abspath(projParentOld)
            absNew = os.path.abspath(projParentNew)
            if absNew.startswith(absOld):
                ConvertToPlus.error(u'The QSWAT+ project cannot be within the QSWAT project')
                continue
            elif absOld.startswith(absNew):
                ConvertToPlus.error(u'The QSWAT project cannot be within the QSWAT+ project')
                continue
            # convert to string from QString
            projParentNew = str(projParentNew)
            if ConvertToPlus.question(u'Use {0} as new project name?'.format(self.projNameOld)) == QMessageBox.Yes:
                self.projNameNew = self.projNameOld
            else:
                self.projNameNew, ok = QInputDialog.getText(None, u'QSWATPlus project name', u'Please enter the new project name, starting with a letter:')
                if not ok:
                    return
                if not str(self.projNameNew[0]).isalpha():
                    self.error(u'Project name must start with a letter')
                    continue
            self.projDirNew = os.path.join(projParentNew, self.projNameNew)
            if os.path.exists(self.projDirNew):
                response = ConvertToPlus.question(u'Project directory {0} already exists.  Do you wish to delete it?'.format(self.projDirNew))
                if response != QMessageBox.Yes:
                    continue
                try:
                    shutil.rmtree(self.projDirNew, ignore_errors=True)
                    time.sleep(2)  # givr deletion time to complete
                except Exception:
                    ConvertToPlus.error(u'Problems encountered removing {0}: {1}.  Trying to continue regardless.'.format(self.projDirNew, traceback.format_exc()))
            self.projFileNew = os.path.join(self.projDirNew, self.projNameNew + '.qgs')
            break
        try: 
            ConvertToPlus.makeDirs(self.projDirNew)
        except Exception:
            ConvertToPlus.error(u'Failed to create QSWAT+ project directory {0}: {1}'.format(self.projDirNew, traceback.format_exc()))
            return
        self.readParameters(projFileOld)
        # get basename of DEM
        demBase = self.demFile.replace('Source\\', '').replace('.tif', '')
        # select choice of full or no GIS
        result = self._dlg.exec_()
        if result == 0:
            return
        settings.setValue('/QSWAT/LastInputPath', self.projDirNew)
        self.projDirOld = os.path.join(projParentOld, self.projNameOld)
        if self.choice == ConvertToPlus._fullChoice:
            # the first group of 5 patterns matches entries under <delin>
            # the next group of 5 matches entries under <maplayer><datasource>
            patts = [r'>Source\{0}wshed.shp'.format(demBase), r'>Source\{0}net.shp'.format(demBase), 
                     r'>Source\crop', r'>Source\soil', '>Source', 
                     './{0}/Source/{1}wshed.shp'.format(self.projNameOld, demBase), './{0}/Source/{1}net.shp'.format(self.projNameOld, demBase), 
                     './{0}/Source/crop'.format(self.projNameOld), './{0}/Source/soil'.format(self.projNameOld), 
                     './{0}/Source'.format(self.projNameOld), './{0}'.format(self.projNameOld), 'TablesOut']
            reps = ['>./Watershed/Shapes/{0}wshed.shp'.format(demBase), '>./Watershed/Shapes/{0}net.shp'.format(demBase),
                    '>./Watershed/Rasters/Landuse', '>./Watershed/Rasters/Soil', '>./Watershed/Rasters/DEM',
                    './Watershed/Shapes/{0}wshed.shp'.format(demBase), './Watershed/Shapes/{0}net.shp'.format(demBase),
                    './Watershed/Rasters/Landuse', './Watershed/Rasters/Soil', 
                    './Watershed/Rasters/DEM', '.', 'Results']
            print('Creating project file ...')
            with open(projFileOld, 'r') as inFile:
                with open(self.projFileNew, 'w', newline='') as outFile:
                    for line in inFile:
                        for i in range(len(patts)):
                            line = line.replace(patts[i], reps[i])
                        outFile.write(line)
            # copy files
            try:
                print('Creating directories and copying files ...')
                self.createSubDirectories(True)
            except Exception:
                ConvertToPlus.error(u'Problems creating subdirectories or copying files: {0}'.format(traceback.format_exc()))
        else:
            # create empty project file
            templateProjectFile = r'C:\SWAT\SWATPlus\Databases\example.qgs'
            if not os.path.isfile(templateProjectFile):
                ConvertToPlus.information("""WARNING: cannot create project file, since cannt find {0}.  
You will have to start a new project called {1} in {2}.""".format(templateProjectFile, self.projNameNew, self.projDirNew))
            else:
                shutil.copyfile(templateProjectFile, self.projFileNew)
            # create sub directories and copy only Results files
            try:
                print('Creating directories and copying results files ...')
                self.createSubDirectories(False)
            except Exception:
                ConvertToPlus.error(u'Problems creating subdirectories or copying results files: {0}'.format(traceback.format_exc()))
        # set up transform from lat-long to project projection and reverse
        self.setTransformFromDeg()
        try:
            print('Extracting project and reference tables ...')
            self.copyDbs()
        except Exception:
            ConvertToPlus.error(u'Problems copying databases or creating csv files: {0}'.format(traceback.format_exc()))
        print('Writing wgn tables ...')
        self.createWgnTables()
        self.createWeatherData()
        self.createDataFiles()
        self.setupTime()
        print('Project converted')
        if self.choice == ConvertToPlus._noGISChoice:
            ConvertToPlus.information('QSWAT project {0} converted to SWAT+ project {1} in {2}'.
                                       format(self.projNameOld, self.projNameNew, self.projDirNew))
            response = ConvertToPlus.question('Run SWAT+ Editor on the SWAT+ project?')
            if response == QMessageBox.Yes:
                editorDir = 'C:/SWAT/SWATPlus/SWATPlusEditor'
                editor = os.path.join(editorDir, 'SWATPlusEditor.exe')
                if not os.path.isfile(editor):
                    title = 'Cannot find SWAT+ Editor {0}.  Please select it.'.format(editor)
                    editor, _ = QFileDialog.getOpenFileName(None, title, '', 'Executable files (*.exe)')
                    if editor == '':
                        return
                qProjDb = os.path.join(self.projDirNew, self.projNameNew + '.sqlite')
                subprocess.call('"{0}" "{1}"'.format(editor, qProjDb), shell=True)
        else:
            ConvertToPlus.information('QSWAT project {0} converted to QSWAT+ project {1} in {2}'.
                                       format(self.projNameOld, self.projNameNew, self.projDirNew))
            response = ConvertToPlus.question('Run QGIS on the QSWAT+ project?')
            if response == QMessageBox.Yes:
                osgeo4wroot = r'C:\Program Files\QGIS 3.10'
                qgisname = 'qgis-ltr'
                batFile = r'{0}\bin\{1}.bat'.format(osgeo4wroot, qgisname)
                if not os.path.exists(batFile):
                    title = 'Cannot find QGIS start file {0}.  Please select it.'.format(batFile)
                    batFile, _ = QFileDialog.getOpenFileName(None, title, '', 'Bat files (*.bat)')
                    if batFile is None:
                        return
                command = '"{0}" --project "{1}"'.format(batFile, self.projFileNew)
                subprocess.call(command, shell=True)
            
    def createSubDirectories(self, isFull):
        """
        Create subdirectories under new project's directory, and populate from old project.
        """
        watershedDir = os.path.join(self.projDirNew, 'Watershed')
        ConvertToPlus.makeDirs(watershedDir)
        rastersDir = os.path.join(watershedDir, 'Rasters')
        ConvertToPlus.makeDirs(rastersDir)
        demDir = os.path.join(rastersDir, 'DEM')
        ConvertToPlus.makeDirs(demDir)
        if isFull:
            ConvertToPlus.copyFiles(self.projDirOld + '/Source', demDir)
        soilDir = os.path.join(rastersDir, 'Soil')
        ConvertToPlus.makeDirs(soilDir)
        if isFull:
            ConvertToPlus.copyFiles(self.projDirOld + '/Source/soil', soilDir)
        landuseDir = os.path.join(rastersDir, 'Landuse')
        ConvertToPlus.makeDirs(landuseDir)
        if isFull:
            ConvertToPlus.copyFiles(self.projDirOld + '/Source/crop', landuseDir)
        landscapeDir = os.path.join(rastersDir, 'Landscape')
        ConvertToPlus.makeDirs(landscapeDir)    
        floodDir = os.path.join(landscapeDir, 'Flood')
        ConvertToPlus.makeDirs(floodDir)
        scenariosDir = os.path.join(self.projDirNew, 'Scenarios')
        ConvertToPlus.makeDirs(scenariosDir)
        scensPattern = self.projDirOld + '/Scenarios/*'
        for oldScenDir in glob.iglob(scensPattern):
            scen = os.path.split(oldScenDir)[1]
            newScenDir = os.path.join(scenariosDir, scen)
            ConvertToPlus.makeDirs(newScenDir)
            txtInOutDir = os.path.join(newScenDir, 'TxtInOut')
            ConvertToPlus.makeDirs(txtInOutDir)
            resultsDir = os.path.join(newScenDir, 'Results')
            ConvertToPlus.makeDirs(resultsDir)
            ConvertToPlus.copyFiles(oldScenDir + '/TablesOut', resultsDir)
        defaultResultsDir = os.path.join(scenariosDir, 'Default/Results')
        plotsDir = os.path.join(defaultResultsDir, 'Plots')
        ConvertToPlus.makeDirs(plotsDir)
        animationDir = os.path.join(defaultResultsDir, 'Animation')
        ConvertToPlus.makeDirs(animationDir)
        pngDir = os.path.join(animationDir, 'Png')
        ConvertToPlus.makeDirs(pngDir)
        textDir = os.path.join(watershedDir, 'Text')
        ConvertToPlus.makeDirs(textDir)
        shapesDir = os.path.join(watershedDir, 'Shapes')
        ConvertToPlus.makeDirs(shapesDir)
        if isFull:
            ConvertToPlus.copyFiles(self.projDirOld + '/Watershed/Shapes', shapesDir)
            # wshed and net in wrong place
            ConvertToPlus.moveShapefile('wshed', demDir, shapesDir)
            ConvertToPlus.moveShapefile('net', demDir, shapesDir)
        csvDir = os.path.join(self.projDirNew, 'csv')
        ConvertToPlus.makeDirs(csvDir)
        projCsvDir = os.path.join(csvDir, 'Project')
        ConvertToPlus.makeDirs(projCsvDir)
        refCsvDir = os.path.join(csvDir, 'Reference')
        ConvertToPlus.makeDirs(refCsvDir)
        
    def copyDbs(self):
        """Set up project and reference databases; extract landuse and soil tables as .csv files."""
        projDbTemplate = r'C:\SWAT\SWATPlus\Databases\QSWATPlusProj2018.sqlite'
        refDbTemplate = r'C:\SWAT\SWATPlus\Databases\swatplus_datasets.sqlite'
        projDbNew = os.path.join(self.projDirNew, self.projNameNew + '.sqlite')
        shutil.copy(projDbTemplate, projDbNew)
        shutil.copy(refDbTemplate, self.projDirNew)
        projDbOld = os.path.join(self.projDirOld, self.projNameOld + '.mdb')
        connectionString = 'DRIVER={Microsoft Access Driver (*.mdb)};DBQ=' + projDbOld
        with pyodbc.connect(connectionString, readonly=True) as connOld:
            if connOld is None:
                ConvertToPlus.error(u'Failed to connect to old project database {0}'.format(projDbOld))
                return
            cursorOld = connOld.cursor()
            tables = []
            for row in cursorOld.tables(tableType='TABLE'):
                name = row.table_name
                if 'landuse' in name or 'soil' in name:
                    tables.append(name)
            if self.landuseLookup != '' and self.landuseLookup not in tables:
                tables.append(self.landuseLookup)
            if not self.useSSURGO and self.soilLookup != '' and self.soilLookup not in tables:
                tables.append(self.soilLookup)
            for name in tables:
                ConvertToPlus.writeCsvFile(cursorOld, name, os.path.join(self.projDirNew, r'csv\Project\{0}.csv'.format(name)))
            # copy lookup tables into new project database
            with sqlite3.connect(projDbNew) as connNew:
                if connNew is None:
                    ConvertToPlus.error(u'Failed to connect to new project database {0}'.format(projDbNew))
                    return
                cursorNew = connNew.cursor()
                if self.landuseLookup != '':
                    self.readLookupFile(os.path.join(self.projDirNew, r'csv\Project\{0}.csv'.format(self.landuseLookup)),
                                     self.landuseLookup, ConvertToPlus._LANDUSELOOKUPTABLE, cursorNew)
                if not self.useSSURGO and self.soilLookup != '':
                    self.readLookupFile(os.path.join(self.projDirNew, r'csv\Project\{0}.csv'.format(self.soilLookup)),
                                     self.soilLookup, ConvertToPlus._SOILLOOKUPTABLE, cursorNew)
                self.copyExemptSplitElevBand(cursorOld, cursorNew)
                connNew.commit()
        refDbOld = os.path.join(self.projDirOld, 'QSWATRef2012.mdb')
        connectionString = 'DRIVER={Microsoft Access Driver (*.mdb)};DBQ=' + refDbOld
        with pyodbc.connect(connectionString, readonly=True) as refConnOld:
            if refConnOld is None:
                ConvertToPlus.error(u'Failed to connect to reference database {0}'.format(refDbOld))
                return
            refCursorOld = refConnOld.cursor()
            projDbNew = os.path.join(self.projDirNew, self.projNameNew + '.sqlite')
            with sqlite3.connect(projDbNew) as projConnNew:
                projCursorNew = projConnNew.cursor()
                if not self.useSTATSGO and not self.useSSURGO:
                    self.createUsersoilTable(projCursorNew, refCursorOld)
                self.createPlantTable(projCursorNew, refCursorOld)
                self.createFertTable(projCursorNew, refCursorOld)
                self.createPestTable(projCursorNew, refCursorOld)
                self.createSeptTable(projCursorNew, refCursorOld)
                self.createTillTable(projCursorNew, refCursorOld)
                self.createUrbanTable(projCursorNew, refCursorOld)
                if self.choice == ConvertToPlus._noGISChoice:
                    self.createGISTables(projCursorNew)
                    # plant_plt and urban_urb already created
                    projConnNew.commit()  # else user soil table might not be written before it is used to create soils_sol
                    self.createSoilTables(projCursorNew)
                    self.createProjectConfig(projCursorNew)
                projConnNew.commit()
                
    def setTransformFromDeg(self):
        """Set the transform from lat-long to project projection."""
        
        # Get the project CRS from one of the .tif files in old Source directory
        pattern = self.projDirOld + r'\Source\*.tif'
        projCrs = None
        for f in glob.iglob(pattern):
            layer = QgsRasterLayer(f, 'raster')
            projCrs = layer.crs()
            break
        crsLatLong = QgsCoordinateReferenceSystem('EPSG:4326')
        self.transformFromDeg = QgsCoordinateTransform(crsLatLong, projCrs, QgsProject.instance())
        self.transformToLatLong = QgsCoordinateTransform(projCrs, crsLatLong, QgsProject.instance())
    
    def createProjectConfig(self, cursor):
        """Write project_config table to project database."""
        newProjDb = self.projNameNew + '.sqlite'
        newRefDb = os.path.join(self.projDirNew, 'swatplus_datasets.sqlite')
        weatherDataDir = os.path.join(self.projDirNew, r'Scenarios\Default\TxtInOut')
        gisType = 'qgis'
        gisVersion = '0.8'
        cursor.execute('DROP TABLE IF EXISTS project_config')
        cursor.execute(ConvertToPlus._CREATEPROJECTCONFIG)
        cursor.execute(ConvertToPlus._INSERTPROJECTCONFIG, 
                       (1, self.projNameNew, self.projDirNew, None, 
                        gisType, gisVersion, newProjDb, newRefDb, None, None, weatherDataDir, None, None, None, None, 
                        1, 1, ConvertToPlus._SOILS_SOL_NAME, ConvertToPlus._SOILS_SOL_LAYER_NAME, None, 0, 0))
                
    def createUsersoilTable(self, cursorNew, cursorOld):
        """Create usersoil in new project database from usersoil in old."""
        sqlOld = 'SELECT * FROM usersoil'
        tableNew = 'usersoil'
        cursorNew.execute('DROP TABLE IF EXISTS {0}'.format(tableNew))
        cursorNew.execute('CREATE TABLE ' + tableNew + ConvertToPlus._USERSOILTABLE)
        values = ' VALUES(' + ','.join(['?']*152) + ')'
        sqlNew = 'INSERT INTO ' + tableNew + values
        for row in cursorOld.execute(sqlOld):
            cursorNew.execute(sqlNew, tuple(row))
            
    def createPlantTable(self, cursorNew, cursorOld):
        """Create plant in new project database from crop in old."""
        sqlOld = 'SELECT * FROM crop'
        tableNew =  'plants_plt' if self.choice == ConvertToPlus._noGISChoice else 'plant'
        cursorNew.execute('DROP TABLE IF EXISTS {0}'.format(tableNew))
        cursorNew.execute('CREATE TABLE ' + tableNew + ConvertToPlus._PLANTTABLE)
        sqlNew = 'INSERT INTO {0} VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'.format(tableNew)
        num = 0
        for row in cursorOld.execute(sqlOld):
            num += 1
            self.writePlantRow(num, row, cursorNew, sqlNew)
            
    def createFertTable(self, cursorNew, cursorOld):
        """Create fert in new project database from fert in old."""
        sqlOld = 'SELECT * FROM fert'
        tableNew = 'fert'
        cursorNew.execute('DROP TABLE IF EXISTS {0}'.format(tableNew))
        cursorNew.execute('CREATE TABLE ' + tableNew + ConvertToPlus._FERTILIZERTABLE)
        sqlNew = 'INSERT INTO {0} VALUES(?,?,?,?,?,?,?,?,?)'.format(tableNew)
        num = 0
        for row in cursorOld.execute(sqlOld):
            num += 1
            self.writeFertRow(num, row, cursorNew, sqlNew)
            
    def createPestTable(self, cursorNew, cursorOld):
        """Create pest in new project database from pest in old."""
        sqlOld = 'SELECT * FROM pest'
        tableNew = 'pest'
        cursorNew.execute('DROP TABLE IF EXISTS {0}'.format(tableNew))
        cursorNew.execute('CREATE TABLE ' + tableNew + ConvertToPlus._PESTICIDETABLE)
        sqlNew = 'INSERT INTO {0} VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'.format(tableNew)
        num = 0
        for row in cursorOld.execute(sqlOld):
            num += 1
            self.writePestRow(num, row, cursorNew, sqlNew)
            
    def createSeptTable(self, cursorNew, cursorOld):
        """Create septwq in new project database from septwq in old."""
        sqlOld = 'SELECT * FROM septwq'
        tableNew = 'septwq'
        cursorNew.execute('DROP TABLE IF EXISTS {0}'.format(tableNew))
        cursorNew.execute('CREATE TABLE ' + tableNew + ConvertToPlus._SEPTICTABLE)
        sqlNew = 'INSERT INTO {0} VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)'.format(tableNew)
        num = 0
        for row in cursorOld.execute(sqlOld):
            num += 1
            self.writeSeptRow(num, row, cursorNew, sqlNew)
            
    def createTillTable(self, cursorNew, cursorOld):
        """Create till in new project database from till in old."""
        sqlOld = 'SELECT * FROM till'
        tableNew = 'till'
        cursorNew.execute('DROP TABLE IF EXISTS {0}'.format(tableNew))
        cursorNew.execute('CREATE TABLE ' + tableNew + ConvertToPlus._TILLAGETABLE)
        sqlNew = 'INSERT INTO {0} VALUES(?,?,?,?,?,?,?,?)'.format(tableNew)
        num = 0
        for row in cursorOld.execute(sqlOld):
            num += 1
            self.writeTillRow(num, row, cursorNew, sqlNew)
            
    def createUrbanTable(self, cursorNew, cursorOld):
        """Create urban in new project database from urban in old."""
        sqlOld = 'SELECT * FROM urban'
        tableNew = 'urban_urb' if self.choice == ConvertToPlus._noGISChoice else 'urban'
        cursorNew.execute('DROP TABLE IF EXISTS {0}'.format(tableNew))
        cursorNew.execute('CREATE TABLE ' + tableNew + ConvertToPlus._URBANTABLE)
        sqlNew = 'INSERT INTO {0} VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)'.format(tableNew)
        num = 0
        for row in cursorOld.execute(sqlOld):
            num += 1
            self.writeUrbanRow(num, row, cursorNew, sqlNew)
         
    def writePlantRow(self, num, row, cursor, sql):
        """Write values from row of crop table using cursor and sql, using num for the first element."""
        idc = int(row[3])
        daysMat = 120 if idc == 4 or idc == 5 else 365
        data = (num, row[2].lower(), idc, 'temp_gro', 0, daysMat) + tuple(row[5:13]) + (1,) + \
                tuple(row[13:34]) + tuple(row[40:45]) + (12, 3, row[45], 0, 0, 0, 0, 0, 0, 0.5, 0, 0, 0, row[4])
        cursor.execute(sql, data)
            
    def writeFertRow(self, num, row, cursor, sql):
        """Write values from row of fert table using cursor and sql, using num for the first element."""
        # columns 2-7 of new table same as columns 2:7 of fert, plus FERTNAME for description
        data = (num, row[2].lower()) + tuple(row[3:8]) + ('', row[11])
        cursor.execute(sql, data)
            
    def writePestRow(self, num, row, cursor, sql):
        """Write values from row of pest table using cursor and sql, using num for the first element."""
        data = (num, row[2].lower()) + tuple(row[3:7]) + (row[8], 0, 0, 0, 0, 0, 0, 0, 0, row[10])
        cursor.execute(sql, data)
            
    def writeSeptRow(self, num, row, cursor, sql):
        """Write values from row of septwq table using cursor and sql, using num for the first element."""
        data = (num, row[1].lower()) + tuple(row[4:7]) + tuple(row[8:12]) + tuple(row[13:16]) + (row[2],)
        cursor.execute(sql, data)
            
    def writeTillRow(self, num, row, cursor, sql):
        """Write values from row of till table using cursor and sql, using num for the first element."""
        data = (num, row[2].lower()) + tuple(row[3:5]) + (row[7], 0, 0, row[5])
        cursor.execute(sql, data)
            
    def writeUrbanRow(self, num, row, cursor, sql):
        """Write values from row of urban table using cursor and sql, using num for the first element."""
        # columns 2-10 of new table same as columns 4-12 of urban
        data = (num, row[2].lower()) + tuple(row[4:13]) + (row[18], row[3])
        cursor.execute(sql, data)
        
    def createSoilTables(self, writeCursor):
        """Write soils_sol and soils_sol_layer tables."""
        print('Writing soil tables ...')
        if not self.useSTATSGO and not self.useSSURGO:
            table = 'usersoil'
            layerTable = ''
            soilDb = os.path.join(self.projDirNew, self.projNameNew + '.sqlite')
            selectSql = 'SELECT * FROM usersoil WHERE SNAM=?'
        else:
            soilDb = r'C:\SWAT\SWATPlus\Databases\swatplus_soils.sqlite'
            if self.useSSURGO:
                table = 'ssurgo'
                layerTable = 'ssurgo_layer'
                selectSql = 'SELECT * FROM ssurgo WHERE muid=?'
            else:
                table = 'statsgo'
                layerTable = 'statsgo_layer'
                selectSql = 'SELECT * FROM statsgo WHERE muid=?'
            sqlLayer = 'SELECT * FROM {0} WHERE soil_id=? ORDER BY layer_num'.format(layerTable)
        sql = 'DROP TABLE IF EXISTS {0}'.format(ConvertToPlus._SOILS_SOL_NAME)
        writeCursor.execute(sql)
        sql = 'CREATE TABLE {0} {1}'.format(ConvertToPlus._SOILS_SOL_NAME, ConvertToPlus._SOILS_SOL_TABLE)
        writeCursor.execute(sql)
        sql = 'DROP TABLE IF EXISTS {0}'.format(ConvertToPlus._SOILS_SOL_LAYER_NAME)
        writeCursor.execute(sql)
        sql = 'CREATE TABLE {0} {1}'.format(ConvertToPlus._SOILS_SOL_LAYER_NAME, ConvertToPlus._SOILS_SOL_LAYER_TABLE)
        writeCursor.execute(sql)
        insert = 'INSERT INTO {0} VALUES(?,?,?,?,?,?,?,?)'.format(ConvertToPlus._SOILS_SOL_NAME)
        insertLayer = 'INSERT INTO {0} VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'.format(ConvertToPlus._SOILS_SOL_LAYER_NAME)
        with sqlite3.connect(soilDb) as readConn:
            readCursor = readConn.cursor()
            sid = 0 # last soil id used
            lid = 0 # last layer id used
            for soil in self.usedSoils:
                args = (soil,)
                row = readCursor.execute(selectSql, args).fetchone()
                if row is None:
                    ConvertToPlus.error(u'Soil name {0} (and perhaps others) not defined in {1} table in database {2}.  {3} table not written.'.
                                     format(soil, table, soilDb, ConvertToPlus._SOILS_SOL_NAME))
                    return
                sid += 1
                if layerTable == '':
                    lid = self.writeUsedSoilRow(sid, lid, soil, row, writeCursor, insert, insertLayer)
                else:
                    lid = self.writeUsedSoilRowSeparate(sid, lid, soil, row, writeCursor, insert, insertLayer, readCursor, sqlLayer, layerTable)
    
    @staticmethod                    
    def writeUsedSoilRow(sid, lid, name, row, cursor, insert, insertLayer):
        """Write data from one row of usersoil table to soils_sol and soils_sol_layer tables."""
        cursor.execute(insert, (sid, name) + row[7:12] + (None,))
        startLayer1 = 12 # index of SOL_Z1
        layerWidth = 12 # number of entries per layer
        startCal = 132 # index of SOL_CAL1
        startPh = 142 # index of SOL_PH1
        for i in range(int(row[6])):
            lid += 1 
            startLayer = startLayer1 + i*layerWidth
            cursor.execute(insertLayer, (lid, sid, i+1) +  row[startLayer:startLayer+layerWidth] +  (row[startCal+i], row[startPh+i]))
        return lid 
          
    @staticmethod        
    def writeUsedSoilRowSeparate(sid, lid, name, row, cursor, insert, insertLayer, readCursor, sqlLayer, layerTable):
        """Write data from one row of usersoil table plus separate layer table 
        to soils_sol and soils_sol_layer tables.
        """
        # check whether there is a non-null description item
        if len(row) == 11:
            cursor.execute(insert, (sid, name) +  row[6:] + (None,))
        else:
            cursor.execute(insert, (sid, name) +  row[6:])
        layerRows = readCursor.execute(sqlLayer, (row[0],)).fetchall()
        if layerRows is None or len(layerRows) == 0:
            ConvertToPlus.error(u'Failed to find soil layers in table {0} with soil_id {1}'.
                             format(layerTable, row[0]))
            return lid
        for ro in layerRows:
            lid += 1
            cursor.execute(insertLayer, (lid, sid) + ro[2:])
        return lid
    
    def createGISTables(self, writeCursor):
        """Create gis_channels, _lsus, _points, _routing, _subbasins and _water 
        from old project database"""
        # subasin - reach relation is 1-1, so use same number for each
        downstreamSubbasin = dict()
        projDbOld = os.path.join(self.projDirOld, self.projNameOld + '.mdb')
        connectionString = 'DRIVER={Microsoft Access Driver (*.mdb)};DBQ=' + projDbOld
        with pyodbc.connect(connectionString, readonly=True) as connOld:
            if connOld is None:
                ConvertToPlus.error(u'Failed to connect to old project database {0}'.format(projDbOld))
                return
            cursorOld = connOld.cursor()
            # gis_lsus and _subbasins
            writeCursor.execute('DROP TABLE IF EXISTS gis_lsus')
            writeCursor.execute('DROP TABLE IF EXISTS gis_subbasins')
            writeCursor.execute(ConvertToPlus._CREATELSUS)
            writeCursor.execute(ConvertToPlus._CREATESUBBASINS)
            subbasinAreaLatLonElev = dict()
            sql = 'SELECT * FROM Watershed'
            for row in cursorOld.execute(sql):
                subbasin = int(row[3])
                lsu = subbasin * 10
                channel = subbasin
                area = row[4]
                slo1 = row[5]
                len1 = row[6]
                sll = row[7]
                csl = row[8]
                wid1 = row[9]
                dep1 = row[10]
                lat = row[11]
                lon = row[12]
                elev = row[13]
                elevmin = row[14]
                elevmax = row[15]
                lonlat = QgsPointXY(float(lon), float(lat))
                xy = self.transformFromDeg.transform(lonlat)
                subbasinAreaLatLonElev[subbasin] = (area, xy.x(), xy.y(), lat, lon, elev)
                waterId = 0
                writeCursor.execute(ConvertToPlus._INSERTLSUS, 
                               (lsu, 0, channel, area, slo1, len1, csl, wid1, dep1, lat, lon, elev))
                writeCursor.execute(ConvertToPlus._INSERTSUBBASINS, 
                               (subbasin, area, slo1, len1, sll, lat, lon, elev, elevmin, elevmax, waterId))
            # gis_channels
            writeCursor.execute('DROP TABLE IF EXISTS gis_channels')
            writeCursor.execute(ConvertToPlus._CREATECHANNELS)
            sql = 'SELECT * FROM Reach'
            for row in cursorOld.execute(sql):
                subbasin = int(row[6])
                channel = subbasin
                _, _, _, lat, lon, _ = subbasinAreaLatLonElev[subbasin]
                writeCursor.execute(ConvertToPlus._INSERTCHANNELS, 
                               (channel, subbasin) + (row[8], 0) + tuple(row[9:15]) + (lat, lon))
                downstreamSubbasin[subbasin] = int(row[7])
            # calculate Strahler orders
            us = dict()
            outlets = []
            for link, dsLink in downstreamSubbasin.items():
                if dsLink > 0:
                    ups = us.setdefault(dsLink, [])
                    ups.append(link)
                else:
                    outlets.append(link)
            strahler = dict()
            for link in outlets:
                ConvertToPlus.setStrahler(link, us, strahler)
            # update order in gis_channels table
            sql = 'UPDATE gis_channels SET strahler = ? WHERE id = ?'
            for link, strahler in strahler.items():
                writeCursor.execute(sql, (strahler, link))
            # gis_aquifers and gis_deep_aquifers
            deepAquifers = dict()
            deepData = dict()
            writeCursor.execute('DROP TABLE IF EXISTS gis_aquifers')
            writeCursor.execute('DROP TABLE IF EXISTS gis_deep_aquifers')
            writeCursor.execute(ConvertToPlus._CREATEAQUIFERS)
            writeCursor.execute(ConvertToPlus._CREATEDEEPAQUIFERS)
            for subbasin, (area, x, y, lat, lon, elev) in subbasinAreaLatLonElev.items():
                outletBasin = ConvertToPlus.findOutlet(subbasin, downstreamSubbasin)
                deepAquifers[subbasin] = outletBasin
                writeCursor.execute(ConvertToPlus._INSERTAQUIFERS,
                               (subbasin, 0, subbasin, outletBasin, area, lat, lon, elev))
                (deepArea, deepElevMoment, deepXMoment, deepYMoment) = deepData.setdefault(outletBasin, (0,0,0,0))
                deepArea += area
                deepElevMoment += elev * area
                deepXMoment += x * area
                deepYMoment += y * area
                deepData[outletBasin] = (deepArea, deepElevMoment, deepXMoment, deepYMoment)
            for outletBasin, (deepArea, deepElevMoment, deepXMoment, deepYMoment) in deepData.items():
                x = deepXMoment / deepArea
                y = deepYMoment / deepArea
                lonlat = self.transformToLatLong.transform(QgsPointXY(x, y))
                writeCursor.execute(ConvertToPlus._INSERTDEEPAQUIFERS,
                               (outletBasin, outletBasin, deepArea, lonlat.y(), lonlat.x(), deepElevMoment / deepArea))
            # gis_points
            writeCursor.execute('DROP TABLE IF EXISTS gis_points')
            writeCursor.execute(ConvertToPlus._CREATEPOINTS)
            reservoirSubbasins = set()  # subbasins with reservoirs
            subbasinToOutlet = dict()
            inletToSubbasin = dict()
            ptsrcToSubbasin = dict()
            ptNum = 0
            sql = 'SELECT * FROM MonitoringPoint'
            for row in cursorOld.execute(sql):
                ptNum += 1
                subbasin = int(row[11])
                arcType = row[10]
                if arcType in ['L', 'T', 'O']:
                    qType = 'O'
                    subbasinToOutlet[subbasin] = ptNum
                elif arcType in ['W', 'I']:
                    qType = 'I'
                    inletToSubbasin[ptNum] = subbasin
                elif arcType in ['D', 'P']:
                    qType = 'P'
                    ptsrcToSubbasin[ptNum] = subbasin
                elif arcType == 'R':
                    reservoirSubbasins.add(subbasin)
                    continue  # reservoirs not included in gis_points
                else:
                    # weather gauge: not included in gis_points
                    continue
                elev = row[8]
                if elev == '': # avoid null: SWAT only requiress elevations for weather gauges
                    elev = 0
                writeCursor.execute(ConvertToPlus._INSERTPOINTS, 
                               (ptNum, subbasin, qType) + tuple(row[4:8]) + (elev,))
            # gis_hrus and _water
            writeCursor.execute('DROP TABLE IF EXISTS gis_hrus')
            writeCursor.execute('DROP TABLE IF EXISTS gis_water')
            writeCursor.execute(ConvertToPlus._CREATEHRUS)
            writeCursor.execute(ConvertToPlus._CREATEWATER)
            hruToSubbasin = dict()
            # subbasin number from previous row
            lastSubbasin = 0
            # flag to show if water done for current subbasin (since we amalgamate HRUs with landuse WATR)
            waterDone = False
            waterNum = 0
            waters = dict()
            self.usedSoils = set()
            sql = 'SELECT * FROM hrus'
            for row in cursorOld.execute(sql):
                subbasin = int(row[1])
                lsu = subbasin * 10
                if subbasin != lastSubbasin:
                    waterDone = False
                landuse = row[3]
                soil = row[5]
                self.usedSoils.add(soil)
                area = float(row[8])
                _, x, y, lat, lon, elev = subbasinAreaLatLonElev[subbasin]
                if landuse == 'WATR':
                    if subbasin in reservoirSubbasins:
                        wtype = 'RES'
                    else:
                        wtype = 'PND'
                    if not waterDone:
                        waterDone = True
                        waterNum += 1
                        waterArea = float(row[4])  # ARLU field: area in this subbasin which is WATR
                        writeCursor.execute(ConvertToPlus._INSERTWATER,
                                       (waterNum, wtype, lsu, subbasin, waterArea, x, y, lat, lon, elev))
                        waters[waterNum] = wtype, subbasin
                else:
                    hruNum = int(row[11])
                    writeCursor.execute(ConvertToPlus._INSERTHRUS, 
                                   (hruNum, lsu, row[2]) + tuple(row[2:10]) + (lat, lon, elev))
                    hruToSubbasin[hruNum] = subbasin
                lastSubbasin = subbasin
            # gis_routing
            writeCursor.execute('DROP TABLE IF EXISTS gis_routing')
            writeCursor.execute(ConvertToPlus._CREATEROUTING)
            # route subbasin to outlet and outlet to downstream subbasin
            for subbasin, outlet in subbasinToOutlet.items():
                writeCursor.execute(ConvertToPlus._INSERTROUTING, 
                               (subbasin, 'SUB', 'tot', outlet, 'PT', 100))
                writeCursor.execute(ConvertToPlus._INSERTROUTING, 
                               (subbasin, 'AQU', 'tot', outlet, 'PT', 100))
                # aquifer recharges deep aquifer
                writeCursor.execute(ConvertToPlus._INSERTROUTING, 
                               (subbasin, 'AQU', 'rhg', deepAquifers[subbasin], 'DAQ', 100))
                # LSUs are just copies of subbasins for ArcSWAT models
                lsu = subbasin * 10
                writeCursor.execute(ConvertToPlus._INSERTROUTING, 
                               (lsu, 'LSU', 'tot', outlet, 'PT', 100))
                # LSU recharges aquifer
                writeCursor.execute(ConvertToPlus._INSERTROUTING, 
                               (lsu, 'LSU', 'rhg', subbasin, 'AQU', 100))
                # subbasin reaches drain to the reservoir if there is one else to the outlet
                channel = subbasin
                if subbasin in reservoirSubbasins:
                    # check if in waters
                    wnum = 0
                    for num, (wtype, wsubbasin) in waters.items():
                        if subbasin == wsubbasin:
                            wnum = num
                            break
                    if wnum > 0:
                        writeCursor.execute(ConvertToPlus._INSERTROUTING, 
                                       (channel, 'CH', 'tot', wnum, 'RES', 100))
                    else:
                        # make zero area reservoir
                        waterNum += 1
                        _, x, y, lat, lon, elev = subbasinAreaLatLonElev[subbasin]
                        writeCursor.execute(ConvertToPlus._INSERTWATER,
                                       (waterNum, 'RES', lsu, subbasin, 0, x, y, lat, lon, elev))
                        waters[waterNum] = 'RES', subbasin
                        writeCursor.execute(ConvertToPlus._INSERTROUTING, 
                                       (channel, 'CH', 'tot', waterNum, 'RES', 100))
                else:
                    writeCursor.execute(ConvertToPlus._INSERTROUTING, 
                                   (channel, 'CH', 'tot', outlet, 'PT', 100))
                # the outlet point drains to 0, X if a watershed outlet
                # else the downstream subbasins reach
                downSubbasin = downstreamSubbasin[subbasin]
                if downSubbasin == 0:
                    # add deep aquifer routing to watershed outlet
                    writeCursor.execute(ConvertToPlus._INSERTROUTING,
                                   (subbasin, 'DAQ', 'tot', outlet, 'PT', 100))
                    writeCursor.execute(ConvertToPlus._INSERTROUTING,
                                   (outlet, 'PT', 'tot', 0, 'X', 100))
                else:
                    downChannel = downSubbasin
                    writeCursor.execute(ConvertToPlus._INSERTROUTING, 
                                   (outlet, 'PT', 'tot', downChannel, 'CH', 100))
            # inlets and point sources drain to channels
            for inlet, subbasin in inletToSubbasin.items():
                channel = subbasin
                writeCursor.execute(ConvertToPlus._INSERTROUTING, 
                               (inlet, 'PT', 'tot', channel, 'CH', 100))
            for ptsrc, subbasin in ptsrcToSubbasin.items():
                channel = subbasin
                writeCursor.execute(ConvertToPlus._INSERTROUTING, 
                               (ptsrc, 'PT', 'tot', channel, 'CH', 100))
            # reservoirs route to points, ponds to channels
            for wnum, (wtype, wsubbasin) in waters.items():
                if wtype == 'RES':
                    writeCursor.execute(ConvertToPlus._INSERTROUTING, 
                                   (wnum, 'RES', 'tot', subbasinToOutlet[wsubbasin], 'PT', 100))
                else:
                    channel = wsubbasin
                    writeCursor.execute(ConvertToPlus._INSERTROUTING, 
                                   (wnum, 'PND', 'tot', channel, 'CH', 100))
            # HRUs drain to channels
            for hruNum, subbasin in hruToSubbasin.items():
                channel = subbasin
                writeCursor.execute(ConvertToPlus._INSERTROUTING, 
                                (hruNum, 'HRU', 'tot', channel, 'CH', 100))
#             # checkRouting assumes sqlite3.Row used for row_factory
#             conn.row_factory = sqlite3.Row
#             msg = DBUtils.checkRouting(conn)
#             if msg != '':
#                 ConvertToPlus.error(msg)
            print('gis_ tables written')
          
    @staticmethod            
    def findOutlet(basin, downBasins):
        """downBasins maps basin to downstream basin or 0 if none.  Return final basin starting from basin."""
        downBasin = downBasins.get(basin, 0)
        if downBasin == 0:
            return basin
        else:
            return ConvertToPlus.findOutlet(downBasin, downBasins)
                        
    def copyExemptSplitElevBand(self, cursorOld, cursorNew):
        """Copy LuExempt, SplitHrus and ElevationBand tables."""
        tableOld = 'LuExempt'
        tableNew = 'gis_landexempt'
        cursorNew.execute('DROP TABLE IF EXISTS {0}'.format(tableNew))
        cursorNew.execute(ConvertToPlus._LANDEXEMPTCREATESQL)
        sqlOld = 'SELECT * FROM ' + tableOld
        for row in cursorOld.execute(sqlOld):
            cursorNew.execute(ConvertToPlus._LANDEXEMPTINSERTSQL, tuple(row[1:]))
        tableOld = 'SplitHrus'
        tableNew = 'gis_splithrus'
        cursorNew.execute('DROP TABLE IF EXISTS {0}'.format(tableNew))
        cursorNew.execute(ConvertToPlus._SPLITHRUSCREATESQL)
        sqlOld = 'SELECT * FROM ' + tableOld
        for row in cursorOld.execute(sqlOld):
            cursorNew.execute(ConvertToPlus._SPLITHRUSINSERTSQL, tuple(row[1:]))
        tableOld = 'ElevationBand'
        tableNew = 'gis_elevationbands'
        cursorNew.execute('DROP TABLE IF EXISTS {0}'.format(tableNew))
        cursorNew.execute(ConvertToPlus._ELEVATIONBANDSCREATESQL)
        sqlOld = 'SELECT * FROM ' + tableOld
        for row in cursorOld.execute(sqlOld):
            cursorNew.execute(ConvertToPlus._ELEVATIONBANDSINSERTSQL, tuple(row[1:]))
                
    def createWgnTables(self):
        """Create tables weather_wgn_cli and weather_wgn_cli_mon in project database from QSWAT TxtInOut wgn files."""
        self.wgnStations = dict()
        projDbNew = os.path.join(self.projDirNew, self.projNameNew + '.sqlite')
        pattern = os.path.join(self.projDirOld, r'Scenarios\Default\TxtInOut\*.wgn')
        stationNames = set()
        stationId = 0
        monId = 0
        with sqlite3.connect(projDbNew) as conn:
            cursor = conn.cursor()
            cursor.execute('DROP TABLE IF EXISTS weather_wgn_cli')
            cursor.execute(ConvertToPlus._CREATEWGN)
            cursor.execute('DROP TABLE IF EXISTS weather_wgn_cli_mon')
            cursor.execute(ConvertToPlus._CREATEWGNMON)
            for f in glob.iglob(pattern):
                with open(f, 'r') as wgnFile:
                    header = wgnFile.readline().split()
                    stationName = header[5][5:]
                    if stationName not in stationNames:
                        stationNames.add(stationName)
                        stationId += 1
                        latLong = wgnFile.readline()
                        latitude = float(latLong[12:19])
                        longitude = float(latLong[31:])
                        elev = float(wgnFile.readline()[12:])
                        rainYears = int(float(wgnFile.readline()[12:]))
                        cursor.execute(ConvertToPlus._INSERTWGN, 
                                       (stationId, stationName, latitude, longitude, elev, rainYears))
                        self.wgnStations[stationId] = (latitude, longitude)
                        arr = numpy.empty([14, 12], dtype=float)
                        for row in range(14):
                            line = wgnFile.readline()
                            for col in range(12):
                                i = col*6
                                arr[row,col] = float(line[i:i+6])
                        for col in range(12):
                            monId += 1
                            cursor.execute(ConvertToPlus._INSERTWGNMON, 
                                           (monId, stationId, col+1) + tuple(arr[:,col].astype(float).tolist()))
            conn.commit()
            
    def createWeatherData(self):
        """Create weather tables and files from QSWAT TxtInOut weather files."""
        qProjDb = os.path.join(self.projDirNew, self.projNameNew + '.sqlite')
        txtInOutDirOld = os.path.join(self.projDirOld, r'Scenarios\Default\TxtInOut')
        if not os.path.isdir(txtInOutDirOld):
            return
        txtInOutDirNew = os.path.join(self.projDirNew, r'Scenarios\Default\TxtInOut')
        gaugeStats = ConvertToPlus.GaugeStats()
        gaugeStats.setStats(self.projDirOld, self.projNameOld)
        # map typ -> order in data file -> WeatherStation
        stationTables = dict()
        self.populateWeatherTables(stationTables)
        with sqlite3.connect(qProjDb) as qConn:
            cursor = qConn.cursor()
            cursor.execute('DROP TABLE IF EXISTS weather_file')
            cursor.execute(ConvertToPlus._CREATEWEATHERFILE)
            cursor.execute('DROP TABLE IF EXISTS weather_sta_cli')
            cursor.execute(ConvertToPlus._CREATEWEATHERSTATION)
            self.createWeatherTypeData('pcp', 'precipitation', stationTables.get('pcp', dict()), 
                                       gaugeStats.nrgauge, gaugeStats.nrtot, txtInOutDirOld, txtInOutDirNew)
            self.createWeatherTypeData('tmp', 'temperature', stationTables.get('tmp', dict()), 
                                       gaugeStats.ntgauge, gaugeStats.nttot, txtInOutDirOld, txtInOutDirNew)
            self.createWeatherTypeData('hmd', 'relative humidity', stationTables.get('hmd', dict()), 
                                       1, gaugeStats.nhtot, txtInOutDirOld, txtInOutDirNew)
            self.createWeatherTypeData('slr', 'solar radiation', stationTables.get('slr', dict()), 
                                       1, gaugeStats.nstot, txtInOutDirOld, txtInOutDirNew)
            self.createWeatherTypeData('wnd', 'wind speed', stationTables.get('wnd', dict()), 
                                       1, gaugeStats.nwtot, txtInOutDirOld, txtInOutDirNew)
            # write stations to project database
            self.writeWeatherStations(stationTables, cursor)
            qConn.commit()
            
    def populateWeatherTables(self, stationTables):
        """Fill stationTables from Subtyp and typ tables."""
        
        def populateStations(typTable, typStations, cursor):
            """Use typ table to make map staId -> WeatherStation."""
            sql = 'SELECT * FROM {0}'.format(typTable)
            for row in cursor.execute(sql):
                staId = int(row[0])
                station = ConvertToPlus.WeatherStation(row[1], float(row[2]), float(row[3]), float(row[4]))
                typStations[staId] = station
                
        def hasData(table, cursor):
            """Return true if table exists and has data."""
            try:
                sql = 'SELECT * FROM ' + table
                row = cursor.execute(sql).fetchone()
                return row is not None
            except:
                return False
                
        def findTypTable(typ, cursor):
            """Return typ if there is a table with this name with data.
            Else return first table found (if any) starting with typ that has the appropriate fields and has data.
            Else return None."""
            if hasData(typ, cursor):
                return typ
            for row in cursor.tables(tableType='TABLE'):
                table = row.table_name
                if table.startswith(typ) and table != typ:
                    sql = 'SELECT * FROM ' + table
                    row = cursor.execute(sql).fetchone()
                    if row is None:
                        continue
                    columns = [column[0].upper() for column in cursor.description]
                    if columns[0] == 'ID' and columns[1] == 'NAME' and columns[2] == 'LAT' and columns[3] == 'LONG' and columns[4] == 'ELEVATION':
                        return table
            return None
        
        projDbOld = os.path.join(self.projDirOld, self.projNameOld + '.mdb')
        connectionString = 'DRIVER={Microsoft Access Driver (*.mdb)};DBQ=' + projDbOld
        with pyodbc.connect(connectionString, readonly=True) as connOld:
            if connOld is None:
                ConvertToPlus.error(u'Failed to connect to old project database {0}'.format(projDbOld))
                return
            cursor = connOld.cursor() 
            stations = dict()   
            typStrings = {'pcp': 'precipitation', 'tmp': 'temperature'}
            for typ, strng in typStrings.items():
                typTable = findTypTable(typ, cursor)
                if typTable is None:
                    ConvertToPlus.error('Cannot find {0} data'.format(strng))
                    return
                sql = 'SELECT * FROM {0}'.format(typTable)
                typStations = dict()
                stations[typ] = typStations
                populateStations(typTable, typStations, cursor)
            # important to do pcp and tmp first here as others use pcp or tmp station latitude etc
            for typ in ['pcp', 'tmp', 'hmd', 'slr', 'wnd']:
                data = dict()
                # leave this entry as an empty table if no data of this typ, since passed to createWeatherTypeData later
                stationTables[typ] = data
                table = 'Sub{0}'.format(typ.capitalize())
                if hasData(table, cursor):
                    sql = 'SELECT * FROM ' + table
                    for row in cursor.execute(sql):
                        minRec = int(row[3])
                        name = row[4]
                        order = int(row[5])
                        if order in data:
                            continue
                        if typ in typStrings:
                            station = stations[typ][minRec]
                        else:
                            if typ == 'slr':
                                # order is order in tmp data
                                station1 = stationTables['tmp'][order]
                            else:
                                station1 = stationTables['pcp'][order]
                            station = ConvertToPlus.WeatherStation(name, station1.latitude, station1.longitude, station1.elevation) 
                        data[order] = station
                    
    def createWeatherTypeData(self, typ, descr, stationTable, numFiles, numRecords, txtInOutDirOld, txtInOutDirNew):
        """Create typ data files files from QSWAT TxtInOut files."""
        if len(stationTable) == 0:
            # no weather data for this typ
            return
        print('Writing {0} data ...'.format(descr))
        now = datetime.datetime.now()
        timeNow = now.strftime("%Y-%m-%d %H:%M")
        staFile = os.path.join(txtInOutDirNew, '{0}.cli'.format(typ))
        with open(staFile, 'w', newline='') as staF:
            staF.write('{0}.cli : {1} file names - file written by ConvertToPlus {2}\n'.format(typ, descr, timeNow))
            staF.write('filename\n')
            stationNamesToSort = []
            for num in range(numFiles):
                if typ == 'pcp' or typ == 'tmp':
                    infileNum = num+1
                    inFile = os.path.join(txtInOutDirOld, '{1}{0!s}.{1}'.format(infileNum, typ))
                    if not os.path.isfile(inFile):
                        ConvertToPlus.error('Cannot find weather data file {0}'.format(inFile))
                        return
                else:
                    inFile = os.path.join(txtInOutDirOld, '{0}.{0}'.format(typ))
                    if not os.path.isfile(inFile):
                        ConvertToPlus.error('Cannot find weather data file {0}'.format(inFile))
                        return
                numWidth = 5
                with open(inFile, 'r') as f:
                    # skip comment first line
                    f.readline()
                    if typ == 'pcp' or typ == 'tmp':
                        if typ == 'tmp':
                            width = 10
                        else:
                            width = 5
                        latitudes = f.readline()
                        # use latitudes line to get number of records in this file
                        numRecords = (len(latitudes) - 7) // width
                        _ = f.readline()  # longitudes
                        _ = f.readline()  # elevations
                    else:
                        width = 8            
                    for i in range(numRecords):
                        order = i+1
                        name = stationTable[order].name
                        stationNamesToSort.append(name) 
                    # collect data in arrays
                    dates = []
                    data = []
                    while True:
                        line = f.readline()
                        if line == '':
                            break
                        dates.append(line[:7])
                        if typ == 'tmp':
                            nextData = [(float(line[start:start+numWidth]),
                                         float(line[start+numWidth:start+width])) 
                                         for start in [7+width*i for i in range(numRecords)]]
                        else:
                            nextData = [float(line[start:start+width]) for start in [7+width*i for i in range(numRecords)]]
                        data.append(nextData)
                    # write files
                    for order, station in stationTable.items():
                        pos = order - 1
                        fileName = '{0}.{1}'.format(station.name, typ)
                        outFile = os.path.join(txtInOutDirNew, fileName)
                        with open(outFile, 'w', newline='') as f:
                            f.write('{0}: {2} data - file written by ConvertToPlus {1}\n'
                                    .format(fileName, timeNow, descr))
                            f.write('nbyr     tstep       lat       lon      elev\n')
                            firstYear = int(dates[0][:4])
                            lastYear = int(dates[-1][:4])
                            numYears = lastYear - firstYear + 1
                            f.write(str(numYears).rjust(4))
                            f.write('0'.rjust(10)) # TODO: time step 
                            f.write('{0:.3F}'.format(station.latitude).rjust(10))
                            f.write('{0:.3F}'.format(station.longitude).rjust(10))
                            f.write('{0:.3F}\n'.format(station.elevation).rjust(11))
                            row = 0
                            for date in dates:
                                f.write(date[:4])
                                f.write(str(int(date[4:])).rjust(5))
                                if typ == 'tmp':
                                    maxx, minn = data[row][pos]
                                    f.write('{0:.1F}'.format(maxx).rjust(10))
                                    f.write('{0:.1F}\n'.format(minn).rjust(10))
                                elif typ == 'pcp':
                                    f.write('{0:.1F}\n'.format(data[row][pos]).rjust(9))
                                else:
                                    f.write('{0:.3F}\n'.format(data[row][pos]).rjust(11))
                                row += 1
            # write weather station file names in staFile, in sorted order
            for name in sorted(stationNamesToSort):
                staF.write('{0}.{1}\n'.format(name, typ))
                            
    def writeWeatherStations(self, stationTables, cursor):
        """Wtite entries for stations in weather_file and weather_sta_cli. """
        # dictionary collectedName -> typ -> WeatherStation
        collectedStations = dict()
        for typ, stations in stationTables.items():
            for station in stations.values():
                # generate name from latitude and longitude enabling co-located stations of different types to be merged
                lat = int(round(station.latitude, 2) * 100)
                latStr = '{0}n'.format(lat) if lat >= 0 else '{0}s'.format(abs(lat))
                lon = int(round(station.longitude, 2) * 100)
                if lon > 180:
                    lon = lon - 360
                lonStr = '{0}e'.format(lon) if lon >= 0 else '{0}w'.format(abs(lon))
                collectedName = 'sta' + lonStr + latStr
                data = collectedStations.setdefault(collectedName, dict())
                data[typ] = station
        staId = 0
        staFileId = 0
        for collectedName, data in collectedStations.items():
            files = ['sim', 'sim', 'sim', 'sim', 'sim', 'sim', 'sim']
            first = True
            wgnId = 0
            latitude = 0.0
            longitude = 0.0
            for typ, station in data.items():
                if first:
                    latitude = station.latitude
                    longitude = station.longitude
                    wgnId = self.nearestWgn(latitude, longitude)
                    first = False
                staFileId += 1
                fileName = '{0}.{1}'.format(station.name, typ)
                cursor.execute(ConvertToPlus._INSERTWEATHERFILE, 
                               (staFileId, fileName, typ, latitude, longitude))
                indx = ['pcp', 'tmp', 'slr', 'hmd', 'wnd'].index(typ)
                files[indx] = fileName
            staId += 1
            cursor.execute(ConvertToPlus._INSERTWEATHERSTATION, 
                           (staId, collectedName, wgnId) + tuple(files) + (latitude, longitude))
                            
    def nearestWgn(self, lat, lon):
        """Return nearest wgn station id, or -1 if none.
        
        Uses sum of squares of latitude and longitude differences as the measure of proximity."""
        result = -1
        currentMeasure = 64800  # 2 * 180 * 180  :  maximum possible value
        for stationId, (latitude, longitude) in self.wgnStations.items():
            latDiff = latitude - lat
            lonDiff = abs(longitude - lon)
            # allow for either side of date line
            if lonDiff > 180:
                lonDiff = 360 - lonDiff 
            measure = latDiff * latDiff + lonDiff * lonDiff
            if measure < currentMeasure:
                currentMeasure = measure
                result = stationId
        return result
            
    def createDataFiles(self):
        """Create csv files from REC files identified in fig.fig file in each scenario."""
        scensPattern = self.projDirOld + '/Scenarios/*'
        for scenDirOld in glob.iglob(scensPattern):
            scenario = os.path.split(scenDirOld)[1]
            self.createScenarioDataFiles(scenario)
        
    def createScenarioDataFiles(self, scenario):
        """Create csv files from REC files identified in fig.fig file."""
        txtInOutDirOld = os.path.join(self.projDirOld, r'Scenarios\{0}\TxtInOut'.format(scenario))
        txtInOutDirNew = os.path.join(self.projDirNew, r'Scenarios\{0}\TxtInOut'.format(scenario))
        if not os.path.isdir(txtInOutDirOld):
            return
        figFile = os.path.join(txtInOutDirOld, 'fig.fig')
        if not os.path.isfile(figFile):
            return
        recConst = []
        recYear = []
        recOther = []
        with open(figFile) as f:
            while True:
                line = f.readline()
                if line == '':
                    break
                try:
                    # go one place too far to right so that eg '    10 ' distinguished from '0000100' appearing in a file name
                    command = int(line[10:17])
                except:
                    continue
                if command == 11:  # reccnst
                    line = f.readline()
                    recConst.append(line[10:23].strip())
                elif command == 8:  # recyear
                    line = f.readline()
                    recYear.append(line[10:23].strip())
                elif command in {7, 10}:  # recmon or recday
                    line = f.readline()
                    recOther.append(line[10:23].strip())
        if len(recConst) > 0:
            qConstFile = os.path.join(txtInOutDirNew, 'rec_const.csv')
            qConst = open(qConstFile, 'w', newline='')
            qConst.write('name,flo,sed,ptl_n,ptl_p,no3_n,sol_p,chla,nh3_n,no2_n,cbn_bod,oxy,sand,silt,clay,sm_agg,lg_agg,gravel,tmp\n')
            for datFile in recConst:
                with open(os.path.join(txtInOutDirOld, datFile)) as f:
                    # skip 6 lines
                    for _ in range(6):
                        _ = f.readline()
                    fName = os.path.splitext(datFile)[0]
                    if fName.endswith('p'):
                        name = 'pt' + fName[:-1]
                    elif fName.endswith('i'):
                        name = 'in' + fName[:-1]
                    else:
                        name = 'x' + fName  # just ensure starts with a letter
                    vals = f.readline().split()
                    qConst.write('{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},0,0,0,0,0,0,0\n'
                                     .format(name, vals[0], vals[1], vals[2], vals[3], vals[4], vals[7], vals[10], vals[5], vals[6], vals[8], vals[9]))
            print('{0} written'.format(qConstFile))
        for datFile in recYear:
            qFile = os.path.join(txtInOutDirNew, os.path.splitext(datFile)[0] + '.csv')
            with open(os.path.join(txtInOutDirOld, datFile)) as f:
                # skip 6 lines
                for _ in range(6):
                    _ = f.readline()
                with open(qFile, 'w', newline='') as q:
                    q.write('yr,t_step,flo,sed,ptl_n,ptl_p,no3_n,sol_p,chla,nh3_n,no2_n,cbn_bod,oxy,sand,silt,clay,sm_agg,lg_agg,gravel,tmp\n')
                    year = 0
                    while True:
                        vals = f.readline().split()
                        if len(vals) == 0:
                            break
                        year += 1
                        q.write('{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12},0,0,0,0,0,0,0\n'
                                .format(vals[0], str(year), vals[1], vals[2], vals[3], vals[4], vals[5], vals[8], vals[11], vals[6], vals[7], vals[9], vals[10]))
            print('{0} written'.format(qFile)) 
        for datFile in recOther:
            qFile = os.path.join(txtInOutDirNew, os.path.splitext(datFile)[0] + '.csv')
            with open(os.path.join(txtInOutDirOld, datFile)) as f:
                # skip 6 lines
                for _ in range(6):
                    _ = f.readline()
                with open(qFile, 'w', newline='') as q:
                    q.write('yr,t_step,flo,sed,ptl_n,ptl_p,no3_n,sol_p,chla,nh3_n,no2_n,cbn_bod,oxy,sand,silt,clay,sm_agg,lg_agg,gravel,tmp\n')
                    while True:
                        vals = f.readline().split()
                        if len(vals) == 0:
                            break
                        q.write('{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12},0,0,0,0,0,0,0\n'
                                .format(vals[1], vals[0], vals[2], vals[3], vals[4], vals[5], vals[6], vals[9], vals[12], vals[7], vals[8], vals[10], vals[11]))
            print('{0} written'.format(qFile))
    
    def setupTime(self):
        """Read file.cio to setup start/finsh dates and nyskip."""
        print('Writing start/finish dates ...')
        # read file.cio
        cioFile = os.path.join(self.projDirOld, r'Scenarios\Default\TxtInOut\file.cio')
        if not os.path.isfile(cioFile):
            return
        with open(cioFile, 'r') as f:
            for _ in range(7):
                f.readline()
            line = f.readline()
            nbyr = int(line[:18])
            line = f.readline()
            iyr = int(line[:18])
            line = f.readline()
            idaf = int(line[:18])
            line = f.readline()
            idal = int(line[:18])
            for _ in range(4):
                line = f.readline()
            idt = int(line[:18])
            for _ in range(45):
                line = f.readline()
            nyskip = int(line[:18])
        qProjDb = os.path.join(self.projDirNew, self.projNameNew + '.sqlite')
        with sqlite3.connect(qProjDb) as qConn:
            cursor = qConn.cursor()
            cursor.execute('DROP TABLE IF EXISTS time_sim')
            cursor.execute(ConvertToPlus._CREATETIMESIM)
            cursor.execute('DROP TABLE IF EXISTS print_prt')
            cursor.execute(ConvertToPlus._CREATEPRINTPRT)
            cursor.execute(ConvertToPlus._INSERTTIMESIM, (1, idaf, iyr, idal, iyr + nbyr - 1, idt))
            cursor.execute(ConvertToPlus._INSERTPRINTPRT, (1, nyskip, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0))
            qConn.commit()
        
    def readParameters(self, projFile):
        """Read parameters from project file."""
        proj = QgsProject.instance()
        proj.read(projFile)
        title = proj.title()
        self.demFile, _ = proj.readEntry(title, 'delin/DEM')
        self.landuseLookup, _ = proj.readEntry(title, 'landuse/table', '')
        self.soilLookup, _ = proj.readEntry(title, 'soil/table', '')
        self.useSTATSGO, _ = proj.readBoolEntry(title, 'soil/useSTATSGO', False)
        self.useSSURGO, _ = proj.readBoolEntry(title, 'soil/useSSURGO', False)
        
    def getChoice(self):
        """Set choice from form."""
        if self._dlg.fullButton.isChecked():
            self.choice = ConvertToPlus._fullChoice
        else:
            self.choice = ConvertToPlus._noGISChoice
        
    @staticmethod
    def writeCsvFile(cursor, table, outFile):
        """Write table to csv file outFile."""
        sql = 'SELECT * FROM {0}'.format(table)
        rows = cursor.execute(sql)
        with open(outFile, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([x[0] for x in cursor.description])  # column headers
            for row in rows:
                writer.writerow(row)
                
    def readLookupFile(self, csvFile, table, tableSQL, cursor):
        """User cursor to create a lookup table populated from csv file."""
        if not os.path.isfile(csvFile):
            ConvertToPlus.error(u'Cannot find csv file {0}'.format(csvFile))
            return
        cursor.execute('DROP TABLE IF EXISTS {0}'.format(table))
        cursor.execute('CREATE TABLE {0} {1}'.format(table, tableSQL))
        sql = 'INSERT INTO {0} VALUES(?,?)'.format(table)
        with open(csvFile, 'r') as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            for row in reader:
                cursor.execute(sql, tuple(row[:2]))  # ignore coloumns beyond second
    
    @staticmethod
    def setStrahler(link, us, strahler):
        """Define Strahler order in strahler map using upstream relation us, starting from link."""
        ups = us.get(link, [])
        if ups == []:
            strahler[link] = 1
            return 1
        orders = [ConvertToPlus.setStrahler(up, us, strahler) for up in ups]
        omax = max(orders)
        count = len([o for o in orders if o == omax])
        order = omax if count == 1 else omax+1
        strahler[link] = order
        return order

    @staticmethod
    def copyFiles(inDir, saveDir):
        """
        Copy files from inDir to saveDir, excluding directories 
        unl;ess they are ESRI grids.
        """
        pattern = inDir + '/*.*'
        for f in glob.iglob(pattern):
            shutil.copy(f, saveDir)
        pattern = inDir + '/*'
        for f in glob.iglob(pattern):
            if os.path.isdir(f) and os.path.exists(f + '/hdr.adf'):
                # ESRI grid: need to copy directory to saveDir
                target = os.path.join(saveDir, os.path.split(f)[1])
                shutil.copytree(f, target)
                
    
    @staticmethod
    def moveShapefile(strng, fromDir, toDir):
        """Move shapefile *strng.shp from fromDir to toDir"""
        pattern = fromDir + '/*{0}.shp'.format(strng)
        for f in glob.iglob(pattern):
            for suffix in ['.shp', '.prj', '.dbf', '.shx']:
                fromPath = os.path.splitext(f)[0] + suffix
                toPath = os.path.join(toDir, os.path.split(fromPath)[1])
                shutil.move(fromPath, toPath)
                
    @staticmethod
    def makeDirs(direc):
        """Make directory dir unless it already exists."""
        if not os.path.exists(direc):
            os.makedirs(direc)
                
    @staticmethod
    def trans(msg):
        """Translate message."""
        return QApplication.translate("SWAT", msg, None)

    @staticmethod
    def question(msg):
        """Ask msg as a question, returning Yes or No."""
        questionBox = QMessageBox()
        questionBox.setWindowTitle('QSWATPlus')
        questionBox.setIcon(QMessageBox.Question)
        questionBox.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        questionBox.setText(ConvertToPlus.trans(msg))
        result = questionBox.exec_()
        return result
    
    @staticmethod
    def error(msg):
        """Report msg as an error."""
        msgbox = QMessageBox()
        msgbox.setWindowTitle('QSWATPlus')
        msgbox.setIcon(QMessageBox.Critical)
        msgbox.setText(ConvertToPlus.trans(msg))
        msgbox.exec_()
        return
    
    @staticmethod
    def information(msg):
        """Report msg."""
        msgbox = QMessageBox()
        msgbox.setWindowTitle('QSWATPlus')
        msgbox.setIcon(QMessageBox.Information)
        msgbox.setText(ConvertToPlus.trans(msg))
        msgbox.exec_()
        return
    
    _LANDUSELOOKUPTABLE = \
    """
    (
    LANDUSE_ID INTEGER PRIMARY KEY,
    SWAT_CODE  TEXT
    )
    """
    
    _SOILLOOKUPTABLE = \
    """
    (
    SOIL_ID INTEGER PRIMARY KEY,
    SNAM    TEXT
    )
    """
    
    _USERSOILTABLE = \
    """
    (
    OBJECTID   INTEGER,
    MUID       TEXT,
    SEQN       INTEGER,
    SNAM       TEXT,
    S5ID       TEXT,
    CMPPCT     REAL,
    NLAYERS    INTEGER,
    HYDGRP     TEXT,
    SOL_ZMX    REAL,
    ANION_EXCL REAL,
    SOL_CRK    REAL,
    TEXTURE    TEXT,
    SOL_Z1     REAL,
    SOL_BD1    REAL,
    SOL_AWC1   REAL,
    SOL_K1     REAL,
    SOL_CBN1   REAL,
    CLAY1      REAL,
    SILT1      REAL,
    SAND1      REAL,
    ROCK1      REAL,
    SOL_ALB1   REAL,
    USLE_K1    REAL,
    SOL_EC1    REAL,
    SOL_Z2     REAL,
    SOL_BD2    REAL,
    SOL_AWC2   REAL,
    SOL_K2     REAL,
    SOL_CBN2   REAL,
    CLAY2      REAL,
    SILT2      REAL,
    SAND2      REAL,
    ROCK2      REAL,
    SOL_ALB2   REAL,
    USLE_K2    REAL,
    SOL_EC2    REAL,
    SOL_Z3     REAL,
    SOL_BD3    REAL,
    SOL_AWC3   REAL,
    SOL_K3     REAL,
    SOL_CBN3   REAL,
    CLAY3      REAL,
    SILT3      REAL,
    SAND3      REAL,
    ROCK3      REAL,
    SOL_ALB3   REAL,
    USLE_K3    REAL,
    SOL_EC3    REAL,
    SOL_Z4     REAL,
    SOL_BD4    REAL,
    SOL_AWC4   REAL,
    SOL_K4     REAL,
    SOL_CBN4   REAL,
    CLAY4      REAL,
    SILT4      REAL,
    SAND4      REAL,
    ROCK4      REAL,
    SOL_ALB4   REAL,
    USLE_K4    REAL,
    SOL_EC4    REAL,
    SOL_Z5     REAL,
    SOL_BD5    REAL,
    SOL_AWC5   REAL,
    SOL_K5     REAL,
    SOL_CBN5   REAL,
    CLAY5      REAL,
    SILT5      REAL,
    SAND5      REAL,
    ROCK5      REAL,
    SOL_ALB5   REAL,
    USLE_K5    REAL,
    SOL_EC5    REAL,
    SOL_Z6     REAL,
    SOL_BD6    REAL,
    SOL_AWC6   REAL,
    SOL_K6     REAL,
    SOL_CBN6   REAL,
    CLAY6      REAL,
    SILT6      REAL,
    SAND6      REAL,
    ROCK6      REAL,
    SOL_ALB6   REAL,
    USLE_K6    REAL,
    SOL_EC6    REAL,
    SOL_Z7     REAL,
    SOL_BD7    REAL,
    SOL_AWC7   REAL,
    SOL_K7     REAL,
    SOL_CBN7   REAL,
    CLAY7      REAL,
    SILT7      REAL,
    SAND7      REAL,
    ROCK7      REAL,
    SOL_ALB7   REAL,
    USLE_K7    REAL,
    SOL_EC7    REAL,
    SOL_Z8     REAL,
    SOL_BD8    REAL,
    SOL_AWC8   REAL,
    SOL_K8     REAL,
    SOL_CBN8   REAL,
    CLAY8      REAL,
    SILT8      REAL,
    SAND8      REAL,
    ROCK8      REAL,
    SOL_ALB8   REAL,
    USLE_K8    REAL,
    SOL_EC8    REAL,
    SOL_Z9     REAL,
    SOL_BD9    REAL,
    SOL_AWC9   REAL,
    SOL_K9     REAL,
    SOL_CBN9   REAL,
    CLAY9      REAL,
    SILT9      REAL,
    SAND9      REAL,
    ROCK9      REAL,
    SOL_ALB9   REAL,
    USLE_K9    REAL,
    SOL_EC9    REAL,
    SOL_Z10    REAL,
    SOL_BD10   REAL,
    SOL_AWC10  REAL,
    SOL_K10    REAL,
    SOL_CBN10  REAL,
    CLAY10     REAL,
    SILT10     REAL,
    SAND10     REAL,
    ROCK10     REAL,
    SOL_ALB10  REAL,
    USLE_K10   REAL,
    SOL_EC10   REAL,
    SOL_CAL1   REAL,
    SOL_CAL2   REAL,
    SOL_CAL3   REAL,
    SOL_CAL4   REAL,
    SOL_CAL5   REAL,
    SOL_CAL6   REAL,
    SOL_CAL7   REAL,
    SOL_CAL8   REAL,
    SOL_CAL9   REAL,
    SOL_CAL10  REAL,
    SOL_PH1    REAL,
    SOL_PH2    REAL,
    SOL_PH3    REAL,
    SOL_PH4    REAL,
    SOL_PH5    REAL,
    SOL_PH6    REAL,
    SOL_PH7    REAL,
    SOL_PH8    REAL,
    SOL_PH9    REAL,
    SOL_PH10   REAL
    )
    """
    
    _LANDEXEMPTCREATESQL = \
    """
    CREATE TABLE gis_landexempt (
    landuse TEXT
    );
    """
    
    _LANDEXEMPTINSERTSQL = 'INSERT INTO gis_landexempt VALUES(?)'
    
    _SPLITHRUSCREATESQL = \
    """
    CREATE TABLE gis_splithrus (
    landuse    TEXT,
    sublanduse TEXT,
    percent    REAL
    );
    """
    
    _SPLITHRUSINSERTSQL = 'INSERT INTO gis_splithrus VALUES(?,?,?)'
    
    _ELEVATIONBANDSCREATESQL = \
    """
    CREATE TABLE gis_elevationbands (
    subbasin INTEGER PRIMARY KEY UNIQUE NOT NULL,  
    elevb1 REAL,  
    elevb2 REAL,  
    elevb3 REAL,  
    elevb4 REAL,  
    elevb5 REAL,  
    elevb6 REAL,  
    elevb7 REAL,  
    elevb8 REAL,  
    elevb9 REAL,  
    elevb10 REAL,  
    elevb_fr1 REAL,  
    elevb_fr2 REAL,  
    elevb_fr3 REAL,  
    elevb_fr4 REAL,  
    elevb_fr5 REAL,  
    elevb_fr6 REAL,  
    elevb_fr7 REAL,  
    elevb_fr8 REAL,  
    elevb_fr9 REAL,  
    elevb_fr10 REAL)
    """
    
    _ELEVATIONBANDSINSERTSQL = 'INSERT INTO gis_elevationbands VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
 
    _CREATEWGN = \
    """
    CREATE TABLE weather_wgn_cli (
        id       INTEGER       NOT NULL
                               PRIMARY KEY,
        name     VARCHAR (255) NOT NULL,
        lat      REAL          NOT NULL,
        lon      REAL          NOT NULL,
        elev     REAL          NOT NULL,
        rain_yrs INTEGER       NOT NULL
    );
    """
    
    _INSERTWGN = 'INSERT INTO weather_wgn_cli VALUES(?,?,?,?,?,?)'
    
    _CREATEWGNMON = \
    """
    CREATE TABLE weather_wgn_cli_mon (
        id          INTEGER NOT NULL
                            PRIMARY KEY,
        weather_wgn_cli_id      INTEGER NOT NULL,
        month       INTEGER NOT NULL,
        tmp_max_ave REAL    NOT NULL,
        tmp_min_ave REAL    NOT NULL,
        tmp_max_sd  REAL    NOT NULL,
        tmp_min_sd  REAL    NOT NULL,
        pcp_ave     REAL    NOT NULL,
        pcp_sd      REAL    NOT NULL,
        pcp_skew    REAL    NOT NULL,
        wet_dry     REAL    NOT NULL,
        wet_wet     REAL    NOT NULL,
        pcp_days    REAL    NOT NULL,
        pcp_hhr     REAL    NOT NULL,
        slr_ave     REAL    NOT NULL,
        dew_ave     REAL    NOT NULL,
        wnd_ave     REAL    NOT NULL,
        FOREIGN KEY (
            weather_wgn_cli_id
        )
        REFERENCES weather_wgn_cli (id) ON DELETE CASCADE
    );
    """
    
    _INSERTWGNMON = 'INSERT INTO weather_wgn_cli_mon VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
    
    _CREATETIMESIM = \
    """
    CREATE TABLE time_sim (
    id        INTEGER NOT NULL
                      PRIMARY KEY,
    day_start INTEGER NOT NULL,
    yrc_start INTEGER NOT NULL,
    day_end   INTEGER NOT NULL,
    yrc_end   INTEGER NOT NULL,
    step      INTEGER NOT NULL
    );
    """
    
    _INSERTTIMESIM = 'INSERT INTO time_sim VALUES(?,?,?,?,?,?)'
    
    _CREATEPRINTPRT = \
    """
    CREATE TABLE print_prt (
    id        INTEGER NOT NULL
                      PRIMARY KEY,
    nyskip    INTEGER NOT NULL,
    day_start INTEGER NOT NULL,
    yrc_start INTEGER NOT NULL,
    day_end   INTEGER NOT NULL,
    yrc_end   INTEGER NOT NULL,
    interval  INTEGER NOT NULL,
    csvout    INTEGER NOT NULL,
    dbout     INTEGER NOT NULL,
    cdfout    INTEGER NOT NULL,
    soilout   INTEGER NOT NULL,
    mgtout    INTEGER NOT NULL,
    hydcon    INTEGER NOT NULL,
    fdcout    INTEGER NOT NULL
    );

    """
    
    _INSERTPRINTPRT = 'INSERT INTO print_prt VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
    
    _CREATEWEATHERFILE = \
    """
    CREATE TABLE weather_file (
    id       INTEGER       NOT NULL
                           PRIMARY KEY,
    filename VARCHAR (255) NOT NULL,
    type     VARCHAR (255) NOT NULL,
    lat      REAL          NOT NULL,
    lon      REAL          NOT NULL
    );
    """ 
    
    _INSERTWEATHERFILE = 'INSERT INTO weather_file VALUES(?,?,?,?,?)'
    
    _CREATEWEATHERSTATION = \
    """
    CREATE TABLE weather_sta_cli (
    id       INTEGER       NOT NULL
                           PRIMARY KEY,
    name     VARCHAR (255) NOT NULL,
    wgn_id   INTEGER,
    pcp      VARCHAR (255),
    tmp      VARCHAR (255),
    slr      VARCHAR (255),
    hmd      VARCHAR (255),
    wnd      VARCHAR (255),
    wnd_dir  VARCHAR (255),
    atmo_dep VARCHAR (255),
    lat      REAL,
    lon      REAL,
    FOREIGN KEY (
        wgn_id
    )
    REFERENCES weather_wgn_cli (id) ON DELETE SET NULL
    );
    """
    
    _INSERTWEATHERSTATION = 'INSERT INTO weather_sta_cli VALUES(?,?,?,?,?,?,?,?,?,?,?,?)'

    _PLANTTABLE = \
    """
    (id          INTEGER       NOT NULL PRIMARY KEY,
    name        TEXT          NOT NULL,
    plnt_typ    TEXT          NOT NULL,
    gro_trig    TEXT          NOT NULL,
    nfix_co     REAL          NOT NULL,
    days_mat    REAL          NOT NULL,
    bm_e        REAL          NOT NULL,
    harv_idx    REAL          NOT NULL,
    lai_pot     REAL          NOT NULL,
    frac_hu1    REAL          NOT NULL,
    lai_max1    REAL          NOT NULL,
    frac_hu2    REAL          NOT NULL,
    lai_max2    REAL          NOT NULL,
    hu_lai_decl REAL          NOT NULL,
    dlai_rate   REAL          NOT NULL,
    can_ht_max  REAL          NOT NULL,
    rt_dp_max   REAL          NOT NULL,
    tmp_opt     REAL          NOT NULL,
    tmp_base    REAL          NOT NULL,
    frac_n_yld  REAL          NOT NULL,
    frac_p_yld  REAL          NOT NULL,
    frac_n_em   REAL          NOT NULL,
    frac_n_50   REAL          NOT NULL,
    frac_n_mat  REAL          NOT NULL,
    frac_p_em   REAL          NOT NULL,
    frac_p_50   REAL          NOT NULL,
    frac_p_mat  REAL          NOT NULL,
    harv_idx_ws REAL          NOT NULL,
    usle_c_min  REAL          NOT NULL,
    stcon_max   REAL          NOT NULL,
    vpd         REAL          NOT NULL,
    frac_stcon  REAL          NOT NULL,
    ru_vpd      REAL          NOT NULL,
    co2_hi      REAL          NOT NULL,
    bm_e_hi     REAL          NOT NULL,
    plnt_decomp REAL          NOT NULL,
    lai_min     REAL          NOT NULL,
    bm_tree_acc REAL          NOT NULL,
    yrs_mat     REAL          NOT NULL,
    bm_tree_max REAL          NOT NULL,
    ext_co      REAL          NOT NULL,
    leaf_tov_mn REAL          NOT NULL,
    leaf_tov_mx REAL          NOT NULL,
    bm_dieoff   REAL          NOT NULL,
    rt_st_beg   REAL          NOT NULL,
    rt_st_end   REAL          NOT NULL,
    plnt_pop1   REAL          NOT NULL,
    frac_lai1   REAL          NOT NULL,
    plnt_pop2   REAL          NOT NULL,
    frac_lai2   REAL          NOT NULL,
    frac_sw_gro REAL          NOT NULL,
    wnd_live    REAL          NOT NULL,
    wnd_dead    REAL          NOT NULL,
    wnd_flat    REAL          NOT NULL,
    description TEXT)
    """
    
    _URBANTABLE = \
    """
    (id          INTEGER       NOT NULL PRIMARY KEY,
    name        TEXT          NOT NULL,
    frac_imp    REAL          NOT NULL,
    frac_dc_imp REAL          NOT NULL,
    curb_den    REAL          NOT NULL,
    urb_wash    REAL          NOT NULL,
    dirt_max    REAL          NOT NULL,
    t_halfmax   REAL          NOT NULL,
    conc_totn   REAL          NOT NULL,
    conc_totp   REAL          NOT NULL,
    conc_no3n   REAL          NOT NULL,
    urb_cn      REAL          NOT NULL,
    description TEXT)
    """
    
    _FERTILIZERTABLE = \
    """
    (
    id          INTEGER       NOT NULL
                              PRIMARY KEY,
    name        VARCHAR (255) NOT NULL,
    min_n       REAL          NOT NULL,
    min_p       REAL          NOT NULL,
    org_n       REAL          NOT NULL,
    org_p       REAL          NOT NULL,
    nh3_n       REAL          NOT NULL,
    pathogens   TEXT,
    description TEXT
    )
    """
    
    _PESTICIDETABLE = \
    """
    (
    id          INTEGER       NOT NULL
                              PRIMARY KEY,
    name        VARCHAR (255) NOT NULL,
    soil_ads    REAL          NOT NULL,
    frac_wash   REAL          NOT NULL,
    hl_foliage  REAL          NOT NULL,
    hl_soil     REAL          NOT NULL,
    solub       REAL          NOT NULL,
    aq_hlife    REAL          NOT NULL,
    aq_volat    REAL          NOT NULL,
    mol_wt      REAL          NOT NULL,
    aq_resus    REAL          NOT NULL,
    aq_settle   REAL          NOT NULL,
    ben_act_dep REAL          NOT NULL,
    ben_bury    REAL          NOT NULL,
    ben_hlife   REAL          NOT NULL,
    description TEXT
    )
    """
    
    _TILLAGETABLE = \
    """
    (
    id          INTEGER       NOT NULL
                              PRIMARY KEY,
    name        VARCHAR (255) NOT NULL,
    mix_eff     REAL          NOT NULL,
    mix_dp      REAL          NOT NULL,
    rough       REAL          NOT NULL,
    ridge_ht    REAL          NOT NULL,
    ridge_sp    REAL          NOT NULL,
    description TEXT
    )
    """
    
    _SEPTICTABLE = \
    """
    (
    id          INTEGER       NOT NULL
                              PRIMARY KEY,
    name        VARCHAR (255) NOT NULL,
    q_rate      REAL          NOT NULL,
    bod         REAL          NOT NULL,
    tss         REAL          NOT NULL,
    nh4_n       REAL          NOT NULL,
    no3_n       REAL          NOT NULL,
    no2_n       REAL          NOT NULL,
    org_n       REAL          NOT NULL,
    min_p       REAL          NOT NULL,
    org_p       REAL          NOT NULL,
    fcoli       REAL          NOT NULL,
    description TEXT
    )
    """
     
    _CREATEPROJECTCONFIG = \
    """
    CREATE TABLE project_config (
    id                       INTEGER  PRIMARY KEY
                                      NOT NULL
                                      DEFAULT (1),
    project_name             TEXT,
    project_directory        TEXT,
    editor_version           TEXT,
    gis_type                 TEXT,
    gis_version              TEXT,
    project_db               TEXT,
    reference_db             TEXT,
    wgn_db                   TEXT,
    wgn_table_name           TEXT,
    weather_data_dir         TEXT,
    weather_data_format      TEXT,
    input_files_dir          TEXT,
    input_files_last_written DATETIME,
    swat_last_run            DATETIME,
    delineation_done         BOOLEAN  DEFAULT (0) 
                                      NOT NULL,
    hrus_done                BOOLEAN  DEFAULT (0) 
                                      NOT NULL,
    soil_table               TEXT,
    soil_layer_table         TEXT,
    output_last_imported     DATETIME,
    imported_gis             BOOLEAN  DEFAULT (0) 
                                      NOT NULL,
    is_lte                   BOOLEAN  DEFAULT (0) 
                                      NOT NULL
    )
    """
    
    _INSERTPROJECTCONFIG = 'INSERT INTO project_config VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)' 
        
    _SOILS_SOL_TABLE = \
    """
    (id        INTEGER NOT NULL PRIMARY KEY,
    name       TEXT NOT NULL,
    hyd_grp    TEXT NOT NULL,
    dp_tot     REAL NOT NULL,
    anion_excl REAL NOT NULL,
    perc_crk   REAL NOT NULL,
    texture    TEXT NOT NULL,
    description     TEXT)
    """
    
    _SOILS_SOL_NAME = 'soils_sol'
    
    _SOILS_SOL_LAYER_TABLE = \
    """
    (id       INTEGER NOT NULL PRIMARY KEY,
    soil_id   INTEGER NOT NULL,
    layer_num INTEGER NOT NULL,
    dp        REAL    NOT NULL,
    bd        REAL    NOT NULL,
    awc       REAL    NOT NULL,
    soil_k    REAL    NOT NULL,
    carbon    REAL    NOT NULL,
    clay      REAL    NOT NULL,
    silt      REAL    NOT NULL,
    sand      REAL    NOT NULL,
    rock      REAL    NOT NULL,
    alb       REAL    NOT NULL,
    usle_k    REAL    NOT NULL,
    ec        REAL    NOT NULL,
    caco3     REAL,
    ph        REAL,
    FOREIGN KEY (
        soil_id
    )
    REFERENCES {0} (id) ON DELETE CASCADE)
    """.format(_SOILS_SOL_NAME)
    
    _SOILS_SOL_LAYER_NAME = 'soils_sol_layer'
    
    _CREATECHANNELS = \
    """
    CREATE TABLE gis_channels (
    id       INTEGER PRIMARY KEY
                     UNIQUE
                     NOT NULL,
    subbasin INTEGER,
    areac    REAL,
    strahler INTEGER,
    len2     REAL,
    slo2     REAL,
    wid2     REAL,
    dep2     REAL,
    elevmin  REAL,
    elevmax  REAL,
    midlat   REAL,
    midlon   REAL
    )
    """
    
    _INSERTCHANNELS = 'INSERT INTO gis_channels VALUES(?,?,?,?,?,?,?,?,?,?,?,?)'
    
    _CREATEHRUS = \
    """
    CREATE TABLE gis_hrus (
    id      INTEGER PRIMARY KEY
                    UNIQUE
                    NOT NULL,
    lsu     INTEGER,
    arsub   REAL,
    arlsu   REAL,
    landuse TEXT,
    arland  REAL,
    soil    TEXT,
    arso    REAL,
    slp     TEXT,
    arslp   REAL,
    slope   REAL,
    lat     REAL,
    lon     REAL,
    elev    REAL
)
    """
    
    _INSERTHRUS = 'INSERT INTO gis_hrus VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
    
    _CREATELSUS = \
    """
    CREATE TABLE gis_lsus (
    id    INTEGER PRIMARY KEY
                  UNIQUE
                  NOT NULL,
    category   INTEGER,
    channel    INTEGER,
    area  REAL,
    slope REAL,
    len1  REAL,
    csl   REAL,
    wid1  REAL,
    dep1  REAL,
    lat   REAL,
    lon   REAL,
    elev  REAL
    )
    """
    
    _INSERTLSUS = 'INSERT INTO gis_lsus VALUES(?,?,?,?,?,?,?,?,?,?,?,?)'
    
    _CREATEPOINTS = \
    """
    CREATE TABLE gis_points (
    id       INTEGER PRIMARY KEY
                     UNIQUE
                     NOT NULL,
    subbasin INTEGER,
    ptype    TEXT,
    xpr      REAL,
    ypr      REAL,
    lat      REAL,
    lon      REAL,
    elev     REAL
    )
    """
    
    _INSERTPOINTS = 'INSERT INTO gis_points VALUES(?,?,?,?,?,?,?,?)'
    
    _CREATEROUTING = \
    """
    CREATE TABLE gis_routing (
    sourceid  INTEGER,
    sourcecat TEXT,
    hyd_typ   TEXT,
    sinkid    INTEGER,
    sinkcat   TEXT,
    percent   REAL
    )
    """
    
    _INSERTROUTING = 'INSERT INTO gis_routing VALUES(?,?,?,?,?,?)'
    
    _CREATESUBBASINS = \
    """
    CREATE TABLE gis_subbasins (
    id      INTEGER PRIMARY KEY
                    UNIQUE
                    NOT NULL,
    area    REAL,
    slo1    REAL,
    len1    REAL,
    sll     REAL,
    lat     REAL,
    lon     REAL,
    elev    REAL,
    elevmin REAL,
    elevmax REAL,
    waterid INTEGER
    )
    """
    
    _INSERTSUBBASINS = 'INSERT INTO gis_subbasins VALUES(?,?,?,?,?,?,?,?,?,?,?)'
    
    _CREATEWATER = \
    """
    CREATE TABLE gis_water (
    id    INTEGER PRIMARY KEY
                  UNIQUE
                  NOT NULL,
    wtype TEXT,
    lsu   INTEGER,
    subbasin INTEGER,
    area  REAL,
    xpr   REAL,
    ypr   REAL,
    lat   REAL,
    lon   REAL,
    elev  REAL
    )
    """
    
    _INSERTWATER = 'INSERT INTO gis_water VALUES(?,?,?,?,?,?,?,?,?,?)'
    
    _CREATEAQUIFERS = \
    """
    CREATE TABLE gis_aquifers (
    id         INTEGER PRIMARY KEY,
    category   INTEGER,
    subbasin   INTEGER,
    deep_aquifer INTEGER,
    area       REAK,
    lat        REAL,
    lon        REAL,
    elev       REAL
    );
    """
    
    _INSERTAQUIFERS = 'INSERT INTO gis_aquifers VALUES(?,?,?,?,?,?,?,?)'
    
    _CREATEDEEPAQUIFERS = \
    """
    CREATE TABLE gis_deep_aquifers (
    id         INTEGER PRIMARY KEY,
    subbasin   INTEGER,
    area       REAK,
    lat        REAL,
    lon        REAL,
    elev       REAL
    );
    """
    
    _INSERTDEEPAQUIFERS = 'INSERT INTO gis_deep_aquifers VALUES(?,?,?,?,?,?)'
    
    class WeatherStation():
        """Name, lat, long, etc for weather station."""
        def __init__(self, name, latitude, longitude, elevation):
            """Constructor."""
            ## name
            self.name = name
            ## latitude
            self.latitude = latitude
            ## longitude
            self.longitude = longitude
            ## elevation
            self.elevation = elevation
            
    class GaugeStats():
        """Number of precipitation gauges etc."""
        def __init__(self):
            """Initialize"""
            ## number of .pcp files
            self.nrgauge = 0
            ## number of pcp records used
            self.nrtot = 0
            ## number of pcp records in each pcp file
            self.nrgfil = 0
            ## number of .tmp files
            self.ntgauge = 0
            ## number of tmp records used
            self.nttot = 0
            ## number of tmp records in each tmp file
            self.ntgfil = 0
            ## number of slr records in slr file
            self.nstot = 0
            ## number of hmd records in hmd file
            self.nhtot = 0
            ## number of wnd records in wnd file
            self.nwtot = 0
            
        def setStats(self, projDirOld, projNameOld):
            """Set gauge parameters from cio file."""
            projDbOld = os.path.join(projDirOld, projNameOld + '.mdb')
            connectionString = 'DRIVER={Microsoft Access Driver (*.mdb)};DBQ=' + projDbOld
            with pyodbc.connect(connectionString, readonly=True) as connOld:
                if connOld is None:
                    ConvertToPlus.error(u'Failed to connect to old project database {0}'.format(projDbOld))
                    return
                cursorOld = connOld.cursor()
                sql = 'SELECT * FROM cio'
                row = cursorOld.execute(sql).fetchone()
                self.nrgauge = int(row[10])
                self.nrtot = int(row[11])
                self.nrgfil = int(row[12])
                self.ntgauge = int(row[14])
                self.nttot = int(row[15])
                self.ntgfil = int(row[16])
                self.nstot = int(row[18])
                self.nhtot = int(row[20])
                self.nwtot = int(row[22])

if __name__ == '__main__':
    ## QApplication object needed 
    app = QgsApplication([], True)
    app.initQgis()
    ## main program
    main = ConvertToPlus()
    ## result flag
    result = 1
    main.run()
#     try:
#         main.run()
#     except Exception:
#         ConvertToPlus.error('Error: {0}'.format(traceback.format_exc()))
#         result = 0
#     finally:
#         exit(result)    
    
