"""
Quantiphyse - Vessel Encoded ASL widgets

Copyright (c) 2016-2018 University of Oxford
"""

from __future__ import division, unicode_literals, absolute_import, print_function

import numpy as np
from PySide import QtCore, QtGui
import pyqtgraph as pg

from quantiphyse.gui.widgets import NumberGrid
from quantiphyse.gui.options import OptionBox, NumericOption

# TODO allow drag/drop XY only file

veslocs_default = np.array([
    [1.0000000e+01, -1.0000000e+01, 1.0000000e+01, -1.0000000e+01,],
    [1.0000000e+01, 1.0000000e+01, -1.0000000e+01, -1.0000000e+01,],
    [0.3, 0.3, 0.3, 0.3,],
], dtype=np.float)   

class EncodingWidget(QtGui.QWidget):
    """
    Widget which displays the encoding setup in MAC and TWO forms and keeps the two in sync
    """

    def __init__(self, *args, **kwargs):
        QtGui.QWidget.__init__(self, *args, **kwargs)
        self.veslocs = None
        self.imlist = None
        self.nvols = 0
        self.updating = False

        vbox = QtGui.QVBoxLayout()
        self.setLayout(vbox)

        hbox = QtGui.QHBoxLayout()
        self.auto_combo = QtGui.QComboBox()
        self.auto_combo.addItem("Automatic (vessels are RC, LC, RV, LV brain arteries)")
        self.auto_combo.addItem("Custom")
        self.auto_combo.currentIndexChanged.connect(self._auto_changed)
        hbox.addWidget(self.auto_combo)

        self.mode_combo = QtGui.QComboBox()
        self.mode_combo.addItem("TWO specification")
        self.mode_combo.addItem("MAC specification")
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        hbox.addWidget(self.mode_combo)
        vbox.addLayout(hbox)

        self.warning = QtGui.QLabel()
        self.warning.setVisible(False)
        vbox.addWidget(self.warning)

        self.two_mtx = NumberGrid([[0, 0, 0, 0]], col_headers=["\u03b8 (\u00b0)", "Image type", "vA", "vB"], expandable=(False, True), fix_height=True)
        self.two_mtx.sig_changed.connect(self._two_changed)
        vbox.addWidget(self.two_mtx)

        self.mac_mtx = NumberGrid([[0], [0], [0], [0]], row_headers=["CX", "CY", "\u03b8 (\u00b0)", "D"], expandable=(True, False), fix_height=True)
        self.mac_mtx.sig_changed.connect(self._mac_changed)
        vbox.addWidget(self.mac_mtx)

        self._mode_changed(0)

    def _auto_changed(self):
        self._autogen()
        
    def _mode_changed(self, idx):
        self.two_mtx.setVisible(idx == 0)
        self.mac_mtx.setVisible(idx == 1)

    def set_nenc(self, nvols):
        """
        Set the total number of tag/control and encoded volumes
        """
        self.nvols = nvols
        self._autogen()

    def set_veslocs(self, veslocs):
        """
        Set the initial vessel locations.
        
        If enabled, this automatically generates an encoding matrix from initial vessel locations
        with either 6 or 8 encoding images
        """
        print("setting veslocs: ", veslocs)
        self.veslocs = np.array(veslocs)
        self._autogen()

    def _warn(self, warning):
        if warning:
            self.warning.setText(warning)
            self.warning.setVisible(True)
        else:
            self.warning.setVisible(False)

    def _autogen(self):
        if self.veslocs is not None and self.auto_combo.currentIndex() == 0:
            try:
                print("autogenerating encoding matrix")
                nvols = self.nvols
                if nvols == 0:
                    # Default if data is not loaded
                    nvols = 8
                print(self.veslocs, nvols)

                from oxasl_ve import veslocs_to_enc
                print("imported")
                two = veslocs_to_enc(self.veslocs[:2, :], nvols)
                print("ran")
                print(two)
                self.two_mtx.setValues(two)
                self._warn("")
            except ValueError as exc:
                self._warn(str(exc))
            except Exception as exc:
                print(exc)
            except:
                print("unexpected")
                import traceback
                traceback.print_exc()
        
    def _two_changed(self):
        """
        Update MAC matrix to match TWO matrix
        """
        if not self.updating: 
            try:
                print("two changed")
                from oxasl_ve import two_to_mac
                self.updating = True
                two = np.array(self.two_mtx.values())
                print(two)
                mac, self.imlist = two_to_mac(two)
                print(mac, self.imlist)
                self.mac_mtx.setValues(mac)
            finally:
                self.updating = False

    def _mac_changed(self):
        """ 
        Convert MAC format encoding into TWO format

        This is an inverse of _two_changed done with remarkably little understanding.
        It seems to assume that 'reverse cycles' occur in odd numbered images which 
        seems unreasonable, but I can't see an obvious way to detect this otherwise
        """
        if not self.updating: 
            try:
                print("mac changed")
                from oxasl_ve import mac_to_two
                self.updating = True
                mac = np.array(self.mac_mtx.values())
                print(mac)
                two, self.imlist = mac_to_two(mac)
                print(two, self.imlist)
                self.two_mtx.setValues(two)
            finally:
                self.updating = False

