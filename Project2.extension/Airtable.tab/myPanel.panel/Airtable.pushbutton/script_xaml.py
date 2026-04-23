import clr 
clr.AddReference("System.Windows.Forms")

from pyrevit import script

xamlfile = script.get_bundle_file("ui.xaml")

import wpf

from System.Windows import Window

class Mywindow(Window):
    def __init__(self):
        wpf.LoadComponent(self, xamlfile)

Mywindow().ShowDialog()
