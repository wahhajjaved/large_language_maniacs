#!/usr/bin/python
#
# File:   make_person_course.py
# Date:   13-Oct-14
# Author: I. Chuang <ichuang@mit.edu>
#
# make the person_course dataset for a specified course, using Google BigQuery
# and data stored in Google cloud storage.
#
# each entry has the following fields:
# 
# course_id
# user_id
# username
# registered (bool)
# viewed+ (bool)
# viewed (bool)
# explored+ (bool)
# explored (bool)
# explored_by_logs+ (bool)
# explored_by_logs (bool)
# certified+ (bool)
# certified (bool)
# ip
# cc_by_ip
# LoE (level of education)
# YoB (year of birth)
# gender
# grade (from certificate table)
# start_time (registration time, from enrollment table)
# last_event (time, from derived_person_last_active)
# nevents (total number of events in tracking_log, from derived_daily_event_counts)
# ndays_act (number of days with activity in the tracking_log, up to end-date)
# nplay_video (number of play_video events for this user & course)
# nchapters (number of chapters viewed in course by given student)
# nforum_posts (number of forum posts for user & course)
# roles (empty for students, otherwise "instructor" or "staff" if had that role in the course)
# nprogcheck (number of progress checks)
# nproblem_check (number of problem checks)
# nforum_events (number of forum views)
# mode (kind of enrollment, e.g. honor, idverified)
#
# performs queries needed to compute derivative tables, including:
#
# - pc_nevents
# - pc_modal_ip
#
# Assembles final person_course dataset locally, then uploads back to GS & BQ.
#
# Usage:
#
#    python make_person_course.py course_directory
#
# e.g.:
#
#    python make_person_course.py 6.SFMx

import os
import sys
import unicodecsv as csv
import gzip
import json
import bqutil
import gsutil
import datetime
import copy
from path import path
from collections import OrderedDict, defaultdict
from check_schema_tracking_log import schema2dict, check_schema
from load_course_sql import find_course_sql_dir

#-----------------------------------------------------------------------------