class PriorsWidget(QtGui.QWidget):
    """
    Widget providing priors options
    """

    def __init__(self, *args, **kwargs):
        QtGui.QWidget.__init__(self, *args, **kwargs)
        vbox = QtGui.QVBoxLayout()
        self.setLayout(vbox)

        self.optbox = OptionBox()
        self.optbox.add("Prior standard deviation on co-ordinates", NumericOption(minval=0, maxval=2, default=1), key="xy-std")
        self.optbox.add("(distance units defined by encoding setup)")
        self.optbox.add("Prior mean for flow velocity", NumericOption(minval=0, maxval=1, default=0.3), key="v-mean")
        self.optbox.add("Prior standard deviation for flow velocity", NumericOption(minval=0, maxval=0.1, decimals=3, default=0.01), key="v-std")
        self.optbox.add("Prior mean for rotation angle (\u00b0)", NumericOption(minval=0, maxval=5, default=1.2), key="rot-std")
        vbox.addWidget(self.optbox)

    def set_infer_v(self, infer_v):
        """ Set whether flow velocity should be inferred - enables modification of prior"""
        self.optbox.option("v-mean").setEnabled(infer_v)
        self.optbox.option("v-std").setEnabled(infer_v)
    
    def set_infer_transform(self, infer_trans):
        """ Set whether vessel locations are inferred by transformation - enables modification of prior for rotation angle"""
        self.optbox.option("rot-std").setEnabled(infer_trans)

    def options(self):
        """ :return: options as dictionary """
        return self.optbox.values()

