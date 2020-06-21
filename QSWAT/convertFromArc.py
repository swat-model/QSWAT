'''
Created on 8 August, 2018

@author: Chris George
\***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and\or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************\
 '''
from qgis.core import QgsApplication, QgsWkbTypes, QgsFeature, QgsGeometry, QgsPointXY, QgsField, QgsFields, QgsVectorLayer, QgsProject, QgsRasterLayer, QgsVectorFileWriter  # @UnresolvedImport
# from qgis.analysis import QgsRasterCalculator, QgsRasterCalculatorEntry
from PyQt5.QtCore import *  # @UnusedWildImport
from PyQt5.QtGui import *  # @UnusedWildImport
from PyQt5.QtWidgets import *  # @UnusedWildImport
import sys
import os
import shutil
import glob
import csv
from osgeo import gdal, ogr
import numpy
import pyodbc
import time
import subprocess
import traceback

from arc_convertdialog import ConvertDialog
from QSWATUtils import QSWATUtils
from QSWATTopology import QSWATTopology
from parameters import Parameters
from qgis._core import QgsCoordinateTransformContext

class ConvertFromArc(QObject):
    """Convert ArcSWAT project to QSWAT project."""
    
    _fullChoice = 0
    _existingChoice = 1
    _editChoice = 2  # NB this value is used in QSATPlus.py
    
    def __init__(self):
        """Initialise class variables."""
        QObject.__init__(self)
        ## plugin directory
        self.pluginDir = os.path.dirname(__file__)
        ## QGIS project
        self.proj = None
        ## ArcSWAT project directory
        self.arcProjDir = ''
        ## ArcSWAT project name
        self.arcProjName = ''
        ## QSWAT+ project directory
        self.qProjDir = ''
        ## QSWAT+ project name
        self.qProjName = ''
        ## copy of Default\\TablesOut for use with Full or Existing if ArcSWAT output database exists
        self.arcSimTablesOut = ''
        ## DEM
        self.demFile = ''
        ## coordinate reference system
        self.crs = None
        ## outlets
        self.outletFile = ''
        ## extra outlets
        self.extraOutletFile = ''
        ## watershed shapefile
        self.wshedFile = ''
        ## stream network shapefile
        self.netFile = ''
        ## landuse file
        self.landuseFile = ''
        ## soil file
        self.soilFile = ''
        # connection string for project database
        self._connStr = ''
        ## number of landuse classes reported in MasterProgress
        self.numLuClasses = 0
        ## soil option reported in MasterProgress
        self.soilOption = ''
        ## soils used in model (no GIS option only)
        self.usedSoils = set()
        ## landuses used in model (no GIS option only)
        self.usedLanduses = set()
        ## wgn stations stored as station id -> (lat, long)
        self.wgnStations = dict()
        self._dlg = ConvertDialog()
        self._dlg.setWindowFlags(self._dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint & Qt.WindowMinimizeButtonHint)
        self._dlg.fullButton.clicked.connect(self.getChoice)
        self._dlg.existButton.clicked.connect(self.getChoice)
        self._dlg.editButton.clicked.connect(self.getChoice)
        ## choice of conversion
        self.choice = ConvertFromArc._fullChoice
        ## options for creating shapefiles
        self.vectorFileWriterOptions = QgsVectorFileWriter.SaveVectorOptions()
        self.vectorFileWriterOptions.ActionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
        self.vectorFileWriterOptions.driverName = "ESRI Shapefile"
        self.vectorFileWriterOptions.fileEncoding = "UTF-8"
        
    def run(self):
        """Run the conversion."""
        settings = QSettings()
        if settings.contains('/QSWAT/LastInputPath'):
            path = settings.value('/QSWAT/LastInputPath')
        else:
            path = ''
        self.arcProjDir = None
        title = u'Select ArcSWAT directory, i.e. directory containing directories RasterStore.idb, Scenarios and Watershed.'
        while self.arcProjDir is None:
            self.arcProjDir = QFileDialog.getExistingDirectory(None, title, path)
            if self.arcProjDir is None or self.arcProjDir == '':
                return
            try:
                # convert to string from QString
                self.arcProjDir = str(self.arcProjDir)
                self.arcProjName = os.path.split(self.arcProjDir)[1]
                arcProjFile = os.path.join(self.arcProjDir, self.arcProjName + '.mxd')
                if not os.path.exists(arcProjFile):
                    ConvertFromArc.error(u'Cannot find ArcSWAT project file {0}'.format(arcProjFile))
                    self.arcProjDir = None
                    continue
            except Exception:
                ConvertFromArc.error(u'Cannot find ArcSWAT project file in {0}: {1}'.format(self.arcProjDir, traceback.format_exc()))
                self.arcProjDir = None
                continue
        # set up QSWAT project directory
        qProjFile = None
        while qProjFile is None:
            title = u'Select a parent directory to hold the new QSWAT project'
            projParent = QFileDialog.getExistingDirectory(None, title, self.arcProjDir)
            if projParent is None or projParent == '':
                return
            arcAbs = os.path.abspath(self.arcProjDir)
            qAbs = os.path.abspath(projParent)
            if qAbs.startswith(arcAbs):
                ConvertFromArc.error(u'The QSWAT project cannot be within the ArcSWAT project')
                continue
            elif arcAbs.startswith(qAbs):
                ConvertFromArc.error(u'The ArcSWAT project cannot be within the QSWAT project')
                continue
            # convert to string from QString
            projParent = str(projParent)
            if ConvertFromArc.question(u'Use {0} as new project name?'.format(self.arcProjName)) == QMessageBox.Yes:
                self.qProjName = self.arcProjName
            else:
                self.qProjName, ok = QInputDialog.getText(None, u'QSWAT project name', u'Please enter the new project name, starting with a letter:')
                if not ok:
                    return
                if not str(self.qProjName[0]).isalpha():
                    self.error(u'Project name must start with a letter')
                    continue
            self.qProjDir = os.path.join(projParent, self.qProjName)
            if os.path.exists(self.qProjDir):
                response = ConvertFromArc.question(u'Project directory {0} already exists.  Do you wish to delete it?'.format(self.qProjDir))
                if response != QMessageBox.Yes:
                    continue
                try:
                    shutil.rmtree(self.qProjDir, ignore_errors=True)
                    time.sleep(2)  # give deletion time to complete
                except Exception:
                    ConvertFromArc.error(u'Problems encountered removing {0}: {1}.  Trying to continue regardless.'.format(self.qProjDir, traceback.format_exc()))
            qProjFile = self.qProjDir + '.qgs'
            try:
                os.remove(qProjFile)
            except:
                pass
            break
        try: 
            ConvertFromArc.makeDirs(self.qProjDir)
        except Exception:
            ConvertFromArc.error(u'Failed to create QSWAT project directory {0}: {1}'.format(self.qProjDir, traceback.format_exc()))
            return
        try:
            print('Creating directories ...')
            self.createSubDirectories()
        except Exception:
            ConvertFromArc.error(u'Problems creating subdirectories: {0}'.format(traceback.format_exc()))
            return
        settings.setValue('/QSWAT/LastInputPath', self.qProjDir)
        try:
            print('Copying databases ...')
            self.copyDbs()
        except Exception:
            ConvertFromArc.error(u'Problems creating databases or project file: {0}'.format(traceback.format_exc()))
            return
        result = self._dlg.exec_()
        if result == 0:
            return
        self.proj = QgsProject.instance()
        self.proj.read(qProjFile)
        self.proj.setTitle(self.qProjName)
        # avoids annoying gdal messages
        gdal.UseExceptions()
        ogr.UseExceptions()
        print('Copying shapefiles ...')
        self.copyVisualisationShapefiles()
        print('Copying DEM ...')
        if not self.copyDEM():
            return
        if self.choice != ConvertFromArc._editChoice:
            isFull = self.choice == ConvertFromArc._fullChoice
            if not self.createOutletShapefiles(isFull):
                return
            if not isFull: 
                print('Creating existing watershed files ...')
                if not self.createExistingWatershed():
                    return
        self.setDelinParams()
        if self.choice != ConvertFromArc._editChoice:
            print('Copying landuse and soil files ...')
            self.copyLanduseAndSoil()
        # write fromArc flag to project file
        self.proj.writeEntry(self.qProjName, 'fromArc', self.choice)
        self.proj.write()
        print('Project converted')
        ConvertFromArc.information(u'ArcSWAT project {0} converted to QSWAT project {1} in {2}'.
                                  format(self.arcProjName, self.qProjName, projParent))
        response = ConvertFromArc.question(u'Run QGIS on the QSWAT project?')
        if response == QMessageBox.Yes:
            osgeo4wroot = os.environ['OSGEO4W_ROOT']
            # print('OSGEO4W_ROOT: {0}'.format(osgeo4wroot))
            qgisname = os.environ['QGISNAME']
            # print('QGISNAME: {0}'.format(gisname))
            batFile = r'{0}\bin\{1}.bat'.format(osgeo4wroot, qgisname)
            if not os.path.exists(batFile):
                title = 'Cannot find QGIS start file {0}.  Please select it.'.format(batFile)
                batFile, _ = QFileDialog.getOpenFileName(None, title, '', 'Bat files (*.bat)')
                if batFile is None:
                    return
            command = '"{0}" --project "{1}.qgs"'.format(batFile, self.qProjDir)
            #print(command)
            subprocess.call(command, shell=True)
 
    def createSubDirectories(self):
        """Create subdirectories under QSWAT project's directory."""
        watershedDir = os.path.join(self.qProjDir, 'Watershed')
        ConvertFromArc.makeDirs(watershedDir)
        arcWatershedDir = os.path.join(self.arcProjDir, 'Watershed')
        # copy contents of Shapes, Tables, temp and text
        # but don't bother with Grid: copy landuse and soil from there later
        print('- copying Watershed ...')
        shutil.copytree(os.path.join(arcWatershedDir, 'Shapes'), os.path.join(watershedDir, 'Shapes'))
        shutil.copytree(os.path.join(arcWatershedDir, 'Tables'), os.path.join(watershedDir, 'Tables'))
        shutil.copytree(os.path.join(arcWatershedDir, 'temp'), os.path.join(watershedDir, 'temp'))
        shutil.copytree(os.path.join(arcWatershedDir, 'text'), os.path.join(watershedDir, 'text'))
        sourceDir = os.path.join(self.qProjDir, 'Source')
        ConvertFromArc.makeDirs(sourceDir)
        soilDir = os.path.join(sourceDir, 'soil')
        ConvertFromArc.makeDirs(soilDir)
        landuseDir = os.path.join(sourceDir, 'crop')
        ConvertFromArc.makeDirs(landuseDir)
        # copy contents of Scenarios folder
        scenariosDir = os.path.join(self.qProjDir, 'Scenarios')
        print('- copying Scenarios ...')
        shutil.copytree(os.path.join(self.arcProjDir, 'Scenarios'), scenariosDir)
        animationDir = os.path.join(scenariosDir, r'Default\TablesOut\Animation')
        ConvertFromArc.makeDirs(animationDir)
        pngDir = os.path.join(animationDir, 'Png')
        ConvertFromArc.makeDirs(pngDir)
        if self.choice != ConvertFromArc._editChoice:
            # make extra copy of default scenario if we have ArcSWAT outputs
            outputDb = os.path.join(scenariosDir, r'Default\TablesOut\SWATOutput.mdb')
            if os.path.exists(outputDb):
                arcSim = ConvertFromArc.getNewFileOrDir(scenariosDir, 'ArcSim', '')
                shutil.copytree(os.path.join(scenariosDir, 'Default'), arcSim)
                self.arcSimTablesOut = os.path.join(arcSim, 'TablesOut')
        
    def copyDbs(self):
        """Set up project and reference databases, plus QGIS project file."""
        arcProjDb = os.path.join(self.arcProjDir, self.arcProjName + '.mdb')
        qProjDb = os.path.join(self.qProjDir, self.qProjName + '.mdb')
        arcRefDb = os.path.join(self.arcProjDir, 'SWAT2012.mdb')
        qRefDb = os.path.join(self.qProjDir, 'QSWATRef2012.mdb')
        projFileTemplate = os.path.join(self.pluginDir, r'Databases\example.qgs')
        shutil.copy(arcProjDb, qProjDb)
        shutil.copy(arcRefDb, qRefDb)
        shutil.copy(projFileTemplate, self.qProjDir + '.qgs')
        self._connStr = Parameters._ACCESSSTRING + r'{0};'.format(qProjDb.replace('\\', '/'))
    
    def copyDEM(self):
        """Copy ESRI DEM as GeoTiff into QSWAT project."""
        inDEM = os.path.join(self.arcProjDir, r'Watershed\Grid\sourcedem\hdr.adf')
        if not os.path.exists(inDEM):
            ConvertFromArc.error(u'Cannot find DEM {0}'.format(inDEM))
            return False
        outDEM = os.path.join(self.qProjDir, r'Source\dem.tif')
        if not ConvertFromArc.copyESRIGrid(inDEM, outDEM):
            return False
        self.demFile = outDEM
        # need to provide a prj
        demLayer = QgsRasterLayer(self.demFile, 'DEM')
        QSWATUtils.writePrj(self.demFile, demLayer)
        self.crs = demLayer.crs()
        return True
        
    @staticmethod
    def copyESRIGrid(inFile, outFile):
        """Copy ESRI grid as a GeoTiff."""
        # use GDAL CreateCopy to ensure result is a GeoTiff
        inDs = gdal.Open(inFile)
        driver = gdal.GetDriverByName('GTiff')
        outDs = driver.CreateCopy(outFile, inDs, 0)
        if outDs is None or not os.path.exists(outFile):
            ConvertFromArc.error(u'Failed to create dem in geoTiff format')
            return False
        return True
    
    def copyVisualisationShapefiles(self):
        """Copy subbasin, stream and hru shapefiles into TablesOut folder if they exist.
        
        Also strip them of unwanted fields.
        """
        tablesOutDir = os.path.join(self.qProjDir, r'Scenarios\Default\TablesOut')
        shapesDir = os.path.join(self.qProjDir, r'Watershed\Shapes')
        arcSubsShapefile = self.getMaxFileOrDir(shapesDir, 'subs', '.shp')
        if os.path.exists(arcSubsShapefile):
            QSWATUtils.copyShapefile(arcSubsShapefile, 'subs', tablesOutDir)
            subsShapefile = os.path.join(tablesOutDir, 'subs.shp')
            subsLayer = QgsVectorLayer(subsShapefile, 'Watershed', 'ogr')
            provider = subsLayer.dataProvider()
            QSWATTopology.removeFields(provider, ['Subbasin'], subsShapefile, True)
            if os.path.isdir(self.arcSimTablesOut):
                QSWATUtils.copyShapefile(subsShapefile, 'subs', self.arcSimTablesOut)
        arcRivsShapefile = self.getMaxFileOrDir(shapesDir, 'riv', '.shp')
        if os.path.exists(arcRivsShapefile):
            QSWATUtils.copyShapefile(arcRivsShapefile, 'rivs', tablesOutDir)
            rivsShapefile = os.path.join(tablesOutDir, 'rivs.shp')
            rivsLayer = QgsVectorLayer(rivsShapefile, 'Streams', 'ogr')
            provider = rivsLayer.dataProvider()
            # add penwidth field
            OK = provider.addAttributes([QgsField(QSWATTopology._PENWIDTH, QVariant.Double)])
            if not OK:
                ConvertFromArc.error(u'Cannot add {0} field to streams shapefile {1}'.format(QSWATTopology._PENWIDTH, rivsShapefile))
                return
            wid2Data = self.getWid2Data()
            QSWATTopology.setPenWidth(wid2Data, provider, True)
            QSWATTopology.removeFields(provider, ['Subbasin', QSWATTopology._PENWIDTH], rivsShapefile, True)
            if os.path.isdir(self.arcSimTablesOut):
                QSWATUtils.copyShapefile(rivsShapefile, 'rivs', self.arcSimTablesOut)
        arcHrusShapefile = self.getMaxFileOrDir(shapesDir, 'hru', '.shp')
        if os.path.exists(arcHrusShapefile):
            QSWATUtils.copyShapefile(arcHrusShapefile, 'hrus', tablesOutDir)
            hrusShapefile = os.path.join(tablesOutDir, 'hrus.shp')
            hrusLayer = QgsVectorLayer(hrusShapefile, 'HRUs', 'ogr')
            provider = hrusLayer.dataProvider()
            fields = provider.fields()
            # ArcSWAT HRUs shapefile has column HRU_GIS: rename to HRUGIS
            # rename attributes only from QGIS 2.16
            hruIndex = fields.indexOf('HRU_GIS')
            provider.renameAttributes({hruIndex : 'HRUGIS'})
            hrusLayer.updateFields()
