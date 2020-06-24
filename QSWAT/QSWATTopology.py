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
# Import the PyQt and QGIS libraries
from PyQt5.QtCore import * # @UnusedWildImport
from PyQt5.QtGui import * # @UnusedWildImport
from PyQt5.QtWidgets import * # @UnusedWildImport
from qgis.core import QgsUnitTypes, QgsProject, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsField, QgsVectorLayer, QgsLayerTreeGroup, QgsRasterLayer, QgsVectorDataProvider  
from osgeo import gdal
from numpy import * # @UnusedWildImport
import os.path
import time
import traceback
from typing import Set, List, Dict, Tuple, Iterable, Iterator, cast, Any, Optional, Union, Callable, TYPE_CHECKING  # @UnusedImport @Reimport

try:
    from .QSWATUtils import QSWATUtils, FileTypes, ListFuns  # @UnresolvedImport
    from .parameters import Parameters  # @UnresolvedImport
except ImportError:
    # for convert from Arc and to plus
    from QSWATUtils import QSWATUtils, FileTypes, ListFuns  # @UnresolvedImport
    from parameters import Parameters  # @UnresolvedImport
    

class ReachData():
    """Location and elevation of points at ends of reach, 
    draining from upper to lower.
    """
        
    def __init__(self, x1: float, y1: float, z1: float, x2: float, y2: float, z2: float) -> None:
        """Initialise class variables."""
        ## x coordinate of upper end
        self.upperX = x1
        ## y coordinate of upper end
        self.upperY = y1
        ## elevation of upper end
        self.upperZ = z1
        ## x coordinate of lower end
        self.lowerX = x2
        ## y coordinate of lower end
        self.lowerY = y2
        ## elevation of lower end
        self.lowerZ = z2
        