class VeslocsWidget(QtGui.QWidget):
    """
    Widget for setting initial vessel locations and viewing inferred locations
    """

    sig_initial_changed = QtCore.Signal(object)

    def __init__(self, *args, **kwargs):
        QtGui.QWidget.__init__(self, *args, **kwargs)

        grid = QtGui.QGridLayout()
        self.setLayout(grid)

        grid.addWidget(QtGui.QLabel("Initial"), 0, 0)
        self.vessels_initial = NumberGrid([[], [], []], row_headers=["X", "Y", "v"], expandable=(True, False), fix_height=True)
        self.vessels_initial.sig_changed.connect(self._initial_vessels_changed)
        grid.addWidget(self.vessels_initial, 1, 0)

        grid.addWidget(QtGui.QLabel("Inferred"), 2, 0)
        self.vessels_inferred = NumberGrid([[], [], []], row_headers=["X", "Y", "v"], expandable=(True, False), fix_height=True)
        self.vessels_inferred.sig_changed.connect(self._inferred_vessels_changed)
        grid.addWidget(self.vessels_inferred, 3, 0) 

        # Vessel locations plot
        plot_win = pg.GraphicsLayoutWidget()
        plot_win.setBackground(background=None)
        #sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        #sizePolicy.setHeightForWidth(True)
        #plot_win.setSizePolicy(sizePolicy)
        plot_win.setFixedSize(200, 200)

        self.vessel_plot = plot_win.addPlot(lockAspect=True)
        self.vessel_plot.showAxis('right')
        self.vessel_plot.showAxis('top')
        grid.addWidget(plot_win, 0, 1, 5, 1)
   
    def _initial_vessels_changed(self):
        vessel_data = self.vessels_initial.values()
        if len(vessel_data) == 2:
            vessel_data.append([0.3,] * len(vessel_data[0]))
            self.vessels_initial.setValues(vessel_data, validate=False, row_headers=["X", "Y", "v"])
        self.vessels_inferred.setValues(vessel_data, validate=False, row_headers=["X", "Y", "v"])
        self._update_vessel_plot()
        self.sig_initial_changed.emit(vessel_data)

    def _inferred_vessels_changed(self):
        self._update_vessel_plot()

    def _update_vessel_plot(self):
        """ Plot vessel locations on graph """
        veslocs = self.vessels_initial.values()
        veslocs_inferred = self.vessels_inferred.values()
        self.vessel_plot.clear()
        self.vessel_plot.plot(veslocs[0], veslocs[1], 
                              pen=None, symbolBrush=(50, 50, 255), symbolPen='k', symbolSize=10.0)
        self.vessel_plot.plot(veslocs_inferred[0], veslocs_inferred[1], 
                              pen=None, symbolBrush=(255, 50, 50), symbolPen='k', symbolSize=10.0)
        self.vessel_plot.autoRange()

class ClasslistWidget(NumberGrid):
    """
    Widget which displays the class list and inferred proportions
    """

    def __init__(self):
        NumberGrid.__init__(self, [[], [], [], [], []], expandable=(False, False), fix_height=True)
    
    def update(self, num_sources, nfpc):
        """
        Update the class list for a given number of sources and number of sources per class
        """
        classes = self._make_classlist(num_sources, nfpc)
        if not classes:
            return
        if len(self.values()) == len(classes):
            pis = [row[-1] for row in self.values()]
        else:
            # Number of sources has changed so current PIs are invalid
            pis = [1/float(len(classes)),] * len(classes)
        classes = [c + [pi,] for c, pi in zip(classes, pis)]
        row_headers = ["Class %i" % (i+1) for i in range(len(classes))]
        col_headers = ["Vessel %i" % (i+1) for i in range(num_sources)] + ["Proportion",]
        self.setValues(classes, validate=False, col_headers=col_headers, row_headers=row_headers)

    def set_pis(self, pis):
        """
        Set the inferred proportions of each class
        """
        current_values = self.values()
        if len(current_values) != len(pis):
            raise ValueError("Number of PIs must match number of classes")
        num_sources = len(current_values[0]) - 1
        new_values = [[c[0], c[1], pi] for c, pi in zip(current_values, pis)]
        row_headers = ["Class %i" % (i+1) for i in range(len(current_values))]
        col_headers = ["Vessel %i" % (i+1) for i in range(num_sources)] + ["Proportion",]
        self.setValues(new_values, validate=False, col_headers=col_headers, row_headers=row_headers)

    def _make_classlist(self, nsources, nfpc):
        """
        Generate the class list with specified number of sources per class
        A rather crude approach is used which will be fine so long as nsources
        is not too big. We generate all combinations of sources and just select
        those where the total number of sources is correct

        The equivalent code was 70 lines of c++ :-)
        """
        classlist = [c for c in self._all_combinations(nsources) if sum(c) == nfpc]
        # add class with no flows in FIXME not in Matlab - should we do thi?
        # classlist += [0,] * nsources
        return classlist

    def _all_combinations(self, nsources):
        if nsources == 0:
            yield []
        else:
            for c in self._all_combinations(nsources-1):
                yield [0,] + c
                yield [1,] + c
