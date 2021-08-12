import PyQt5

PyQt5.uic.compileUiDir("G:/Users/Public/QSWAT3/QSWAT3/QSWAT", from_imports=True)  # @UndefinedVariable
# need relative import of resources_rc for next 3
arcFile = open("G:/Users/Public/QSWAT3/QSWAT3/QSWAT/ui_arc_convert.py", 'w')
PyQt5.uic.compileUi("G:/Users/Public/QSWAT3/QSWAT3/QSWAT/ui_arc_convert.ui", arcFile)  # @UndefinedVariable 
arcFile.close()
convFile = open("G:/Users/Public/QSWAT3/QSWAT3/QSWAT/ui_convert.py", 'w')
PyQt5.uic.compileUi("G:/Users/Public/QSWAT3/QSWAT3/QSWAT/ui_convert.ui", convFile)  # @UndefinedVariable 
convFile.close()
graphFile = open("G:/Users/Public/QSWAT3/QSWAT3/QSWAT/ui_graph1.py", 'w')
PyQt5.uic.compileUi("G:/Users/Public/QSWAT3/QSWAT3/QSWAT/ui_graph.ui", graphFile)  # @UndefinedVariable 
graphFile.close()