#             if not provider.addAttributes([QgsField('HRUGIS', QVariant.String, len=20)]):
#                 ConvertFromArc.error(u'Could not edit HRUs shapefile {0}'.format(hrusShapefile))
#                 return
#             hru_Index = fields.indexOf('HRU_GIS')
#             if hru_Index < 0:
#                 ConvertFromArc.error(u'Could not find HRU_GIS field in HRUs shapefile {0}'.format(hrusShapefile))
#                 return
#             hruIndex = fields.indexOf('HRUGIS')
#             mmap = dict()
#             for f in provider.getFeatures():
#                 mmap[f.id()] = {hruIndex : f[hru_Index]}
#             if not provider.changeAttributeValues(mmap):
#                 ConvertFromArc.error(u'Could not edit HRUs shapefile {0}'.format(hrusShapefile))
#                 return
#             QSWATTopology.removeFields(provider, ['HRUGIS'], hrusShapefile, True)
            if os.path.isdir(self.arcSimTablesOut):
                QSWATUtils.copyShapefile(hrusShapefile, 'hrus', self.arcSimTablesOut)
    
    def createOutletShapefiles(self, isFull):
        """Create inlets\outlets file and extra inlets\outlets file.  Return true if OK.
        
        The inlets/outlets shapefile is created even if not isFull, although it is not recorded in the project file,
        as it might be useful to users if they decide to delineate again.
        """
        if isFull:
            print('Creating inlets/outlets file ...')
        qOutlets = os.path.join(self.qProjDir, r'Watershed\Shapes\out.shp')
        rivsFile = ConvertFromArc.getMaxFileOrDir(os.path.join(self.arcProjDir, r'Watershed\Shapes'), 'riv', '.shp')
        prjFile = os.path.splitext(rivsFile)[0] + '.prj'
        rivsLayer = QgsVectorLayer(rivsFile, 'Rivers', 'ogr')
        rivsFields = rivsLayer.fields()
        subIndex = rivsFields.indexOf('Subbasin')
        toNodeIndex = rivsFields.indexOf('TO_NODE')
        # collect outlet subbasins
        outletSubs = set()
        for river in rivsLayer.getFeatures():
            if river[toNodeIndex] == 0:
                outletSubs.add(river[subIndex])
        fields = ConvertFromArc.makeOutletFields()
        writer = self.makeOutletFile(qOutlets, fields, prjFile)
        if writer is None:
            return False
        # add main outlets and inlets to outlets file
        idIndex = fields.indexOf('ID')
        inletIndex = fields.indexOf('INLET')
        resIndex = fields.indexOf('RES')
        ptsrcIndex = fields.indexOf('PTSOURCE')
        # cannot use monitoring_points shapefile as it omits reservoirs
        # instead use MonitoringPoint table
        idNum = 0
        reservoirs = []
        ptsrcs = []
        with pyodbc.connect(self._connStr, readonly=True) as conn:
            sql = 'SELECT Xpr, Ypr, Type, Subbasin FROM MonitoringPoint'
            for row in conn.cursor().execute(sql):
                typ = row.Type
                if typ in ['T', 'O'] or int(row.Subbasin) in outletSubs and typ == 'L':
                    qPt = QgsFeature(fields)
                    qPt.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(row.Xpr), float(row.Ypr))))
                    qPt.setAttribute(idIndex, idNum)
                    idNum += 1
                    qPt.setAttribute(inletIndex, 0)
                    qPt.setAttribute(resIndex, 0)
                    qPt.setAttribute(ptsrcIndex, 0)
                    writer.addFeature(qPt)
                elif typ in ['W', 'I']:
                    qPt = QgsFeature(fields)
                    qPt.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(row.Xpr), float(row.Ypr))))
                    qPt.setAttribute(idIndex, idNum)
                    idNum += 1
                    qPt.setAttribute(inletIndex, 1)
                    qPt.setAttribute(resIndex, 0)
                    qPt.setAttribute(ptsrcIndex, 0)
                    writer.addFeature(qPt)
                elif typ == 'R':
                    reservoirs.append(row)
                elif typ in ['P', 'D']:
                    ptsrcs.append(row)
        # flush writer
        del writer
        self.outletFile = qOutlets
        if len(reservoirs) != 0 or len(ptsrcs) != 0:
            # need an extra outlets layer
            # note the file name arcextra.shp is used by delineation.py and by FileTypes in QSWATUtils.py
            # and if changed here must be changed there
            print('Creating reservoirs and point sources file ...')
            qExtra = os.path.join(self.qProjDir, r'Watershed\Shapes\arcextra.shp')
            writer = self.makeOutletFile(qExtra, fields, prjFile, basinWanted=True)
            if writer is None:
                return False
            outSubIndex = fields.indexOf('Subbasin')
            idNum = 0
            for res in reservoirs:
                qPt = QgsFeature(fields)
                qPt.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(res.Xpr), float(res.Ypr))))
                qPt.setAttribute(idIndex, idNum)
                idNum += 1
                qPt.setAttribute(inletIndex, 0)
                qPt.setAttribute(resIndex, 1)
                qPt.setAttribute(ptsrcIndex, 0)
                qPt.setAttribute(outSubIndex, int(res.Subbasin))
                writer.addFeature(qPt)
            for ptsrc in ptsrcs:
                qPt = QgsFeature(fields)
                qPt.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(ptsrc.Xpr), float(ptsrc.Ypr))))
                qPt.setAttribute(idIndex, idNum)
                idNum += 1
                qPt.setAttribute(inletIndex, 1)
                qPt.setAttribute(resIndex, 0)
                qPt.setAttribute(ptsrcIndex, 1)
                qPt.setAttribute(outSubIndex, int(ptsrc.Subbasin))
                writer.addFeature(qPt)
            self.extraOutletFile = qExtra
            # flush writer
            del writer
        return True
    
    # attempt to use flow accumulation and direction from ArcSWAT to get delineation consistent with ArcSWAT
    # problems:
    # - inlets make it hard to count subbasins (upstream ones missing from ArcSWAT;s subs1.shp)
    # - stream reaches affected similarly by inlets
    # - should snap inlets and outlets - TauDEM move can change subbasin boundaries
    # - still have to match subbasin numbers to ArcSWAT numbering
