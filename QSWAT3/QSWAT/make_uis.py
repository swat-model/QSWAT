from qgis.PyQt import uic
import sys

if __name__ == '__main__': 
    sourceDir = sys.argv[1]
    # sourceDir = "K:/Users/Public/QSWAT3/QSWAT3/QSWAT"
    
    uic.compileUiDir(sourceDir, from_imports=True)  # @UndefinedVariable
    # need relative import of resources_rc for next 3
    arcFile = open(sourceDir + "/ui_arc_convert.py", 'w')
    uic.compileUi(sourceDir + "/ui_arc_convert.ui", arcFile)  # @UndefinedVariable 
    arcFile.close()
    convFile = open(sourceDir + "/ui_convert.py", 'w')
    uic.compileUi(sourceDir + "/ui_convert.ui", convFile)  # @UndefinedVariable 
    convFile.close()
    graphFile = open(sourceDir + "/ui_graph1.py", 'w')
    uic.compileUi(sourceDir + "/ui_graph.ui", graphFile)  # @UndefinedVariable 
    graphFile.close()
    
    # Post-process imports: qgis.PyQt/PyQt6 -> qgis.PyQt
    from postprocess_ui import postprocess_directory  # @UnresolvedImport
    postprocess_directory(sourceDir)

