import os
import re
import unittest

from aodncore.pipeline import PipelineFilePublishType, FileType, PipelineFileCollection, \
    PipelineFile
from aodncore.pipeline.exceptions import InvalidInputFileError, MissingFileError
from aodncore.pipeline.storage import get_storage_broker
from aodncore.testlib import HandlerTestCase


from aodndata.anfog.classifiers import AnfogFileClassifier
from aodndata.anfog.handlers import AnfogHandler

TEST_ROOT = os.path.join(os.path.dirname(__file__))
TEST_MISSION_LIST = os.path.join(TEST_ROOT, 'HarvestmissionList.csv')
GOOD_NC = os.path.join(TEST_ROOT, 'IMOS_ANFOG_BCEOPSTUV_20180503T080042Z_SL210_FV01_timeseries_END-20180505T054942Z.nc')
DSTG = os.path.join(TEST_ROOT, 'DSTO_MD_CEPSTUV_20130706T122916Z_SL090_FV01_timeseries_END-20130715T040955Z.nc')
ZIP_NRL = os.path.join(TEST_ROOT, 'NRL_test.zip')
GOOD_ZIP_DM = os.path.join(TEST_ROOT,
                           'IMOS_ANFOG_BCEOPSTUV_20180503T080042Z_SL210_FV01_timeseries_END-20180505T054942Z.zip')
GOOD_ZIP_RT = os.path.join(TEST_ROOT, 'TwoRocks20180503a.zip')
PREV_NC_RT = os.path.join(TEST_ROOT,
                          'IMOS_ANFOG_BCEOSTUV_20180503T075848Z_SL210_FV00_timeseries_END-20180504T000000Z.nc')
PREV_PNG_TRANSECT = os.path.join(TEST_ROOT, 'unit210_b700_tser_20180503T000000-20180504T000000.png')
PREV_PNG_MISSION = os.path.join(TEST_ROOT, 'unit210_b700_tser_mission.png')
MISSION_STATUS = os.path.join(TEST_ROOT, 'SL-TwoRocks20180503a_renamed.txt')
MISSION_STATUS_COMPLETED = os.path.join(TEST_ROOT, 'SL-TwoRocks20180503a_completed.txt')
MISSION_STATUS_DM = os.path.join(TEST_ROOT, 'SL-TwoRocks20180503a_delayed_mode.txt')
BAD_RT_ZIP = os.path.join(TEST_ROOT, 'RT_NONETCDF.zip')