#===============================================================================
#     def createExistingWatershed(self):
#         """Try to create ArcSWAT watershed using arc's flow direction and accumulation."""
#         # make GeoTiff from flow direction with TauDEM d8 values
#         arcD8File = os.path.join(self.arcProjDir, r'Watershed\Grid\flowdir\hdr.adf')
#         if not os.path.exists(arcD8File):
#             ConvertFromArc.error(u'Cannot find arc flow direction {0}'.format(arcD8File))
#             return False
#         arcD8Layer = QgsRasterLayer(arcD8File, 'F')
#         threshold = int(arcD8Layer.width() * arcD8Layer.height() * 0.01)
#         entry = QgsRasterCalculatorEntry()
#         entry.bandNumber = 1
#         entry.raster = arcD8Layer
#         entry.ref = 'F@1' 
#         d8File = os.path.join(self.qProjDir, r'Watershed\Rasters\DEM\d8.tif')
#         formula = '("F@1" = 1) + ("F@1" = 128) * 2 + ("F@1" = 64) * 3 + ("F@1" = 32) * 4 + ("F@1" = 16) * 5 + ("F@1" = 8) * 6 + ("F@1" = 4) * 7 + ("F@1" = 2) * 8'
#         calc = QgsRasterCalculator(formula, d8File, 'GTiff', arcD8Layer.extent(), arcD8Layer.width(), arcD8Layer.height(), [entry])
#         result = calc.processCalculation(p=None)
#         if result == 0:
#             assert os.path.exists(d8File), u'QGIS calculator formula {0} failed to write output {1}'.format(formula, d8File)
#             QSWATUtils.copyPrj(self.demFile, d8File)
#         else:
#             QSWATUtils.error(u'QGIS calculator formula {0} failed: returned {1}'.format(formula, result), True)
#             return False 
#         arcAd8 = os.path.join(self.arcProjDir, r'Watershed\Grid\flowacc\hdr.adf')
#         if not os.path.exists(arcAd8):
#             ConvertFromArc.error(u'Cannot find arc flow accumulation {0}'.format(arcAd8))
#             return False
#         ad8File = os.path.join(self.qProjDir, r'Watershed\Rasters\DEM\ad8.tif')
# #         arcAd8Layer = QgsRasterLayer(arcAd8, 'F')
# #         entry.raster = arcAd8Layer
# #         formula = '"F@1"'
# #         calc = QgsRasterCalculator(formula, ad8File, 'GTiff', arcAd8Layer.extent(), arcAd8Layer.width(), arcAd8Layer.height(), [entry])
# #         result = calc.processCalculation(p=None)
# #         if result == 0:
# #             assert os.path.exists(ad8File), u'QGIS calculator formula {0} failed to write output {1}'.format(formula, ad8File)
# #             QSWATUtils.copyPrj(self.demFile, ad8File)
# #         else:
# #             QSWATUtils.error(u'QGIS calculator formula {0} failed: returned {1}'.format(formula, result), True)
# #             return False 
#         # use GDAL CreateCopy to ensure result is a GeoTiff
#         inDs = gdal.Open(arcAd8)
#         driver = gdal.GetDriverByName('GTiff')
#         outDs = driver.CreateCopy(ad8File, inDs, 0)
#         if outDs is None or not os.path.exists(ad8File):
#             ConvertFromArc.error(u'Failed to create flow accumulation in geoTiff format')
#             return False 
#         QSWATUtils.copyPrj(self.demFile, ad8File)
#         # create Dinf slopes
#         (base, suffix) = os.path.splitext(self.demFile)
#         shapesBase = os.path.join(self.qProjDir, r'Watershed\Shapes')
#         numProcesses = 0
#         felFile = base + 'fel' + suffix
#         slpFile = base + 'slp' + suffix
#         angFile = base + 'ang' + suffix
#         ok = TauDEMUtils.runPitFill(self.demFile, felFile, numProcesses, None) 
#         if not ok:
#             ConvertFromArc.error(u'Failed to create pit filled DEM {0}'.format(felFile))
#             return False
#         ok = TauDEMUtils.runDinfFlowDir(felFile, slpFile, angFile, numProcesses, None)  
#         if not ok:
#             ConvertFromArc.error(u'Failed to create DInf slopes {0}'.format(slpFile))
#             return  False
#         ok = TauDEMUtils.runAreaD8(d8File, ad8File, self.outletFile, None, numProcesses, None)   
#         if not ok:
#             ConvertFromArc.error(u'Failed to run area d8 on outlets')
#             return False
#         gordFile = base + 'gord' + suffix
#         plenFile = base + 'plen' + suffix
#         tlenFile = base + 'tlen' + suffix
#         ok = TauDEMUtils.runGridNet(d8File, plenFile, tlenFile, gordFile, self.outletFile, numProcesses, None)  
#         if not ok:
#             ConvertFromArc.error(u'Failed to create upslope lengths'.format(plenFile))
#             return False
#         # need to mask dem for use with arc d8 and ad8 files
#         demClip = base + 'masked' + suffix
#         d8Layer = QgsRasterLayer(d8File, 'F')
#         entry1 = QgsRasterCalculatorEntry()
#         entry1.bandNumber = 1
#         entry1.raster = d8Layer
#         entry1.ref = 'F@1' 
#         demLayer = QgsRasterLayer(self.demFile, 'D')
#         entry2 = QgsRasterCalculatorEntry()
#         entry2.bandNumber = 1
#         entry2.raster = demLayer
#         entry2.ref = 'D@1' 
#         formula = '("F@1" > 0) * "D@1"'
#         calc = QgsRasterCalculator(formula, demClip, 'GTiff', d8Layer.extent(), d8Layer.width(), d8Layer.height(), [entry1, entry2])
#         result = calc.processCalculation(p=None)
#         if result == 0:
#             assert os.path.exists(demClip), u'QGIS calculator formula {0} failed to write output {1}'.format(formula, demClip)
#             QSWATUtils.copyPrj(self.demFile, demClip)
#         else:
#             ConvertFromArc.error(u'QGIS calculator formula {0} failed: returned {1}'.format(formula, result))
#             return False 
#         QSWATUtils.copyPrj(self.demFile, demClip)
#         assert os.path.exists(demClip), u'Failed to create clipped raster  {2} by clipping {0} with {1}'.format(self.demFile, d8File, demClip)
#         srcStreamFile = base + 'srcStream' + suffix
#         arcSubsFile = self.getMaxFileOrDir(os.path.join(self.arcProjDir, r'Watershed\Shapes'), 'subs', '.shp')
#         arcSubsLayer = QgsVectorLayer(arcSubsFile, 'Subbasins', 'ogr')
#         numSubs = arcSubsLayer.featureCount()
#         prevLowThreshold = 0
#         prevHighThreshold = threshold * 10
#         while True:
#             ok = TauDEMUtils.runThreshold(ad8File, srcStreamFile, str(threshold), numProcesses, None) 
#             if not ok:
#                 ConvertFromArc.error(u'Failed to create stream raster {0}'.format(srcStreamFile))
#                 return False
#             outletMovedFile = os.path.splitext(self.outletFile)[0] + '_moved.shp'
#             ok = TauDEMUtils.runMoveOutlets(d8File, srcStreamFile, self.outletFile, outletMovedFile, numProcesses, None)
#             if not ok:
#                 ConvertFromArc.error(u'Moving outlets to streams failed')
#                 return False
#             ordStreamFile = base + 'ordStream' + suffix
#             streamFile = os.path.join(shapesBase,'stream.shp')
#             treeStreamFile = base + 'treeStream.dat'
#             coordStreamFile = base + 'coordStream.dat'
#             wStreamFile = base + 'wStream' + suffix
#             ok = TauDEMUtils.runStreamNet(demClip, d8File, ad8File, srcStreamFile, outletMovedFile, ordStreamFile, treeStreamFile, coordStreamFile,
#                                               streamFile, wStreamFile, False, numProcesses, None)
#             if not ok:
#                 ConvertFromArc.error(u'Failed to create stream shapefile {0}'.format(streamFile))
#                 return False
#             QSWATUtils.copyPrj(self.demFile, streamFile)
#             subbasinsLayer = None
#             subbasinsFile = os.path.join(shapesBase, 'subbasins.shp')
#             QSWATUtils.tryRemoveFiles(subbasinsFile)
#             subbasinsLayer = self.createWatershedShapefile(wStreamFile, subbasinsFile)
#             if subbasinsLayer is None:
#                 return False
#             numCreatedSubs = subbasinsLayer.featureCount()
#             print('Threshold {0} produced {1} subbasins: seeking for {2}'.format(threshold, numCreatedSubs, numSubs))
#             if numCreatedSubs < numSubs:
#                 # reduce threshold
#                 prevHighThreshold = threshold
#                 nextThreshold = (prevLowThreshold + threshold) // 2
#             elif numCreatedSubs > numSubs:
#                 # increase threshold
#                 prevLowThreshold = threshold
#                 nextThreshold = (prevHighThreshold + threshold) // 2
#             else:
#                 break
#             if nextThreshold == threshold:
#                 # avoid an endless loop
#                 break
#             threshold = nextThreshold
#         return False
#     
#     def createWatershedShapefile(self, wFile, subbasinsFile):
#         """Create watershed shapefile subbasinsFile from watershed grid wFile."""
#         # create shapes from wFile
#         wDs = gdal.Open(wFile, gdal.GA_ReadOnly)
#         if wDs is None:
#             QSWATUtils.error('Cannot open watershed grid {0}'.format(wFile), self._gv.isBatch)
#             return None
#         wBand = wDs.GetRasterBand(1)
#         noData = wBand.GetNoDataValue()
#         transform = wDs.GetGeoTransform()
#         numCols = wDs.RasterXSize
#         numRows = wDs.RasterYSize
#         isConnected4 = True
#         shapes = Polygonize(isConnected4, numCols, noData, 
#                             QgsPointXY(transform[0], transform[3]), transform[1], abs(transform[5]))
#         for row in range(numRows):
#             wBuffer = wBand.ReadAsArray(0, row, numCols, 1).astype(int)
#             shapes.addRow(wBuffer.reshape([numCols]), row)
#         shapes.finish()
#         # create shapefile
#         fields = QgsFields()
#         fields.append(QgsField('Basin', QVariant.Int))
#         writer = QgsVectorFileWriter(subbasinsFile, 'CP1250', fields, 
#                                      Qgis.WKBMultiPolygon, None, 'ESRI Shapefile')
#         if writer.hasError() != QgsVectorFileWriter.NoError:
#             ConvertFromArc.error('Cannot create subbasin shapefile {0}: {1}'. \
#                              format(subbasinsFile, writer.errorMessage()))
#             return None
#         # need to release writer before making layer
#         writer = None
#         # wFile may not have a .prj (being a .tif) so use DEM's
#         QSWATUtils.copyPrj(self.demFile, subbasinsFile)
#         subbasinsLayer = QgsVectorLayer(subbasinsFile, 'Subbasins', 'ogr')
#         provider = subbasinsLayer.dataProvider()
#         basinIndex = fields.indexFromName('Basin')
#         for basin in shapes.shapes:
#             geometry = shapes.getGeometry(basin)
#             feature = QgsFeature(fields)
#             # basin is a numpy.int32 so we need to convert it to a Python int
#             feature.setAttribute(basinIndex, int(basin))
#             feature.setGeometry(geometry)
#             if not provider.addFeatures([feature]):
#                 ConvertFromArc.error('Unable to add feature to watershed shapefile {0}'. \
#                                  format(subbasinsFile))
#                 return None
#         return subbasinsLayer
#===============================================================================
    
    def createExistingWatershed(self):
        """Make watershed and stream network shapefiles based on subsn.shp and rivn.shp."""
        # create subbasins shapefile
        arcShapesDir = os.path.join(self.arcProjDir, r'Watershed\Shapes')
        arcSubsFile = ConvertFromArc.getMaxFileOrDir(arcShapesDir, 'subs', '.shp')
        qSourceDir = os.path.join(self.qProjDir, 'Source')
        QSWATUtils.copyShapefile(arcSubsFile, 'wshed', qSourceDir)
        qSubsFile = os.path.join(qSourceDir, 'wshed.shp')
        qSubsLayer = QgsVectorLayer(qSubsFile, 'Subbasins', 'ogr')
        provider = qSubsLayer.dataProvider()
        provider.addAttributes([QgsField(QSWATTopology._POLYGONID, QVariant.Int)])
        fields = provider.fields()
        subIndex = fields.indexOf('Subbasin')
        polyIndex = fields.indexOf(QSWATTopology._POLYGONID)
        # no renameAttributes in QGIS 2.6
