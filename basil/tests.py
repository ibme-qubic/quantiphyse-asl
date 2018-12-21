"""
Quantiphyse - Tests for ASL widgets

Copyright (c) 2013-2018 University of Oxford
"""
import sys
import unittest 

import numpy as np

from quantiphyse.data import NumpyData
from quantiphyse.processes import Process
from quantiphyse.test import WidgetTest, ProcessTest

from .widgets import AslPreprocWidget
from .aslimage_widget import LabelType, DataOrdering, ORDER_LABELS
from .oxasl_widgets import OxaslWidget

def _struc_widget(aslimage_widget, cls):
    for view in aslimage_widget.views:
        if isinstance(view, cls):
            return view

class AslPreprocWidgetTest(WidgetTest):
    """ Tests for the preprocessing widget"""

    def widget_class(self):
        return AslPreprocWidget

    def testNoData(self):
        """ User clicks the generate buttons with no data"""
        self.harmless_click(self.w.run_btn)

    def test3dDataNoPreproc(self):
        self.ivm.add(self.data_3d, grid=self.grid, name="data_3d")
        self.w.aslimage_widget.set_data_name("data_3d")
        self.processEvents()
        self.assertFalse(self.error)
        
        # 3D data so set to already differenced
        label_type_widget = _struc_widget(self.w.aslimage_widget, LabelType)
        label_type_widget.combo.setCurrentIndex(2)
        self.processEvents()

        struc = self.ivm.data["data_3d"].metadata.get("AslData", None)
        self.assertTrue(struc is not None)
        self.assertEqual(len(struc["tis"]), 1)
        self.assertTrue("l" not in struc["order"])
        self.assertEqual(struc["iaf"], "diff")

        self.harmless_click(self.w.run_btn)
        self.processEvents()

        # Nothing done, so no new data
        self.assertEqual(len(self.ivm.data), 1)
        self.assertTrue("data_3d" in self.ivm.data)

    def test4dDataNoPreproc(self):
        """
        Check a single-ti data set with no preprocessing
        """
        self.ivm.add(self.data_4d, grid=self.grid, name="data_4d")
        self.w.aslimage_widget.set_data_name("data_4d")
        self.processEvents()
        self.assertFalse(self.error)
    
        # Treat data as TC pairs
        label_type_widget = _struc_widget(self.w.aslimage_widget, LabelType)
        label_type_widget.combo.setCurrentIndex(0)
        self.processEvents()

        struc = self.ivm.data["data_4d"].metadata.get("AslData", None)
        self.assertTrue(struc is not None)
        self.assertEqual(len(struc["tis"]), 1)
        self.assertTrue("l" in struc["order"])
        self.assertEqual("tc", struc["iaf"])
        
        self.harmless_click(self.w.run_btn)
        self.processEvents()

        # Nothing done, so no new data
        self.assertEqual(len(self.ivm.data), 1)
        self.assertTrue("data_4d" in self.ivm.data)

    def testDiff(self):
        """
        Check a single-ti data set with tag-control differencing
        """
        self.ivm.add(self.data_4d, grid=self.grid, name="data_4d")
        self.w.aslimage_widget.set_data_name("data_4d")
        self.processEvents()
        self.assertFalse(self.error)
        
        # Treat data as TC pairs
        label_type_widget = _struc_widget(self.w.aslimage_widget, LabelType)
        label_type_widget.combo.setCurrentIndex(0)
        self.processEvents()

        # Select tag-control differencing
        self.w.sub_cb.setChecked(True)
        self.processEvents()
        
        self.harmless_click(self.w.run_btn)
        self.processEvents()

        self.assertEqual(len(self.ivm.data), 2)
        self.assertTrue("data_4d" in self.ivm.data)
        self.assertTrue("data_4d_diff" in self.ivm.data)

        # Check shape is as expected
        diffdata = self.ivm.data["data_4d_diff"]
        shape = list(self.data_4d.shape)
        shape[3] = shape[3] / 2
        for idx, n in enumerate(shape):
            self.assertEqual(diffdata.raw().shape[idx], n)

        # Check struct is as expected
        struc = diffdata.metadata.get("AslData", None)
        self.assertTrue(struc is not None)
        self.assertEqual(len(struc["tis"]), 1)
        self.assertTrue("l" not in struc["order"])
        self.assertEqual(struc["iaf"], "diff")
        
        # Check data is as expected (control - tag)
        diffdata_test = np.zeros(shape)
        for v in range(shape[3]):
            diffdata_test[..., v] = self.data_4d[..., v*2+1] - self.data_4d[..., v*2]
        self.assertTrue(np.all(diffdata_test == diffdata.raw()))

    def testMean(self):
        """
        Check a single-ti data set with the 'mean across repeats option
        """
        self.ivm.add(self.data_4d, grid=self.grid, name="data_4d")
        self.w.aslimage_widget.set_data_name("data_4d")
        self.processEvents()
        self.assertFalse(self.error)
        
        # Treat data as TC pairs
        label_type_widget = _struc_widget(self.w.aslimage_widget, LabelType)
        label_type_widget.combo.setCurrentIndex(0)
        self.processEvents()

        # Select mean across repeats
        self.w.mean_cb.setChecked(True)
        self.processEvents()
        
        self.harmless_click(self.w.run_btn)
        self.processEvents()

        self.assertEqual(len(self.ivm.data), 2)
        self.assertTrue("data_4d" in self.ivm.data)
        self.assertTrue("data_4d_mean" in self.ivm.data)

        # Check shape is as expected
        meandata = self.ivm.data["data_4d_mean"]
        shape = list(self.data_4d.shape[:3])
        for idx, n in enumerate(shape):
            self.assertEqual(meandata.raw().shape[idx], n)

        # Check struct is as expected
        struc = meandata.metadata.get("AslData", None)
        self.assertTrue(struc is not None)
        self.assertEqual(len(struc["tis"]), 1)
        self.assertTrue("l" not in struc["order"])
        self.assertEqual(struc["iaf"], "diff")
        
        # Check data is as expected (differenced, then mean across repeats)
        meandata_test = np.zeros(shape)
        diffdata_test = np.zeros(list(shape) + [self.data_4d.shape[3] / 2])
        for v in range(diffdata_test.shape[3]):
            diffdata_test[..., v] = self.data_4d[..., v*2+1] - self.data_4d[..., v*2]
        meandata_test = np.mean(diffdata_test, axis=-1)
        self.assertTrue(np.allclose(meandata_test, meandata.raw()))

    def testReorder(self):
        """
        Check a single-ti data set with reordering to 'all tags' then 'all controls'
        """
        self.ivm.add(self.data_4d, grid=self.grid, name="data_4d")
        self.w.aslimage_widget.set_data_name("data_4d")
        self.processEvents()
        self.assertFalse(self.error)
        
        # Treat data as TC pairs in order prt (top = outermost)
        label_type_widget = _struc_widget(self.w.aslimage_widget, LabelType)
        label_type_widget.combo.setCurrentIndex(0)
        data_order_widget = _struc_widget(self.w.aslimage_widget, DataOrdering)
        items = []
        for group in "trl":
            labels = ORDER_LABELS[group]
            if isinstance(labels, tuple):
                items.append(labels[2])
            else:
                items.append(labels["tc"][2])
        data_order_widget.group_list.setItems(items)
        self.processEvents()

        # Select reorder
        self.w.reorder_cb.setChecked(True)
        self.w.new_order.setText("trl")
        self.processEvents()
        
        self.harmless_click(self.w.run_btn)
        self.processEvents()

        self.assertEqual(len(self.ivm.data), 2)
        self.assertTrue("data_4d" in self.ivm.data)
        self.assertTrue("data_4d_reorder" in self.ivm.data)

        # Check shape is as expected
        reordered_data = self.ivm.data["data_4d_reorder"]
        shape = list(self.data_4d.shape)
        for idx, n in enumerate(shape):
            self.assertEqual(reordered_data.raw().shape[idx], n)

        # Check struct is as expected
        struc = reordered_data.metadata.get("AslData", None)
        self.assertTrue(struc is not None)
        self.assertEqual(len(struc["tis"]), 1)
        self.assertEqual(struc["order"], "trl")
        
        # Check data is as expected (all tags first, then all controls)
        reordered_test = np.zeros(shape)
        for v in range(shape[3]/2):
            reordered_test[..., v] = self.data_4d[..., 2*v]
            reordered_test[..., v+shape[3]/2] = self.data_4d[..., 2*v+1]
        self.assertTrue(np.allclose(reordered_test, reordered_data.raw()))

