# -*- coding: utf-8 -*-
"""
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
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

# derived from http://snorf.net/blog/2014/01/04/writing-unit-tests-for-qgis-python-plugins/

from qgis.core import QgsApplication, QgsUnitTypes, QgsProject, QgsProviderRegistry
from qgis.gui import * # @UnusedWildImport

from qgis.PyQt.QtCore import Qt, pyqtSlot, QFileInfo, QObject
# from PyQt5.QtGui import * # @UnusedWildImport
from qgis.PyQt import QtTest
import os.path
from osgeo import gdal
import shutil

import unittest
import atexit
# from processing.core.Processing import Processing  


# create a new application object
# without this importing processing causes the following error:
# QWidget: Must construct a QApplication before a QPaintDevice
app = QgsApplication([], True)

from QSWAT import qswat  # @UnresolvedImport
from QSWAT.delineation import Delineation  # @UnresolvedImport
from QSWAT.hrus import HRUs  # @UnresolvedImport
from QSWAT.QSWATUtils import QSWATUtils, FileTypes  # @UnresolvedImport
from QSWAT.parameters import Parameters  # @UnresolvedImport
from QSWAT.selectsubs import SelectSubbasins  # @UnresolvedImport

osGeo4wRoot = os.getenv('OSGEO4W_ROOT')
QgsApplication.setPrefixPath(osGeo4wRoot + r'\apps\qgis-ltr', True)

QgsApplication.initQgis()

# create a new application object
# without this importing processing causes the following error:
# QWidget: Must construct a QApplication before a QPaintDevice

if len(QgsProviderRegistry.instance().providerList()) == 0:
    raise RuntimeError('No data providers available.  Check prefix path setting in test_qswat.py.')

# QSWATUtils.information('Providers: {0!s}'.format(QgsProviderRegistry.instance().providerList()), True)

atexit.register(QgsApplication.exitQgis)

class DummyInterface(object):
    """Dummy iface."""
    def __getattr__(self, *args, **kwargs):  # @UnusedVariable
        """Dummy function."""
        def dummy(*args, **kwargs):  # @UnusedVariable
            return self
        return dummy
    def __iter__(self):
        """Dummy function."""
        return self
    def next(self):
        """Dummy function."""
        raise StopIteration
    def layers(self):
        """Simulate iface.legendInterface().layers()."""
        return QgsProject.instance().mapLayers().values()
iface = DummyInterface()

#QCoreApplication.setOrganizationName('QGIS')
#QCoreApplication.setApplicationName('QGIS2')

is64 = 'QSWAT3_64' in __file__ 

#===============================================================================
# Test1:
#   - No MPI
#   - single outlet only
#   - no merging/adding in delineation
#   - slope limit 10
#   - percent filters 20/10/5
#===============================================================================

HashTable1 = dict()
if is64:
    HashTable1['Reach'] = 'aa727f2049148a27826ab0e9d2b75662'
    HashTable1['MonitoringPoint'] = '902a3418990a6298ae1247991cebfc04'
    HashTable1['BASINSDATA1'] = 'ea92a74739ee636a1ef34d2567a9e513'
    HashTable1['BASINSDATA2'] = 'f45aff5a4242e6a2706443c730155d5a'
    HashTable1['ElevationBand'] = '1188632392838f5ecce923892d35bdfc'
    HashTable1['LUExempt'] = 'd41d8cd98f00b204e9800998ecf8427e'
    HashTable1['SplitHRUs'] = 'd41d8cd98f00b204e9800998ecf8427e'
    HashTable1['hrus'] = '5544ad451a2efc005c2f9be1903a17f6'
    HashTable1['uncomb'] = '54badd623e6ef1fdae08ba245e7c01ce'
    HashTable1['Watershed'] = '0dc7b1b785302c89e3d5608ce7c449fa'
else:
    HashTable1['Reach'] = '0c4294d2325cc5e4da192d1c67f0b334'
    HashTable1['MonitoringPoint'] = '602737473d13d63fffba571d1c48184e'
    HashTable1['BASINSDATA1'] = '449f70bd2c7d122572808bd055e1b93e'
    HashTable1['BASINSDATA2'] = '593ecb65ab4d8f49cefcb7bbb74d98cf'
    HashTable1['ElevationBand'] = '1188632392838f5ecce923892d35bdfc'
    HashTable1['LUExempt'] = 'd41d8cd98f00b204e9800998ecf8427e'
    HashTable1['SplitHRUs'] = 'd41d8cd98f00b204e9800998ecf8427e'
    HashTable1['hrus'] = '947a2f86346fb1ed4d163ed3e41cd15c'
    HashTable1['uncomb'] = '34b08d63db85a21f670adeb31d976827'
    HashTable1['Watershed'] = '05dc7a18e5ce85e0885130417c53f805'

#===============================================================================
# Test2:
#   - MPI with 12 processes
#   - delineation threshold 100 sq km
#   - 8 inlets/outlets
#   - snap threshold set to 600 (fails on default 300)
#   - no merging/adding in delineation
#   - no slope limit
#   - FullHRUs created
#   - 6 elev bands: threshold 2000
#   - area filter 5000 ha
#===============================================================================

HashTable2 = dict()
if is64:
    HashTable2['Reach'] = 'e96032bd868bad58a4f53dd0f55b5314'
    HashTable2['MonitoringPoint'] = '453124da04baffbead94dafff7d2dff7'
    HashTable2['BASINSDATA1'] = '7f9bb77cc9f750b22212ba616d7fb84f'
    HashTable2['BASINSDATA2'] = '2f9216f533d695820ff57e963a3b639b'
    HashTable2['ElevationBand'] = 'df71197f4bdf33993c7cc4700e6d58aa'
    HashTable2['LUExempt'] = 'd41d8cd98f00b204e9800998ecf8427e'
    HashTable2['SplitHRUs'] = 'd41d8cd98f00b204e9800998ecf8427e'
    HashTable2['hrus'] = 'c4cdaa9c0e13be624af84c2a63c3fc88'
    HashTable2['uncomb'] = '677d8e2f43b22bb2e2136cf9aa71f984'
    HashTable2['Watershed'] = '28962355da261ed3b56660bdb1afc493'
else:
    HashTable2['Reach'] = '1d7c0bde12e5a9f2494b941447cd01a8'
    HashTable2['MonitoringPoint'] = '1f7ce3c15b4b5a73b3b9ed1fc8c51036'
    HashTable2['BASINSDATA1'] = '0735497fef27f345d53f4695deb147c6'
    HashTable2['BASINSDATA2'] = '471057b700f5cadca604fb81b8ef3cf3'
    HashTable2['ElevationBand'] = 'df71197f4bdf33993c7cc4700e6d58aa'
    HashTable2['LUExempt'] = 'd41d8cd98f00b204e9800998ecf8427e'
    HashTable2['SplitHRUs'] = 'd41d8cd98f00b204e9800998ecf8427e'
    HashTable2['hrus'] = '534f86bfc6fede76bbde04c649c33208'
    HashTable2['uncomb'] = 'd4fd3ca14cefc3c0ecdae6f7d03c3505'
    HashTable2['Watershed'] = 'bddf216fbfa4d3ae1dd96a6fc83d23dd'

#===============================================================================
# Test3:
#   - No MPI
#   - delineation threshold 14400 cells
#   - single outlet only
#   - merge subbasins 2 and 6
#   - add reservoirs to 1 and 15
#   - add point sources
#   - split GRAS into 10% SWRN and 90% RNGE
#   - exempt Landuses CRDY and SWRN
#   - no slope limits
#   - target by area 100
#===============================================================================

HashTable3 = dict()
# HashTable3['Reach'] = 'e18f5ba56607fa5af3887f7c6e0223ed'  # unreliable
# HashTable3['MonitoringPoint'] = 'fc2a3cb74c9d20d95f5f84cf97f52709'
HashTable3['BASINSDATA1'] = '2f2b2128a084a20b6f206696a5296971'
HashTable3['BASINSDATA2'] = '445d0f5da4029beb05cb927efdf99866' if is64 else 'bdb14e3e1fb52d82c1301306d316441a'
HashTable3['ElevationBand'] = '192510a66a96e36354283900097ba9b1'
HashTable3['LUExempt'] = 'faa3ee70bebcc7d6a4ee0302e9e23ad0'
HashTable3['SplitHRUs'] = '5c3f1888ea4e1064e3f6d1b2025ebbe7'
# HashTable3['hrus'] = 'bc8748cdc0ec3868e4d438de3f52addb'
# HashTable3['uncomb'] = '1ce3917b984939e716f3b4cb4d497453'
# HashTable3['Watershed'] = 'd3c9f79c8c530c72a78af6ecae1d0a48'

#===============================================================================
# Test4:
#   - No MPI
#   - use existing
#   - no outlet
#   - no merging/adding in delineation
#   - make FullHRs shapefile
#   - no slope limits
#   - filter by percent area 10%
#===============================================================================

HashTable4 = dict()
HashTable4['Reach'] = '321d49eb5493cb6181cd785f26086b9f'  if is64 else '28f7931add98497cd7681dc7aa36369d'
HashTable4['MonitoringPoint'] = 'b3ce02e9cb72d16192319f7b95a0c0c4'  if is64 else 'a0da75a8df134d0c7277aa3f6e815704'
HashTable4['BASINSDATA1'] = '64c29c087d6681d7dacb320651061403'
HashTable4['BASINSDATA2'] = 'fe6ceed16df5e4329be7d6af52d2608d'  if is64 else '9d6ebc9775cb40c2a1ba092c9f4a748a'
HashTable4['ElevationBand'] = '1188632392838f5ecce923892d35bdfc'
HashTable4['LUExempt'] = 'd41d8cd98f00b204e9800998ecf8427e'
HashTable4['SplitHRUs'] = 'd41d8cd98f00b204e9800998ecf8427e'
HashTable4['hrus'] = 'fd8a0a5c3934a301585af55eacbe3188'
HashTable4['uncomb'] = 'ff2decfc7c329f1b0e7b8c09e117487c'
HashTable4['Watershed'] = '31e8e0bec809de21345f9fbc7446308b'  if is64 else '6cecd53e5c8916c1531b83fbf506feee'

#===============================================================================
# Test5:
#   - No MPI
#   - Duffins example (with triple stream reach join)
#   - delineation threshold 100 ha
#   - merges small subbasins with default 5% threshold in delineation
#   - no slope limits
#   - filter by target 170 HRUs by percentage
#===============================================================================

HashTable5 = dict()
#HashTable5['Reach'] = 'af3dd93f9bb309c6d5d2f026997b9e80'
#HashTable5['MonitoringPoint'] = '244a02cdd0ab328030361a993fe4dfc4'
HashTable5['BASINSDATA1'] = '001220c1fa3c9b8811e0bacb99e03e2d'
HashTable5['BASINSDATA2'] = '53365194986b036fa6d6c229c845902b'
HashTable5['ElevationBand'] = 'fc30a7eb95db576ea55f1438aa25a603'
HashTable5['LUExempt'] = 'd41d8cd98f00b204e9800998ecf8427e'
HashTable5['SplitHRUs'] = 'd41d8cd98f00b204e9800998ecf8427e'
#HashTable5['hrus'] = '4a28cb602771ed0b167ca649b573e3a5'
#HashTable5['uncomb'] = 'badb9767f7e645e5981fb7ecdeabf40c'
#HashTable5['Watershed'] = '932f6dc0923266228d4145498917581c'

# listen to the QGIS message log
message_log = {}
def log(message, tag, level):
    message_log.setdefault(tag, [])
    message_log[tag].append((message, level,))
QgsApplication.instance().messageLog().messageReceived.connect(log)

class TestQswat(unittest.TestCase):
    """Test cases for QSWAT."""
    def setUp(self):
        """Remove old project; read test project file; prepare for delineation."""
#         Processing.initialize()
#         if 'native' not in [p.id() for p in QgsApplication.processingRegistry().providers()]:
#             QgsApplication.processingRegistry().addProvider(QgsNativeAlgorithms())
#         # SRS path is not set properly.
#         self.assertTrue(os.path.exists(QgsApplication.srsDbFilePath()), \
#                          'Need to copy resources folder to make directory {0} exist, eg copy OSGeo4W/apps/qgis/resources to OSGeo4W'.format(QgsApplication.srsDbFilePath()))
        ## QSWAT plugin
        self.plugin = qswat.QSwat(iface)
        ## Main QSWAT form
        self.dlg = self.plugin._odlg # useful for shorthand later
        ## Test data directory
        self.dataDir = os.path.join(self.plugin.plugin_dir, '../testdata')
        ## Project directory
        self.projDir = os.path.join(self.dataDir, 'test')
        # clean up from previous runs
        QgsProject.instance().removeAllMapLayers()
        projectDatabase = os.path.join(self.projDir, 'test.mdb')
        if os.path.exists(projectDatabase):
            os.remove(projectDatabase)
        shutil.rmtree(os.path.join(self.projDir, 'Scenarios'), ignore_errors=True)
        shutil.rmtree(os.path.join(self.projDir, 'Source'), ignore_errors=True)
        shutil.rmtree(os.path.join(self.projDir, 'Watershed'), ignore_errors=True)
        # start with empty project
        shutil.copy(os.path.join(self.dataDir, 'test_proj_qgs'), self.projDir + '.qgs')
        ## QGSproject instance
        self.proj = QgsProject.instance()
        self.proj.read(self.projDir + '.qgs')
        ## project's layer tree root 
        self.root = self.proj.layerTreeRoot()
        self.plugin.setupProject(self.proj, True)
        self.assertTrue(os.path.exists(self.plugin._gv.textDir) and os.path.exists(self.plugin._gv.landuseDir), 'Directories not created')
        self.assertTrue(self.dlg.delinButton.isEnabled(), 'Delineate button not enabled')
        ## Delineation object
        self.delin = Delineation(self.plugin._gv, self.plugin._demIsProcessed)
        self.delin.init()
        self.delin._dlg.numProcesses.setValue(0)
        
        
    def test01(self):
        """No MPI; single outlet only; no merging/adding in delineation; slope limit 10; percent filters 20/10/5."""
        self.delin._dlg.selectDem.setText(self.copyDem('sj_dem.tif'))
        self.assertTrue(os.path.exists(self.delin._dlg.selectDem.text()), 'Failed to copy DEM to source directory')
        ## HRUs object
        self.hrus = HRUs(self.plugin._gv, self.dlg.reportsBox)
        # listener = Listener(self.delin, self.hrus, self.hrus.CreateHRUs)
        numLayers = len(QgsProject.instance().mapLayers().values())
        self.assertEqual(numLayers, 0, 'Unexpected start with {0} layers'.format(numLayers))
        demLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), self.delin._dlg.selectDem.text(), FileTypes._DEM, 
                                                         self.plugin._gv, True, QSWATUtils._WATERSHED_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(demLayer and loaded, 'Failed to load DEM {0}'.format(self.delin._dlg.selectDem.text()))
        self.assertTrue(demLayer.crs().mapUnits() == QgsUnitTypes.DistanceMeters, 'Map units not meters but {0}'.format(demLayer.crs().mapUnits()))
        QSWATUtils.copyFiles(QFileInfo(os.path.join(self.dataDir, 'sj_out.shp')), self.plugin._gv.shapesDir)
        self.delin._dlg.selectOutlets.setText(os.path.join(self.plugin._gv.shapesDir, 'sj_out.shp'))
        self.assertTrue(os.path.exists(self.delin._dlg.selectOutlets.text()), 'Failed to copy out.shp to Outlet directory')
        self.delin._dlg.useOutlets.setChecked(True)
        QtTest.QTest.mouseClick(self.delin._dlg.delinRunButton2, Qt.LeftButton)
        self.assertTrue(self.delin.areaOfCell > 0, 'Area of cell is ' + str(self.delin.areaOfCell))
        QtTest.QTest.mouseClick(self.delin._dlg.OKButton, Qt.LeftButton)
        self.assertTrue(self.dlg.hrusButton.isEnabled(), 'HRUs button not enabled')
        self.hrus.init()
        hrudlg = self.hrus._dlg
        self.hrus.landuseFile = os.path.join(self.dataDir, 'sj_land.tif')
        numLayers = len(QgsProject.instance().mapLayers().values())
        self.hrus.landuseLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), self.hrus.landuseFile, FileTypes._LANDUSES, 
                                                                       self.plugin._gv, None, QSWATUtils._LANDUSE_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(self.hrus.landuseLayer and loaded, 'Failed to load landuse file {0}'.format(self.hrus.landuseFile))
        self.hrus.soilFile = os.path.join(self.dataDir, 'sj_soil.tif')
        numLayers = len(QgsProject.instance().mapLayers().values())
        self.hrus.soilLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), self.hrus.soilFile, FileTypes._SOILS, 
                                                                    self.plugin._gv, None, QSWATUtils._SOIL_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(self.hrus.soilLayer and loaded, 'Failed to load soil file {0}'.format(self.hrus.soilFile))
        landCombo = hrudlg.selectLanduseTable
        landIndex = landCombo.findText('global_landuses')
        self.assertTrue(landIndex >= 0, 'Cannot find global landuses table')
        landCombo.setCurrentIndex(landIndex)
        soilCombo = hrudlg.selectSoilTable
        soilIndex = soilCombo.findText('global_soils')
        self.assertTrue(soilIndex >= 0, 'Cannot find global soils table')
        soilCombo.setCurrentIndex(soilIndex)
        hrudlg.slopeBand.setText('10')
        QtTest.QTest.mouseClick(hrudlg.insertButton, Qt.LeftButton)
        lims = self.plugin._gv.db.slopeLimits
        self.assertTrue(len(lims) == 1 and lims[0] == 10, 'Failed to set slope limit of 10: limits list is {0!s}'.format(lims))
        self.assertTrue(hrudlg.elevBandsButton.isEnabled(), 'Elevation bands button not enabled')
        QtTest.QTest.mouseClick(hrudlg.readButton, Qt.LeftButton)
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.textDir, Parameters._TOPOREPORT)))
        self.assertTrue(self.dlg.reportsBox.isEnabled() and self.dlg.reportsBox.findText(Parameters._TOPOITEM) >= 0, \
                        'Elevation report not accessible from main form')
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.textDir, Parameters._BASINREPORT)))
        self.assertTrue(self.dlg.reportsBox.findText(Parameters._BASINITEM) >= 0, \
                        'Landuse and soil report not accessible from main form')
        self.assertTrue(hrudlg.splitButton.isEnabled(), 'Split landuses button not enabled')
        self.assertTrue(hrudlg.exemptButton.isEnabled(), 'Exempt landuses button not enabled')
        self.assertTrue(hrudlg.filterLanduseButton.isEnabled(), 'Filter landuse button not enabled')
        QtTest.QTest.mouseClick(hrudlg.filterLanduseButton, Qt.LeftButton)
        self.assertTrue(hrudlg.percentButton.isEnabled(), 'Percent button not enabled')
        QtTest.QTest.mouseClick(hrudlg.percentButton, Qt.LeftButton)
        self.assertTrue(hrudlg.stackedWidget.currentIndex() == 0, 'Wrong threshold page {0} selected'.format(hrudlg.stackedWidget.currentIndex()))
        hrudlg.landuseVal.setText('20')
        self.assertTrue(hrudlg.landuseButton.isEnabled(), 'Landuse button not enabled')
        QtTest.QTest.mouseClick(hrudlg.landuseButton, Qt.LeftButton)
        hrudlg.soilVal.setText('10')
        self.assertTrue(hrudlg.soilButton.isEnabled(), 'Soil button not enabled')
        QtTest.QTest.mouseClick(hrudlg.soilButton, Qt.LeftButton)
        hrudlg.slopeVal.setText('5')
        self.assertTrue(hrudlg.createButton.isEnabled(), 'Create button not enabled')
        QtTest.QTest.mouseClick(hrudlg.createButton, Qt.LeftButton)
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.textDir, Parameters._HRUSREPORT)))
        self.assertTrue(self.dlg.reportsBox.findText(Parameters._HRUSITEM) >= 0, \
                        'HRUs report not accessible from main form')
        self.assertEqual(len(self.hrus.CreateHRUs.basins), 25, 'Subbasin count is {0} instead of 25'.format(len(self.hrus.CreateHRUs.basins)))
        self.assertEqual(len(self.hrus.CreateHRUs.hrus), 135, 'HRU count is {0} instead of 135'.format(len(self.hrus.CreateHRUs.hrus)))
        self.checkHashes(HashTable1)
        self.assertTrue(self.dlg.editButton.isEnabled(), 'SWAT Editor button not enabled')
        
    def test02(self):
        """MPI with 12 processes; delineation threshold 100 sq km; 8 inlets/outlets; snap threshold 600; FullHRUs;  6 elev bands;  area filter 5000 ha."""
        self.delin._dlg.selectDem.setText(self.copyDem('sj_dem.tif'))
        self.assertTrue(os.path.exists(self.delin._dlg.selectDem.text()), 'Failed to copy DEM to source directory')
        self.hrus = HRUs(self.plugin._gv, self.dlg.reportsBox)
        # listener = Listener(self.delin, self.hrus, self.hrus.CreateHRUs)
        QgsProject.instance().removeAllMapLayers()
        numLayers = len(QgsProject.instance().mapLayers().values())
        self.assertEqual(numLayers, 0, 'Unexpected start with {0} layers'.format(numLayers))
        self.delin._dlg.numProcesses.setValue(12)
        demLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), self.delin._dlg.selectDem.text(), FileTypes._DEM, 
                                                         self.plugin._gv, True, QSWATUtils._WATERSHED_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(demLayer and loaded, 'Failed to load DEM {0}'.format(self.delin._dlg.selectDem.text()))
        self.assertTrue(demLayer.crs().mapUnits() == QgsUnitTypes.DistanceMeters, 'Map units not meters but {0}'.format(demLayer.crs().mapUnits()))
        unitIndex = self.delin._dlg.areaUnitsBox.findText(Parameters._SQKM)
        self.assertTrue(unitIndex >= 0, 'Cannot find sq km area units')
        self.delin._dlg.areaUnitsBox.setCurrentIndex(unitIndex)
        self.delin.setDefaultNumCells(demLayer)
        self.delin._dlg.area.setText('100')
        self.assertTrue(self.delin._dlg.numCells.text() == '14400', 'Unexpected number of cells for delineation {0}'.format(self.delin._dlg.numCells.text()))
        QSWATUtils.copyFiles(QFileInfo(os.path.join(self.dataDir, 'out8.shp')), self.plugin._gv.shapesDir)
        self.delin._dlg.selectOutlets.setText(os.path.join(self.plugin._gv.shapesDir, 'out8.shp'))
        self.assertTrue(os.path.exists(self.delin._dlg.selectOutlets.text()), 'Failed to find outlet file {0}'.format(self.delin._dlg.selectOutlets.text()))
        self.delin._dlg.useOutlets.setChecked(True)
        # QtTest.QTest.mouseClick(self.delin._dlg.delinRunButton2, Qt.LeftButton)
        # self.assertTrue('7 snapped: 1 failed' in self.delin._dlg.snappedLabel.text(), 'Unexpected snapping result: {0}'.format(self.delin._dlg.snappedLabel.text()))
        self.delin._dlg.snapThreshold.setText('600')
        QtTest.QTest.mouseClick(self.delin._dlg.delinRunButton2, Qt.LeftButton)
        self.assertTrue('8 snapped' in self.delin._dlg.snappedLabel.text(), 'Unexpected snapping result: {0}'.format(self.delin._dlg.snappedLabel.text()))
        self.assertTrue(self.delin.areaOfCell > 0, 'Area of cell is ' + str(self.delin.areaOfCell))
        QtTest.QTest.mouseClick(self.delin._dlg.OKButton, Qt.LeftButton)
        self.assertTrue(self.dlg.hrusButton.isEnabled(), 'HRUs button not enabled')
        self.hrus.init()
        hrudlg = self.hrus._dlg
        self.hrus.landuseFile = os.path.join(self.dataDir, 'sj_land.tif')
        numLayers = len(QgsProject.instance().mapLayers().values())
        self.hrus.landuseLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), self.hrus.landuseFile, FileTypes._LANDUSES, 
                                                                       self.plugin._gv, None, QSWATUtils._LANDUSE_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(self.hrus.landuseLayer and loaded, 'Failed to load landuse file {0}'.format(self.hrus.landuseFile))
        self.hrus.soilFile = os.path.join(self.dataDir, 'sj_soil.tif')
        numLayers = len(QgsProject.instance().mapLayers().values())
        self.hrus.soilLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), self.hrus.soilFile, FileTypes._SOILS, 
                                                                    self.plugin._gv, None, QSWATUtils._SOIL_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(self.hrus.soilLayer and loaded, 'Failed to load soil file {0}'.format(self.hrus.soilFile))
        landCombo = hrudlg.selectLanduseTable
        landIndex = landCombo.findText('global_landuses')
        self.assertTrue(landIndex >= 0, 'Cannot find global landuses table')
        landCombo.setCurrentIndex(landIndex)
        soilCombo = hrudlg.selectSoilTable
        soilIndex = soilCombo.findText('global_soils')
        self.assertTrue(soilIndex >= 0, 'Cannot find global soils table')
        soilCombo.setCurrentIndex(soilIndex)
        lims = self.plugin._gv.db.slopeLimits
        self.assertTrue(len(lims) == 0, 'Limits list is not empty')
        self.assertTrue(hrudlg.elevBandsButton.isEnabled(), 'Elevation bands button not enabled')
        self.plugin._gv.elevBandsThreshold = 2000
        self.plugin._gv.numElevBands = 6
        hrudlg.generateFullHRUs.setChecked(True)
        QtTest.QTest.mouseClick(hrudlg.readButton, Qt.LeftButton)
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.shapesDir, 'hru1.shp')), 'Full HRUs shapefile not created')
        fullHrusLayer = QSWATUtils.getLayerByLegend(QSWATUtils._FULLHRUSLEGEND, self.root.findLayers())
        self.assertTrue(fullHrusLayer, 'FullHRUs file not loaded')
        self.assertTrue(fullHrusLayer.layer().featureCount() == 191, 'Unexpected number of full HRUs: {0}'.format(fullHrusLayer.layer().featureCount()))
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.textDir, Parameters._TOPOREPORT)))
        self.assertTrue(self.dlg.reportsBox.isEnabled() and self.dlg.reportsBox.findText(Parameters._TOPOITEM) >= 0, \
                        'Elevation report not accessible from main form')
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.textDir, Parameters._BASINREPORT)))
        self.assertTrue(self.dlg.reportsBox.findText(Parameters._BASINITEM) >= 0, \
                        'Landuse and soil report not accessible from main form')
        self.assertTrue(hrudlg.splitButton.isEnabled(), 'Split landuses button not enabled')
        self.assertTrue(hrudlg.exemptButton.isEnabled(), 'Exempt landuses button not enabled')
        self.assertTrue(hrudlg.filterAreaButton.isEnabled(), 'Filter area button not enabled')
        QtTest.QTest.mouseClick(hrudlg.filterAreaButton, Qt.LeftButton)
        self.assertTrue(hrudlg.areaButton.isEnabled(), 'Area button not enabled')
        QtTest.QTest.mouseClick(hrudlg.areaButton, Qt.LeftButton)
        self.assertTrue(hrudlg.stackedWidget.currentIndex() == 1, 'Wrong threshold page {0} selected'.format(hrudlg.stackedWidget.currentIndex()))
        hrudlg.areaVal.setText('5000')
        self.assertTrue(hrudlg.createButton.isEnabled(), 'Create button not enabled')
        QtTest.QTest.mouseClick(hrudlg.createButton, Qt.LeftButton)
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.textDir, Parameters._HRUSREPORT)))
        self.assertTrue(self.dlg.reportsBox.findText(Parameters._HRUSITEM) >= 0, \
                        'HRUs report not accessible from main form')
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.shapesDir, 'hru2.shp')), 'Actual HRUs shapefile not created.')
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.tablesOutDir, 'hrus.shp')), 'HRUs results template file not created.')
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.tablesOutDir, 'rivs.shp')), 'Reaches results template file not created.')
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.tablesOutDir, 'subs.shp')), 'Watershed results template file not created.')
        self.assertEqual(len(self.hrus.CreateHRUs.basins), 28, 'Subbasin count is {0} instead of 28'.format(len(self.hrus.CreateHRUs.basins)))
        self.assertEqual(len(self.hrus.CreateHRUs.hrus), 41, 'HRU count is {0} instead of 41'.format(len(self.hrus.CreateHRUs.hrus)))
        self.checkHashes(HashTable2)
        self.assertTrue(self.dlg.editButton.isEnabled(), 'SWAT Editor button not enabled')
        
    def test03(self):
        """No MPI; delineation threshold 14400 cells; single outlet; merge subbasins; add reservoirs; add point sources; split and exempts; target by area 100."""
        self.delin._dlg.selectDem.setText(self.copyDem('sj_dem.tif'))
        self.assertTrue(os.path.exists(self.delin._dlg.selectDem.text()), 'Failed to copy DEM to source directory')
        self.hrus = HRUs(self.plugin._gv, self.dlg.reportsBox)
        # listener = Listener(self.delin, self.hrus, self.hrus.CreateHRUs)
        QgsProject.instance().removeAllMapLayers()
        numLayers = len(QgsProject.instance().mapLayers().values())
        self.assertEqual(numLayers, 0, 'Not all map layers removed')
        demLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), self.delin._dlg.selectDem.text(), FileTypes._DEM, 
                                                         self.plugin._gv, True, QSWATUtils._WATERSHED_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(demLayer and loaded, 'Failed to load DEM {0}'.format(self.delin._dlg.selectDem.text()))
        self.assertTrue(demLayer.crs().mapUnits() == QgsUnitTypes.DistanceMeters, 'Map units not meters but {0}'.format(demLayer.crs().mapUnits()))
        unitIndex = self.delin._dlg.areaUnitsBox.findText(Parameters._SQKM)
        self.assertTrue(unitIndex >= 0, 'Cannot find sq km area units')
        self.delin._dlg.areaUnitsBox.setCurrentIndex(unitIndex)
        self.delin.setDefaultNumCells(demLayer)
        self.delin._dlg.numCells.setText('14400')
        self.assertTrue(self.delin._dlg.area.text() == '100', 'Unexpected area for delineation {0}'.format(self.delin._dlg.area.text()))
        QSWATUtils.copyFiles(QFileInfo(os.path.join(self.dataDir, 'sj_out.shp')), self.plugin._gv.shapesDir)
        self.delin._dlg.selectOutlets.setText(os.path.join(self.plugin._gv.shapesDir, 'sj_out.shp'))
        self.assertTrue(os.path.exists(self.delin._dlg.selectOutlets.text()), 'Failed to copy out.shp to Outlet directory')
        self.delin._dlg.useOutlets.setChecked(True)
        self.delin._dlg.numProcesses.setValue(0)
        QtTest.QTest.mouseClick(self.delin._dlg.delinRunButton2, Qt.LeftButton)
        self.assertTrue(self.delin.areaOfCell > 0, 'Area of cell is ' + str(self.delin.areaOfCell))
        # merge basin 2, 6 and 14
        wshedLayer = QSWATUtils.getLayerByLegend(FileTypes.legend(FileTypes._WATERSHED), self.root.findLayers())
        self.assertTrue(wshedLayer, 'No watershed layer')
        wshedLayer.layer().select([11, 15, 19])  # polygonids 4, 23, 27
        # this does not seem to work in actually calling mergeSubbasins
        # QtTest.QTest.mouseClick(self.delin._dlg.mergeButton, Qt.LeftButton)
        self.delin.mergeSubbasins()
        # add reservoirs to 1 and 15
        self.delin.extraReservoirBasins = {12, 18}  # polygonids 24, 1
        # add point sources
        self.delin._dlg.checkAddPoints.setChecked(True)
        # this does not seem to work in actually calling addReservoirs
        # QtTest.QTest.mouseClick(self.delin._dlg.addButton, Qt.LeftButton)
        self.delin.addReservoirs()
        QtTest.QTest.mouseClick(self.delin._dlg.OKButton, Qt.LeftButton)
        self.assertTrue(self.dlg.hrusButton.isEnabled(), 'HRUs button not enabled')
        self.hrus.init()
        hrudlg = self.hrus._dlg
        self.hrus.landuseFile = os.path.join(self.dataDir, 'sj_land.tif')
        numLayers = len(QgsProject.instance().mapLayers().values())
        self.hrus.landuseLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), self.hrus.landuseFile, FileTypes._LANDUSES, 
                                                                       self.plugin._gv, None, QSWATUtils._LANDUSE_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(self.hrus.landuseLayer and loaded, 'Failed to load landuse file {0}'.format(self.hrus.landuseFile))
        self.hrus.soilFile = os.path.join(self.dataDir, 'sj_soil.tif')
        numLayers = len(QgsProject.instance().mapLayers().values())
        self.hrus.soilLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), self.hrus.soilFile, FileTypes._SOILS, 
                                                                    self.plugin._gv, None, QSWATUtils._SOIL_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(self.hrus.soilLayer and loaded, 'Failed to load soil file {0}'.format(self.hrus.soilFile))
        landCombo = hrudlg.selectLanduseTable
        landIndex = landCombo.findText('global_landuses')
        self.assertTrue(landIndex >= 0, 'Cannot find global landuses table')
        landCombo.setCurrentIndex(landIndex)
        soilCombo = hrudlg.selectSoilTable
        soilIndex = soilCombo.findText('global_soils')
        self.assertTrue(soilIndex >= 0, 'Cannot find global soils table')
        soilCombo.setCurrentIndex(soilIndex)
        self.assertTrue(hrudlg.elevBandsButton.isEnabled(), 'Elevation bands button not enabled')
        QtTest.QTest.mouseClick(hrudlg.readButton, Qt.LeftButton)
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.textDir, Parameters._TOPOREPORT)))
        self.assertTrue(self.dlg.reportsBox.isEnabled() and self.dlg.reportsBox.findText(Parameters._TOPOITEM) >= 0, \
                        'Elevation report not accessible from main form')
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.textDir, Parameters._BASINREPORT)))
        self.assertTrue(self.dlg.reportsBox.findText(Parameters._BASINITEM) >= 0, \
                        'Landuse and soil report not accessible from main form')
        self.assertTrue(hrudlg.splitButton.isEnabled(), 'Split landuses button not enabled')
        # split GRAS into 10% SWRN and 90% RNGE
        self.plugin._gv.splitLanduses.clear()
        self.plugin._gv.splitLanduses['GRAS'] = dict()
        self.plugin._gv.splitLanduses['GRAS']['SWRN'] = 10
        self.plugin._gv.splitLanduses['GRAS']['RNGE'] = 90
        self.assertTrue(hrudlg.exemptButton.isEnabled(), 'Exempt landuses button not enabled')
        self.plugin._gv.exemptLanduses = ['CRDY', 'SWRN']
        self.assertTrue(hrudlg.targetButton.isEnabled(), 'Target button not enabled')
        QtTest.QTest.mouseClick(hrudlg.targetButton, Qt.LeftButton)
        self.assertTrue(hrudlg.areaButton.isEnabled(), 'Area button not enabled')
        QtTest.QTest.mouseClick(hrudlg.areaButton, Qt.LeftButton)
        self.assertTrue(hrudlg.stackedWidget.currentIndex() == 2, 'Wrong threshold page {0} selected'.format(hrudlg.stackedWidget.currentIndex()))
        hrudlg.targetSlider.setValue(100)
        self.assertTrue(hrudlg.createButton.isEnabled(), 'Create button not enabled')
        QtTest.QTest.mouseClick(hrudlg.createButton, Qt.LeftButton)
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.textDir, Parameters._HRUSREPORT)))
        self.assertTrue(self.dlg.reportsBox.findText(Parameters._HRUSITEM) >= 0, \
                        'HRUs report not accessible from main form')
        self.assertEqual(len(self.hrus.CreateHRUs.basins), 26, 'Subbasin count is {0} instead of 26'.format(len(self.hrus.CreateHRUs.basins)))
        self.assertEqual(len(self.hrus.CreateHRUs.hrus), 132, 'HRU count is {0} instead of 132'.format(len(self.hrus.CreateHRUs.hrus)))
        self.checkHashes(HashTable3)
        self.assertTrue(self.dlg.editButton.isEnabled(), 'SWAT Editor button not enabled')
        
    def test04(self):
        """No MPI; use existing; no outlet; no merging/adding in delineation; FullHRUs; no slope limits; filter by percent area 10%."""
        self.delin._dlg.selectDem.setText(self.copyDem('sj_dem.tif'))
        self.assertTrue(os.path.exists(self.delin._dlg.selectDem.text()), 'Failed to copy DEM to source directory')
        self.hrus = HRUs(self.plugin._gv, self.dlg.reportsBox)
        # listener = Listener(self.delin, self.hrus, self.hrus.CreateHRUs)
        QgsProject.instance().removeAllMapLayers()
        numLayers = len(QgsProject.instance().mapLayers().values())
        self.assertEqual(numLayers, 0, 'Not all map layers removed')
        demLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), self.delin._dlg.selectDem.text(), FileTypes._DEM, 
                                                         self.plugin._gv, True, QSWATUtils._WATERSHED_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(demLayer and loaded, 'Failed to load DEM {0}'.format(self.delin._dlg.selectDem.text()))
        self.assertTrue(demLayer.crs().mapUnits() == QgsUnitTypes.DistanceMeters, 'Map units not meters but {0}'.format(demLayer.crs().mapUnits()))
        self.delin._dlg.tabWidget.setCurrentIndex(1)
        wshedFile = os.path.join(self.dataDir, 'sj_demwshed.shp')
        numLayers = len(QgsProject.instance().mapLayers().values())
        wshedLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), wshedFile, FileTypes._EXISTINGWATERSHED, 
                                                           self.plugin._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(wshedLayer and loaded, 'Failed to load watershed shapefile'.format(wshedFile))
        self.delin._dlg.selectWshed.setText(wshedFile)
        self.plugin._gv.wshedFile = wshedFile
        streamFile = os.path.join(self.dataDir, 'sj_demnet.shp')
        numLayers = len(QgsProject.instance().mapLayers().values())
        streamLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), streamFile, FileTypes._STREAMS, 
                                                            self.plugin._gv, None, QSWATUtils._WATERSHED_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(streamLayer and loaded, 'Failed to load streams shapefile'.format(streamFile))
        self.delin._dlg.selectNet.setText(streamFile)
        self.plugin._gv.streamFile = streamFile
        self.delin._dlg.numProcesses.setValue(0)
        QtTest.QTest.mouseClick(self.delin._dlg.existRunButton, Qt.LeftButton)
        self.assertTrue(self.delin.isDelineated, 'Delineation incomplete')
        QtTest.QTest.mouseClick(self.delin._dlg.OKButton, Qt.LeftButton)
        self.assertTrue(self.dlg.hrusButton.isEnabled(), 'HRUs button not enabled')
        self.hrus.init()
        hrudlg = self.hrus._dlg
        self.hrus.landuseFile = os.path.join(self.dataDir, 'sj_land.tif')
        numLayers = len(QgsProject.instance().mapLayers().values())
        self.hrus.landuseLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), self.hrus.landuseFile, FileTypes._LANDUSES, 
                                                                       self.plugin._gv, None, QSWATUtils._LANDUSE_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(self.hrus.landuseLayer and loaded, 'Failed to load landuse file {0}'.format(self.hrus.landuseFile))
        self.hrus.soilFile = os.path.join(self.dataDir, 'sj_soil.tif')
        numLayers = len(QgsProject.instance().mapLayers().values())
        self.hrus.soilLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), self.hrus.soilFile, FileTypes._SOILS, 
                                                                    self.plugin._gv, None, QSWATUtils._SOIL_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(self.hrus.soilLayer and loaded, 'Failed to load soil file {0}'.format(self.hrus.soilFile))
        landCombo = hrudlg.selectLanduseTable
        landIndex = landCombo.findText('global_landuses')
        self.assertTrue(landIndex >= 0, 'Cannot find global landuses table')
        landCombo.setCurrentIndex(landIndex)
        soilCombo = hrudlg.selectSoilTable
        soilIndex = soilCombo.findText('global_soils')
        self.assertTrue(soilIndex >= 0, 'Cannot find global soils table')
        soilCombo.setCurrentIndex(soilIndex)
        self.assertTrue(hrudlg.elevBandsButton.isEnabled(), 'Elevation bands button not enabled')
        hrudlg.generateFullHRUs.setChecked(True)
        QtTest.QTest.mouseClick(hrudlg.readButton, Qt.LeftButton)
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.shapesDir, 'hru1.shp')), 'Full HRUs file not created.')
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.textDir, Parameters._TOPOREPORT)))
        self.assertTrue(self.dlg.reportsBox.isEnabled() and self.dlg.reportsBox.findText(Parameters._TOPOITEM) >= 0, \
                        'Elevation report not accessible from main form')
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.textDir, Parameters._BASINREPORT)))
        self.assertTrue(self.dlg.reportsBox.findText(Parameters._BASINITEM) >= 0, \
                        'Landuse and soil report not accessible from main form')
        self.assertTrue(hrudlg.splitButton.isEnabled(), 'Split landuses button not enabled')
        self.assertTrue(hrudlg.exemptButton.isEnabled(), 'Exempt landuses button not enabled')
        self.assertTrue(hrudlg.filterAreaButton.isEnabled(), 'Filter by area button not enabled')
        QtTest.QTest.mouseClick(hrudlg.filterAreaButton, Qt.LeftButton)
        self.assertTrue(hrudlg.percentButton.isEnabled(), 'Area button not enabled')
        QtTest.QTest.mouseClick(hrudlg.percentButton, Qt.LeftButton)
        self.assertTrue(hrudlg.stackedWidget.currentIndex() == 1, 'Wrong threshold page {0} selected'.format(hrudlg.stackedWidget.currentIndex()))
        hrudlg.areaSlider.setValue(10)
        self.assertTrue(hrudlg.createButton.isEnabled(), 'Create button not enabled')
        QtTest.QTest.mouseClick(hrudlg.createButton, Qt.LeftButton)
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.textDir, Parameters._HRUSREPORT)))
        self.assertTrue(self.dlg.reportsBox.findText(Parameters._HRUSITEM) >= 0, \
                        'HRUs report not accessible from main form')
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.shapesDir, 'hru2.shp')), 'Actual HRUs shapefile not created.')
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.tablesOutDir, 'hrus.shp')), 'HRUs results template file not created.')
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.tablesOutDir, 'rivs.shp')), 'Reaches results template file not created.')
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.tablesOutDir, 'subs.shp')), 'Watershed results template file not created.')
        self.assertEqual(len(self.hrus.CreateHRUs.basins), 25, 'Subbasin count is {0} instead of 25'.format(len(self.hrus.CreateHRUs.basins)))
        self.assertEqual(len(self.hrus.CreateHRUs.hrus), 78, 'HRU count is {0} instead of 78'.format(len(self.hrus.CreateHRUs.hrus)))
        self.checkHashes(HashTable4)
        self.assertTrue(self.dlg.editButton.isEnabled(), 'SWAT Editor button not enabled')
        
    def test05(self):
        """No MPI; Duffins example (with triple stream reach join); delineation threshold 100 ha; merges small subbasins with default 5% threshold;  no slope limits; target 170 HRUs by percentage."""
        demFileName = self.copyDem('duff_dem.tif')
        self.delin._dlg.selectDem.setText(demFileName)
        self.assertTrue(os.path.exists(self.delin._dlg.selectDem.text()), 'Failed to copy DEM to source directory')
        self.hrus = HRUs(self.plugin._gv, self.dlg.reportsBox)
        # listener = Listener(self.delin, self.hrus, self.hrus.CreateHRUs)
        numLayers = len(QgsProject.instance().mapLayers().values())
        self.assertEqual(numLayers, 0, 'Unexpected start with {0} layers'.format(numLayers))
        demLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), self.delin._dlg.selectDem.text(), FileTypes._DEM, 
                                                         self.plugin._gv, True, QSWATUtils._WATERSHED_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(demLayer and loaded, 'Failed to load DEM {0}'.format(self.delin._dlg.selectDem.text()))
        self.assertTrue(demLayer.crs().mapUnits() == QgsUnitTypes.DistanceMeters, 'Map units not meters but {0}'.format(demLayer.crs().mapUnits()))
        unitIndex = self.delin._dlg.areaUnitsBox.findText(Parameters._HECTARES)
        self.assertTrue(unitIndex >= 0, 'Cannot find hectares area units')
        self.delin._dlg.areaUnitsBox.setCurrentIndex(unitIndex)
        self.delin.setDefaultNumCells(demLayer)
        self.delin._dlg.area.setText('100')
        self.assertTrue(self.delin._dlg.numCells.text() == '100', 'Unexpected number of cells for delineation {0}'.format(self.delin._dlg.numCells.text()))
        QSWATUtils.copyFiles(QFileInfo(os.path.join(self.dataDir, 'duff_out.shp')), self.plugin._gv.shapesDir)
        self.delin._dlg.selectOutlets.setText(os.path.join(self.plugin._gv.shapesDir, 'duff_out.shp'))
        self.assertTrue(os.path.exists(self.delin._dlg.selectOutlets.text()), 'Failed to copy duff_out.shp to Outlet directory')
        self.delin._dlg.useOutlets.setChecked(True)
        QtTest.QTest.mouseClick(self.delin._dlg.delinRunButton2, Qt.LeftButton)
        self.assertTrue(self.delin.areaOfCell > 0, 'Area of cell is ' + str(self.delin.areaOfCell))
        self.assertTrue(self.delin._dlg.selectSubButton.isEnabled(), 'Select subbasins button not enabled')
        wshedFileName = os.path.join(self.plugin._gv.sourceDir, os.path.splitext(demFileName)[0] + 'wshed.shp')
        self.assertTrue(os.path.exists(wshedFileName), 'Failed to make watershed shapefile {0}'.format(wshedFileName))
        wshedLayer = QSWATUtils.getLayerByFilename(self.root.findLayers(), wshedFileName, FileTypes._WATERSHED, 
                                                   None, None, None)[0]
        self.assertTrue(wshedLayer, 'Cannot find watershed layer')
        numSubs = wshedLayer.featureCount()
        selSubs = SelectSubbasins(self.plugin._gv, wshedLayer)
        selSubs.init()
        selSubs._dlg.checkBox.setChecked(True)
        # QtTest.QTest.mouseClick(selSubs._dlg.pushButton, Qt.LeftButton)
        selSubs.selectByThreshold()
        self.waitCountChanged(wshedLayer.selectedFeatureCount, 0)
        self.assertEqual(wshedLayer.selectedFeatureCount(), 6, 'Unexpected number of subbasins selected: {0!s}'.format(wshedLayer.selectedFeatureCount()))
        QtTest.QTest.mouseClick(self.delin._dlg.mergeButton, Qt.LeftButton)
        self.waitCountChanged(wshedLayer.featureCount, numSubs)
        # featureCount gives strange results: don't use
        # self.assertEqual(numSubs, 141, 'Wrong total subbasins {0!s}'.format(numSubs))
        # self.assertEqual(wshedLayer.featureCount(), 134, 'Wrong number of subbasins merged: {0!s}'.format(wshedLayer.featureCount()))
        QtTest.QTest.mouseClick(self.delin._dlg.OKButton, Qt.LeftButton)
        self.assertTrue(self.dlg.hrusButton.isEnabled(), 'HRUs button not enabled')
        self.hrus.init()
        hrudlg = self.hrus._dlg
        self.hrus.landuseFile = os.path.join(self.dataDir, 'duff_landuse.tif')
        numLayers = len(QgsProject.instance().mapLayers().values())
        self.hrus.landuseLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), self.hrus.landuseFile, FileTypes._LANDUSES, 
                                                                       self.plugin._gv, None, QSWATUtils._LANDUSE_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(self.hrus.landuseLayer and loaded, 'Failed to load landuse file {0}'.format(self.hrus.landuseFile))
        self.hrus.soilFile = os.path.join(self.dataDir, 'duff_soil.tif')
        numLayers = len(QgsProject.instance().mapLayers().values())
        self.hrus.soilLayer, loaded = QSWATUtils.getLayerByFilename(self.root.findLayers(), self.hrus.soilFile, FileTypes._SOILS, 
                                                                    self.plugin._gv, None, QSWATUtils._SOIL_GROUP_NAME)
        self.waitLayerAdded(numLayers)
        self.assertTrue(self.hrus.soilLayer and loaded, 'Failed to load soil file {0}'.format(self.hrus.soilFile))
        landCombo = hrudlg.selectLanduseTable
        landIndex = landCombo.findText('global_landuses')
        self.assertTrue(landIndex >= 0, 'Cannot find global landuses table')
        landCombo.setCurrentIndex(landIndex)
        soilCombo = hrudlg.selectSoilTable
        soilIndex = soilCombo.findText('global_soils')
        self.assertTrue(soilIndex >= 0, 'Cannot find global soils table')
        soilCombo.setCurrentIndex(soilIndex)
        lims = self.plugin._gv.db.slopeLimits
        self.assertTrue(len(lims) == 0, 'Failed to start with empty slope limits: limits list is {0!s}'.format(lims))
        self.assertTrue(hrudlg.elevBandsButton.isEnabled(), 'Elevation bands button not enabled')
        QtTest.QTest.mouseClick(hrudlg.readButton, Qt.LeftButton)
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.textDir, Parameters._TOPOREPORT)))
        self.assertTrue(self.dlg.reportsBox.isEnabled() and self.dlg.reportsBox.findText(Parameters._TOPOITEM) >= 0, \
                        'Elevation report not accessible from main form')
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.textDir, Parameters._BASINREPORT)))
        self.assertTrue(self.dlg.reportsBox.findText(Parameters._BASINITEM) >= 0, \
                        'Landuse and soil report not accessible from main form')
        self.assertTrue(hrudlg.splitButton.isEnabled(), 'Split landuses button not enabled')
        self.assertTrue(hrudlg.exemptButton.isEnabled(), 'Exempt landuses button not enabled')
        self.assertTrue(hrudlg.targetButton.isEnabled(), 'Target button not enabled')
        QtTest.QTest.mouseClick(hrudlg.targetButton, Qt.LeftButton)
        self.assertTrue(hrudlg.percentButton.isEnabled(), 'Percent button not enabled')
        QtTest.QTest.mouseClick(hrudlg.percentButton, Qt.LeftButton)
        self.assertTrue(hrudlg.stackedWidget.currentIndex() == 2, 'Wrong threshold page {0} selected'.format(hrudlg.stackedWidget.currentIndex()))
        hrudlg.targetVal.setText('170')
        self.assertTrue(hrudlg.createButton.isEnabled(), 'Create button not enabled')
        QtTest.QTest.mouseClick(hrudlg.createButton, Qt.LeftButton)
        self.assertTrue(os.path.exists(os.path.join(self.plugin._gv.textDir, Parameters._HRUSREPORT)))
        self.assertTrue(self.dlg.reportsBox.findText(Parameters._HRUSITEM) >= 0, \
                        'HRUs report not accessible from main form')
        self.assertEqual(len(self.hrus.CreateHRUs.basins), 134, 'Subbasin count is {0} instead of 134'.format(len(self.hrus.CreateHRUs.basins)))
        self.assertEqual(len(self.hrus.CreateHRUs.hrus), 170, 'HRU count is {0} instead of 170'.format(len(self.hrus.CreateHRUs.hrus)))
        self.checkHashes(HashTable5)
        self.assertTrue(self.dlg.editButton.isEnabled(), 'SWAT Editor button not enabled')
        
    def copyDem(self, demFile):
        """Copy DEM to Source directory as GeoTIFF."""
        inFileName = os.path.join(self.dataDir, demFile)
        outFileName = os.path.join(self.plugin._gv.sourceDir, demFile)
        inDs = gdal.Open(inFileName)
        driver = gdal.GetDriverByName('GTiff')
        outDs = driver.CreateCopy(outFileName, inDs, 0)
        if outDs is None:
            raise RuntimeError('Failed to create dem in geoTiff format')
        QSWATUtils.copyPrj(inFileName, outFileName)
        return outFileName
    
    def waitLayerAdded(self, numLayers):
        """Wait for a new layer to be added."""
        timeout = 20 # seconds
        count = 0
        while count < timeout:
            QtTest.QTest.qWait(1000) # wait 1000ms
#             # parse message log for critical errors
#             if 'QSWAT' in message_log:
#                 while message_log['QSWAT']:
#                     message, level = message_log['QSWAT'].pop()
#                     self.assertNotEqual(level, QgsMessageLog.CRITICAL, \
#                                         'Critical error in message log:\n{}'.format(message))
            # check if any layers have been added
            if len(QgsProject.instance().mapLayers().values()) > numLayers:
                break
            count += 1
            
    def waitCountChanged(self, counter, num):
        """Wait for counter to be different from num."""
        timeout = 20 # seconds
        count = 0
        while count < timeout:
            QtTest.QTest.qWait(1000) # wait 1000ms
            if not counter() == num:
                break
            count += 1
            
    def checkHashes(self, hashes):
        """Check predefined hashes against project database tables."""
        with self.plugin._gv.db.connect(readonly=True) as conn:
            self.assertTrue(conn, 'Failed to connect to project database {0}'.format(self.plugin._gv.db.dbFile))
            # useful in setting up tests: print hash
            for table in hashes.keys():
                print(table + ': ' +  self.plugin._gv.db.hashDbTable(conn, table))
#            return            
            for (table, val) in hashes.items():
                newval = self.plugin._gv.db.hashDbTable(conn, table)
                self.assertEqual(val, newval, 'Wrong hash value {0} for table {1}'.format(newval, table))
            
# this does not work, but why is mysterious
class Listener(QObject):
    """Listener for messages."""
    def __init__(self, o1, o2, o3):
        """Constructor."""
        QObject.__init__(self)
        o1.progress_signal.connect(self.listen_progress)
        o2.progress_signal.connect(self.listen_progress)
        o3.progress_signal.connect(self.listen_progress)
        
    @pyqtSlot(str)
    def listen_progress(self, msg):
        """Print msg."""
        print(msg + '\n')
            
if __name__ == '__main__':
    unittest.main()