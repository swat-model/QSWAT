import PyQt5

PyQt5.uic.compileUiDir("C:/Users/Public/QSWAT3/QSWAT3/QSWAT", from_imports=True) 
# need non-relative import of resources_rc for next 3
arcFile = open("C:/Users/Public/QSWAT3/QSWAT3/QSWAT/ui_arc_convert.py", 'w')
PyQt5.uic.compileUi("C:/Users/Public/QSWAT3/QSWAT3/QSWAT/ui_arc_convert.ui", arcFile) 
arcFile.close()
convFile = open("C:/Users/Public/QSWAT3/QSWAT3/QSWAT/ui_convert.py", 'w')
PyQt5.uic.compileUi("C:/Users/Public/QSWAT3/QSWAT3/QSWAT/ui_convert.ui", convFile) 
convFile.close()
graphFile = open("C:/Users/Public/QSWAT3/QSWAT3/QSWAT/ui_graph1.py", 'w')
PyQt5.uic.compileUi("C:/Users/Public/QSWAT3/QSWAT3/QSWAT/ui_graph.ui", graphFile) 
graphFile.close()