class PersonCourse(object):
    
    def __init__(self, course_id, course_dir=None, course_dir_root='', course_dir_date='', 
                 verbose=True, gsbucket="gs://x-data", 
                 force_recompute_from_logs=False,
                 start_date = '2012-01-01',
                 end_date = '2014-09-21',
                 nskip = 0,
                 use_dataset_latest=False,
                 skip_geoip = False,
                 ):

        self.course_id = course_id
        self.course_dir = find_course_sql_dir(course_id, course_dir_root, course_dir_date, use_dataset_latest)
        self.cdir = path(self.course_dir)
        self.logmsg = []
        self.nskip = nskip
        self.skip_geoip = skip_geoip

        if not self.cdir.exists():
            print "Oops: missing directory %s!" % self.cdir
            sys.exit(-1)

        self.verbose = verbose
        self.force_recompute_from_logs = force_recompute_from_logs

        self.gspath = gsutil.gs_path_from_course_id(course_id, gsbucket, use_dataset_latest)

        self.dataset = bqutil.course_id2dataset(course_id, use_dataset_latest=use_dataset_latest)
        self.dataset_logs = bqutil.course_id2dataset(course_id, 'logs')
        self.dataset_pcday = bqutil.course_id2dataset(course_id, 'pcday')
        self.dataset_courses = 'courses'

        self.tableid = "person_course"
        self.log("dataset=%s" % self.dataset)

        if self.dataset not in bqutil.get_list_of_datasets():
            msg = "[person_course] error! aborting - no dataset %s" % self.dataset
            self.log(msg)
            raise Exception(msg)

        self.end_date = end_date
        self.start_date = start_date
        # self.start_date = '2014-08-01'			# for debugging - smaller BQ queries
        self.sql_parameters = {'dataset': self.dataset, 
                               'dataset_logs': self.dataset_logs,
                               'dataset_pcday': self.dataset_pcday,
                               'end_date': self.end_date, 
                               'start_date': self.start_date,
                               'course_id': self.course_id,
                               }

        mypath = os.path.dirname(os.path.realpath(__file__))
        self.SCHEMA_FILE = '%s/schemas/schema_person_course.json' % mypath

        try:
            self.the_schema = json.loads(open(self.SCHEMA_FILE).read())['person_course']
        except Exception as err:
            print "Oops!  Failed to load schema file for person course.  Error: %s" % str(err)
            raise

        self.the_dict_schema = schema2dict(copy.deepcopy(self.the_schema))
        self.pctab = OrderedDict()

        self.log("="*100)
        self.log("Person Course initialized, course_dir=%s, dataset=%s (started %s)" % (self.cdir, self.dataset, datetime.datetime.now()))
        self.log("="*100)

    def log(self, msg):
        self.logmsg.append(msg)
        if self.verbose:
            print msg
            sys.stdout.flush()

    def openfile(self, fn, mode='r'):
        if fn.endswith('.gz'):
            return gzip.GzipFile(self.cdir / fn, mode)
        return open(self.cdir / fn, mode)
    
    def load_csv(self, fn, key, schema=None, multi=False, fields=None, keymap=None):
        '''
        load csv file into memory, storing into dict with specified field (key) as the key.
        if multi, then each dict value is a list, with one or more values per key.
    
        if fields, load only those specified fields.
        '''
        data = OrderedDict()
        if keymap is None:
            keymap = lambda x: x
        for line in csv.DictReader(self.openfile(fn)):
            try:
                the_id = keymap(line[key])
            except Exception as err:
                self.log("oops, failed to do keymap, key=%s, line=%s" % (line[key], line))
                raise
            if fields:
                newline = { x: line[x] for x in fields }
                line = newline
            if multi:
                if the_id in data:
                    data[the_id].append(line)
                else:
                    data[the_id] = [ line ]
            else:
                data[the_id] = line
        return data
    
    def load_json(self, fn, key):
        data = OrderedDict()
        cnt = 0
        for line in self.openfile(fn):
            cnt += 1
            jd = json.loads(line)
            if key in jd:
                the_id = jd[key]
                data[the_id] = jd
            else:
                self.log("[make_person_course] oops!  missing %s from %s row %s=%s" % (key, fn, cnt, jd))
        return data
    
    @staticmethod
    def copy_fields(src, dst, fields, mapfun=None):
        if not mapfun:
            mapfun = lambda x: x
        for key, val in fields.items():
            if type(val)==list:
                for valent in val:
                    if valent in src:
                        dst[key] = src[valent]
                        break
            else:
                if val in src:
                    dst[key] = mapfun(src[val])
    
    #-----------------------------------------------------------------------------
    
    def get_nchapters_from_course_metainfo(self):
        '''
        Determine the number of chapters from the course_metainfo table, which is computed
        by analyze_content, based on the course XML, but dropping chapters which haven't
        seen a significant number of viewers.
        
        If the course_metainfo table does not exist, then fall back to using
        get_nchapters_from_course_structure.
        '''
        table = "course_metainfo"
        
        tables = bqutil.get_list_of_table_ids(self.dataset)
        if not table in tables:
            return self.get_nchapters_from_course_structure()

        bqdat = bqutil.get_table_data(self.dataset, table, key={'name': 'key'})
        cminfo = bqdat['data_by_key']

        ccent = cminfo.get('count_chapter')
        if ccent:
            self.nchapters = int(ccent['value'])
            nexcluded = cminfo.get('nexcluded_sub_20_chapter', {}).get('value', 0)
            self.log('course %s has %s chapters, based on course_metainfo, with %s excluded' % (self.course_id, 
                                                                                                self.nchapters, 
                                                                                                nexcluded))
            return self.nchapters

        self.log('-> No count_chapter in course_metainfo table...falling back to get_nchapters_from_course_structure')
        return self.get_nchapters_from_course_structure()

    def get_nchapters_from_course_structure(self):
        '''
        Determine the number of chapters from the course structure or course axis file.
        '''
        nchapters = 0

        def getonefile(files):
            for fn in files:
                if (self.cdir / fn).exists():
                    return fn
            return None

        csfiles = ['course_structure-prod-analytics.json.gz', 'course_structure.json', 'course_axis.json']
        csfn = getonefile(csfiles)
        if csfn is None:
            self.log('[make_person_course] get_nchapters: Cannot find required file in %s, one of %s' % (self.cdir, csfiles))
            sys.stdout.flush()
            return 9999   	# dummy value

        if csfn=='course_axis.json':
            struct = {x: json.loads(x) for x in self.openfile(csfn) }
        else:
            struct = json.loads(self.openfile(csfn).read())
        for key, ent in struct.iteritems():
            if ent['category']=='chapter':
                nchapters += 1

        self.log('course %s has %s chapters, based on %s' % (self.course_id, nchapters, csfn))
        self.nchapters = nchapters

        return nchapters
    
    def reload_table(self):
        '''
        load current verison of the person course table from an existing
        person_course.json.gz file
        
        This is useful to do, for example, when the second or third phases of 
        the person course dataset need to be added to an existing dataset.
        '''
        dfn = 'person_course.json.gz'
        data = {}
        for line in self.openfile(dfn):
            dline = json.loads(line)
            key = dline['username']

            if 'city' in dline:
                dline['city'] = dline['city'].encode('utf8')
            if 'countryLabel' in dline:
                dline['countryLabel'] = dline['countryLabel'].encode('utf8')

            data[key] = dline
        self.pctab = data
        self.log("Loaded %d lines from %s" % (len(data), self.cdir / dfn))

    def compute_first_phase(self):
    
        # -----------------------------------------------------------------------------
        # person_course part 1: stuff which can be computed using just the user_info_combo table

        self.log("-"*20)
        self.log("Computing first phase based on user_info_combo")
        
        try:
            uicdat = self.load_json('user_info_combo.json.gz', 'username') # start with user_info_combo file, use username as key becase of tracking logs
        except Exception as err:
            self.log('[person_course] Error loading user_info_combo.json.gz, a required file ; aborting!')
            self.log('                err=%s' % str(err))
            raise Exception('no user_info_combo')

        self.uicdat = uicdat
    
        for key, uicent in uicdat.iteritems():
            pcent = OrderedDict()
            self.pctab[key] = pcent			# key = username
            self.copy_fields(uicent, pcent,
                             {'course_id': ['enrollment_course_id', 'certificate_course_id'],
                              'user_id': 'user_id',
                              'username': 'username',
                              'gender': 'profile_gender',
                              'LoE': 'profile_level_of_education',
                              'YoB': 'profile_year_of_birth',
                              'grade': 'certificate_grade',
                              'start_time': 'enrollment_created',
                              'mode': 'enrollment_mode',
                              'is_active': 'enrollment_is_active',
                              'cert_created_date': 'certificate_created_date',
                              'cert_modified_date': 'certificate_modified_date',
                              'cert_status': 'certificate_status',
                              'profile_country': 'profile_country',
                              "y1_anomalous": "y1_anomalous",
                              })
        
            pcent['registered'] = True	# by definition
        
            # derived entries, from SQL data
        
            # certificate status can be [ "downloadable", "notpassing", "unavailable" ]
            # if uicent.get('certificate_status', '') in [ "downloadable","unavailable" ]:
            if uicent.get('certificate_status', '') in [ "downloadable" ]:
                pcent['certified'] = True
            else:
                pcent['certified'] = False
        
            # email domain
            pcent['email_domain'] = uicent.get('email').split('@')[1]

    def compute_second_phase(self):
    
        # -----------------------------------------------------------------------------
        # person_course part 2: stuff which can be computed using SQL tables, and no tracking log queries
        
        self.log("-"*20)
        self.log("Computing second phase based on SQL table queries done in BigQuery")

        self.load_nchapters()
        self.load_pc_forum()
        try:
            nchapters = self.get_nchapters_from_course_metainfo()
        except Exception as err:
            self.log("Error %s getting nchapters!" % str(err))
            nchapters = None
            self.pc_nchapters = None

        for key, pcent in self.pctab.iteritems():

            uid = str(pcent['user_id'])
            if self.pc_nchapters is not None:
                if uid in self.pc_nchapters['data_by_key']:
                    pcent['viewed'] = True
                    pcent['nchapters'] = int(self.pc_nchapters['data_by_key'][uid]['nchapters'])
                    if int(self.pc_nchapters['data_by_key'][uid]['nchapters']) >= nchapters/2:
                        pcent['explored'] = True
                    else:
                        pcent['explored'] = False
                else:
                    pcent['viewed'] = False

            if self.pc_forum is not None:
                for field in [  ['nforum', 'nforum_posts'],
                                ['nvotes', 'nforum_votes'],
                                ['nendorsed', 'nforum_endorsed'],
                                ['nthread', 'nforum_threads'],
                                ['ncomment', 'nforum_comments'],
                                ['npinned', 'nforum_pinned'],
                              ]:
                    self.copy_from_bq_table(self.pc_forum, pcent, uid, field)
    
    @staticmethod
    def copy_from_bq_table(src, dst, username, field, new_field=None, mkutf=False):
        '''
        Copy fields from downloaded BQ table dict (src) into the person course dict (dst).
        '''
        if type(field) is list:
            (field, new_field) = field
        datum = src['data_by_key'].get(username, {}).get(field, None)
        if datum is not None:
            if new_field is not None:
                dst[new_field] = datum
            else:
                dst[field] = datum
            if mkutf:
                dst[field] = dst[field].encode('utf8')

    def are_tracking_logs_available(self):
        datasets = bqutil.get_list_of_datasets()
        return (self.dataset_logs in datasets)

    def compute_third_phase(self, skip_modal_ip=False, skip_last_event=False):
    
        # -----------------------------------------------------------------------------
        # person_course part 3: activity metrics which need tracking log queries
        
        self.log("-"*20)
        self.log("Computing third phase based on tracking log table queries done in BigQuery")

        # skip if no tracking logs available
        if not self.are_tracking_logs_available():
            self.log("--> Missing tracking logs dataset %s_logs, skipping third phase of person_course" % self.dataset)
            return

        if False:
            self.load_last_event()	# this now comes from pc_day_totals

        self.load_pc_day_totals()	# person-course-day totals contains all the aggregate nevents, etc.

        skip_modal_ip = skip_modal_ip or self.skip_geoip

        if not skip_modal_ip:
            self.load_modal_ip()

        pcd_fields = ['nevents', 'ndays_act', 'nprogcheck', 'nshow_answer', 'nvideo', 'nproblem_check', 
                      ['nforum', 'nforum_events'], 'ntranscript', 'nseq_goto',
                      ['nvideo', 'nplay_video'],
                      'nseek_video', 'npause_video', 'avg_dt', 'sdv_dt', 'max_dt', 'n_dt', 'sum_dt']

        nmissing_ip = 0
        nmissing_ip_cert = 0
        for key, pcent in self.pctab.iteritems():
            username = pcent['username']

            # pcent['nevents'] = self.pc_nevents['data_by_key'].get(username, {}).get('nevents', None)

            if not skip_last_event:
                # le = self.pc_last_event['data_by_key'].get(username, {}).get('last_event', None)
                le = self.pc_day_totals['data_by_key'].get(username, {}).get('last_event', None)
                if le is not None and le:
                    try:
                        le = str(datetime.datetime.utcfromtimestamp(float(le)))
                    except Exception as err:
                        self.log('oops, last event cannot be turned into a time; le=%s, username=%s' % (le, username))
                    pcent['last_event'] = le

            if not skip_modal_ip:
                self.copy_from_bq_table(self.pc_modal_ip, pcent, username, 'modal_ip', new_field='ip')
                if self.pc_modal_ip['data_by_key'].get(username, {}).get('source', None)=='missing':
                    nmissing_ip += 1
                    if pcent.get('certified'):
                        nmissing_ip_cert += 1

            for pcdf in pcd_fields:
                self.copy_from_bq_table(self.pc_day_totals, pcent, username, pcdf)

        if not skip_modal_ip:
            self.log("--> modal_ip's number missing = %d" % nmissing_ip)
            if nmissing_ip_cert:
                self.log("==> WARNING: missing %d ip addresses for users with certified=True!" % nmissing_ip_cert)

    def compute_fourth_phase(self):
    
        # -----------------------------------------------------------------------------
        # person_course part 4: geoip (needs modal ip and maxmind geoip dataset)
        
        self.log("-"*20)
        self.log("Computing fourth phase based on modal_ip and geoip join in BigQuery")

        if self.skip_geoip:
            self.log("--> Skipping geoip")
            return

        # skip if no tracking logs available
        if not self.are_tracking_logs_available():
            self.log("--> Missing tracking logs dataset %s_logs, skipping fourth phase of person_course" % self.dataset)
            return

        self.load_pc_geoip()

        if self.pc_geoip is None:
            self.log("Skipping fourth phase - pc_geoip table is None")
            return

        pcd_fields = [['country', 'cc_by_ip'], 'latitude', 'longitude',
                      ['region_code', 'region'], 'subdivision', 'postalCode', 'continent',
                      ['un_region', 'un_major_region'],
                      ['econ_group', 'un_economic_group'],
                      ['developing_nation', 'un_developing_nation'],
                      ['special_region1', 'un_special_region']]

        for key, pcent in self.pctab.iteritems():
            username = pcent['username']

            for pcdf in pcd_fields:
                self.copy_from_bq_table(self.pc_geoip, pcent, username, pcdf)
            self.copy_from_bq_table(self.pc_geoip, pcent, username, 'countryLabel', mkutf=True)	# unicode
            self.copy_from_bq_table(self.pc_geoip, pcent, username, 'city', mkutf=True)		# unicode

    def compute_fifth_phase(self):
        '''
        Add more geoip information, based on extra_geoip and local maxmind geoip
        '''

        if self.skip_geoip:
            self.log("--> Skipping geoip")
            return

        import make_geoip_table

        try:
            gid = make_geoip_table.GeoIPData()
        except Exception as err:
            self.log("---> Skipping local geoip")
            return
        
        gid.load_geoip()

        def c2pc(field, gdata):
            pcent[field] = gdata[field]

        gfields = ['city', 'countryLabel', 'latitude', 'longitude',
                   'region', 'subdivision', 'postalCode', 'continent']
        # GeoIP Table does not have data for 'un_region', 'econ_group', 'developing_nation', 'special_region1' => These will be blank

        nnew = 0
        nmissing_geo = 0
        nmissing_ip = 0
        nmissing_ip_but_have_events = 0
        for key, pcent in self.pctab.iteritems():
            cc = pcent.get('cc_by_ip', None)
            if cc is not None:
                continue
            ip = pcent.get('ip', None)
            if ip is None:
                nmissing_ip += 1
                if pcent.get('nevents'):
                    nmissing_ip_but_have_events += 1
                continue
            gdat = gid.lookup_ip(ip)
            if gdat is None:
                nmissing_geo += 1
                continue
            pcent['cc_by_ip'] = gdat['country']
            for field in gfields:
                c2pc(field, gdat)
            pcent['city'] = pcent['city'].encode('utf8')
            nnew += 1
            if (nnew%100==0):
                sys.stdout.write('.')
                sys.stdout.flush()
        self.log("Done: %d new geoip entries added to person_course for %s" % (nnew, self.course_id))
        self.log("--> # missing_ip = %d, # missing_geo = %d, # missing_ip_but_have_events = %d" % (nmissing_ip, nmissing_geo, nmissing_ip_but_have_events))
        sys.stdout.flush()
        gid.write_geoip_table()

        
    def compute_sixth_phase(self):
        '''
        Add forum and course (staff) roles flags
        '''
        rfn = 'roles.csv'
        if not (self.cdir / rfn).exists():
            self.log("Skipping sixth phase (adding roles), no file %s" % rfn)
            return

        self.log("-"*20)
        self.log("Computing sixth phase based on %s" % rfn)
        
        roles = self.load_csv(rfn, 'user_id', keymap=int)

        fields = ["roles_isBetaTester","roles_isInstructor",
                  "roles_isStaff","forumRoles_isAdmin","forumRoles_isCommunityTA",
                  "forumRoles_isModerator","forumRoles_isStudent"]

        def mapfun(x):
            if x or x==0:
                return int(float(x))
            return None

        nroles = 0
        nmissing = 0
        missing_uids = []
        for key, pcent in self.pctab.iteritems():
            uid = int(pcent['user_id'])
            if not uid in roles:
                missing_uids.append(uid)
                nmissing += 1
                continue

            self.copy_fields(roles[uid], pcent, {x:x for x in fields}, mapfun=mapfun)
            nroles += 1

        if self.verbose and False:
            self.log("--> Err! missing roles information for uid=%s" % missing_uids)
        self.log("  Added roles information for %d users; missing roles for %d" % (nroles, nmissing))

    def output_table(self):
        '''
        output person_course table 
        '''
        
        fieldnames = self.the_dict_schema.keys()
        ofn = 'person_course.csv.gz'
        ofnj = 'person_course.json.gz'
        ofp = self.openfile(ofnj, 'w')
        ocsv = csv.DictWriter(self.openfile(ofn, 'w'), fieldnames=fieldnames)
        ocsv.writeheader()
        
        self.log("Writing output to %s and %s" % (ofn, ofnj))

        # write JSON first - it's safer
        cnt = 0
        for key, pcent in self.pctab.iteritems():
            cnt += 1
            check_schema(cnt, pcent, the_ds=self.the_dict_schema, coerce=True)
            ofp.write(json.dumps(pcent) + '\n')
        ofp.close()

        # now write CSV file (may have errors due to unicode)
        for key, pcent in self.pctab.iteritems():
            if 0:	# after switching to unicodecsv, don't do this
                try:
                    if 'countryLabel' in pcent:
                        if pcent['countryLabel'] == u'R\xe9union':
                            pcent['countryLabel'] = 'Reunion'
                        else:
                            #pcent['countryLabel'] = pcent['countryLabel'].decode('utf8').encode('utf8')
                            pcent['countryLabel'] = pcent['countryLabel'].encode('ascii', 'ignore')
                except Exception as err:
                    self.log("Error handling country code unicode row=%s" % pcent)
                    raise
            try:
                ocsv.writerow(pcent)
            except Exception as err:
                self.log("Error writing CSV output row=%s" % pcent)
                raise
        
    def upload_to_bigquery(self):
        '''
        upload person_course table to bigquery, via google cloud storage
        '''
        
        def upload_to_gs(fn):
            ofn = self.cdir / fn
            gsfn = self.gspath + '/'
            gsfnp = gsfn + fn			# full path to google storage data file
            cmd = 'gsutil cp %s %s' % (ofn, gsfn)
            self.log("Uploading to gse using %s" % cmd)
            os.system(cmd)
            return gsfnp

        gsfnp = upload_to_gs('person_course.json.gz')
        upload_to_gs('person_course.csv.gz')

        tableid = self.tableid
        bqutil.load_data_to_table(self.dataset, tableid, gsfnp, self.the_schema, wait=True, verbose=False)

        description = '\n'.join(self.logmsg)
        description += "Person course for %s with nchapters=%s, start=%s, end=%s\n" % (self.course_id,
                                                                                       getattr(self, 'nchapters', 'unknown'),
                                                                                       self.start_date,
                                                                                       self.end_date,
                                                                                       )
        description += "course SQL directory = %s\n" % self.course_dir
        description += "="*100
        description += "\nDone at %s" % datetime.datetime.now()
        bqutil.add_description_to_table(self.dataset, tableid, description, append=True)

    def load_nchapters(self):
        
        tablename = 'pc_nchapters'

        the_sql = '''
        select user_id, count(*) as nchapters from (
            SELECT student_id as user_id, module_id, count(*) as chapter_views
            FROM [{dataset}.studentmodule]
            # FROM [{dataset}.courseware_studentmodule]
            where module_type = "chapter"
            group by user_id, module_id
        )
        group by user_id
        order by user_id
        '''.format(**self.sql_parameters)

        # make sure the studentmodule table exists; if not, skip this
        tables = bqutil.get_list_of_table_ids(self.dataset)
        if not 'studentmodule' in tables:
            self.log("--> No studentmodule table for %s, skipping nchapters statistics" % self.course_id)
            setattr(self, tablename, {'data': [], 'data_by_key': {}})
            return

        self.log('doing nchapters, tables=%s' % tables)

        self.log("Loading %s from BigQuery" % tablename)
        self.pc_nchapters = bqutil.get_bq_table(self.dataset, tablename, the_sql, key={'name': 'user_id'},
                                                depends_on=[ '%s.studentmodule' % self.dataset ],
                                                force_query=self.force_recompute_from_logs, logger=self.log)


    def load_pc_day_totals(self):
        '''
        Compute a single table aggregating all the person_course_day table data, into a single place.
        This uses the new person_course_day table within the {course_id} dataset, if it exists.
        '''
        tables = bqutil.get_list_of_table_ids(self.dataset)
        
        table = 'person_course_day'
        if not table in tables:
            self.log("===> WARNING: computing pc_day_totals using obsolete *_pcday dataset; please create the person_course_day dataset for %s" % self.course_id)
            return self.obsolete_load_pc_day_totals()
        
        the_sql = '''
            select username, 
                "{course_id}" as course_id,
                count(*) as ndays_act,
                sum(nevents) as nevents,
                sum(nprogcheck) as nprogcheck,
                sum(nshow_answer) as nshow_answer,
                sum(nvideo) as nvideo,
                sum(nproblem_check) as nproblem_check,
                sum(nforum) as nforum,
                sum(ntranscript) as ntranscript,
                sum(nseq_goto) as nseq_goto,
                sum(nseek_video) as nseek_video,
                sum(npause_video) as npause_video,
                MAX(last_event) as last_event,
                AVG(avg_dt) as avg_dt,
                sqrt(sum(sdv_dt*sdv_dt * n_dt)/sum(n_dt)) as sdv_dt,
                MAX(max_dt) as max_dt,
                sum(n_dt) as n_dt,
                sum(sum_dt) as sum_dt
            from
                [{dataset}.person_course_day]
            group by username
            order by sum_dt desc
        '''.format(**self.sql_parameters)
        
        tablename = 'pc_day_totals'

        self.log("Loading %s from BigQuery" % tablename)
        setattr(self, tablename, bqutil.get_bq_table(self.dataset, tablename, the_sql, key={'name': 'username'},
                                                     depends_on=[ '%s.person_course_day' % self.dataset ],
                                                     force_query=self.force_recompute_from_logs, logger=self.log))


    def obsolete_load_pc_day_totals(self):
        '''
        This is an old procedure, which uses the old *_pcday dataset.  
        Compute a single table aggregating all the person_course_day table data, into a single place.
        '''
        
        the_sql = '''
            select username, 
                "{course_id}" as course_id,
                count(*) as ndays_act,
                sum(nevents) as nevents,
                sum(nprogcheck) as nprogcheck,
                sum(nshow_answer) as nshow_answer,
                sum(nvideo) as nvideo,
                sum(nproblem_check) as nproblem_check,
                sum(nforum) as nforum,
                sum(ntranscript) as ntranscript,
                sum(nseq_goto) as nseq_goto,
                sum(nseek_video) as nseek_video,
                sum(npause_video) as npause_video,
                AVG(avg_dt) as avg_dt,
                sqrt(sum(sdv_dt*sdv_dt * n_dt)/sum(n_dt)) as sdv_dt,
                MAX(max_dt) as max_dt,
                sum(n_dt) as n_dt,
                sum(sum_dt) as sum_dt
            from 
                (TABLE_DATE_RANGE( 
                      [{dataset_pcday}.pcday_],                                                                                                               
                      TIMESTAMP('{start_date}'), TIMESTAMP('{end_date}')))
            group by username
            order by sum_dt desc
        '''.format(**self.sql_parameters)
        
        tablename = 'pc_day_totals'

        self.log("Loading %s from BigQuery" % tablename)
        setattr(self, tablename, bqutil.get_bq_table(self.dataset, tablename, the_sql, key={'name': 'username'},
                                                     force_query=self.force_recompute_from_logs, logger=self.log))

    def load_pc_forum(self):
        '''
        Compute statistics about forum use by user.
        '''
        
        the_sql = '''
            SELECT author_id as user_id, 
                   count(*) as nforum,
                   sum(votes.count) as nvotes,
                   sum(case when pinned then 1 else 0 end) as npinned,
                   sum(case when endorsed then 1 else 0 end) as nendorsed,
                   sum(case when _type="CommentThread" then 1 else 0 end) as nthread,
                   sum(case when _type="Comment" then 1 else 0 end) as ncomment,
            FROM [{dataset}.forum] 
            group by user_id
            order by nthread desc
        '''.format(**self.sql_parameters)
        
        tablename = 'pc_forum'

        # make sure the forum table exists; if not, skip this
        tables = bqutil.get_list_of_table_ids(self.dataset)
        if not 'forum' in tables:
            self.log("--> No foum table for %s, skipping forum statistics" % self.course_id)
            setattr(self, tablename, None)
            return

        self.log("Loading %s from BigQuery" % tablename)
        setattr(self, tablename, bqutil.get_bq_table(self.dataset, tablename, the_sql, key={'name': 'user_id'},
                                                     depends_on=[ '%s.forum' % self.dataset ],
                                                     force_query=self.force_recompute_from_logs, logger=self.log))
        
    def load_last_event(self):
        
        the_sql = '''
        SELECT username, max(time) as last_event
            FROM (TABLE_DATE_RANGE(
                                   [{dataset_logs}.tracklog_], 
                                   TIMESTAMP('{start_date}'), TIMESTAMP('{end_date}')))
            where username != "" 
            group by username
        order by username
        '''.format(**self.sql_parameters)
        
        tablename = 'pc_last_event'

        self.log("Loading %s from BigQuery" % tablename)
        setattr(self, tablename, bqutil.get_bq_table(self.dataset, tablename, the_sql, key={'name': 'username'},
                                                     force_query=self.force_recompute_from_logs, logger=self.log))

    def ensure_all_daily_tracking_logs_loaded(self):
        '''
        Check to make sure all the needed *_logs.tracklog_* tables exist.
        '''
        return self.ensure_all_daily_tables_loaded('logs', 'tracklog')

    def ensure_all_pc_day_tables_loaded(self):
        '''
        Check to make sure all the needed *_pcday.pcday_* tables exist.
        '''
        return self.ensure_all_daily_tables_loaded('pcday', 'pcday')

    def ensure_all_daily_tables_loaded(self, dsuffix, tprefix):
        dataset = self.dataset + "_" + dsuffix
        tables_info = bqutil.get_tables(dataset)['tables']
        tables = [ x['tableReference']['tableId'] for x in tables_info ]
        
        def daterange(start, end):
            k = start
            dates = []
            while (k <= end):
                dates.append('%04d%02d%02d' % (k.year, k.month, k.day))
                k += datetime.timedelta(days=1)
            return dates

        def d2dt(date):
            return datetime.datetime.strptime(date, '%Y-%m-%d')

        for k in daterange(d2dt(self.start_date), d2dt(self.end_date)):
            tname = tprefix + '_' + str(k)
            if tname not in tables:
                msg = "Oops, missing needed table %s from database %s" % (tname, dataset)
                self.log(msg)
                self.tables = tables
                raise Exception(msg)
        return

    def obsolete_load_nevents(self):
        '''
        '''
        
        the_sql = '''
        SELECT username, count(*) as nevents
            FROM (TABLE_DATE_RANGE(
                                   [{dataset_logs}.tracklog_], 
                                   TIMESTAMP('{start_date}'), TIMESTAMP('{end_date}')))
            where username != "" 
            group by username
        order by username
        '''.format(**self.sql_parameters)
        
        tablename = 'pc_nevents'

        self.log("Loading %s from BigQuery" % tablename)
        setattr(self, tablename, bqutil.get_bq_table(self.dataset, tablename, the_sql, key={'name': 'username'},
                                                     force_query=self.force_recompute_from_logs, logger=self.log))

    def load_modal_ip(self):
        '''
        Compute the modal IP (the IP address most used by the learner), based on the tracking logs.
        
        Actually, this is done from several different data sources.

        If pcday_ip_counts exists, then use that to create a modal_ips table, then use that. 

        If the modal_ips table for this course exists, then use that.

        Else use the (to be deprecated) person-course-day pcday_* tables.
        '''
        tables = bqutil.get_list_of_table_ids(self.dataset)
        
        table = 'pcday_ip_counts'
        if not table in tables:
            return self.load_modal_ip_from_old_multiple_person_course_day_tables()
        
        # pcday_ip_counts exists!

        self.make_course_specific_modal_ip_table()	# make course-specific modal ip table
        
        use_each = ""
        # check to see if the course_modal_ip table is too large; if so, must do JOIN EACH
        cmi_size = bqutil.get_bq_table_size_bytes(self.dataset, "course_modal_ip")        
        if cmi_size > 5e6:
            use_each = "EACH"

        # does the global_pcday_ip_counts table exist in the 'courses' dataset?

        depends_on = [ '%s.course_modal_ip' % self.dataset, '%s.user_info_combo' % self.dataset ]

        try:
            tinfo = bqutil.get_bq_table_info('courses', 'global_modal_ip')            
            has_global_modal_ip = (tinfo is not None)
        except Exception as err:
            self.log("--> looking for courses.global_modal_ip, error=%s" % str(err))
            has_global_modal_ip = False

        if (not has_global_modal_ip):
            self.log("---> WARNING: courses.global_modal_ip is missing, so global modal IP's won't be included!")

            the_sql = """
              SELECT uic.username as username, 
                     mip.modal_ip as course_modal_ip,
                     mip.ip_count as course_ip_count,
                     "" as global_modal_ip,
                     0 as global_ip_count,

                     mip.modal_ip as modal_ip,
                     CASE when mip.modal_ip !="" then 'course' else 'missing' end as source,
              FROM [{dataset}.user_info_combo] as uic
              LEFT JOIN {each} [{dataset}.course_modal_ip] as mip
              ON uic.username = mip.username
              """.format(each=use_each, **self.sql_parameters)
        else:
            # make modal ip table which includes global modal ip's for those missing from course-specific modal ip table
            # do only usernames in user_info_combo table
            the_sql = """
                  SELECT uic.username as username, 
                         mip.course_modal_ip as course_modal_ip,
                         mip.course_ip_count as course_ip_count,
                         mip.global_modal_ip as global_modal_ip,
                         mip.global_ip_count as global_ip_count,

                         # logic to take the course ip when available, else the global ip
                         CASE when course_modal_ip !="" then course_modal_ip else global_modal_ip end as modal_ip,
                         CASE when course_modal_ip !="" then 'course' 
                              when global_modal_ip !="" then 'global'
                              else 'missing' end as source,
                  FROM [{dataset}.user_info_combo] as uic
                  LEFT JOIN EACH ( 

                     # what we really want is a full outer join, and bigquery does not have that.
                     # so take the union of two left joins

                     SELECT * FROM 
                       (
                         #  first, get cases where both course and global are available
                         SELECT (case when cmi.username != "" then cmi.username else gmi.username end) as username,
                                cmi.modal_ip as course_modal_ip,
                                cmi.ip_count as course_ip_count,
                                gmi.modal_ip as global_modal_ip,
                                gmi.ip_count as global_ip_count,
                         FROM [courses.global_modal_ip] as gmi
                         LEFT JOIN {each} [{dataset}.course_modal_ip] as cmi
                         ON cmi.username = gmi.username
                         order by username
                       ),
                       #  now get cases where course is available but not global
                       (
                         SELECT (case when cmi.username != "" then cmi.username else gmi.username end) as username,
                                cmi.modal_ip as course_modal_ip,
                                cmi.ip_count as course_ip_count,
                                gmi.modal_ip as global_modal_ip,
                                gmi.ip_count as global_ip_count,
                         FROM
                                [{dataset}.course_modal_ip] as cmi
                         LEFT JOIN EACH
                                [courses.global_modal_ip] as gmi
                         ON cmi.username = gmi.username
                         WHERE gmi.username is NULL
                         order by username
                       )
                  ) as mip
                  ON uic.username = mip.username
                  order by username
              """.format(each=use_each, **self.sql_parameters)
            depends_on.append('courses.global_modal_ip')

        tablename = 'pc_modal_ip'

        self.log("Loading %s from BigQuery" % tablename)
        setattr(self, tablename, bqutil.get_bq_table(self.dataset, tablename, the_sql, key={'name': 'username'},
                                                     depends_on=depends_on,
                                                     newer_than=datetime.datetime(2015, 1, 18, 0, 0),
                                                     force_query=self.force_recompute_from_logs, logger=self.log))


    def make_course_specific_modal_ip_table(self):
        '''
        Make a course-specific modal IP table, based on local pcday_ip_counts table
        '''
        SQL = """
              SELECT username, IP as modal_ip, ip_count, n_different_ip,
              FROM
                  ( SELECT username, ip, ip_count,
                          RANK() over (partition by username order by ip_count ASC) n_different_ip,
                          RANK() over (partition by username order by ip_count DESC) rank,
                    from ( select username, ip, sum(ipcount) as ip_count
                           from [{dataset}.pcday_ip_counts] 
                           GROUP BY username, ip
                    )
                  )
                  where rank=1
                  order by username
        """.format(**self.sql_parameters)

        tablename = 'course_modal_ip'

        self.log("Loading %s from BigQuery" % tablename)
        setattr(self, tablename, bqutil.get_bq_table(self.dataset, tablename, SQL, key={'name': 'username'},
                                                     force_query=self.force_recompute_from_logs, 
                                                     depends_on=[ '%s.pcday_ip_counts' % self.dataset ],
                                                     logger=self.log))

    def load_modal_ip_from_old_multiple_person_course_day_tables(self):
        '''
        Compute modal IP the old fashioned way, from the pcday_* tables
        '''
        the_sql = '''
        SELECT username, IP as modal_ip, ip_count from
        ( SELECT username, IP, ip_count, 
            RANK() over (partition by username order by ip_count DESC) rank,
          from
          ( SELECT username, IP, count(IP) as ip_count
            FROM (TABLE_DATE_RANGE(
                                   [{dataset_logs}.tracklog_], 
                                   TIMESTAMP('{start_date}'), TIMESTAMP('{end_date}')))
            where username != "" 
            group by username, IP
          )
        )
        where rank=1
        order by username, rank
        '''.format(**self.sql_parameters)
        
        tablename = 'pc_modal_ip'

        self.log("Loading %s from BigQuery" % tablename)
        setattr(self, tablename, bqutil.get_bq_table(self.dataset, tablename, the_sql, key={'name': 'username'},
                                                     force_query=self.force_recompute_from_logs, logger=self.log))

    def load_pc_geoip(self):
        '''
        geoip information from modal_ip, using bigquery join with maxmind public geoip dataset
        http://googlecloudplatform.blogspot.com/2014/03/geoip-geolocation-with-google-bigquery.html        

        The public table is fh-bigquery:geocode.geolite_city_bq_b2b

        If a private version is available use that instead.
        '''

        try:
            private_geoip_tinfo = bqutil.get_bq_table_info('geocode', 'GeoIPCityCountry')
            assert private_geoip_tinfo is not None
        except Exception as err:
            private_geoip_tinfo = None

        use_private_geoip = False
        geoip_table = "fh-bigquery:geocode.geolite_city_bq_b2b"
        sql_extra_geoip = """
                  "" as region_code,
                  "" as subdivision,
                  postalCode, 
                  "" as continent,
                  "" as un_region,
                  "" as econ_group,
                  "" as developing_nation,
                  "" as special_region1,
        """

        if private_geoip_tinfo:
            use_private_geoip = True
            geoip_table = "geocode.GeoIPCityCountry"
            sql_extra_geoip = """
                  region_code,
                  subdivision,
                  postalCode, 
                  continent,
                  un_region,
                  econ_group,
                  developing_nation,
                  special_region1,
            """
        self.log("    Using %s for geoip information" % geoip_table)

        the_sql = '''
            SELECT username, country, city, countryLabel, latitude, longitude,
                   # region_code, subdivision, postalCode, continent, un_region, econ_group, developing_nation, special_region1
                   {sql_extra_geoip}
            FROM (
             SELECT
               username,
               INTEGER(PARSE_IP(modal_ip)) AS clientIpNum,
               INTEGER(PARSE_IP(modal_ip)/(256*256)) AS classB
             FROM
               [{dataset}.pc_modal_ip]
             WHERE modal_ip IS NOT NULL
               ) AS a
            JOIN EACH [{geoip_table}] AS b
            ON a.classB = b.classB
            WHERE a.clientIpNum BETWEEN b.startIpNum AND b.endIpNum
            AND city != ''
            ORDER BY username
        '''.format(geoip_table=geoip_table, sql_extra_geoip=sql_extra_geoip, **self.sql_parameters)
        
        tablename = 'pc_geoip'

        self.log("Loading %s from BigQuery" % tablename)
        setattr(self, tablename, bqutil.get_bq_table(self.dataset, tablename, the_sql, key={'name': 'username'},
                                                     depends_on=[ '%s.pc_modal_ip' % self.dataset ],
                                                     force_query=self.force_recompute_from_logs, logger=self.log))

    def load_cwsm(self):
        self.cwsm = self.load_csv('studentmodule.csv', 'student_id', fields=['module_id', 'module_type'], keymap=int)

    def make_all(self):
        steps = [
            self.compute_first_phase,
            self.compute_second_phase,
            self.compute_third_phase,
            self.compute_fourth_phase,
            self.compute_fifth_phase,
            self.compute_sixth_phase,	# roles
            ]
        if self.nskip==0:
            for step in steps:
                step()
        else:
            self.log("Running subset of steps, nskip=%s" % self.nskip)
            self.reload_table()
            for step in steps:
                if self.nskip <= 0:
                    step()
                else:
                    self.log("Skipping %s" % repr(step))
                self.nskip -= 1

        self.output_table()
        self.upload_to_bigquery()

    def nightly_update(self):
        '''
        Update person course assuming just tracking logs have changed; start from existing
        person_course table, and don't change the number of rows.  Just update activity counts
        (i.e. the third phase).  Skip computation of modal IP (expensive, won't change on
        a daily basis).
        '''
        self.log("PersonCourse doing nightly update, just activity metrics from tracking logs")
        self.reload_table()
        self.compute_third_phase(skip_modal_ip=True, skip_last_event=True)
        self.output_table()
        self.upload_to_bigquery()
        
    def redo_second_phase(self):
        self.log("PersonCourse just re-doing second phase")
        self.reload_table()
        self.compute_second_phase()
        self.output_table()
        self.upload_to_bigquery()
        
    def redo_extra_geoip(self):
        self.log("PersonCourse just re-doing extra geoip (fifth phase)")
        self.reload_table()
        self.compute_fifth_phase()
        self.output_table()
        self.upload_to_bigquery()
        