class MultiphaseProcessTest(ProcessTest):

    @unittest.skipIf("--fast" in sys.argv, "Slow test")
    def testJLarkin(self):
        """
        Test on James Larkin's multiphase data. Note that this data is not currently
        bundled with Quantiphyse so test will fail if not present
        """
        yaml = """
  - Load:
      data:
        /home/ibmeuser/data/asl/jlarkin/TagDurations/TD=1.4/asl_phase_shifted_5_OPTIMAL/asl_phase_shifted_5.nii: multiphase_data
      rois:
        /home/ibmeuser/data/asl/jlarkin/TagDurations/TD=1.4/asl_phase_shifted_5_OPTIMAL/mask.nii.gz: multiphase_mask

  - AslMultiphase:
      data: multiphase_data
      roi : multiphase_mask
      nphases: 8
      keep-temp: True
      sigma: 1
      n-supervoxels: 8
      compactness: 0.1
"""
        self.run_yaml(yaml)
        self.assertEqual(self.status, Process.SUCCEEDED)
        self.assertTrue("mean_mag" in self.ivm.data)
        self.assertTrue("mean_offset" in self.ivm.data)
        self.assertTrue("mean_phase" in self.ivm.data)

class BasilProcessTest(ProcessTest):

    @unittest.skipIf(True, "Temporarily disabled")
    @unittest.skipIf("--fast" in sys.argv, "Slow test")
    def testFslCourse(self):
        """
        Basil BASIL process test. Note that this data is not currently
        bundled with Quantiphyse so test will fail if not present
        """
        yaml = """
  - Load:
      data:
        /home/ibmeuser/data/asl/fsl_course/ASL/mpld_asltc.nii.gz: asldata
      rois:
        /home/ibmeuser/data/asl/fsl_course/ASL/mask.nii.gz: aslmask

  - Basil:
      data: asldata
      roi : aslmask
      order: prt
      tis: [0.25, 0.5, 0.75, 1.0, 1.25, 1.5]
      casl: True
      taus: [1.4, 1.4, 1.4, 1.4, 1.4, 1.4]
      infertiss: True
"""
        self.run_yaml(yaml)
        self.assertEqual(self.status, Process.SUCCEEDED)
        self.assertTrue("perfusion" in self.ivm.data)
        self.assertTrue("perfusion_std" in self.ivm.data)
        self.assertTrue("arrival" in self.ivm.data)
        self.assertTrue("arrival_std" in self.ivm.data)
        