#         if not provider.renameAttributes({subIndex : QSWATTopology._POLYGONID}):
#             ConvertFromArc.error(u'Could not edit subbasins shapefile {0}'.format(qSubsFile))
#             return False
        mmap = dict()
        for f in provider.getFeatures():
            mmap[f.id()] = {polyIndex : f[subIndex]}
        if not provider.changeAttributeValues(mmap):
            ConvertFromArc.error(u'Could not edit subbasins shapefile {0}'.format(qSubsFile))
            return False
        self.wshedFile = qSubsFile
        # create stream network shapefile
        arcRivFile = ConvertFromArc.getMaxFileOrDir(arcShapesDir, 'riv', '.shp')
        QSWATUtils.copyShapefile(arcRivFile, 'net', qSourceDir)
        # add WSNO, LINKNO, DSLINKNO and Length as copies of Subbasin, FROM_NODE, TO_NODE and Shape_Leng
        # plus Drop as MaxEl - MinEl, or 0 if this is negative
        # (TO_NODE of 0 becomes -1)
        qNetFile = os.path.join(qSourceDir, 'net.shp')
        qNetLayer = QgsVectorLayer(qNetFile, 'Streams', 'ogr')
        provider = qNetLayer.dataProvider()
        f1 = QgsField(QSWATTopology._LINKNO, QVariant.Int)
        f2 = QgsField(QSWATTopology._DSLINKNO, QVariant.Int)
        f3 = QgsField(QSWATTopology._WSNO, QVariant.Int)
        f4 = QgsField(QSWATTopology._LENGTH, QVariant.Double)
        f5 = QgsField(QSWATTopology._DROP, QVariant.Double)
        provider.addAttributes([f1, f2, f3, f4, f5])
        fields = provider.fields()
        subIndex = fields.indexOf('Subbasin')
        fromIndex = fields.indexOf('FROM_NODE')
        toIndex = fields.indexOf('TO_NODE')
        arcLenIndex = fields.indexOf('Shape_Leng')
        minElIndex = fields.indexOf('MinEl')
        maxElIndex = fields.indexOf('MaxEl')
        linkIndex = fields.indexOf(QSWATTopology._LINKNO)
        dsIndex = fields.indexOf(QSWATTopology._DSLINKNO)
        wsnoIndex = fields.indexOf(QSWATTopology._WSNO)
        lenIndex = fields.indexOf(QSWATTopology._LENGTH)
        dropIndex = fields.indexOf(QSWATTopology._DROP)
        mmap = dict()
        for f in provider.getFeatures():
            subbasin = f[subIndex]
            toNode = f[toIndex]
            drop = max(0, f[maxElIndex] - f[minElIndex]) # avoid negative drop
            mmap[f.id()] = {wsnoIndex : subbasin,
                            linkIndex : f[fromIndex], 
                            dsIndex : -1 if toNode == 0 else toNode,
                            lenIndex : f[arcLenIndex],
                            dropIndex : drop}
        if not provider.changeAttributeValues(mmap):
            ConvertFromArc.error(u'Could not edit streams shapefile {0}'.format(qNetFile))
            return False
        self.netFile = qNetFile
        return True
    
    @staticmethod
    def makeOutletFields():
        """Create fields for outlets file."""
        fields = QgsFields()
        fields.append(QgsField('ID', QVariant.Int))
        fields.append(QgsField('INLET', QVariant.Int))
        fields.append(QgsField('RES', QVariant.Int))
        fields.append(QgsField('PTSOURCE', QVariant.Int))
        return fields
        
    def makeOutletFile(self, filePath, fields, prjFile, basinWanted=False):
        """Create filePath with fields needed for outlets file, 
        copying prjFile.  Return true if OK.
        """
        if os.path.exists(filePath):
            QSWATUtils.removeFiles(filePath)
        if basinWanted:
            fields.append(QgsField('Subbasin', QVariant.Int))
        transform_context = QgsProject.instance().transformContext()
        writer = QgsVectorFileWriter.create(filePath, fields, QgsWkbTypes.Point, 
                                            self.crs, transform_context, self.vectorFileWriterOptions)
        if writer.hasError() != QgsVectorFileWriter.NoError:
            ConvertFromArc.error(u'Cannot create outlets shapefile {0}: {1}'.format(filePath, writer.errorMessage()))
            return None
        shutil.copy(prjFile, os.path.splitext(filePath)[0] + '.prj')
        return writer
    
    def setDelinParams(self):
        """Write delineation parameters to project file."""
        self.proj.writeEntry(self.qProjName, 'delin/useGridModel', False)
        self.proj.writeEntry(self.qProjName, 'delin/DEM', r'Source\{0}'.format(os.path.split(self.demFile)[1]))
        if self.choice != ConvertFromArc._editChoice:
            isFull = self.choice == ConvertFromArc._fullChoice
            self.proj.writeEntry(self.qProjName, 'delin/existingWshed', not isFull)
            if not isFull:
                self.proj.writeEntry(self.qProjName, 'delin/net', r'Source\{0}'.format(os.path.split(self.netFile)[1]))
                self.proj.writeEntry(self.qProjName, 'delin/wshed', r'Source\{0}'.format(os.path.split(self.wshedFile)[1]))
            self.proj.writeEntry(self.qProjName, 'delin/useOutlets', isFull)
            if isFull:
                self.proj.writeEntry(self.qProjName, 'delin/outlets', r'Watershed\Shapes\{0}'.format(os.path.split(self.outletFile)[1]))
            self.proj.writeEntry(self.qProjName, 'delin/extraOutlets', r'Watershed\Shapes\{0}'.format(os.path.split(self.extraOutletFile)[1]))
        self.proj.write()
    
    def copyLanduseAndSoil(self):
        """Copy landuse and soil rasters, add to project file, make lookup csv files."""
        self.setSoilOption()
        landuseFile = ConvertFromArc.getMaxFileOrDir(os.path.join(self.arcProjDir, r'Watershed\Grid'), 'landuse', '')
        ConvertFromArc.copyFiles(landuseFile, os.path.join(self.qProjDir, r'Source\crop'))
        self.landuseFile = os.path.join(self.qProjDir, r'Source\crop\{0}\hdr.adf'.format(os.path.split(landuseFile)[1]))
        soilFile = ConvertFromArc.getMaxFileOrDir(os.path.join(self.arcProjDir, r'Watershed\Grid'), 'landsoils', '')
        ConvertFromArc.copyFiles(soilFile, os.path.join(self.qProjDir, r'Source\soil'))
        self.soilFile = os.path.join(self.qProjDir, r'Source\soil\{0}\hdr.adf'.format(os.path.split(soilFile)[1]))
        self.setLanduseAndSoilParams(landuseFile, soilFile)
        self.generateLookup('landuse')
        if self.soilOption != 'ssurgo':
            self.generateLookup('soil')
            if self.soilOption != 'name':
                self.proj.writeEntry(self.qProjName, 'soil/useSTATSGO', True)
        else:
            self.proj.writeEntry(self.qProjName, 'soil/useSSURGO', True)
        self.proj.write()
        
    def setLanduseAndSoilParams(self, landuseFile, soilFile):
        """Write landuse and parameters to project file, plus slope limits."""
        self.proj.writeEntry(self.qProjName, 'landuse/file', r'Source\crop\{0}\hdr.adf'.format(os.path.split(landuseFile)[1]))
        self.proj.writeEntry(self.qProjName, 'soil/file', r'Source\soil\{0}\hdr.adf'.format(os.path.split(soilFile)[1]))
        report = os.path.join(self.arcProjDir, r'Watershed\text\LandUseSoilsReport.txt')
        slopeBands = ConvertFromArc.slopeBandsFromReport(report)
        self.proj.writeEntry(self.qProjName, 'hru/slopeBands', slopeBands)
        self.proj.write()
        
    
    def generateLookup(self, landuseOrSoil):
        """Generate lookup table for landuse or soil if required."""
        msgBox = QMessageBox()
        msgBox.setWindowTitle('Generate {0} lookup csv file'.format(landuseOrSoil))
        text = """
        Do you want to generate a {0} lookup csv file in the project directory?
        """.format(landuseOrSoil)
        infoText = """
        If you already have a suitable csv file click No.
        Otherwise click Yes and the tool will attempt to create a csv file 
        called {0}_lookup.csv in the project directory.
        This involves reading the {0} raster and may take a few minutes.
        """.format(landuseOrSoil)
        msgBox.setText(QSWATUtils.trans(text))
        msgBox.setInformativeText(QSWATUtils.trans(infoText))
        msgBox.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        result = msgBox.exec_()
        if result == QMessageBox.Yes:
            print('Creating {0} lookup table ...'.format(landuseOrSoil))
            self.generateCsv(landuseOrSoil)
            
    def generateCsv(self, landuseOrSoil):
        """Generate landuse or soil lookup csv file by comparing percentages from report and raster."""
        percents = self.percentsFromReport(landuseOrSoil)
        if len(percents) == 0:
            return
        if landuseOrSoil == 'landuse':
            raster = self.landuseFile
        else:
            raster = self.soilFile 
        rasterPercents = self.percentsFromRaster(raster)
        if len(rasterPercents) == 0:
            return
        self.makeLookupCsv(percents, rasterPercents, landuseOrSoil)
    
    def percentsFromReport(self, landuseOrSoil):
        """Generate and return map of value to percent for soil or landuse from landuse and soil report."""
        report = os.path.join(self.arcProjDir, r'Watershed\text\LandUseSoilsReport.txt')
        if not os.path.exists(report):
            ConvertFromArc.error('Cannot find {0}'.format(report))
            return dict()
        if landuseOrSoil == 'landuse':
            return ConvertFromArc.landusePercentsFromReport(report)
        else:
            return ConvertFromArc.soilPercentsFromReport(report)
        
    @staticmethod
    def landusePercentsFromReport(report):
        """Return percents of landuses."""
        with open(report, 'r') as reader:
            found = False
            while not found:
                line = reader.readline()
                found = line.startswith('LANDUSE:')
            if not found:
                ConvertFromArc.error('Cannot find "LANDUSE:" in {0}'.format(report)) 
                return dict()
            result = dict()
            while True:
                line = reader.readline()
                start = line.find('-->') + 3
                fields = line[start:].split()
                if len(fields) != 4:
                    break
                landuse = fields[0]
                percent = float(fields[3])
                result[landuse] = percent
            return result
                
    @staticmethod
    def soilPercentsFromReport(report):
        """Return percents of soils."""
        with open(report, 'r') as reader:
            found = False
            while not found:
                line = reader.readline()
                found = line.startswith('SOILS:')
            if not found:
                ConvertFromArc.error('Cannot find "SOILS:" in {0}'.format(report)) 
                return dict()
            result = dict()
            while True:
                line = reader.readline()
                fields = line.split()
                if len(fields) != 4:
                    break
                soil = fields[0]
                percent = float(fields[3])
                result[soil] = percent
            return result
        
    @staticmethod
    def slopeBandsFromReport(report):
        """Extract slope bands string from landuse and soils report."""
        with open(report, 'r') as reader:
            found = False
            while not found:
                line = reader.readline()
                found = line.startswith('SLOPE:')
            if not found:
                ConvertFromArc.error('Cannot find "SLOPE:" in {0}'.format(report)) 
                return '[0, 9999]'
            result = '['
            first = True
            while True:
                line = reader.readline()
                fields = line.split()
                if len(fields) != 4:
                    result += ', 9999]'
                    break
                if first:
                    first = False
                else:
                    result += ', '
                result += fields[0].split('-')[0]
            return result      
    
    def percentsFromRaster(self, raster):
        """Return map of raster values to percents of raster cells with that value."""
        counts = dict()
        total = 0
        ds = gdal.Open(raster, gdal.GA_ReadOnly)
        numRows = ds.RasterYSize
        numCols = ds.RasterXSize
        band = ds.GetRasterBand(1)
        noData = band.GetNoDataValue()
        buff = numpy.empty([1, numCols], dtype=int)
        for row in range(numRows):
            buff = band.ReadAsArray(0, row, numCols, 1)
            for col in range(numCols):
                val = buff[0, col]
                if val == noData:
                    continue
                total += 1
                if val in counts:
                    counts[val] += 1
                else:
                    counts[val] = 1
        # convert counts to percent
        result = dict()
        for val, count in counts.items():
            result[val] = (float(count) / total) * 100
        return result
    
    def makeLookupCsv(self, percents, rasterPercents, landuseOrSoil):
        """
        Make csv file mapping value to category from percents mapping category to percent 
        and raster percents mapping value to percents by matching percents.
        """
        # make ordered lists of pairs (percent, value) and (percent category
        values = ConvertFromArc.mapToOrderedPairs(rasterPercents)
        cats = ConvertFromArc.mapToOrderedPairs(percents)
        # reduce landuse raster values to number from MasterProgress
        if landuseOrSoil == 'landuse' and self.numLuClasses > 0:
            values = values[:self.numLuClasses]
        numValues = len(values)
        numCats = len(cats)
        if numValues != numCats:
            report = os.path.join(self.arcProjDir, r'Watershed\text\LandUseSoilsReport.txt')
            # percentString = ConvertFromArc.percentMapToString(rasterPercents)
            reportFile = os.path.join(self.qProjDir, '{0}_map_percentages.txt'.format(landuseOrSoil))
            with open(reportFile, 'w') as f:
                writer = csv.writer(f)
                writer.writerow(['Value', 'Percent'])
                for percent, val in values:
                    writer.writerow(['{0!s}, {1:.2F}'.format(val, percent)])
            ConvertFromArc.error("""
            There are {0!s} {2}s reported in {3} but {1!s} values found in the {2} raster: cannot generate {2} lookup csv file.
            Percentages from raster reported in {4}"""
                                     .format(numCats, numValues, landuseOrSoil, report, reportFile))
            return
        # merge
        csvFile = os.path.join(self.qProjDir, '{0}_lookup.csv'.format(landuseOrSoil))
        with open(csvFile, 'w') as f:
            writer = csv.writer(f)
            if landuseOrSoil == 'landuse':
                writer.writerow(['LANDUSE_ID', 'SWAT_CODE'])
            else:
                writer.writerow(['SOIL_ID', 'SNAM'])
            closeWarn = False
            underOneCount = 0
            for i in range(numValues):
                percent1, val = values[i]
                percent2, cat = cats[i]
                writer.writerow([str(val), cat])
                if percent1 < 1 or percent2 < 1:
                    underOneCount += 1
                if abs(percent1 - percent2) > 1:
                    ConvertFromArc.information('Warning: percents {0:.1F}% and {1:.1F}% for {2} not very close'
                                               .format(percent1, percent2, cat))
                if not closeWarn and i > 0 and abs(percent2 - cats[i-1][0]) < 1:
                    closeWarn = True # avoid many wornings
                    ConvertFromArc.information('Warning: percents {0:.1F}% and {1:.1F}% for {2} and {3} are close'
                                              .format(percent2, cats[i-1][0], cat, cats[i-1][1]))
            if underOneCount > 1:
                ConvertFromArc.information('Warning: {0} percentages for {1} were less than 1'.format(underOneCount, landuseOrSoil))
     
    @staticmethod               
    def percentMapToString(mmap):
        """Convert map of int -> float to string, using 2 decimal places."""
        result = '{'
        numItems = len(mmap)
        count = 0
        for val, percent in mmap.items():
            result += '{0!s}: {1:.2F}'.format(val, percent)
            count += 1
            if count == numItems:
                result += '}'
            else:
                result += ', '    
        return result
                    
    def setSoilOption(self):
        """Set soil option from MasterProgress table."""
        with pyodbc.connect(self._connStr, readonly=True) as conn:
            row = conn.cursor().execute('SELECT SoilOption,NumLuClasses FROM MasterProgress').fetchone()
            if row is not None:
                self.soilOption = row.SoilOption
                self.numLuClasses = int(row.NumLuClasses)
                
    def getWid2Data(self):
        """Return mapping of subbasin to wid2."""
        wid2Data = dict()
        #print('Connection string: {0}'.format(self._connStr))
        with pyodbc.connect(self._connStr, readonly=True) as conn:
            for row in conn.cursor().execute('SELECT Subbasin,Wid2 FROM Reach'):
                wid2Data[row.Subbasin] = row.Wid2
        return wid2Data      
                                      
    @staticmethod 
    def mapToOrderedPairs(mapping):
        """If mapping is X to percent, create list of (percent, X) ordered by decreasing percent."""
        result = []
        for x, percent in mapping.items():
            ConvertFromArc.insertSort(percent, x, result)
        return result
    
    @staticmethod
    def insertSort(percent, x, result):
        """Insert (percent, x) in result so percentages are ordered decxreasing."""
        for index in range(len(result)):
            nxt, _ = result[index]
            if percent > nxt:
                result.insert(index, (percent, x))
                return
        result.append((percent, x))
        
    @staticmethod
    def getMaxFileOrDir(direc, base, suffix):
        """Find and return the maximum file of the form 'direc\basensuffix' or 'direc\basen if suffix is empty."""
        num = 1
        current = os.path.join(direc, base + str(num) + suffix)
        while True:
            num += 1
            nxt = os.path.join(direc, base + str(num) + suffix)
            if not os.path.exists(nxt):
                return current
            current = nxt
            
    @staticmethod
    def getNewFileOrDir(direc, base, suffix):
        """Find and return lowest n such that direc\basensuffix, or direc\basen if suffix is empty, does not exist.
        
        Tries first with n as the empty string.  direc is asserted to exist."""
        assert os.path.isdir(direc), 'Directory {0} does not exist'.format(direc)
        nxt = os.path.join(direc, base + suffix)
        if not os.path.exists(nxt):
            return nxt
        num = 1
        nxt = os.path.join(direc, base + str(num) + suffix)
        while os.path.exists(nxt):
            num += 1
            nxt = os.path.join(direc, base + str(num) + suffix)
        return nxt  
            
    @staticmethod
    def copyFiles(inFile, saveDir):
        """
        Copy files with same basename as infile to saveDir, 
        i.e. regardless of suffix.
        """
        if os.path.isdir(inFile):
            # ESRI grid: need to copy directory to saveDir
            target = os.path.join(saveDir, os.path.split(inFile)[1])
            shutil.copytree(inFile, target)
        else:
            pattern = os.path.splitext(inFile)[0] + '.*'
            for f in glob.iglob(pattern):
                shutil.copy(f, saveDir)    
        
    @staticmethod
    def makeDirs(direc):
        """Make directory dir unless it already exists."""
        if not os.path.exists(direc):
            os.makedirs(direc)
        
    def getChoice(self):
        """Set choice from form."""
        if self._dlg.fullButton.isChecked():
            self.choice = ConvertFromArc._fullChoice
        elif self._dlg.existButton.isChecked():
            self.choice = ConvertFromArc._existingChoice
        else:
            self.choice = ConvertFromArc._editChoice
        
    @staticmethod
    def writeCsvFile(cursor, table, outFile):
        """Write table to csv file outFile."""
        sql = 'SELECT * FROM {0}'.format(table)
        rows = cursor.execute(sql)
        with open(outFile, 'w') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([x[0] for x in cursor.description])  # column headers
            for row in rows:
                writer.writerow(row)
        
    @staticmethod
    def copyAllFiles(inDir, outDir):
        """Copy files (containing at least one .) from inDir to OutDir."""
        if os.path.exists(inDir):
            patt = inDir + '\*.*'
            for f in glob.iglob(patt):
                shutil.copy(f, outDir)
                
    @staticmethod
    def question(msg):
        """Ask msg as a question, returning Yes or No."""
        questionBox = QMessageBox()
        questionBox.setWindowTitle('QSWAT')
        questionBox.setIcon(QMessageBox.Question)
        questionBox.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        questionBox.setText(QSWATUtils.trans(msg))
        result = questionBox.exec_()
        return result
    
    @staticmethod
    def error(msg):
        """Report msg as an error."""
        msgbox = QMessageBox()
        msgbox.setWindowTitle('QSWAT')
        msgbox.setIcon(QMessageBox.Critical)
        msgbox.setText(QSWATUtils.trans(msg))
        msgbox.exec_()
        return
    
    @staticmethod
    def information(msg):
        """Report msg."""
        msgbox = QMessageBox()
        msgbox.setWindowTitle('QSWAT')
        msgbox.setIcon(QMessageBox.Information)
        msgbox.setText(QSWATUtils.trans(msg))
        msgbox.exec_()
        return
    
if __name__ == '__main__':
    ## QApplication object needed 
    app = QgsApplication([], True)
    app.initQgis()

    ## main program
    main = ConvertFromArc()
    ## result flag
    result = 1
    try:
        main.run()
    except Exception:
        ConvertFromArc.error('Error: {0}'.format(traceback.format_exc()))
        result = 0
    finally:
        exit(result)    
    