#-----------------------------------------------------------------------------

def make_person_course(course_id, basedir="X-Year-2-data-sql", datedir="2013-09-21", options='', 
                       gsbucket="gs://x-data",
                       start="2012-09-05",
                       end="2013-09-21",
                       force_recompute=False,
                       nskip=0,
                       skip_geoip=False,
                       use_dataset_latest=False,
                       skip_if_table_exists=False,
                       just_do_nightly=False,
                       just_do_geoip=False,
                       ):
    '''
    make one person course dataset
    '''
    print "-"*77
    print "Processing person course for %s (start %s)" % (course_id, datetime.datetime.now())
    force_recompute = force_recompute or ('force_recompute' in options)
    if force_recompute:
        print "--> Note: Forcing re-querying of person_day results from tracking logs!!! Can be $$$ expensive!!!"
        sys.stdout.flush()
    pc = PersonCourse(course_id, course_dir_root=basedir, course_dir_date=datedir,
                      gsbucket=gsbucket,
                      start_date=start, 
                      end_date=end,
                      force_recompute_from_logs=force_recompute,
                      nskip=nskip,
                      skip_geoip=skip_geoip,
                      use_dataset_latest=use_dataset_latest,
                      )

    if skip_if_table_exists:
        # don't run person_course if the dataset table for this course_id already exists
        if pc.tableid in bqutil.get_list_of_table_ids(pc.dataset):
            print "--> %s.%s already exists, skipping" % (pc.dataset, pc.tableid)
            sys.stdout.flush()
            return

    redo2 = 'redo2' in options
    if redo2:
        pc.redo_second_phase()
    elif just_do_geoip:
        pc.redo_extra_geoip()
    elif just_do_nightly:
        pc.nightly_update()
    else:
        pc.make_all()
    print "Done processing person course for %s (end %s)" % (course_id, datetime.datetime.now())
    print "-"*77
        
#-----------------------------------------------------------------------------

def make_pc(*args):
    pc = PersonCourse(**args)
    pc.make_all()
    return pc

def make_pc3(course_id, cdir):
    pc = PersonCourse(course_id, cdir)
    pc.reload_table()
    pc.compute_third_phase()
    pc.output_table()
    pc.upload_to_bigquery()
    return pc