class TestAnfogHandler(HandlerTestCase):
    """It is recommended to inherit from the HandlerTestCase class (which is itself a subclass of the standard
       unittest.TestCase class). This provides some useful methods and properties to shortcut some common test
       scenarios.
    """

    def setUp(self):
        # set the handler_class attribute to your handler (as imported above)
        self.handler_class = AnfogHandler

        super(TestAnfogHandler, self).setUp()

    def test_good_dm_file_with_compliance_check(self):
        #  this is tested as an update to avoid raising invalid input file error cause of missing ancillary material
        preexisting_file = PipelineFileCollection()

        existing_file = PipelineFile(GOOD_NC, dest_path=os.path.join(
            'IMOS/ANFOG/slocum_glider/TwoRocks20180503a/', os.path.basename(GOOD_NC)))

        preexisting_file.update([existing_file])

        # set the files to UPLOAD_ONLY
        preexisting_file.set_publish_types(PipelineFilePublishType.UPLOAD_ONLY)

        # upload the 'preexisting_files' collection to the unit test's temporary upload location
        broker = get_storage_broker(self.config.pipeline_config['global']['upload_uri'])
        broker.upload(preexisting_file)

        handler = self.run_handler(GOOD_NC, check_params={'checks': ['cf', 'imos:1.4']})

        f = handler.file_collection.filter_by_attribute_id('file_type', FileType.NETCDF)
        # self.assertEqual(f[0].check_type, PipelineFileCheckType.NC_COMPLIANCE_CHECK)
        self.assertEqual(f[0].publish_type, PipelineFilePublishType.HARVEST_UPLOAD)

        self.assertEqual(f[0].dest_path,
                         'IMOS/ANFOG/slocum_glider/TwoRocks20180503a/'
                         'IMOS_ANFOG_BCEOPSTUV_20180503T080042Z_SL210_FV01_timeseries_END-20180505T054942Z.nc')
        self.assertTrue(f[0].is_checked)
        self.assertTrue(f[0].is_stored)
        self.assertTrue(f[0].is_harvested)

    def test_good_anfog_dm_zip(self):

        handler = self.run_handler(GOOD_ZIP_DM, check_params={'checks': ['cf', 'imos:1.4']})

        raw = handler.file_collection.filter_by_attribute_regex('name', AnfogFileClassifier.RAW_FILES_REGEX)
        jpg = handler.file_collection.filter_by_attribute_value('extension', '.jpg')

        dm_file = handler.file_collection.filter_by_attribute_regex('name', AnfogFileClassifier.DM_REGEX)

        j = jpg[0]
        self.assertEqual(j.publish_type, PipelineFilePublishType.UPLOAD_ONLY)
        self.assertEqual(j.dest_path,
                         'IMOS/ANFOG/slocum_glider/TwoRocks20180503a/' + j.name)
        self.assertTrue(j.is_stored)

        for r in raw:
            self.assertEqual(r.publish_type, PipelineFilePublishType.ARCHIVE_ONLY)
            self.assertEqual(r.archive_path,
                             'IMOS/ANFOG/slocum_glider/TwoRocks20180503a/' + r.name)
            self.assertTrue(r.is_archived)

        # FV01 file
        nc = dm_file[0]
        self.assertEqual(nc.dest_path,
                         'IMOS/ANFOG/slocum_glider/TwoRocks20180503a/' + nc.name)
        self.assertTrue(nc.is_stored)
        self.assertTrue(nc.is_checked)
        self.assertTrue(nc.is_harvested)

    def test_good_anfog_rt_zip(self):

        handler = self.run_handler(GOOD_ZIP_RT)

        png = handler.file_collection.filter_by_attribute_id('file_type', FileType.PNG)
        nc = handler.file_collection.filter_by_attribute_id('file_type', FileType.NETCDF)

        self.assertEqual(nc[0].dest_path, 'IMOS/ANFOG/REALTIME/slocum_glider/TwoRocks20180503a/' + nc[0].name)
        self.assertTrue(nc[0].is_stored)
        self.assertTrue(nc[0].is_harvested)

        self.assertGreater(0, len(png))
        for p in png:
            self.assertEqual(p.publish_type, PipelineFilePublishType.UPLOAD_ONLY)
            self.assertEqual(p.dest_path, 'IMOS/ANFOG/REALTIME/slocum_glider/TwoRocks20180503a/' + p.name)
            self.assertTrue(p.is_stored)

        csv = handler.file_collection.filter_by_attribute_id('file_type', FileType.CSV)
        self.assertEqual(csv[0].publish_type, PipelineFilePublishType.HARVEST_ONLY)
        self.assertTrue(csv[0].is_harvested)

    def test_dstg(self):
        preexisting_file = PipelineFileCollection()
        existing_file = PipelineFile(DSTG, dest_path=os.path.join(
            'Department_of_Defence/DSTG/slocum_glider/TalismanSaberB20130706/', os.path.basename(DSTG)))

        preexisting_file.update([existing_file])

        # set the files to UPLOAD_ONLY
        preexisting_file.set_publish_types(PipelineFilePublishType.UPLOAD_ONLY)

        # upload the 'preexisting_files' collection to the unit test's temporary upload location
        broker = get_storage_broker(self.config.pipeline_config['global']['upload_uri'])
        broker.upload(preexisting_file)

        # test processing of DSTG and NRL NetCDF files
        handler = self.run_handler(DSTG)

        f = handler.file_collection[0]
        self.assertEqual(f.publish_type, PipelineFilePublishType.HARVEST_UPLOAD)
        self.assertEqual(f.dest_path,
                         'Department_of_Defence/DSTG/slocum_glider/TalismanSaberB20130706/' + f.name)
        self.assertTrue(f.is_stored)
        self.assertTrue(f.is_harvested)

    def test_nrl(self):
        # test processing of NRL file collection. Collection containn FV01 and FV00
        handler = self.run_handler(ZIP_NRL,check_params={'checks': ['cf']})

        non_nc = handler.file_collection.filter_by_attribute_value('extension', '.jpg|.kml')
        fv01 = handler.file_collection.filter_by_attribute_regex('name', AnfogFileClassifier.DM_REGEX)
        fv00 = handler.file_collection.filter_by_attribute_regex('name', AnfogFileClassifier.RAW_DATA_REGEX)

        for n in non_nc:
            self.assertEqual(n.publish_type, PipelineFilePublishType.UPLOAD_ONLY)
            self.assertEqual(n.dest_path,
                             'US_Naval_Research_Laboratory/slocum_glider/AdapterNSW20120415/' + n.name)
            self.assertTrue(n.is_stored)

        # FV01
        f = fv01[0]
        self.assertEqual(f.publish_type, PipelineFilePublishType.HARVEST_UPLOAD)
        self.assertEqual(f.dest_path,
                         'US_Naval_Research_Laboratory/slocum_glider/AdapterNSW20120415/' + f.name)
        self.assertTrue(f.is_checked)
        self.assertTrue(f.is_stored)
        self.assertTrue(f.is_harvested)

        # FV00 => archive

        for a in fv00:
            self.assertEqual(a.publish_type, PipelineFilePublishType.ARCHIVE_ONLY)
            self.assertEqual(a.archive_path,
                             'US_Naval_Research_Laboratory/slocum_glider/AdapterNSW20120415/' + a.name)
            self.assertTrue(a.is_archived)

    def test_rt_update(self):
        """ test the update of realtime mission:
         update consits in :
         - deletion of previous netCDF
         - deletion of transect png files
         - harvest of new netCDF
         - overwriting of other files
        """
        # create some PipelineFiles to represent the existing files on 'S3'
        preexisting_files = PipelineFileCollection()

        existing_file1 = PipelineFile(PREV_NC_RT, dest_path=os.path.join(
            'IMOS/ANFOG/REALTIME/slocum_glider/TwoRocks20180503a/', os.path.basename(PREV_NC_RT)))

        existing_file2 = PipelineFile(PREV_PNG_TRANSECT, dest_path=os.path.join(
            'IMOS/ANFOG/REALTIME/slocum_glider/TwoRocks20180503a/', os.path.basename(PREV_PNG_TRANSECT)))
        existing_file3 = PipelineFile(PREV_PNG_MISSION, dest_path=os.path.join(
            'IMOS/ANFOG/REALTIME/slocum_glider/TwoRocks20180503a/', os.path.basename(PREV_PNG_MISSION)))

        preexisting_files.update([existing_file1, existing_file2, existing_file3])

        # set the files to UPLOAD_ONLY
        preexisting_files.set_publish_types(PipelineFilePublishType.UPLOAD_ONLY)

        # upload the 'preexisting_files' collection to the unit test's temporary upload location
        broker = get_storage_broker(self.config.pipeline_config['global']['upload_uri'])
        broker.upload(preexisting_files)

        # run the handler
        handler = self.run_handler(GOOD_ZIP_RT)

        nc = handler.file_collection.filter_by_attribute_id('file_type', FileType.NETCDF)
        for n in nc:
            if n.name == os.path.basename(PREV_NC_RT):
                self.assertEqual(n.publish_type, PipelineFilePublishType.DELETE_UNHARVEST)
                self.assertTrue(n.is_deleted)
            else:
                self.assertEqual(n.publish_type, PipelineFilePublishType.HARVEST_UPLOAD)
                self.assertTrue(n.is_harvested)
                self.assertTrue(n.is_stored)

        pngs = handler.file_collection.filter_by_attribute_id('file_type', FileType.PNG)
        for png in pngs:
            if png.name == os.path.basename(PREV_PNG_TRANSECT):
                self.assertTrue(png.is_deleted)
            elif png.name == os.path.basename(PREV_PNG_MISSION):
                self.assertTrue(png.is_overwrite)
            else:
                self.assertTrue(png.is_uploaded)

        # no update the harvestMission List in that case
        csv = handler.file_collection.filter_by_attribute_id('file_type', FileType.CSV)
        self.assertEqual(len(csv), 0)

    def test_deletion_rt_after_dm_upload(self):
        """test deletion of RT mission at upload of related DM version"""
        preexisting_files = PipelineFileCollection()

        existing_file1 = PipelineFile(PREV_NC_RT, dest_path=os.path.join(
            'IMOS/ANFOG/REALTIME/slocum_glider/TwoRocks20180503a/', os.path.basename(PREV_NC_RT)))

        existing_file2 = PipelineFile(PREV_PNG_TRANSECT, dest_path=os.path.join(
            'IMOS/ANFOG/REALTIME/slocum_glider/TwoRocks20180503a/', os.path.basename(PREV_PNG_TRANSECT)))
        existing_file3 = PipelineFile(PREV_PNG_MISSION, dest_path=os.path.join(
            'IMOS/ANFOG/REALTIME/slocum_glider/TwoRocks20180503a/', os.path.basename(PREV_PNG_MISSION)))

        preexisting_files.update([existing_file1, existing_file2, existing_file3])

        # set the files to UPLOAD_ONLY
        preexisting_files.set_publish_types(PipelineFilePublishType.UPLOAD_ONLY)

        # upload the 'preexisting_files' collection to the unit test's temporary upload location
        broker = get_storage_broker(self.config.pipeline_config['global']['upload_uri'])
        broker.upload(preexisting_files)

        # run the handler
        handler = self.run_handler(GOOD_ZIP_DM, check_params={'checks': ['cf', 'imos:1.4']})

        nc = handler.file_collection.filter_by_attribute_id('file_type', FileType.NETCDF)
        for n in nc:
            if n.name == os.path.basename(PREV_NC_RT):
                self.assertEqual(n.publish_type, PipelineFilePublishType.DELETE_UNHARVEST)
                self.assertTrue(n.is_deleted)
            elif re.match(AnfogFileClassifier.DM_REGEX, n.name):
                self.assertEqual(n.publish_type, PipelineFilePublishType.HARVEST_UPLOAD)
                self.assertTrue(n.is_harvested)
                self.assertTrue(n.is_stored)
            else:
                self.assertEqual(n.publish_type, PipelineFilePublishType.ARCHIVE_ONLY)
                self.assertTrue(n.is_archived)

        pngs = handler.file_collection.filter_by_attribute_id('file_type', FileType.PNG)
        for png in pngs:
            self.assertTrue(png.is_deleted)

    def test_handling_status_completed(self):
        # test processing of product file
        handler = self.run_handler(MISSION_STATUS_COMPLETED)

        csv = handler.file_collection.filter_by_attribute_id('file_type', FileType.CSV)
        self.assertEqual(csv[0].publish_type, PipelineFilePublishType.HARVEST_ONLY)
        self.assertTrue(csv[0].is_harvested)

    def test_renamed_deployment(self):
        # test eletion of RT files when deployment renamed
        preexisting_files = PipelineFileCollection()

        existing_file1 = PipelineFile(PREV_NC_RT, dest_path=os.path.join(
            'IMOS/ANFOG/REALTIME/slocum_glider/TwoRocks20180503a/', os.path.basename(PREV_NC_RT)))

        existing_file2 = PipelineFile(PREV_PNG_TRANSECT, dest_path=os.path.join(
            'IMOS/ANFOG/REALTIME/slocum_glider/TwoRocks20180503a/', os.path.basename(PREV_PNG_TRANSECT)))
        existing_file3 = PipelineFile(PREV_PNG_MISSION, dest_path=os.path.join(
            'IMOS/ANFOG/REALTIME/slocum_glider/TwoRocks20180503a/', os.path.basename(PREV_PNG_MISSION)))

        preexisting_files.update([existing_file1, existing_file2, existing_file3])

        # set the files to UPLOAD_ONLY
        preexisting_files.set_publish_types(PipelineFilePublishType.UPLOAD_ONLY)

        # upload the 'preexisting_files' collection to the unit test's temporary upload location
        broker = get_storage_broker(self.config.pipeline_config['global']['upload_uri'])
        broker.upload(preexisting_files)

        handler = self.run_handler(MISSION_STATUS)

        # Process should resuls in : input file unhandled , preexisting file should be deleted, cvs file harvested
        csv = handler.file_collection.filter_by_attribute_id('file_type', FileType.CSV)
        self.assertEqual(csv[0].publish_type, PipelineFilePublishType.HARVEST_ONLY)
        self.assertTrue(csv[0].is_harvested)

        nc = handler.file_collection.filter_by_attribute_id('file_type', FileType.NETCDF)
        self.assertEqual(nc[0].publish_type, PipelineFilePublishType.DELETE_UNHARVEST)
        self.assertTrue(nc[0].is_deleted)

        pngs = handler.file_collection.filter_by_attribute_id('file_type', FileType.PNG)
        for png in pngs:
            self.assertEqual(png.publish_type, PipelineFilePublishType.DELETE_ONLY)
            self.assertTrue(png.is_deleted)

    def test_bad_rt_status_file(self):
        # test invalid message
        self.run_handler_with_exception(InvalidInputFileError, MISSION_STATUS_DM)

    def test_rt_zip_no_netcdf(self):
        "ZIP should contain one FV00 NetCDF file"
        self.run_handler_with_exception(InvalidInputFileError, BAD_RT_ZIP)

    def test_missing_material_DM(self):
        "new DM missions should nbe submitted with ancillary material"
        self.run_handler_with_exception(MissingFileError, GOOD_NC)

    if __name__ == '__main__':
        unittest.main()