if __name__ == '__main__':
    unittest.main()

class OxaslWidgetTest(WidgetTest):

    def widget_class(self):
        return OxaslWidget

    def _options_match(self, options, expected):
        for item in set(list(options.keys()) + list(expected.keys())):
            #print(item, options.get(item, "MISSING"), expected.get(item, "MISSING"))
            self.assertTrue(item in options)
            self.assertTrue(item in expected)
            self.assertEqual(options[item], expected[item])

    def _md(self, **kwargs):
        ret = {
            "iaf" : "tc",
            "order" : "lrt", 
            "plds" : [1.7,], 
            "taus" : [1.3,], 
            "casl" : True
        }
        ret.update(kwargs)
        return ret

    def _preproc(self, **kwargs):
        ret = {
            "mc" : True,
            "use_enable" : False,
            "deblur" : False,
        }
        ret.update(kwargs)
        return ret

    def _analysis(self, **kwargs):
        ret = {
            "infertau" : False,
            "inferart" : True,
            "inferbat" : True,
            "infert1" : False,
            "pvcorr" : False,
            "spatial" : True,
            "t1b" : 1.65,
            "t1" : 1.3,
            "bat" : 1.3,
            "wp" : False,
            "save-reg" : False,
            "save-calib" : False,
            "save-struc" : False,
            "save-native" : True,
            "save-mask" : True,
            "save-std" : False,
        }
        ret.update(kwargs)
        return ret

    def _options(self, **kwargs):
        ret = {
            "output" : {}
        }
        ret.update(self._md())
        ret.update(self._preproc())
        ret.update(self._analysis())
        ret.update(kwargs)
        return ret

    def testBasic(self):
        qpdata = NumpyData(self.data_4d, grid=self.grid, name="data_4d")
        md = self._md()
        qpdata.metadata["AslData"] = md

        self.ivm.add(qpdata, name="data_4d")
        self.w.asldata.set_data_name("data_4d")
        self.processEvents()
        self.assertFalse(self.error)

        options = self.w._options()
        self._options_match(options, self._options(data="data_4d", **md))

    def testMoco(self):
        qpdata = NumpyData(self.data_4d, grid=self.grid, name="data_4d")
        md = self._md()
        qpdata.metadata["AslData"] = md

        self.ivm.add(qpdata, name="data_4d")
        self.w.asldata.set_data_name("data_4d")
        self.processEvents()
        self.assertFalse(self.error)

        self.w.preproc.optbox.option("mc").value = True
        self.processEvents()

        options = self.w._options()
        self._options_match(options, self._options(data="data_4d", mc=True, **md))

    def testInferArt(self):
        qpdata = NumpyData(self.data_4d, grid=self.grid, name="data_4d")
        md = self._md()
        qpdata.metadata["AslData"] = md

        self.ivm.add(qpdata, name="data_4d")
        self.w.asldata.set_data_name("data_4d")
        self.processEvents()
        self.assertFalse(self.error)

        self.w.analysis.optbox.option("inferart").value = True
        self.processEvents()

        options = self.w._options()
        self._options_match(options, self._options(data="data_4d", inferart=True, **md))

if __name__ == '__main__':
    unittest.main()
