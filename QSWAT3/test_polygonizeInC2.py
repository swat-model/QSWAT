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


from qgis.core import QgsPointXY
from qgis.gui import * # @UnusedWildImport

from PyQt5.QtCore import * # @UnusedWildImport
from PyQt5.QtGui import * # @UnusedWildImport

import os
import unittest
import random
import numpy as np
#import cythoninit
from QSWAT import polygonizeInC2 as Polygonize



class TestPoly(unittest.TestCase):
    """Test cases for polygonize.""" 
    
    def test1(self):
        """Simplest polygon with a hole."""
        shapes = Polygonize.Polygonize(True, 3, -1, QgsPointXY(0,0), 1, 1)
        shapes.addRow(np.array([1,1,1]), 0)
        shapes.addRow(np.array([1,2,1]), 1)
        shapes.addRow(np.array([1,1,1]), 2)
        shapes.finish()
        self.check(shapes, 3, 'Test1', True)
          
    def test2(self):
        """Nested polygons.  Note this fails geometry validation (nested polygons) if the central square is 1."""
        shapes = Polygonize.Polygonize(True, 5, -1, QgsPointXY(0,0), 1, 1)
        shapes.addRow(np.array([1,1,1,1,1]), 0)
        shapes.addRow(np.array([1,2,2,2,1]), 1)
        shapes.addRow(np.array([1,2,3,2,1]), 2)
        shapes.addRow(np.array([1,2,2,2,1]), 3)
        shapes.addRow(np.array([1,1,1,1,1]), 4)
        shapes.finish()
        self.check(shapes, 5, 'Test2', True)
           
    def test3(self):
        """Multiple holes.  Checks for holes after main polygon."""
        shapes = Polygonize.Polygonize(True, 5, -1, QgsPointXY(0,0), 1, 1)
        shapes.addRow(np.array([1,1,1,1,1]), 0)
        shapes.addRow(np.array([1,2,1,2,1]), 1)
        shapes.addRow(np.array([1,1,1,1,1]), 2)
        shapes.addRow(np.array([1,2,1,2,1]), 3)
        shapes.addRow(np.array([1,1,1,1,1]), 4)
        shapes.finish()
        self.check(shapes, 5, 'Test3', True)
        
    def test4(self):
        """Single complex hole.  In practice makes 3 holes, but still valid."""
        shapes = Polygonize.Polygonize(True, 5, -1, QgsPointXY(0,0), 1, 1)
        shapes.addRow(np.array([1,1,1,1,1]), 0)
        shapes.addRow(np.array([1,2,1,2,1]), 1)
        shapes.addRow(np.array([1,1,2,1,1]), 2)
        shapes.addRow(np.array([1,2,1,2,1]), 3)
        shapes.addRow(np.array([1,1,1,1,1]), 4)
        shapes.finish()
        self.check(shapes, 5, 'Test4', True)

    def test0(self):
        """Example of 1 inside 2 inside 1, which is classed as a geometry error."""
        shapes = Polygonize.Polygonize(True, 10, -1, QgsPointXY(0,0), 1, 1)
        shapes.addRow(np.array([1, 1, 2, 1, 1, 1, 1, 1, 1, 1]), 0)
        shapes.addRow(np.array([1, 1, 1, 2, 1, 1, 2, 2, 1, 2]), 1)
        shapes.addRow(np.array([2, 2, 1, 2, 1, 2, 1, 1, 2, 1]), 2)
        shapes.addRow(np.array([1, 1, 2, 1, 2, 1, 1, 1, 2, 1]), 3)
        shapes.addRow(np.array([2, 1, 1, 1, 1, 2, 1, 1, 1, 2]), 4)
        shapes.addRow(np.array([1, 1, 2, 2, 2, 1, 1, 1, 2, 1]), 5)
        shapes.addRow(np.array([1, 1, 2, 1, 2, 1, 2, 1, 2, 1]), 6)
        shapes.addRow(np.array([1, 1, 2, 2, 2, 1, 1, 1, 1, 1]), 7)
        shapes.addRow(np.array([1, 1, 2, 1, 2, 1, 1, 1, 1, 2]), 8)
        shapes.addRow(np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 1]), 9)
        shapes.finish()
        self.check(shapes, 10, 'Test0', True)
         
    def test5(self):
        """Random 10x10 grid of 1s and 2s.  Probability of 1 set at 70% to encourage holes.
        Run with connectedness4 and then 8"""
        size = 10
        for isConnected4 in [True, False]:
            for _ in range(10000):
                shapes = Polygonize.Polygonize(isConnected4, size, -1, QgsPointXY(0,0), 1, 1)
                rows = []
                for r in range(size):
                    row = []
                    for _ in range(size):
                        val = 1 if random.random() <= 0.7 else 2
                        row.append(val)
                    shapes.addRow(np.array(row), r)
                    rows.append(row)
                shapes.finish()
                arrayString = 'Connected4' if isConnected4 else 'Connected8'
                arrayString += os.linesep
                for r in range(size):
                    arrayString += str(rows[r])
                    arrayString += os.linesep
                self.check(shapes, size, arrayString, isConnected4)
                    
         
    def check(self, shapes, size, arrayString, isConnected4):
        """Print string for shapes; check shapes for closure, no complementary pairs, and for geometric validity."""
        #output = shapes.makeString()
        #print(output)
        # check cell counts: assuming no nodata
        cellCount = 0
        for shape in shapes.shapes.values():
            cellCount += shape.cellCount
        self.assertEqual(size * size, cellCount, 'Cell count is {0} when it should be {1}'.format(cellCount, size * size))
        for hru, shape in shapes.shapes.items():
            for poly in shape.polygons.values():
                ring = poly.rings[0]
                self.assertTrue(Polygonize.isClockwise(ring),
                                'Outer polygon {0} of {1} is not clockwise'.format(Polygonize.ringToString(ring), str(poly)))
                for ring in poly.rings:
                    self.assertTrue(Polygonize.isClosed(ring), 
                                    'Polygon {0} is not closed'.format(Polygonize.ringToString(ring)))
            if isConnected4:
                geometry = shapes.getGeometry(hru)
                self.assertIsNotNone(geometry, 'No geometry for hru {0!s}'.format(hru))
                errors = TestPoly.stripErrors(geometry.validateGeometry())
                for error in errors:
                    if error.hasWhere():
                        self.fail('{0} Geometry error at {1}: {2} for shapes{3}{4}'. \
                                  format(arrayString, error.where().toString(), error.what(), os.linesep, shapes.shapesToString()))
                    else:
                        self.fail('{0} Geometry error: {1} for shapes{2}{3}'. \
                                  format(arrayString, error.what(), os.linesep, shapes.shapesToString()))
      
    @staticmethod       
    def stripErrors(errors):
        """A geometry error is generated if there is double nesting: see test0 above.  
        We ignore these by removing them."""
        outErrors = []
        insideErrorFound = False
        num = len(errors)
        for i in range(num):
            if i == num-1 and insideErrorFound:
                # ignore final message with error count
                return outErrors
            error = errors[i]
            if not error.hasWhere() and ' inside polygon ' in error.what():
                insideErrorFound = True
            else:
                outErrors.append(error)
        return outErrors       
             
if __name__ == '__main__':
    unittest.main()
        