class QSWATTopology:
    
    """Module for creating and storing topological data 
    derived from watershed delineation.
    """
    
    _LINKNO = 'LINKNO'
    _DSLINKNO = 'DSLINKNO'
    _USLINKNO1 = 'USLINKNO1'
    _USLINKNO2 = 'USLINKNO2'
    _DSNODEID = 'DSNODEID'
    _ORDER = 'Order'
    _LENGTH = 'Length'
    _MAGNITUDE = 'Magnitude'
    _DS_CONT_AR = 'DS_Cont_Ar'
    _DROP = 'Drop'
    _SLOPE = 'Slope'
    _STRAIGHT_L = 'Straight_L'
    _US_CONT_AR = 'US_Cont_Ar'
    _WSNO = 'WSNO'
    _DOUT_END = 'DOUT_END'
    _DOUT_START = 'DOUT_START'
    _DOUT_MID = 'DOUT_MID'
    _ID = 'ID'
    _INLET = 'INLET'
    _RES = 'RES'
    _PTSOURCE = 'PTSOURCE'
    _POLYGONID = 'PolygonId'
    _AREA = 'Area'
    _STREAMLINK = 'StreamLink'
    _STREAMLEN = 'StreamLen'
    _DSNODEIDW = 'DSNodeID'
    _DSWSID = 'DSWSID'
    _US1WSID = 'US1WSID'
    _US2WSID = 'US2WSID'
    _SUBBASIN = 'Subbasin'
    _PENWIDTH = 'PenWidth'
    _HRUGIS = 'HRUGIS'
    _TOTDASQKM = 'TotDASqKm'
    _SOURCEX = 'SourceX'
    _SOURCEY = 'SourceY'
    _OUTLETX = 'OutletX'
    _OUTLETY = 'OutletY'
    
    _HUCPointId = 10000  # for HUC models all point ids are this number or greater (must match value in HUC12Models.py in HUC12Watersheds 
    
    def __init__(self, isBatch: bool, isHUC: bool) -> None:
        """Initialise class variables."""
        ## Link to project database
        self.db = None
        ## True if outlet end of reach is its first point, i.e. index zero."""
        self.outletAtStart = True
        ## index to LINKNO in stream shapefile
        self.linkIndex = -1
        ## index to DSLINKNO in stream shapefile
        self.dsLinkIndex = -1
        ## index to WSNO in stream shapefile (value commonly called basin)
        self.wsnoIndex = -1
        ## LINKNO to WSNO in stream shapefile (should be identity but we won't assume it)
        # WSNO is same as PolygonId in watershed shapefile, 
        # while LINKNO is used in DSLINKNO in stream shapefile
        self.linkToBasin = dict()
        ## inverse table, possible since link-basin mapping is 1-1
        self.basinToLink = dict()
        ## WSNO does not obey SWAT rules for basin numbers (range 1:n) 
        # so we invent and store SWATBasin numbers
        # also SWAT basins may not be empty
        self.basinToSWATBasin = dict()
        ##inverse map to make it easy to output in numeric order of SWAT Basins
        self.SWATBasinToBasin = dict()
        ## LINKNO to DSLINKNO in stream shapefile
        self.downLinks = dict()
        ## zero area WSNO values
        self.emptyBasins = set()
        ## centroids of basins as (x, y) pairs in projected units
        self.basinCentroids = dict()
        ## link to reach length in metres
        self.streamLengths = dict()
        ## reach slopes in m/m
        self.streamSlopes = dict()
        ## numpy array of total area draining to downstream end of link in square metres
        self.drainAreas = None
        ## points and elevations at ends of reaches
        self.reachesData = dict()
        ## basin to area in square metres
        self.basinAreas = dict()
        ## links which are user-defined or main outlets
        self.outletLinks = set()
        ## links with reservoirs
        self.reservoirLinks = set()
        ## links with inlets
        self.inletLinks = set()
        ## links with point sources at their outlet points
        self.ptSrcLinks = set()
        ## links draining to inlets
        self.upstreamFromInlets = set()
        ## key to MonitoringPoint table
        self.MonitoringPointFid = 0
        ## width of DEM cell in metres
        self.dx = 0
        ## depth of DEM cell in metres
        self.dy = 0
        ## number of elevation grid rows to make a watershed grid cell (only used in grid model)
        self.gridRows = 0
        ## multiplier to turn DEM elevations to metres
        self.verticalFactor = 1
        ## DEM nodata value
        self.demNodata = 0
        ## DEM extent
        self.demExtent = None
        ## map from basin to outlet point (used for calculating basin flow length)
        self.outlets = dict()
        ## map from basin to near outlet point (used for placing extra reservoirs)
        self.nearoutlets = dict()
        ## map from basin to near source point (use for placing extra point sources)
        self.nearsources = dict()
        ## project projection (set from DEM)
        self.crsProject = None
        ## lat-long coordinate reference system
        self.crsLatLong = QgsCoordinateReferenceSystem.fromEpsgId(4269)
        ## Flag to show if batch run
        self.isBatch = isBatch
        ## flag for HUC projects
        self.isHUC = isHUC
        
    def setUp0(self, demLayer: QgsRasterLayer, streamLayer:  QgsVectorLayer, verticalFactor: float) -> None:
        """Set DEM size parameters and stream orientation, and store source and outlet points for stream reaches."""
        # can fail if demLayer is None or not projected
        try:
            if (self.crsProject == None):
                self.crsProject = demLayer.crs()
            units = self.crsProject.mapUnits()
        except Exception:
            QSWATUtils.loginfo('Failure to read DEM units: {0}'.format(traceback.format_exc()))
            return False
        if units == QgsUnitTypes.DistanceMeters:
            factor = 1
        elif units == QgsUnitTypes.DistanceFeet:
            factor = 0.3048
        else:
            # unknown or degrees - will be reported in delineation - just quietly fail here
            QSWATUtils.loginfo('Failure to read DEM units: {0}'.format(str(units)))
            return False
        self.dx = demLayer.rasterUnitsPerPixelX() * factor
        self.dy = demLayer.rasterUnitsPerPixelY() * factor
        QSWATUtils.loginfo('Factor is {0}, cell width is {1}, cell depth is {2}'.format(factor, self.dx, self.dy))
        self.demExtent = demLayer.extent()  # type: ignore
        self.verticalFactor = verticalFactor
        self.outletAtStart = self.hasOutletAtStart(streamLayer)
        QSWATUtils.loginfo('Outlet at start is {0!s}'.format(self.outletAtStart))
        if not self.saveOutletsAndSources(streamLayer):
            return False
        return True
        
    def setUp(self, demLayer: QgsRasterLayer, streamLayer: QgsVectorLayer, wshedLayer: QgsVectorLayer, 
              outletLayer: QgsVectorLayer, extraOutletLayer: QgsVectorLayer, db: Any, 
              existing: bool, recalculate: bool, useGridModel: bool, reportErrors: bool) -> bool:
        """Create topological data from layers."""
        self.db = db
        self.linkToBasin.clear()
        self.basinToLink.clear()
        self.basinToSWATBasin.clear()
        self.SWATBasinToBasin.clear()
        self.downLinks.clear()
        self.emptyBasins.clear()
        # do not clear centroids unless existing and not using grid model: 
        if existing and not useGridModel:
            self.basinCentroids.clear()
        self.streamLengths.clear()
        self.streamSlopes.clear()
        self.reachesData.clear()
        self.basinAreas.clear()
        self.outletLinks.clear()
        self.reservoirLinks.clear()
        self.inletLinks.clear()
        self.ptSrcLinks.clear()
        self.upstreamFromInlets.clear()
        dsNodeToLink = dict()
        if not useGridModel:
            # upstream array will get very big for grid
            us = dict()
        ignoreError = not reportErrors
        ignoreWithExisting = existing or not reportErrors
        ignoreWithGrid = useGridModel or not reportErrors
        ignoreWithGridOrExisting = ignoreWithGrid or ignoreWithExisting
        ignoreTotDA = not self.isHUC
        self.linkIndex = self.getIndex(streamLayer, QSWATTopology._LINKNO, ignoreMissing=ignoreError)
        if self.linkIndex < 0:
            QSWATUtils.loginfo('No LINKNO field in stream layer')
            return False
        self.dsLinkIndex = self.getIndex(streamLayer, QSWATTopology._DSLINKNO, ignoreMissing=ignoreError)
        if self.dsLinkIndex < 0:
            QSWATUtils.loginfo('No DSLINKNO field in stream layer')
            return False
        dsNodeIndex = self.getIndex(streamLayer, QSWATTopology._DSNODEID, ignoreMissing=ignoreWithGridOrExisting)
        self.wsnoIndex = self.getIndex(streamLayer, QSWATTopology._WSNO, ignoreMissing=ignoreError)
        if self.wsnoIndex < 0:
            QSWATUtils.loginfo('No WSNO field in stream layer')
            return False
        lengthIndex = self.getIndex(streamLayer, QSWATTopology._LENGTH, ignoreMissing=ignoreWithGridOrExisting)
        dropIndex = self.getIndex(streamLayer, QSWATTopology._DROP, ignoreMissing=ignoreWithGridOrExisting)
        totDAIndex = self.getIndex(streamLayer, QSWATTopology._TOTDASQKM, ignoreMissing=ignoreTotDA)
        polyIndex = self.getIndex(wshedLayer, QSWATTopology._POLYGONID, ignoreMissing=ignoreError)
        if polyIndex < 0:
            QSWATUtils.loginfo('No POLYGONID field in watershed layer')
            return False
        areaIndex = self.getIndex(wshedLayer, QSWATTopology._AREA, ignoreMissing=ignoreWithGridOrExisting) 
        subbasinIndex = self.getIndex(wshedLayer, QSWATTopology._SUBBASIN, ignoreMissing=ignoreWithGridOrExisting)
        if outletLayer:
            idIndex = self.getIndex(outletLayer, QSWATTopology._ID, ignoreMissing=ignoreError)
            if idIndex < 0:
                QSWATUtils.loginfo('No ID field in outlets layer')
                return False
            inletIndex = self.getIndex(outletLayer, QSWATTopology._INLET, ignoreMissing=ignoreError)
            if inletIndex < 0:
                QSWATUtils.loginfo('No INLET field in outlets layer')
                return False
            ptSourceIndex = self.getIndex(outletLayer, QSWATTopology._PTSOURCE, ignoreMissing=ignoreError)
            if ptSourceIndex < 0:
                QSWATUtils.loginfo('No PTSOURCE field in outlets layer')
                return False
            resIndex = self.getIndex(outletLayer, QSWATTopology._RES, ignoreMissing=ignoreError)
            if resIndex < 0:
                QSWATUtils.loginfo('No RES field in outlets layer')
                return False
        if extraOutletLayer:
            extraPtSourceIndex = self.getIndex(extraOutletLayer, QSWATTopology._PTSOURCE, ignoreMissing=ignoreError)
            if extraPtSourceIndex < 0:
                QSWATUtils.loginfo('No PTSOURCE field in extra outlets layer')
                return False
            extraResIndex = self.getIndex(extraOutletLayer, QSWATTopology._RES, ignoreMissing=ignoreError)
            if extraResIndex < 0:
                QSWATUtils.loginfo('No RES field in extra outlets layer')
                return False
            extraBasinIndex = self.getIndex(extraOutletLayer, QSWATTopology._SUBBASIN, ignoreMissing=ignoreError)
            if extraBasinIndex < 0:
                QSWATUtils.loginfo('No SUBBASIN field in extra outlets layer')
                return False
        self.demNodata = demLayer.dataProvider().sourceNoDataValue(1)
        time1 = time.process_time()
        maxLink = 0
        manyBasins = streamLayer.featureCount() > 950  # set smaller than Python recursion depth limit, which is 1000
        # drainAreas is a mapping from link number (used as index to array) of grid cell areas in sq m
        if self.isHUC:
            # make it a dictionary rather than a numpy array because there is a big gap
            # between most basin numbers and the nunbers for inlets (10000 +)
            # and we need to do no calculation
            # create it here for HUC models as we set it up from totDASqKm field in streamLayer
            self.drainAreas = dict()
        for reach in streamLayer.getFeatures():
            attrs = reach.attributes()
            link = attrs[self.linkIndex]
            dsLink = attrs[self.dsLinkIndex]
            wsno = attrs[self.wsnoIndex]
            if lengthIndex < 0 or recalculate:
                length = reach.geometry().length()
            else:
                length = attrs[lengthIndex]
            data = self.getReachData(reach, demLayer)
            self.reachesData[link] = data
            if length == 0:
                drop = 0
                slope = 0
            else:
                if data and (dropIndex < 0 or recalculate):
                    drop = data.upperZ - data.lowerZ
                elif dropIndex >= 0:
                    drop = attrs[dropIndex]
                else:
                    drop = 0
                slope = float(drop) / length
            dsNode = attrs[dsNodeIndex] if dsNodeIndex >= 0 else -1
            self.linkToBasin[link] = wsno
            self.basinToLink[wsno] = link
            maxLink = max(maxLink, link)
            # if the length is zero there will not (for TauDEM) be an entry in the wshed shapefile
            # unless the zero length is caused by something in the inlets/outlets file
            # but with HUC models there are empty basins for the zero length links inserted for inlets, and these have positive DSNODEIDs
            if not useGridModel and length == 0 and (dsNode < 0 or self.isHUC):
                self.emptyBasins.add(wsno)
            self.downLinks[link] = dsLink
            self.streamLengths[link] = length
            self.streamSlopes[link] = slope
            if dsNode >= 0:
                dsNodeToLink[dsNode] = link
            if dsLink >= 0 and not (self.isHUC and link >= QSWATTopology._HUCPointId):  # keep HUC links out of us map
                if not useGridModel and not manyBasins:
                    if dsLink in us and us[dsLink]:
                        us[dsLink].append(link)
                    else:
                        us[dsLink] = [link]
                    # check we haven't just made the us relation circular
                    if existing: # probably safe to assume TauDEM won't create a circular network
                        if QSWATTopology.reachable(dsLink, [link], us):
                            QSWATUtils.error(u'Circular drainage network from link {0}'.format(dsLink), self.isBatch)
                            return False
            else:
                self.outletLinks.add(link)
            if self.isHUC:
                self.drainAreas[link] = attrs[totDAIndex] * 1E6  # sq km to sq m
        # create drainAreas here for non-HUC models as we now have maxLink value to size the numpy array
        if not self.isHUC:
            self.drainAreas = zeros((maxLink + 1), dtype=float)
        time2 = time.process_time()
        QSWATUtils.loginfo('Topology setup took {0} seconds'.format(int(time2 - time1)))
        #QSWATUtils.loginfo('Finished setting tables from streams shapefile')
        for polygon in wshedLayer.getFeatures():
            attrs = polygon.attributes()
            if areaIndex < 0 or recalculate:
                area = polygon.geometry().area()
            else:
                area = attrs[areaIndex]
            basin = attrs[polyIndex]
            if useGridModel:
                # all areas the same, so just use first
                # gridArea = area # not used
                self.gridRows = int(polygon.geometry().length() / (4 * self.dy) + 0.5)
                QSWATUtils.loginfo('Using {0!s} DEM grid rows per grid cell'.format(self.gridRows))
                # note this break leaves centroids unset for grid model
                break
            self.basinAreas[basin] = area
            if manyBasins:
                # initialise drainAreas
                link = self.basinToLink[basin]
                self.drainAreas[link] = area
            # belt and braces for empty basins: already stored as empty if length of link is zero
            # in which case TauDEM makes no wshed feature, 
            # but there may be such a feature in an existing watershed shapefile
            if area == 0:
                self.emptyBasins.add(basin)
            if existing: # need to set centroids
                centroid = polygon.geometry().centroid().asPoint()
                self.basinCentroids[basin] = (centroid.x(), centroid.y())
        if outletLayer:
            features = outletLayer.getFeatures()
        else:
            features = []
        if dsNodeIndex >= 0:
            for point in features:
                attrs = point.attributes()
                dsNode = attrs[idIndex]
                if dsNode not in dsNodeToLink:
                    if reportErrors:
                        QSWATUtils.error(u'ID value {0} from inlets/outlets file {1} not found as DSNODEID in stream reaches file {2}'.format(dsNode, 
                                                                         QSWATUtils.layerFileInfo(outletLayer).filePath(), 
                                                                         QSWATUtils.layerFileInfo(streamLayer).filePath()), self.isBatch)
                else:
                    link = dsNodeToLink[dsNode]
                    # an outlet upstream from but too close to a junction can cause a basin 
                    # to not be in the basins file and hence the wshed shapefile, so we check for this
                    # The link with a wsno number missing from the wshed is downstream from this link
                    if not useGridModel:
                        dsLink = self.downLinks[link]
                        if dsLink >= 0:
                            dsBasin = self.linkToBasin[dsLink]
                            if not dsBasin in self.basinAreas: # map derived from wshed shapefile
                                if reportErrors:
                                    QSWATUtils.error(u'ID value {0} from inlets/outlets file {1} has not generated a subbasin: probably too close to a stream junction.  Please move or remove.'
                                                     .format(dsNode, QSWATUtils.layerFileInfo(outletLayer).filePath()), self.isBatch)
                                # try to avoid knock-on errors
                                self.emptyBasins.add(dsBasin)
                    isInlet = attrs[inletIndex] == 1
                    isPtSource = attrs[ptSourceIndex] == 1
                    isReservoir = attrs[resIndex] == 1
                    if isInlet:
                        if isPtSource:
                            self.ptSrcLinks.add(link)
                        else:
                            if self.isHUC:
                                # in HUC models inlets are allowed which do not split streams
                                # so use only the zero length stream added to support the inlet
                                self.inletLinks.add(link)
                            else:
                                # inlet links need to be associated with their downstream links
                                self.inletLinks.add(self.downLinks[link])
                    elif isReservoir:
                        self.reservoirLinks.add(link)
                    else:
                        self.outletLinks.add(link)
        if not useGridModel and not manyBasins:
            for link in self.inletLinks:
                self.addUpstreamLinks(link, us)
            QSWATUtils.loginfo('Outlet links: {0!s}'.format(self.outletLinks))
            QSWATUtils.loginfo('Inlet links: {0!s}'.format(self.inletLinks))
        # add any extra reservoirs and point sources
        if extraOutletLayer:
            for point in extraOutletLayer.getFeatures():
                attrs = point.attributes()
                basin = attrs[extraBasinIndex]
                link = self.basinToLink[basin]
                if basin not in self.emptyBasins and not link in self.upstreamFromInlets: 
                    if attrs[extraResIndex] == 1:
                        self.reservoirLinks.add(link)
                    if attrs[extraPtSourceIndex] == 1:
                        self.ptSrcLinks.add(link)
        if not useGridModel:
            QSWATUtils.loginfo('Reservoir links: {0!s}'.format(self.reservoirLinks))
            QSWATUtils.loginfo('Point source links: {0!s}'.format(self.ptSrcLinks))
            QSWATUtils.loginfo('Empty basins: {0!s}'.format(self.emptyBasins))
        time4 = time.process_time()
        # set drainAreas
        if not self.isHUC:
            if useGridModel:
                self.setGridDrainageAreas(maxLink)
            elif manyBasins:
                self.setManyDrainageAreas(maxLink)
            else:
                self.setDrainageAreas(us)
        time5 = time.process_time()
        QSWATUtils.loginfo(u'Topology drainage took {0} seconds'.format(int(time5 - time4)))
        
        if useGridModel:
            # lower limit on drainage area for outlets to be included
            # 1.5 multiplier guards against rounding errors:
            # ensures that any cell with drainage area exceeding this cannot be a singleton
            minDrainArea = self.dx * self.dy * self.gridRows * self.gridRows * 1.5
            # Create SWAT basin numbers for grid
            # we ignore edge basins which are outlets with nothing upstream, ie they are single cell outlets,
            # by counting only those which have a downstream link or have an upstream link
            SWATBasin = 0
            for link, basin in self.linkToBasin.items():
                dsLink = self.downLinks[link]
                if dsLink >= 0 or self.drainAreas[link] > minDrainArea:
                    SWATBasin += 1
                    self.basinToSWATBasin[basin] = SWATBasin
        else:
            # if not grid, try existing subbasin numbers as SWAT basin numbers
            ok = subbasinIndex >= 0 and self.trySubbasinAsSWATBasin(wshedLayer, polyIndex, subbasinIndex)
            if not ok:
                # failed attempt may have put data in these, so clear them
                self.basinToSWATBasin.clear()
                self.SWATBasinToBasin.clear()
                # create SWAT basin numbers
                SWATBasin = 0
                for link, basin in self.linkToBasin.items():
                    if basin not in self.emptyBasins and link not in self.upstreamFromInlets:
                        SWATBasin += 1
                        self.basinToSWATBasin[basin] = SWATBasin
                        self.SWATBasinToBasin[SWATBasin] = basin
        # put SWAT Basin numbers in subbasin field of watershed shapefile
        wshedLayer.startEditing()
        if subbasinIndex < 0:
            # need to add subbasin field
            wshedLayer.dataProvider().addAttributes([QgsField(QSWATTopology._SUBBASIN, QVariant.Int)])
            wshedLayer.updateFields()
            subbasinIndex = wshedLayer.fieldNameIndex(QSWATTopology._SUBBASIN)
        request = QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry).setSubsetOfAttributes([polyIndex])
        for feature in wshedLayer.getFeatures(request):
            basin = feature.attributes()[polyIndex]
            subbasin = self.basinToSWATBasin.get(basin, 0)
            wshedLayer.changeAttributeValue(feature.id(), subbasinIndex, subbasin)
        wshedLayer.commitChanges()
        wshedLayer.setLabelsEnabled(True)
        wshedLayer.triggerRepaint()
        return True
    
    @staticmethod
    def reachable(link: int, links: List[int], us: Dict[int, List[int]]) -> bool:
        """Return true if link is in links or reachable from an item in links via the one-many relation us."""
        if link in links:
            return True
        for nxt in links:
            if QSWATTopology.reachable(link, us.get(nxt, []), us):
                return True
        return False
                   
    def addUpstreamLinks(self, link: int, us: Dict[int, List[int]]) -> None:
        """Add to upstreamFromInlets the links upstream from link."""
        if link in us:
            ups = us[link]
            if ups:
                for up in ups:
                    self.upstreamFromInlets.add(up)
                    self.addUpstreamLinks(up, us)
    
    def setGridDrainageAreas(self, maxLink: int) -> None:
        """Calculate and save grid drain areas in sq km."""
        gridArea = self.dx * self.dy * self.gridRows * self.gridRows # area of grid cell in sq m
        self.drainAreas.fill(gridArea)
        # number of incoming links for each link
        incount = zeros((maxLink + 1), dtype=int)
        for dsLink in self.downLinks.values():
            if dsLink >= 0:
                incount[dsLink] += 1
        # queue contains all links whose drainage areas have been calculated 
        # i.e. will not increase and can be propagated
        queue = [link for link in range(maxLink + 1) if incount[link] == 0]
        while queue:
            link = queue.pop(0)
            dsLink = self.downLinks.get(link, -1)
            if dsLink >= 0:
                self.drainAreas[dsLink] += self.drainAreas[link]
                incount[dsLink] -= 1
                if incount[dsLink] == 0:
                    queue.append(dsLink)
        # incount values should now all be zero
        remainder = [link for link in range(maxLink + 1) if incount[link] > 0]
        if remainder:
            QSWATUtils.error(u'Drainage areas incomplete.  There is a circularity in links {0!s}'.format(remainder), self.isBatch)
    
               
    def setManyDrainageAreas(self, maxLink: int) -> None:
        """Calculate and save subbasin drain areas in sq km."""
        # number of incoming links for each link
        incount = zeros((maxLink + 1), dtype=int)
        for dsLink in self.downLinks.values():
            if dsLink >= 0:
                incount[dsLink] += 1
        # queue contains all links whose drainage areas have been calculated 
        # i.e. will not increase and can be propagated
        queue = [link for link in range(maxLink + 1) if incount[link] == 0]
        while queue:
            link = queue.pop(0)
            dsLink = self.downLinks.get(link, -1)
            if dsLink >= 0:
                self.drainAreas[dsLink] += self.drainAreas[link]
                incount[dsLink] -= 1
                if incount[dsLink] == 0:
                    queue.append(dsLink)
        # incount values should now all be zero
        remainder = [link for link in range(maxLink + 1) if incount[link] > 0]
        if remainder:
            QSWATUtils.error(u'Drainage areas incomplete.  There is a circularity in links {0!s}'.format(remainder), self.isBatch)
            
    def setDrainageAreas(self, us: Dict[int, List[int]]) -> None:
        """Calculate and save drainAreas."""
        for (link, basin) in self.linkToBasin.items():
            self.setLinkDrainageArea(link, basin, us)
                
    def setLinkDrainageArea(self, link: int, basin: int, us: Dict[int, List[int]]) -> None:
        """Calculate and save drainArea for link."""
        if link in self.upstreamFromInlets:
            self.drainAreas[link] = 0
            return
        if self.drainAreas[link] > 0:
            # already done in calculating one further downstream
            return
        ownArea = self.basinAreas.get(basin, 0) # basin may not exist when link is zero length, so default to zero
        upsArea = 0
        ups = us.get(link, [])
        # python seems to confuse [] with None, hence the next line
        if ups:
            for up in ups:
                self.setLinkDrainageArea(up, self.linkToBasin[up], us)
                upsArea += self.drainAreas[up]
        self.drainAreas[link] = ownArea + upsArea
        
    def getReachData(self, reach: QgsFeature, demLayer: Optional[QgsRasterLayer]) -> Optional[ReachData]:
        """Generate ReachData record for reach."""
        if self.isHUC:
            wsno = reach[self.wsnoIndex]
            pStart = self.outlets[wsno]
            pFinish = self.nearsources[wsno]
        else:
            firstLine = QSWATTopology.reachFirstLine(reach, self.dx, self.dy)
            if firstLine is None or len(firstLine) < 1:
                QSWATUtils.error(u'It looks like your stream shapefile does not obey the single direction rule, that all reaches are either upstream or downstream.', self.isBatch)
                return None
            lastLine = QSWATTopology.reachLastLine(reach, self.dx, self.dy)
            if lastLine is None or len(lastLine) < 1:
                QSWATUtils.error(u'It looks like your stream shapefile does not obey the single direction rule, that all reaches are either upstream or downstream.', self.isBatch)
                return None
            pStart = firstLine[0]
            pFinish = lastLine[len(lastLine)-1]
        startVal = QSWATTopology.valueAtPoint(pStart, demLayer)
        finishVal = QSWATTopology.valueAtPoint(pFinish, demLayer)
        if startVal is None or startVal == self.demNodata:
            if finishVal is None or finishVal == self.demNodata:
                QSWATUtils.loginfo('({0!s},{1!s}) elevation {4} to ({2!s},{3!s}) elevation {5}'
                                   .format(pStart.x(), pStart.y(), pFinish.x(), pFinish.y(), str(startVal), str(finishVal)))
                return None
            else:
                startVal = finishVal
        elif finishVal is None or finishVal == self.demNodata:
            finishVal = startVal
        if self.outletAtStart:
            maxElev = finishVal * self.verticalFactor
            minElev = startVal * self.verticalFactor
            return ReachData(pFinish.x(), pFinish.y(), maxElev, pStart.x(), pStart.y(), minElev)
        else:
            minElev = finishVal * self.verticalFactor
            maxElev = startVal * self.verticalFactor
            return ReachData(pStart.x(), pStart.y(), maxElev, pFinish.x(), pFinish.y(), minElev)
    
    @staticmethod
    def gridReachLength(data: ReachData) -> float:
        """Length of reach assuming it is a single straight line."""
        dx = data.upperX - data.lowerX
        dy = data.upperY - data.lowerY
        return math.sqrt(dx * dx + dy * dy)

    def trySubbasinAsSWATBasin(self, wshedLayer: QgsVectorLayer, polyIndex: int, subIndex: int) -> bool:
        """Return true if the subbasin field values can be used as SWAT basin numbers.
        
        The subbasin numbers, if any, can be used if those for non-empty basins downstream from inlets 
        run from 1 to N, where  N is the number of non-empty subbasins not upstream from inlets,
        and for empty or upstream from inlet subbasins are 0.
        Also populate basinToSWATBasin and SWATBasinToBasin.
        """
        assert polyIndex >= 0 and subIndex >= 0 and len(self.basinToSWATBasin) == 0 and len(self.SWATBasinToBasin) == 0
        numShapes = wshedLayer.featureCount()
        mmin = numShapes
        mmax = 0
        ignoreCount = 0
        request = QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry).setSubsetOfAttributes([subIndex, polyIndex])
        for polygon in wshedLayer.getFeatures(request):
            attrs = polygon.attributes()
            nxt = attrs[subIndex]
            basin = attrs[polyIndex]
            if basin not in self.basinToLink:
                return False
            link = self.basinToLink[basin]
            if link not in self.upstreamFromInlets and basin not in self.emptyBasins:
                if ((nxt > 0) and basin not in self.basinToSWATBasin and nxt not in self.SWATBasinToBasin):
                    if nxt < mmin: mmin = nxt
                    if nxt > mmax: mmax = nxt
                    self.basinToSWATBasin[basin] = nxt
                    self.SWATBasinToBasin[nxt] = basin
                else:
                    return False
            elif nxt == 0:
                # can be ignored
                ignoreCount += 1
            else:
                return False
        expectedCount = numShapes - ignoreCount
        return (mmin == 1) and (mmax == expectedCount) and (len(self.basinToSWATBasin) == expectedCount)
 
    @staticmethod
    def snapPointToReach(streamLayer: QgsVectorLayer, point: QgsPointXY, threshold: float, isBatch: bool) -> Optional[QgsPointXY]:
        """Return the nearest point on a stream segment to the input point."""
        line, pointIndex = QSWATTopology.nearestVertex(streamLayer, point)
        if pointIndex < 0:
            QSWATUtils.error('Cannot snap point ({0:.2f}, {1:.2f}) to stream network'.format(point.x(), point.y()), isBatch)
            return None
        p1, p2 = QSWATTopology.intercepts(line, pointIndex, point)
        p = QSWATTopology.nearer(p1, p2, point)
        if p is None:
            p = line[pointIndex]
        # check p is sufficiently near point
        if QSWATTopology.distanceMeasure(p, point) <= threshold * threshold:
            return p
        else:
            QSWATUtils.error('Cannot snap point ({0:.2f}, {1:.2f}) to stream network within threshold {2!s}'.format(point.x(), point.y(), threshold), isBatch)
            return None
        
    @staticmethod
    def nearestVertex(streamLayer: QgsVectorLayer, point: QgsPointXY) -> Tuple[List[QgsPointXY], int]:
        """Find nearest vertex in streamLayer to point and 
        return the line (list of points) in the reach and 
        index of the vertex within the line.
        """
        bestPointIndex = -1
        bestLine = None
        minMeasure = float('inf')
        for reach in streamLayer.getFeatures():
            geometry = reach.geometry()
            if geometry.isMultipart():
                parts = geometry.asMultiPolyline()
            else:
                parts = [geometry.asPolyline()]
            for line in parts:
                for j in range(len(line)):
                    measure = QSWATTopology.distanceMeasure(line[j], point)
                    if measure < minMeasure:
                        minMeasure = measure
                        bestPointIndex = j
                        bestLine = line
        # distance = math.sqrt(minMeasure)
        # QSWATUtils.information('Nearest point at ({0:.2F}, {1:.2F}), distance {2:.2F}'.format(bestReach[bestPointIndex].x(), bestReach[bestPointIndex].y(), distance), False)
        return (bestLine, bestPointIndex)
    
    @staticmethod
    def intercepts(line: List[QgsPointXY], pointIndex: int, point: QgsPointXY) -> Tuple[Optional[QgsPointXY], Optional[QgsPointXY]]:
        """Get points on segments on either side of pointIndex where 
        vertical from point meets the segment.
        """
        assert pointIndex in range(len(line))
        # first try above pointIndex
        if pointIndex == len(line) - 1:
            # We are at the upper end - no upper segment.  
            # Return just this point to avoid a tiny subbasin.
            return (line[pointIndex], line[pointIndex])
        else:
            upper = QSWATTopology.getIntercept(line[pointIndex], line[pointIndex+1], point)
        if pointIndex == 0:
            # We are at the lower end - no lower segment.  
            # Return just this point to avoid a tiny subbasin.
            return (line[0], line[0])
        else:
            lower = QSWATTopology.getIntercept(line[pointIndex], line[pointIndex-1], point)
        return (lower, upper)
    
    @staticmethod
    def getIntercept(p1: QgsPointXY, p2: QgsPointXY, p: QgsPointXY) -> Optional[QgsPointXY]:
        """Return point on line from p1 to p2 where 
        vertical from p intercepts it, or None if there is no intercept.
        """
        x1 = p1.x()
        x2 = p2.x()
        xp = p.x()
        y1 = p1.y()
        y2 = p2.y()
        yp = p.y()
        X = x1 - x2
        Y = y1 - y2
        assert not (X == 0 and Y == 0)
        prop = (X * (x1 - xp) + Y * (y1 - yp)) / (X * X + Y * Y)
        if prop < 0:
            # intercept is off the line beyond p1
            # technically we should check for prop > 1, which means 
            # intercept is off the line beyond p2, but we can assume p is nearer to p1
            return None
        else:
            assert 0 <= prop < 1
            return QPoint(x1 - prop * X, y1 - prop * Y)
        
    @staticmethod
    def nearer(p1: Optional[QgsPointXY], p2: Optional[QgsPointXY], p: QgsPointXY) -> Optional[QgsPointXY]:
        """Return the nearer of p1 and p2 to p."""
        if p1 is None: 
            return p2
        if p2 is None:
            return p1
        if QSWATTopology.distanceMeasure(p1, p) < QSWATTopology.distanceMeasure(p2, p):
            return p1
        else:
            return p2

    @staticmethod
    def distanceMeasure(p1: QgsPointXY, p2: QgsPointXY) -> float:
        """Return square of distance between p1 and p2."""
        dx = p1.x() - p2.x()
        dy = p1.y() - p2.y()
        return dx * dx + dy * dy
                    
    def writeMonitoringPointTable(self, demLayer: QgsRasterLayer, streamLayer: QgsVectorLayer) -> None:
        """Write the monitoring point table in the project database."""
        with self.db.connect() as conn:
            if not conn:
                return
            curs = conn.cursor()
            table = 'MonitoringPoint'
            clearSQL = 'DELETE FROM ' + table
            curs.execute(clearSQL)
            self.MonitoringPointFid = 1
            time1 = time.process_time()
            # Add outlets from subbasins
            for link in self.linkToBasin:
                if link in self.outletLinks:
                    continue # added later; different type
                if link in self.upstreamFromInlets:
                    continue # excluded
                basin = self.linkToBasin[link]
                if basin not in self.basinToSWATBasin:
                    continue
                data = self.reachesData[link]
                self.addMonitoringPoint(curs, demLayer, streamLayer, link, data, 'L')
            # Add outlets
            for link in self.outletLinks:
                # omit basins upstream from inlets
                if link in self.upstreamFromInlets:
                    continue
                basin = self.linkToBasin[link]
                if basin not in self.basinToSWATBasin:
                    continue
                data = self.reachesData[link]
                self.addMonitoringPoint(curs, demLayer, streamLayer, link, data, 'T')
            # Add inlets
            for link in self.inletLinks:
                if link in self.upstreamFromInlets: 
                # shouldn't happen, but users can be stupid
                    continue
                data = self.reachesData[link]
                self.addMonitoringPoint(curs, demLayer, streamLayer, link, data, 'W')
            # Add point sources
            for link in self.ptSrcLinks:
                if link in self.upstreamFromInlets:
                    continue
                data = self.reachesData[link]
                self.addMonitoringPoint(curs, demLayer, streamLayer, link, data, 'P')
            # Add reservoirs
            for link in self.reservoirLinks:
                if link in self.upstreamFromInlets:
                    continue
                data = self.reachesData[link]
                self.addMonitoringPoint(curs, demLayer, streamLayer, link, data, 'R')
            time2 = time.process_time()
            QSWATUtils.loginfo('Writing MonitoringPoint table took {0} seconds'.format(int(time2 - time1)))
            self.db.hashDbTable(conn, table)
    
    def addMonitoringPoint(self, cursor: Any, demLayer: QgsRasterLayer, streamLayer: QgsVectorLayer, 
                           link: int, data: ReachData, typ: str) -> None:
        """Add a point to the MonitoringPoint table."""
        table = 'MonitoringPoint'
        POINTID = 0 # not used by SWAT Editor
        HydroID = self.MonitoringPointFid + 400000
        OutletID = self.MonitoringPointFid + 100000
        if self.isHUC and typ == 'W':
            # point is associated with zero length link added for it, which has an empty basin
            # so need to use downstream basin
            dsLink = self.downLinks[link]
            basin = self.linkToBasin[dsLink]
        else:
            basin = self.linkToBasin[link]
        # guard against empty basins (included for outlet points)
        SWATBasin = self.basinToSWATBasin.get(basin, 0)
        GRID_CODE = SWATBasin
        # inlets will be located at the upstream ends of their links
        # since they are attached to their downstream basins
        isUp = ((typ == 'W') or (type == 'I'))
        if not data:
            return
        if isUp:
            pt = QgsPointXY(data.upperX, data.upperY)
        else:
            pt = QgsPointXY(data.lowerX, data.lowerY)
        ptll = self.pointToLatLong(pt)
        elev = 0 # only used for weather gauges
        name = '' # only used for weather gauges
        sql = "INSERT INTO " + table + " VALUES(?,0,?,?,?,?,?,?,?,?,?,?,?,?)"
        cursor.execute(sql, self.MonitoringPointFid, POINTID, GRID_CODE, \
                       float(pt.x()), float(pt.y()), float(ptll.y()), float(ptll.x()), float(elev), name, typ, SWATBasin, HydroID, OutletID)
        self.MonitoringPointFid += 1;
    
    def writeReachTable(self, streamLayer: QgsVectorLayer, gv: Any) -> Optional[QgsVectorLayer]:  # setting type of gv to GlobalVars prevents plugin loading
        """
        Write the Reach table in the project database, make riv1.shp in shapes directory, and copy as results template to TablesOut directory.
        
        Changes the stream layer, so if successful, returns the new one.
        """
        QSWATUtils.copyShapefile(gv.streamFile, Parameters._RIV1, gv.shapesDir)
        riv1File = QSWATUtils.join(gv.shapesDir, Parameters._RIV1 + '.shp')
        riv1Layer = QgsVectorLayer(riv1File, 'Stream reaches ({0})'.format(Parameters._RIV1), 'ogr')
        provider1 = riv1Layer.dataProvider()
        # add Subbasin field unless already has it
        subIdx = self.getIndex(riv1Layer, QSWATTopology._SUBBASIN, ignoreMissing=True)
        if subIdx < 0:
            OK = provider1.addAttributes([QgsField(QSWATTopology._SUBBASIN, QVariant.Int)])
            if not OK:
                QSWATUtils.error('Cannot add {0} field to stream reaches shapefile {1}'.format(QSWATTopology._SUBBASIN, riv1File), self.isBatch)
                return None
            riv1Layer.updateFields()
            subIdx = self.getIndex(riv1Layer, QSWATTopology._SUBBASIN)
        wsnoIdx = self.getIndex(riv1Layer, QSWATTopology._WSNO)
        request = QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry).setSubsetOfAttributes([wsnoIdx])
        basinsMap = dict()
        zeroRids = []
        for reach in riv1Layer.getFeatures(request):
            basin = reach.attributes()[wsnoIdx]
            SWATBasin = self.basinToSWATBasin.get(basin, 0)
            rid = reach.id()
            if SWATBasin == 0:
                zeroRids.append(rid)
            basinsMap[rid] = dict()
            basinsMap[rid][subIdx] = SWATBasin
        OK = provider1.changeAttributeValues(basinsMap)
        if not OK:
            QSWATUtils.error('Cannot add Subbasin values to stream reaches shapefile {0}'.format(riv1File), self.isBatch)
            return None
        if zeroRids:
            OK = provider1.deleteFeatures(zeroRids)
            if not OK:
                QSWATUtils.error('Cannot remove zero basins from stream reaches shapefile {0}'.format(riv1File), self.isBatch)
                return None
        # Add fields from Reach table to riv1File if less than RIV1SUBS1MAX features; otherwise takes too long.
        addToRiv1 = not gv.useGridModel and riv1Layer.featureCount() <= Parameters._RIV1SUBS1MAX
        # if we are adding fields we need to
        # 1. remove other fields from riv1
        # 2. copy to make results template
        # and if not we need to 
        # 1. copy to make results template
        # 2. remove other fields from template
        # remove fields apart from Subbasin
        if addToRiv1:
            self.removeFields(provider1, [QSWATTopology._SUBBASIN], riv1File, self.isBatch)
        # make copy as template for stream results
        # first relinquish all references to riv1File for changes to take effect
        riv1Layer = None
        QSWATUtils.copyShapefile(riv1File, Parameters._RIVS, gv.tablesOutDir)
        rivFile = QSWATUtils.join(gv.tablesOutDir, Parameters._RIVS + '.shp')
        rivLayer = QgsVectorLayer(rivFile, 'Stream reaches', 'ogr')
        provider = rivLayer.dataProvider()
        if not addToRiv1:
            self.removeFields(provider, [QSWATTopology._SUBBASIN], rivFile, self.isBatch)
        if not gv.useGridModel:
            # add PenWidth field to stream results template
            OK = provider.addAttributes([QgsField(QSWATTopology._PENWIDTH, QVariant.Double)])
            if not OK:
                QSWATUtils.error('Cannot add {0} field to stream reaches results template {1}'.format(QSWATTopology._PENWIDTH, rivFile), self.isBatch)
                return None
        if addToRiv1:
            fields = []
            fields.append(QgsField('SubbasinR', QVariant.Int))
            fields.append(QgsField('AreaC', QVariant.Double, len=20, prec=0))
            fields.append(QgsField('Len2', QVariant.Double))
            fields.append(QgsField('Slo2', QVariant.Double))
            fields.append(QgsField('Wid2', QVariant.Double))
            fields.append(QgsField('Dep2', QVariant.Double))
            fields.append(QgsField('MinEl', QVariant.Double))
            fields.append(QgsField('MaxEl', QVariant.Double))
            fields.append(QgsField('Shape_Len', QVariant.Double))
            fields.append(QgsField('HydroID', QVariant.Int))
            fields.append(QgsField('OutletID', QVariant.Int))
            riv1Layer = QgsVectorLayer(riv1File, 'Stream reaches ({0})'.format(Parameters._RIV1), 'ogr')
            provider1 = riv1Layer.dataProvider()
            provider1.addAttributes(fields)
            riv1Layer.updateFields()
            subIdx = self.getIndex(riv1Layer, QSWATTopology._SUBBASIN)
            subRIdx = self.getIndex(riv1Layer, 'SubbasinR')
            areaCIdx = self.getIndex(riv1Layer, 'AreaC')
            len2Idx = self.getIndex(riv1Layer, 'Len2')
            slo2Idx = self.getIndex(riv1Layer, 'Slo2')
            wid2Idx = self.getIndex(riv1Layer, 'Wid2')
            dep2Idx = self.getIndex(riv1Layer, 'Dep2')
            minElIdx = self.getIndex(riv1Layer, 'MinEl')
            maxElIdx = self.getIndex(riv1Layer, 'MaxEl')
            shapeLenIdx = self.getIndex(riv1Layer, 'Shape_Len')
            hydroIdIdx = self.getIndex(riv1Layer, 'HydroID')
            OutletIdIdx = self.getIndex(riv1Layer, 'OutletID')
            mmap = dict()
        with self.db.connect() as conn:
            if not conn:
                return None
            curs = conn.cursor()
            table = 'Reach'
            clearSQL = 'DELETE FROM ' + table
            curs.execute(clearSQL)
            oid = 0
            time1 = time.process_time()
            wid2Data = dict()
            for link, basin in self.linkToBasin.items():
                SWATBasin = self.basinToSWATBasin.get(basin, 0)
                if SWATBasin == 0:
                    continue
                downLink = self.downLinks[link]                          
                if downLink < 0:
                    downSWATBasin = 0
                else:
                    downBasin = self.linkToBasin[downLink]
                    while downLink >= 0 and downBasin in self.emptyBasins:
                        downLink = self.downLinks[downLink]
                        downBasin = self.linkToBasin.get(downLink, -1)
                    if downLink < 0:
                        downSWATBasin = 0
                    else:
                        downSWATBasin = self.basinToSWATBasin.get(downLink, 0)
                drainAreaHa = float(self.drainAreas[link] / 1E4) # contributing area in ha
                drainAreaKm = drainAreaHa / 100  # contributing area in sq km
                length = float(self.streamLengths[link])
                slopePercent = float(self.streamSlopes[link] * 100)
                # Formulae from Srini 11/01/06
                channelWidth = float(1.29 * drainAreaKm ** 0.6)
                wid2Data[SWATBasin] = channelWidth
                channelDepth = float(0.13 * drainAreaKm ** 0.4)
                reachData = self.reachesData[link]
                if not reachData:
                    continue
                minEl = float(reachData.lowerZ)
                maxEl = float(reachData.upperZ)
                if addToRiv1:
                    # find the feature for this subbasin
                    fid1 = -1
                    request = QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry).setSubsetOfAttributes([subIdx])
                    for feature in riv1Layer.getFeatures(request):
                        if feature.attributes()[subIdx]  == SWATBasin:
                            fid1 = feature.id()
                            break
                    if fid1 < 0:
                        QSWATUtils.error('Cannot find subbasin {0!s} in {1}'.format(SWATBasin, riv1File), self.isBatch)
                        return None
                    mmap[fid1] = dict()
                    mmap[fid1][subRIdx] = downSWATBasin
                    mmap[fid1][areaCIdx] = drainAreaHa
                    mmap[fid1][len2Idx] = length
                    mmap[fid1][slo2Idx] = slopePercent
                    mmap[fid1][wid2Idx] = channelWidth
                    mmap[fid1][dep2Idx] = channelDepth
                    mmap[fid1][minElIdx] = minEl
                    mmap[fid1][maxElIdx] = maxEl
                    mmap[fid1][shapeLenIdx] = length
                    mmap[fid1][hydroIdIdx] = SWATBasin + 200000
                    mmap[fid1][OutletIdIdx] = SWATBasin + 100000
                oid += 1
                sql = "INSERT INTO " + table + " VALUES(?,0,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                curs.execute(sql, oid, SWATBasin, SWATBasin, SWATBasin, downSWATBasin, SWATBasin, downSWATBasin, \
                             drainAreaHa, length, slopePercent, channelWidth, channelDepth, minEl, maxEl, \
                             length, SWATBasin + 200000, SWATBasin + 100000)
            time2 = time.process_time()
            QSWATUtils.loginfo('Writing Reach table took {0} seconds'.format(int(time2 - time1)))
            self.db.hashDbTable(conn, table)
        if addToRiv1:
            OK = provider1.changeAttributeValues(mmap)
            if not OK:
                QSWATUtils.error('Cannot edit values in stream reaches shapefile {0}'.format(riv1File), self.isBatch)
                return None
        if gv.useGridModel:
            return streamLayer
        else:
            QSWATTopology.setPenWidth(wid2Data, provider, self.isBatch)
            # add layer in place of stream reaches layer
            root = QgsProject.instance().layerTreeRoot()
            riv1Layer = QSWATUtils.getLayerByFilename(root.findLayers(), riv1File, FileTypes._REACHES, 
                                                      gv, streamLayer, QSWATUtils._WATERSHED_GROUP_NAME)[0]
            if streamLayer:
                QSWATUtils.setLayerVisibility(streamLayer, False, root)
            return riv1Layer
    
    @staticmethod
    def removeFields(provider: QgsVectorDataProvider, keepFieldNames: List[str], fileName: str, isBatch: bool) -> None:
        """Remove fields other than keepFieldNames from shapefile fileName with provider."""
        toDelete = []
        fields = provider.fields()
        for idx in range(fields.count()):
            name = fields.field(idx).name()
            if not name in keepFieldNames:
                toDelete.append(idx)
        if len(toDelete) > 0:
            OK = provider.deleteAttributes(toDelete)
            if not OK:
                QSWATUtils.error('Cannot remove fields from shapefile {0}'.format(fileName), isBatch)
    
    @staticmethod
    def setPenWidth(data: Dict[int, float], provider: QgsVectorDataProvider, isBatch: bool) -> None:
        """Scale wid2 data to 1 .. 4 and write to layer."""
        minW = float('inf')
        maxW = 0
        for val in data.values():
            minW = min(minW, val)
            maxW = max(maxW, val)
        if maxW > minW: # guard against division by zero
            rng = maxW - minW
            fun = lambda x: (x - minW) * 3 / rng + 1.0
        else:
            fun = lambda _: 1.0
        subIdx = provider.fieldNameIndex(QSWATTopology._SUBBASIN)
        if subIdx < 0:
            QSWATUtils.error(u'Cannot find {0} field in stream reaches results template'.format(QSWATTopology._SUBBASIN))
            return
        penIdx = provider.fieldNameIndex(QSWATTopology._PENWIDTH)
        if penIdx < 0:
            QSWATUtils.error(u'Cannot find {0} field in stream reaches results template'.format(QSWATTopology._PENWIDTH))
            return
        request = QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry).setSubsetOfAttributes([subIdx, penIdx])
        mmap = dict()
        for f in provider.getFeatures(request):
            sub = f[subIdx]
            mmap[f.id()] = {penIdx: float(fun(data[sub]))}
        OK = provider.changeAttributeValues(mmap)
        if not OK:
            QSWATUtils.error(u'Cannot edit stream reaches results template', isBatch)
            
    def makeStreamOutletThresholds(self, gv: Any, root: QgsLayerTreeGroup) -> int:
        """
        Make file like D8 contributing area but with heightened values at subbasin outlets.
        
        Return -1 if cannot make the file.
        """
        assert os.path.exists(gv.demFile)
        demBase = os.path.splitext(gv.demFile)[0]
        ad8File = demBase + 'ad8.tif'
        if not os.path.exists(ad8File):
            # Probably using existing watershed but switched tabs in delineation form
            # At any rate, cannot calculate flow paths
            QSWATUtils.loginfo('ad8 file not found')
            return -1
        if not QSWATUtils.isUpToDate(gv.demFile, ad8File):
            # Probably using existing watershed but switched tabs in delineation form
            # At any rate, cannot calculate flow paths
            QSWATUtils.loginfo('ad8 file out of date')
            return -1
        gv.hd8File = demBase + 'hd8.tif'
        ok, path = QSWATUtils.removeLayerAndFiles(gv.hd8File, root)
        if not ok:
            QSWATUtils.error('Failed to remove old {0}: try repeating last click, else remove manually.'.format(path), self.isBatch)
            return -1
        assert not os.path.exists(gv.hd8File)
        assert len(self.outlets) > 0
        ad8Layer = QgsRasterLayer(ad8File, 'D8 contributing area')
        # calculate maximum contributing area at an outlet point
        maxContrib = 0
        for outlet in self.outlets.values():
            contrib = QSWATTopology.valueAtPoint(outlet, ad8Layer)
            # assume ad8nodata is negative
            if not (contrib is None or contrib < 0):
                maxContrib = max(maxContrib, contrib)
        threshold = int(2 * maxContrib)
        # copy ad8 to hd8 and then set outlet point values to threshold
        ad8Ds = gdal.Open(ad8File)
        driver = gdal.GetDriverByName('GTiff')
        hd8Ds = driver.CreateCopy(gv.hd8File, ad8Ds, 0)
        if not hd8Ds:
            QSWATUtils.error('Failed to create hd8 file {0}'.format(gv.hd8File), self.isBatch)
            return -1
        ad8Ds = None
        QSWATUtils.copyPrj(ad8File, gv.hd8File)
        band = hd8Ds.GetRasterBand(1)
        transform = hd8Ds.GetGeoTransform()
        arr = array([[threshold]])
        for outlet in self.outlets.values():
            x, y = QSWATTopology.projToCell(outlet.x(), outlet.y(), transform)
            band.WriteArray(arr, x, y)
        hd8Ds = None
        return threshold
      
    @staticmethod      
    def burnStream(streamFile: str, demFile: str, burnFile: str, verticalFactor: float, isBatch: bool) -> None:
        """Create as burnFile a copy of demFile with points on lines streamFile reduced in height by 50 metres."""
        # use vertical factor to convert from metres to vertical units of DEM
        demReduction = 50.0 / verticalFactor # TODO: may want to change this value or allow user to change
        assert not os.path.exists(burnFile)
        demDs = gdal.Open(demFile)
        driver = gdal.GetDriverByName('GTiff')
        burnDs = driver.CreateCopy(burnFile, demDs, 0)
        if burnDs is None:
            QSWATUtils.error('Failed to create burned-in DEM {0}'.format(burnFile), isBatch)
            return
        demDs = None
        QSWATUtils.copyPrj(demFile, burnFile)
        band = burnDs.GetRasterBand(1)
        nodata = band.GetNoDataValue()
        burnTransform = burnDs.GetGeoTransform()
        streamLayer = QgsVectorLayer(streamFile, 'Burn in streams', 'ogr')
        start = time.process_time()
        countHits = 0
        countPoints = 0
        countChanges = 0
        changed = dict()
        for reach in streamLayer.getFeatures():
            geometry = reach.geometry()
            if geometry.isMultipart():
                lines = geometry.asMultiPolyline()
            else:
                lines = [geometry.asPolyline()]
            for line in lines:
                for i in range(len(line) - 1):
                    countPoints += 1
                    p0 = line[i]
                    px0 = p0.x()
                    py0 = p0.y()
                    x0, y0 = QSWATTopology.projToCell(px0, py0, burnTransform)
                    p1 = line[i+1]
                    px1 = p1.x()
                    py1 = p1.y()
                    x1, y1 = QSWATTopology.projToCell(px1, py1, burnTransform)
                    steep = abs(y1 - y0) > abs(x1 - x0)
                    if steep:
                        x0, y0 = y0, x0
                        x1, y1 = y1, x1
                    if x0 > x1:
                        x0, x1 = x1, x0
                        y0, y1 = y1, y0
                    deltax = x1 - x0
                    deltay = abs(y1 - y0)
                    err = 0
                    deltaerr = deltay
                    y = y0
                    ystep = 1 if y0 < y1 else -1
                    arr = array([[0.0]])
                    for x in range(x0, x1+1):
                        if steep:
                            if QSWATTopology.addPointToChanged(changed, y, x):
                                arr = band.ReadAsArray(y, x, 1, 1)
                                # arr may be none if stream map extends outside DEM extent
                                if arr and arr[0,0] != nodata:
                                    arr[0,0] = arr[0,0] - demReduction
                                    band.WriteArray(arr, y, x)
                                    countChanges += 1
                            else:
                                countHits += 1
                        else:
                            if QSWATTopology.addPointToChanged(changed, x, y):
                                arr = band.ReadAsArray(x, y, 1, 1)
                                # arr may be none if stream map extends outside DEM extent
                                if arr and arr[0,0] != nodata:
                                    arr[0,0] = arr[0,0] - demReduction
                                    band.WriteArray(arr, x, y)
                                    countChanges += 1
                            else:
                                countHits += 1
                        err += deltaerr
                        if 2 * err < deltax:
                            continue
                        y += ystep
                        err -= deltax
        finish = time.process_time()
        QSWATUtils.loginfo('Created burned-in DEM {0} in {1!s} milliseconds; {2!s} points; {3!s} hits; {4!s} changes'.format(burnFile, int((finish - start)*1000), countPoints, countHits, countChanges))
        
    @staticmethod
    def addPointToChanged(changed: Dict[int, List[int]], col: int, row: int) -> bool:
        """Changed points held in dictionary column -> row-sortedlist, since it is like a sparse matrix.
        Add a point unless ready there.  Return true if added.
        """
        rows = changed.get(col, [])
        inserted = ListFuns.insertIntoSortedList(row, rows, True)
        if inserted:
            changed[col] = rows
            return True
        else:
            return False
        
    @staticmethod  
    def valueAtPoint(point: QgsPointXY, layer: QgsRasterLayer) -> Optional[float]:
        """
        Get the band 1 value at point in a grid layer.
        
        Note that this can return None if the point is outside the extent as well as nodata.
        """
        # use band 1
        val, ok =  layer.dataProvider().sample(point, 1)
        if not ok:
            return None
        else:
            return val
         
    def isUpstreamBasin(self, basin: int) -> bool:
        """Return true if a basin is upstream from an inlet."""
        return self.basinToLink.get(basin, -1) in self.upstreamFromInlets
    
    def pointToLatLong(self, point: QgsPointXY) -> QgsPointXY: 
        """Convert a QgsPointXY to latlong coordinates and return it."""
        crsTransform = QgsCoordinateTransform(self.crsProject, self.crsLatLong, QgsProject.instance())
        geom = QgsGeometry().fromPointXY(point)
        geom.transform(crsTransform)
        return geom.asPoint()
            
    def getIndex(self, layer: QgsVectorLayer, name: str, ignoreMissing: bool=False) -> int:
        """Get the index of a shapefile layer attribute name, 
        reporting error if not found, unless ignoreMissing is true.
        """
        # field names are truncated to 10 characters when created, so only search for up to 10 characters
        index = layer.fields().lookupField(name[:10])
        if not ignoreMissing and index < 0:
            QSWATUtils.error('Cannot find field {0} in {1}'.format(name, QSWATUtils.layerFileInfo(layer).filePath()), self.isBatch)
        return index
            
    def getProviderIndex(self, provider: QgsVectorDataProvider, name: str, ignoreMissing: bool=False) -> int:
        """Get the index of a shapefile provider attribute name, 
        reporting error if not found, unless ignoreMissing is true.
        """
        # field names are truncated to 10 characters when created, so only search for up to 10 characters
        index = provider.fieldNameIndex(name[:10])
        if not ignoreMissing and index < 0:
            QSWATUtils.error('Cannot find field {0} in provider'.format(name), self.isBatch)
        return index
    
    def makePointInLine(self, reach: QgsFeature, percent: float) -> QgsPointXY:
        """Return a point percent along line from outlet end to next point."""
        if self.outletAtStart:
            line = QSWATTopology.reachFirstLine(reach, self.dx, self.dy)
            pt1 = line[0]
            pt2 = line[1]
        else:
            line = QSWATTopology.reachLastLine(reach, self.dx, self.dy)
            length = len(line)
            pt1 = line[length-1]
            pt2 = line[length-2]
        x = (pt1.x() * (100 - percent) + pt2.x() * percent) / 100.0
        y = (pt1.y() * (100 - percent) + pt2.y() * percent) / 100.0
        return QgsPointXY(x, y)
    
    def hasOutletAtStart(self, streamLayer: QgsVectorLayer) -> bool:
        """Returns true iff streamLayer lines have their outlet points at their start points.
         
        Finds shapes with a downstream connections, and 
        determines the orientation by seeing how such a shape is connected to the downstream shape.
        If they don't seem to be connected (as my happen after merging subbasins) 
        tries other shapes with downstream connections, up to 10.
        A line is connected to another if their ends are less than dx and dy apart horizontally and vertically.
        Assumes the orientation found for this shape can be used generally for the layer.
        For HUC models just returns False immediately as NHD flowlines start from source end.
        """
        if self.isHUC:
            return False
        self.linkIndex = self.getIndex(streamLayer, QSWATTopology._LINKNO, ignoreMissing=False)
        if self.linkIndex < 0:
            QSWATUtils.error('No LINKNO field in stream layer', self.isBatch)
            return True # default as true for TauDEM
        self.dsLinkIndex = self.getIndex(streamLayer, QSWATTopology._DSLINKNO, ignoreMissing=False)
        if self.dsLinkIndex < 0:
            QSWATUtils.error('No DSLINKNO field in stream layer', self.isBatch)
            return True # default as true for TauDEM
        # find candidates: links with a down connection
        candidates = [] # reach, downReach pairs
        for reach in streamLayer.getFeatures():
            downLink = reach.attributes()[self.dsLinkIndex]
            if downLink >= 0:
                # find the down reach
                downReach = QSWATUtils.getFeatureByValue(streamLayer, self.linkIndex, downLink)
                if downReach:
                    candidates.append((reach, downReach))
                    if len(candidates) < 10:
                        continue
                    else:
                        break
                else:
                    QSWATUtils.error('Cannot find link {0!s} in {1}'.format(downLink, QSWATUtils.layerFileInfo(streamLayer).filePath()), self.isBatch)
                    return True
        if candidates == []:
            QSWATUtils.information('Cannot find link with a downstream link in {0}.  Do you only have one stream?'.format(QSWATUtils.layerFileInfo(streamLayer).filePath()), self.isBatch)
            return True
        for (upReach, downReach) in candidates:
            downStart = QSWATTopology.reachFirstLine(downReach, self.dx, self.dy)
            if downStart is None:
                continue
            downFinish = QSWATTopology.reachLastLine(downReach, self.dx, self.dy)
            if downFinish is None:
                continue
            upStart = QSWATTopology.reachFirstLine(upReach, self.dx, self.dy)
            if upStart is None:
                continue
            upFinish = QSWATTopology.reachLastLine(upReach, self.dx, self.dy)
            if upFinish is None:
                continue
            if QSWATTopology.pointOnLine(upStart[0], downFinish, self.dx, self.dy):
                return True
            if QSWATTopology.pointOnLine(upFinish[-1], downStart, self.dx, self.dy):
                return False
        QSWATUtils.information('Cannot find physically connected reaches in reaches shapefile {0}.  Try increasing nearness threshold'.format(QSWATUtils.layerFileInfo(streamLayer).filePath()), self.isBatch)  
        return True
    
    def saveOutletsAndSources(self, streamLayer: QgsVectorLayer) -> bool:
        """Write outlets, nearoutlets and nearsources tables."""
        # in case called twice
        self.outlets.clear()
        self.nearoutlets.clear()
        self.nearsources.clear()
        lengthIndex = self.getIndex(streamLayer, QSWATTopology._LENGTH, ignoreMissing=not self.isHUC)
        wsnoIndex = self.getIndex(streamLayer, QSWATTopology._WSNO, ignoreMissing=not self.isHUC)
        sourceXIndex = self.getIndex(streamLayer, QSWATTopology._SOURCEX, ignoreMissing=not self.isHUC)
        sourceYIndex = self.getIndex(streamLayer, QSWATTopology._SOURCEY, ignoreMissing=not self.isHUC)
        outletXIndex = self.getIndex(streamLayer, QSWATTopology._OUTLETX, ignoreMissing=not self.isHUC)
        outletYIndex = self.getIndex(streamLayer, QSWATTopology._OUTLETY, ignoreMissing=not self.isHUC)
        for reach in streamLayer.getFeatures():
            attrs = reach.attributes()
            if lengthIndex < 0:
                length = reach.geometry().length()
            else:
                length = attrs[lengthIndex]
            if self.isHUC:
                basin = attrs[wsnoIndex]
                self.outlets[basin] = QgsPointXY(attrs[outletXIndex], attrs[outletYIndex])
                self.nearoutlets[basin] = self.outlets[basin]  # unlikely to be studied viusally, so not important
                self.nearsources[basin] = QgsPointXY(attrs[sourceXIndex], attrs[sourceYIndex])
            elif length > 0: # otherwise can ignore
                basin = attrs[wsnoIndex]
                first = QSWATTopology.reachFirstLine(reach, self.dx, self.dy)
                if first is None or len(first) < 2:
                    if self.isHUC:
                        QSWATUtils.error(u'You probably have a loop in stream of subbasin {0} and will have to add a comid to channelsToOmit'.format(basin), self.isBatch)
                    else:
                        QSWATUtils.error(u'It looks like your stream shapefile does not obey the single direction rule, that all reaches are either upstream or downstream.', self.isBatch)
                    return False
                p1 = first[0]
                p2 = first[1]
                midFirst = QgsPointXY((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0)
                last = QSWATTopology.reachLastLine(reach, self.dx, self.dy)
                if last is None or len(last) < 2:
                    if self.isHUC:
                        QSWATUtils.error(u'You probably have a loop in stream of subbasin {0} and will have to add a comid to channelsToOmit'.format(basin), self.isBatch)
                    else:
                        QSWATUtils.error(u'It looks like your stream shapefile does not obey the single direction rule, that all reaches are either upstream or downstream.', self.isBatch)
                    return False
                p1 = last[-1]
                p2 = last[-2]
                midLast = QgsPointXY((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0)
                if self.outletAtStart:
                    self.outlets[basin] = first[0]
                    self.nearoutlets[basin] = midFirst
                    self.nearsources[basin] = midLast
                else:
                    self.outlets[basin] = last[-1]
                    self.nearoutlets[basin] = midLast
                    self.nearsources[basin] = midFirst
        return True
    
    @staticmethod
    def reachFirstLine(reach: QgsFeature, dx: float, dy: float) -> Optional[List[QgsPointXY]]:
        """Returns the line of a single polyline, 
        or a line in a multipolyline whose first point is not adjacent to a point 
        of another line in the multipolyline.
        """
        geometry = reach.geometry()
        if not geometry.isMultipart():
            return geometry.asPolyline()
        mpl = geometry.asMultiPolyline()
        numLines = len(mpl)
        for i in range(numLines):
            linei = mpl[i]
            connected = False
            if linei is None or len(linei) == 0:
                continue
            else:
                start = linei[0]
                for j in range(numLines):
                    if i != j:
                        linej = mpl[j]
                        if QSWATTopology.pointOnLine(start, linej, dx, dy):
                            connected = True
                            break
            if not connected:
                return linei
        # should not get here
        return None
    
    @staticmethod
    def reachLastLine(reach: QgsFeature, dx: float, dy: float) -> Optional[List[QgsPointXY]]:
        """Returns the line of a single polyline, 
        or a line in a multipolyline whose last point is not adjacent to a point 
        of another line in the multipolyline.
        """
        geometry = reach.geometry()
        if not geometry.isMultipart():
            return geometry.asPolyline()
        mpl = geometry.asMultiPolyline()
        numLines = len(mpl)
        for i in range(numLines):
            linei = mpl[i]
            connected = False
            if linei is None or len(linei) == 0:
                continue
            else:
                finish = linei[-1]
                for j in range(numLines):
                    if i != j:
                        linej = mpl[j]
                        if QSWATTopology.pointOnLine(finish, linej, dx, dy):
                            connected = True
                            break
            if not connected:
                return linei
        # should not get here
        return None
    
    @staticmethod
    def pointOnLine(point: QgsPointXY, line: List[QgsPointXY], dx: float, dy: float) -> bool:
        """Return true if point is within dx and dy horizontally and vertically
        of a point on the line. 
        
        Note this only checks if the point is close to a vertex."""
        if line is None or len(line) == 0:
            return False
        x = point.x()
        y = point.y()
        xThreshold = dx * Parameters._NEARNESSTHRESHOLD
        yThreshold = dy * Parameters._NEARNESSTHRESHOLD
        for pt in line:
            if abs(x - pt.x()) < xThreshold and abs(y - pt.y()) < yThreshold:
                return True
        return False
            
    @staticmethod
    def colToX(col: int, transform: Dict[int, float]) -> float:
        """Convert column number to X-coordinate."""
        return (col + 0.5) * transform[1] + transform[0]
    
    @staticmethod
    def rowToY(row: int, transform: Dict[int, float]) -> float:
        """Convert row number to Y-coordinate."""
        return (row + 0.5) * transform[5] + transform[3]
    
    @staticmethod
    def xToCol(x: float, transform: Dict[int, float]) -> int:
        """Convert X-coordinate to column number."""
        return int((x - transform[0]) / transform[1])
    
    @staticmethod
    def yToRow(y: float, transform: Dict[int, float]) -> int:
        """Convert Y-coordinate to row number."""
        return int((y - transform[3]) / transform[5])
        
    @staticmethod
    def cellToProj(col: int, row: int, transform: Dict[int, float]) -> Tuple[float, float]:
        """Convert column and row numbers to (X,Y)-coordinates."""
        x = (col + 0.5) * transform[1] + transform[0]
        y = (row + 0.5) * transform[5] + transform[3]
        return (x,y)
        
    @staticmethod
    def projToCell(x: float, y: float, transform: Dict[int, float]) -> Tuple[int, int]:
        """Convert (X,Y)-coordinates to column and row numbers."""
        col = int((x - transform[0]) / transform[1])
        row = int((y - transform[3]) / transform[5])
        return (col, row)
    

            
        
