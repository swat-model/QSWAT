"""Post-process generated ui_*.py files for QGIS compatibility.

Replaces direct qgis.PyQt/PyQt6 imports with qgis.PyQt imports so the
generated files work under both QGIS 3.x (qgis.PyQt) and QGIS 4.x (PyQt6).

Usage:
    python postprocess_ui.py [directory]

If no directory is given, processes the script's own directory.

Author  : Celray James CHAWANDA
Email   : celray.chawanda@outlook.com
Licence : GNU General Public License
Repo    : https://github.com/celray

Date    : 2026-04-07 - 15:51
"""

import os
import re
import sys


def postprocess_file(filepath):
    """Fix PyQt imports in a single generated ui file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    # Replace direct qgis.PyQt or PyQt6 imports with qgis.PyQt
    content = re.sub(r'from PyQt[56]', 'from qgis.PyQt', content)
    # Make resource imports relative so they work inside a sub-package
    content = re.sub(r'^import resources_rc$', 'from . import resources_rc', content, flags=re.MULTILINE)
    # correct Qt5 ui compiler issues
    # some of these are incomplete - limited to those actually used
    content = re.sub(r'QIcon.Normal', 'QIcon.Mode.Normal', content)
    content = re.sub(r'QIcon.Off', 'QIcon.State.Off', content)
    content = re.sub(r'QSizePolicy.(Preferred|Fixed|Minimum|Maximum|Expanding|MinimumExpanding|Ignored)', r'QSizePolicy.Policy.\1', content)
    content = re.sub(r'Qt.(Horizontal|Vertical)', r'Qt.Orientation.\1', content)
    content = re.sub(r'QDialogButtonBox.(Ok|Open|Save|Cancel|Close)', r'QDialogButtonBox.StandardButton.\1', content)
    content = re.sub(r'Qt.Align(Left|Right|Center|VCenter|Leading|Trailing|Top|Bottom)', r'Qt.AlignmentFlag.Align\1', content)
    content = re.sub(r'QSlider.Ticks(Above|Below)', r'QSlider.TickPosition.Ticks\1', content)
    content = re.sub(r'QFrame.StyledPanel', 'QFrame.Shape.StyledPanel', content)
    content = re.sub(r'QFrame.Raised', 'QFrame.Shadow.Raised', content)
    content = re.sub(r'Qt.Imh', 'Qt.InputMethodHint.Imh', content)
    content = re.sub(r'Qt.LeftToRight', 'Qt.LayoutDirection.LeftToRight', content)
    content = re.sub(r'Qt.AutoText', 'Qt.TextFormat.AutoText', content)
    content = re.sub(r'Qt.WheelFocus', 'Qt.FocusPolicy.WheelFocus', content)
    content = re.sub(r'QComboBox.InsertAlphabetically', 'QComboBox.InsertPolicy.InsertAlphabetically', content)
    content = re.sub(r'QComboBox.AdjustToContents', 'QComboBox.SizeAdjustPolicy.AdjustToContents', content)
    content = re.sub(r'QAbstractItemView.SingleSelection', 'QAbstractItemView.SelectionMode.SingleSelection', content)
    content = re.sub(r'QAbstractItemView.NoEditTriggers', 'QAbstractItemView.EditTrigger.NoEditTriggers', content)
    content = re.sub(r'QAbstractItemView.SelectRows', 'QAbstractItemView.SelectionBehavior.SelectRows', content)
    content = re.sub(r'Qt.ScrollBarAlwaysOff', 'Qt.ScrollBarPolicy.ScrollBarAlwaysOff', content)
    content = re.sub(r'QAbstractScrollArea.AdjustToContents', 'QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents', content)

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        #print(f'  Fixed imports in {os.path.basename(filepath)}')


def postprocess_directory(directory):
    """Post-process all ui_*.py files in the given directory."""
    count = 0
    for filename in sorted(os.listdir(directory)):
        if filename.startswith('ui_') and filename.endswith('.py'):
            postprocess_file(os.path.join(directory, filename))
            count += 1
    print(f'Post-processed {count} ui files in {directory}')


if __name__ == '__main__':
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = os.path.dirname(os.path.abspath(__file__))
    postprocess_directory(target)
