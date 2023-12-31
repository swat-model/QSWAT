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


from typing import Dict, Tuple, Any, List

from .QSWATUtils import QSWATUtils  # type: ignore
from .parameters import Parameters  # type: ignore

class CellData:
    """Data collected about cells in watershed grid that make an HRU."""
    def __init__(self, count: int, area: float, slope: float, crop: int) -> None:
        """Constructor."""
        ## Cell count
        self.cellCount = count
        ## Total area in square metres
        self.area = area
        ## Total slope (for calculating mean slope)
        self.totalSlope = slope
        ## Original crop number (for use with split landuses)
        self.crop = crop
        
    def addCell(self, area: float, slope: float) -> None:
        """Add data for 1 cell."""
        self.cellCount += 1
        self.area += area
        self.totalSlope += slope
        
    def addCells(self, cd: Any) -> None:
        """Add a cell data to this one."""
        self.cellCount += cd.cellCount
        self.area += cd.area
        self.totalSlope += cd.totalSlope
        
    def multiply(self, factor: float) -> None:
        """Multiply cell values by factor."""
        self.cellCount = round(self.cellCount * factor) 
        self.area *= factor
        self.totalSlope *= factor 
        
class BasinData:
    """Data held about subbasin."""
    def __init__(self, outletCol: int, outletRow: int, outletElevation: float, 
                 startCol: int, startRow:int, length: float, drop: float, minDist: float, 
                 isBatch: bool) -> None:
        """Initialise class variables."""
        ## Number of cells in subbasin
        self.cellCount = 0
        ## area of basin polygon
        self.polyArea = 0.0
        ## Area of subbasin in square metres.  Equals cropSoilSlopeArea plus reservoirArea plus pondArea plus lakeArea plus nodata area
        self.area = 0.0
        ## Area draining through outlet of subbasin in square metres
        self.drainArea = 0.0
        ## pond area in square metres
        self.pondArea = 0.0
        ## reservoir area in square metres
        self.reservoirArea = 0.0
        ## objectids of reservoirs in basin (list of integer ids in a string)
        self.reservoirObjectids = ''
        ## playa area in square metres according to NHD data (only used with HUC)
        self.playaArea = 0.0
        ## lake area in square metres  before any adjustment for total area according to NHD data (only used with HUC)
        self.lakeArea = 0.0
        ## wetland area in square metres according to NHD data (only used with HUC)
        self.wetlandArea = 0.0
        ## area of buffered stream in square metres
        self.streamArea = 0.0
        ## area of WATR pixels in buffered stream in square metres
        self.WATRInStreamArea = 0.0
        ## Total of elevation values in the subbasin (to compute mean)
        self.totalElevation = 0.0
        ## Total of slope values for the subbasin (to compute mean)
        self.totalSlope = 0.0
        ## Column in DEM of outlet point of the subbasin
        self.outletCol = outletCol
        ## Row in DEM of outlet point of the subbasin
        self.outletRow = outletRow
        ## Elevation in metres of outlet point of the subbasin
        self.outletElevation = outletElevation
        ## Elevation in metres of highest point of the subbasin
        self.maxElevation = 0.0
        ## Column in DEM of start point of the main channel of the subbasin
        self.startCol = startCol
        ## Row in DEM of start point of the main channel of the subbasin
        self.startRow = startRow
        ## Channel distance in metres from main channel start to outlet
        self.startToOutletDistance = length
        ## Drop in metres from main channel start to outlet
        self.startToOutletDrop = drop
        ## No longer used 
        self.farCol = 0
        ## No longer used
        self.farRow = 0
        ## No longer used
        self.farthest = 0
        ## Elevation in metres of farthest (longest channel length) point from the outlet
        # defaults to source elevation
        self.farElevation = outletElevation + drop
        ## Longest channel length in metres.  
        #
        # Make it initially min of x and y resolutions of DEM so cannot be zero.
        self.farDistance = minDist
        ## Area with not-Nodata crop, soil, and slope values (equals sum of hruMap areas).
        # reduced by water bodies
        self.cropSoilSlopeArea = 0.0
        ## same as cropSoilSlope area, but not reduced by water bodies
        self.definedArea = 0.0
        ## Map hru (relative) number -> CellData.
        self.hruMap: Dict[int, CellData] = dict()
        ## Nested map crop -> soil -> slope -> hru number.
        # Range of cropSoilSlopeNumbers must be same as domain of hruMap
        self.cropSoilSlopeNumbers: Dict[int, Dict[int, Dict[int, int]]] = dict()
        ## Latest created relative HRU number for this subbasin.
        self.relHru = 0
        ## Map of crop to area of crop in subbasin.
        #
        # This and the similar maps for soil and slope are duplicated:
        # an original version created after basin data is calculated and 
        # before HRUs are created, and another after HRUs are created.
        self.cropAreas: Dict[int, float] = dict()
        ## Original crop area map
        self.originalCropAreas: Dict[int, float] = dict()
        ## Map of soil to area of soil in subbasin.
        self.soilAreas: Dict[int, float] = dict()
        ## Original soil area map
        self.originalSoilAreas: Dict[int, float] = dict()
        ## Map of slope to area of slope in subbasin.
        self.slopeAreas: Dict[int, float] = dict()
        ## Original slope area map
        self.originalSlopeAreas: Dict[int, float] = dict()
        ## Flag to show if batch run
        self.isBatch = isBatch
        
    def addCell(self, crop: int, soil: int, slope: int, area: float, 
                elevation: float, slopeValue: float, dist: float, _gv: Any):
        """Add data for 1 cell in watershed raster."""
        hru = 0
        self.cellCount += 1
        self.area += area
        self.polyArea += area
        # drain area calculated separately
        if slopeValue != _gv.slopeNoData:
            self.totalSlope += slopeValue
        if elevation != _gv.elevationNoData:
            self.totalElevation += elevation
            if dist != _gv.distNoData and dist > self.farDistance:
                # We have found a new  (by flow distance) point from the outlet, store distance and its elevation
                self.farDistance = dist
                self.farElevation = elevation
            if elevation > self.maxElevation:
                self.maxElevation = elevation
        if ((crop != _gv.cropNoData) and (soil != _gv.soilNoData) and (slopeValue != _gv.slopeNoData)):
            self.cropSoilSlopeArea += area
            hru = BasinData.getHruNumber(self.cropSoilSlopeNumbers, self.relHru, crop, soil, slope)
            if hru in self.hruMap:
                cellData = self.hruMap[hru]
                cellData.addCell(area, slopeValue)
                self.hruMap[hru] = cellData
            else:
                # new hru
                cellData = CellData(1, area, slopeValue, crop)
                self.hruMap[hru] = cellData
                self.relHru = hru
    
    @staticmethod
    def getHruNumber(cropSoilSlopeNumbers: Dict[int, Dict[int, Dict[int, int]]], 
                     hru: int, crop: int, soil: int, slope: int) -> int:
        """Return HRU number (new if necessary, adding one to input hru number) 
        for the crop/soil/slope combination.
        """
        resultHru = hru
        if crop in cropSoilSlopeNumbers:
            soilSlopeNumbers = cropSoilSlopeNumbers[crop]
            if soil in soilSlopeNumbers:
                slopeNumbers = soilSlopeNumbers[soil]
                if slope in slopeNumbers:
                    return slopeNumbers[slope]
                else:
                    # new slope for existing crop and soil
                    resultHru += 1
                    slopeNumbers[slope] = resultHru
            else:
                # new soil for existing crop
                resultHru += 1
                slopeNumbers = dict()
                slopeNumbers[slope] = resultHru
                soilSlopeNumbers[soil] = slopeNumbers
                cropSoilSlopeNumbers[crop] = soilSlopeNumbers
        else:
            # new crop
            resultHru += 1
            slopeNumbers = dict()
            slopeNumbers[slope] = resultHru
            soilSlopeNumbers = dict()
            soilSlopeNumbers[soil] = slopeNumbers
            cropSoilSlopeNumbers[crop] = soilSlopeNumbers
        return resultHru
    
    def setAreas(self, isOriginal: bool, redistributeNodata=True) -> None:
        """Set area maps for crop, soil and slope.
        Add nodata area to HRUs if redistributeNodata, else reduce basin cellCount, area and totalSlope to total of defined HRUs."""
        if isOriginal:
            if redistributeNodata:
                # nodata area is included in final areas: need to add to original
                # so final and original tally
                self.redistributeNodata()
            else:
                # if we are not redistributing nodata, need to correct the basin area, cell count and totalSlope, which may be reduced 
                # as we are removing nodata area from the model
                self.area = self.cropSoilSlopeArea + self.pondArea + self.reservoirArea + self.lakeArea
                self.cellCount = self.totalHRUCellCount()
                self.totalSlope = self.totalHRUSlopes()
        self.setCropAreas(isOriginal)
        self.setSoilAreas(isOriginal)
        self.setSlopeAreas(isOriginal)
        
    def redistributeNodata(self) -> None:
        """Redistribute nodata area in each HRU."""
        nonWaterbodyArea = self.area - (self.pondArea + self.reservoirArea + self.lakeArea)
        areaToRedistribute = nonWaterbodyArea - self.cropSoilSlopeArea
        if nonWaterbodyArea > areaToRedistribute > 0:
            redistributeFactor = nonWaterbodyArea / (nonWaterbodyArea - areaToRedistribute)
            self.redistribute(redistributeFactor)
        # adjust cropSoilSlopeArea so remains equal to sum of HRU areas
        # also allows this function to be called again with no effect
        self.cropSoilSlopeArea = nonWaterbodyArea
            
    def totalHRUCellCount(self) -> int:
        """Total cell count of HRUs in this subbasin."""
        totalCellCount = 0
        for hruData in self.hruMap.values():
            totalCellCount += hruData.cellCount
        return totalCellCount
            
    def totalHRUAreas(self) -> float:
        """Total area in square metres of HRUs in this subbasin."""
        totalArea = 0.0
        for hruData in self.hruMap.values():
            totalArea += hruData.area
        return totalArea
            
    def totalHRUSlopes(self) -> float:
        """Total slope values of HRUs in this subbasin."""
        totalSlope = 0.0
        for hruData in self.hruMap.values():
            totalSlope += hruData.totalSlope
        return totalSlope
                  
    def setCropAreas(self, isOriginal: bool) -> None:
        '''Make map crop -> area from hruMap and cropSoilSlopeNumbers.'''
        cmap = self.originalCropAreas if isOriginal else self.cropAreas
        cmap.clear()
        for crop, soilSlopeNumbers in self.cropSoilSlopeNumbers.items():
            area = 0.0
            for slopeNumbers in soilSlopeNumbers.values():
                for hru in slopeNumbers.values():
                    try:
                        cellData = self.hruMap[hru]
                    except Exception:
                        QSWATUtils.error('Hru {0} not in hruMap'.format(hru), self.isBatch)
                        continue
                    area += cellData.area
            cmap[crop] = area
        
    def setSoilAreas(self, isOriginal: bool) -> None:
        '''Make map soil -> area from hruMap and cropSoilSlopeNumbers.'''
        smap = self.originalSoilAreas if isOriginal else self.soilAreas
        smap.clear()
        for soilSlopeNumbers in self.cropSoilSlopeNumbers.values():
            for soil, slopeNumbers in soilSlopeNumbers.items():
                for hru in slopeNumbers.values():
                    try:
                        cellData = self.hruMap[hru]
                    except Exception:
                        QSWATUtils.error('Hru {0} not in hruMap'.format(hru), self.isBatch)
                        continue
                    if  soil in smap:
                        area = smap[soil]
                        smap[soil] = area + cellData.area
                    else:
                        smap[soil] = cellData.area
    
    def setSlopeAreas(self, isOriginal: bool) -> None:
        '''Make map slope -> area from hruMap and cropSoilSlopeNumbers.'''
        smap = self.originalSlopeAreas if isOriginal else self.slopeAreas
        smap.clear()
        for soilSlopeNumbers in self.cropSoilSlopeNumbers.values():
            for slopeNumbers in soilSlopeNumbers.values():
                for slope, hru in slopeNumbers.items():
                    try:
                        cellData = self.hruMap[hru]
                    except Exception:
                        QSWATUtils.error('Hru {0} not in hruMap'.format(hru), self.isBatch)
                        continue
                    if slope in smap:
                        area = smap[slope]
                        smap[slope] = area + cellData.area
                    else:
                        smap[slope] = cellData.area
                        
    def cropSoilAreas(self, crop: int) -> Dict[int, float]:
        '''Map of soil -> area in square metres for this crop.'''
        csmap = dict()
        soilSlopeNumbers = self.cropSoilSlopeNumbers.get(crop, dict())
        for soil in soilSlopeNumbers:
            csmap[soil] = self.cropSoilArea(crop, soil)
        return csmap
    
    def cropArea(self, crop: int) -> float:
        '''Area in square metres for crop.'''
        # use when cropAreas may not be set
        area = 0.0
        soilSlopeNumbers = self.cropSoilSlopeNumbers.get(crop, dict())
        for slopeNumbers in soilSlopeNumbers.values():
            for hru in slopeNumbers.values():
                try:
                    cellData = self.hruMap[hru]
                except Exception:
                    QSWATUtils.error(u'Hru {0} not in hruMap'.format(hru), self.isBatch)
                    continue
                area += cellData.area
        return area
    
    def cropSoilArea(self, crop: int, soil: int) -> float:
        '''Area in square metres for crop-soil combination.'''
        area = 0.0
        soilSlopeNumbers = self.cropSoilSlopeNumbers.get(crop, dict())
        slopeNumbers = soilSlopeNumbers.get(soil, dict())
        for hru in slopeNumbers.values():
            try:
                cellData = self.hruMap[hru]
            except Exception:
                QSWATUtils.error(u'Hru {0} not in hruMap'.format(hru), self.isBatch)
                continue
            area += cellData.area
        return area
    
    def cropSoilSlopeAreas(self, crop: int, soil: int) -> Dict[int, float]:
        '''Map of slope -> area in square metres for this crop and soil.'''
        cssmap = dict()
        soilSlopeNumbers = self.cropSoilSlopeNumbers.get(crop, dict())
        slopeNumbers = soilSlopeNumbers.get(soil, dict())
        for (slope, hru) in slopeNumbers.items():
            try:
                cellData = self.hruMap[hru]
            except Exception:
                QSWATUtils.error(u'Hru {0} not in hruMap'.format(hru), self.isBatch)
                continue
            cssmap[slope] = cellData.area
        return cssmap
    
    @staticmethod
    def dominantKey(table: Dict[int, float]) -> int:
        '''Find the dominant key for a dictionary table of numeric values, 
        i.e. the key to the largest value.
        '''
        maxKey = -1
        maxVal = 0.0
        for (key, val) in table.items():
            if val > maxVal:
                maxKey = key
                maxVal = val
        return maxKey
    
    def getDominantHRU(self) -> Tuple[int, int, int]:
        '''Find the HRU with the largest area, 
        and return its crop, soil and slope.
        '''
        maxArea = 0.0
        maxCrop = 0
        maxSoil = 0
        maxSlope = 0
        for (crop, soilSlopeNumbers) in self.cropSoilSlopeNumbers.items():
            for (soil, slopeNumbers) in soilSlopeNumbers.items():
                for (slope, hru) in slopeNumbers.items():
                    cellData = self.hruMap[hru]
                    area = cellData.area
                    if area > maxArea:
                        maxArea = area
                        maxCrop = crop
                        maxSoil = soil
                        maxSlope = slope
        return (maxCrop, maxSoil, maxSlope)
            
    def redistribute(self, factor: float) -> None:
        '''Multiply all the HRU areas by factor.'''
        for (hru, cellData) in self.hruMap.items():
            cellData.multiply(factor)
            self.hruMap[hru] = cellData
            
    def removeHRU(self, hru: int, crop: int, soil: int, slope: int) -> None:
        '''Remove an HRU from the hruMap and the cropSoilSlopeNumbers map.'''
        assert crop in self.cropSoilSlopeNumbers and \
            soil in self.cropSoilSlopeNumbers[crop] and \
            slope in self.cropSoilSlopeNumbers[crop][soil] and \
            hru == self.cropSoilSlopeNumbers[crop][soil][slope]
        del self.hruMap[hru]
        del self.cropSoilSlopeNumbers[crop][soil][slope]
        if len(self.cropSoilSlopeNumbers[crop][soil]) == 0:
            del self.cropSoilSlopeNumbers[crop][soil]
            if len(self.cropSoilSlopeNumbers[crop]) == 0:
                del self.cropSoilSlopeNumbers[crop]
                
    def removeWaterBodiesArea(self, WATRInStream: float, basin: int, conn: Any, gv: Any) -> float:
        """Reduce areas to allow for reservoir, pond, lake and playa areas.  Set WATR HRU to WATRInStream.
        Return reduction in WATR area in square metres"""
        
        def setMinimalReach():
            """Replace record in Reach table with minimal 100m stream."""
            SWATBasin = gv.topo.basinToSWATBasin[basin]
            sql1 = 'SELECT MinEl FROM Reach WHERE Subbasin=?'
            sql2 = 'UPDATE Reach SET Len2=100, MaxEl=?, Shape_Length=100 WHERE Subbasin=?'
            row = conn.execute(sql1, (SWATBasin,)).fetchone()
            minEl = row[0]
            maxEl = minEl +  Parameters._WATERMAXSLOPE * 100
            conn.execute(sql2, (maxEl, SWATBasin))
                
        
        def getWaterHRUArea(waterLanduse: int) -> float:
            """Area determined as water from reading landuse and soil rasters."""
            soilSlopeNumbers = self.cropSoilSlopeNumbers.get(waterLanduse, dict())
            slopeNumbers = soilSlopeNumbers.get(Parameters._SSURGOWater, dict())
            hru = slopeNumbers.get(0, -1)
            if hru >= 0:  # have existing WATR HRU
                return self.hruMap[hru].area
            else:
                return 0
        
        def setWaterHRUArea(waterLanduse: int, area: float) -> None:
            """Set the area of WATR HRU to area."""
            soilSlopeNumbers = self.cropSoilSlopeNumbers.get(waterLanduse, dict())
            slopeNumbers = soilSlopeNumbers.get(Parameters._SSURGOWater, dict())
            hru = slopeNumbers.get(0, -1)
            if hru >= 0:  # have existing WATR HRU
                hruData = self.hruMap[hru]
                hruData.area = area
                hruData.cellCount = round(area / gv.cellArea)
            else:  # create a water HRU
                cellCount = round(area / gv.cellArea)
                hruData = CellData(cellCount, area, Parameters._WATERMAXSLOPE * cellCount, waterLanduse)
                self.relHru += 1
                self.hruMap[self.relHru] = hruData
                slopeNumbers[0] = self.relHru
                soilSlopeNumbers[Parameters._SSURGOWater] = slopeNumbers
                self.cropSoilSlopeNumbers[waterLanduse] = soilSlopeNumbers
            
        def removeWater(waterLanduse: int) -> None:
            """Remove all waterLanduse HRUs."""
            removedArea = 0.0
            soilSlopeNumbers = self.cropSoilSlopeNumbers.get(waterLanduse, None)
            if soilSlopeNumbers is not None:
                for slopeNumbers in soilSlopeNumbers.values():
                    for hru in slopeNumbers.values():
                        removedArea += self.hruMap[hru].area
                        del self.hruMap[hru]
                del self.cropSoilSlopeNumbers[waterLanduse]
        
        def allWATR(waterLanduse: int) -> bool:
            for crop in self.cropSoilSlopeNumbers:
                if crop != waterLanduse:
                    return False
            return True
            
        # first store defined area as cropSoilSlopeArea
        self.definedArea = self.cropSoilSlopeArea
        areaToRemove = self.reservoirArea + self.pondArea + self.lakeArea + self.playaArea
        availableForHRUs = self.cropSoilSlopeArea - areaToRemove
        waterLanduse = gv.db.getLanduseCat('WATR')
        if availableForHRUs <= 0:
            ## remove all HRUs
            self.hruMap = dict()
            self.relHru = 0
            self.cropSoilSlopeNumbers = dict()
            self.cropSoilSlopeArea = 0
            if areaToRemove > self.area:
                factor = self.area / areaToRemove
                self.reservoirArea *= factor
                self.pondArea *= factor
                self.lakeArea *= factor
                self.playaArea *= factor
            # add a dummy 1 ha WATR HRU to avoid no HRUs in a subbasin
            area = min(1E4, self.area)
            setWaterHRUArea(waterLanduse, area)
            # create a dummy 100m stream to replace existing one in Reach table
            setMinimalReach()
            return 0
        if allWATR(waterLanduse):
            # just use all the non-reservoir, pond, lake and playa area as water: cannot redistribute anything as no crop HRUs to change
            setWaterHRUArea(waterLanduse, availableForHRUs)
            return 0
        oldWaterArea = getWaterHRUArea(waterLanduse)
        waterOutsideWaterbody = oldWaterArea - areaToRemove
        # only need to have streams and playas as water HRU
        # note difference between what we have as water and the minimum we need
        # large difference suggests we missed a pond, lake or reservoir
        waterReduction = waterOutsideWaterbody - WATRInStream
        useForWater = min(waterOutsideWaterbody, WATRInStream)
        if useForWater > 0:
            QSWATUtils.loginfo('Water area changed from {0} to {1}: {2:.1F}%'.format(waterOutsideWaterbody, useForWater, useForWater * 100 / waterOutsideWaterbody))
            self.playaArea = min(useForWater, self.playaArea)
            setWaterHRUArea(waterLanduse, useForWater)
        else:
            removeWater(waterLanduse)
            useForWater = 0
        availableForCropHRUs = availableForHRUs - useForWater
        if availableForCropHRUs == 0:
            # remove non WATR HRUs
            cropsToDelete: List[int] = []
            for crop, soilSlopeNumbers in self.cropSoilSlopeNumbers.items():
                if crop != waterLanduse:
                    cropsToDelete.append(crop)
                    for slopeNumbers in soilSlopeNumbers.values():
                        for hru in slopeNumbers.values():
                            del self.hruMap[hru]
            for crop in cropsToDelete:
                del self.cropSoilSlopeNumbers[crop]
        else:
            oldCropArea = self.cropSoilSlopeArea - oldWaterArea
            factor = availableForCropHRUs / oldCropArea
            # multiply non-water HRUs by factor
            for crop, soilSlopeNumbers in self.cropSoilSlopeNumbers.items():
                if crop != waterLanduse:
                    for slopeNumbers in soilSlopeNumbers.values():
                        for hru in slopeNumbers.values():
                            self.hruMap[hru].multiply(factor)
        self.cropSoilSlopeArea = availableForHRUs
        return waterReduction
                
class HRUData:
    
    """Data about an HRU."""
    def __init__(self, basin: int, crop: int, origCrop: int, soil: int, 
                 slope: int, cellCount: int, area: float, totalSlope: float, 
                 cellArea: float, relHru: int) -> None:
        """Constructor."""
        ## Basin number
        self.basin = basin
        ## Landuse number
        self.crop = crop
        ## Original landuse number (for split landuses)
        self.origCrop = origCrop
        ## Soil number
        self.soil = soil
        ## Slope index
        self.slope = slope
        ## Number of DEM cells
        self.cellCount = cellCount
        ## Area in square metres
        self.area = area
        ## Originally used cellCount for mean slope, 
        # but cellCounts (which are integer) are inaccurate when small,
        # and may even round to zero because of split and exempt landuses.
        self.meanSlope = 0 if area == 0 else totalSlope * cellArea / area
        ## HRU number within the subbasin
        self.relHru = relHru
        
