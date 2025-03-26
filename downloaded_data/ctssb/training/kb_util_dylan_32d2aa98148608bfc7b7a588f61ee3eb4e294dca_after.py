#BEGIN_HEADER
import os
import sys
import shutil
import hashlib
import subprocess
import requests
import re
import traceback
import uuid
from datetime import datetime
from pprint import pprint, pformat
import numpy as np
import gzip

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from Bio.Alphabet import generic_protein
from biokbase.workspace.client import Workspace as workspaceService
from requests_toolbelt import MultipartEncoder  # added
from biokbase.AbstractHandle.Client import AbstractHandle as HandleService  # added

#END_HEADER


class kb_util_dylan:
    '''
    Module Name:
    kb_util_dylan

    Module Description:
    ** A KBase module: kb_util_dylan
**
** This module contains basic utilities
    '''

    ######## WARNING FOR GEVENT USERS #######
    # Since asynchronous IO can lead to methods - even the same method -
    # interrupting each other, you must be *very* careful when using global
    # state. A method could easily clobber the state set by another while
    # the latter method is running.
    #########################################
    #BEGIN_CLASS_HEADER
    workspaceURL = None
    shockURL = None
    handleURL = None

    # target is a list for collecting log messages
    def log(self, target, message):
        # we should do something better here...
        if target is not None:
            target.append(message)
        print(message)
        sys.stdout.flush()

    def get_single_end_read_library(self, ws_data, ws_info, forward):
        pass

    def get_feature_set_seqs(self, ws_data, ws_info):
        pass

    def get_genome_feature_seqs(self, ws_data, ws_info):
        pass

    def get_genome_set_feature_seqs(self, ws_data, ws_info):
        pass

    # config contains contents of config file in a hash or None if it couldn't
    # be found
    def __init__(self, config):
        #BEGIN_CONSTRUCTOR
        self.workspaceURL = config['workspace-url']
        self.shockURL = config['shock-url']
        self.handleURL = config['handle-service-url']
        self.scratch = os.path.abspath(config['scratch'])
        # HACK!! temporary hack for issue where megahit fails on mac because of silent named pipe error
        #self.host_scratch = self.scratch
        self.scratch = os.path.join('/kb','module','local_scratch')
        # end hack
        if not os.path.exists(self.scratch):
            os.makedirs(self.scratch)

        #END_CONSTRUCTOR
        pass


    # Helper script borrowed from the transform service, logger removed
    #
    def upload_file_to_shock(self,
                             console,  # DEBUG
                             shock_service_url = None,
                             filePath = None,
                             ssl_verify = True,
                             token = None):
        """
        Use HTTP multi-part POST to save a file to a SHOCK instance.
        """
        self.log(console,"UPLOADING FILE "+filePath+" TO SHOCK")

        if token is None:
            raise Exception("Authentication token required!")

        #build the header
        header = dict()
        header["Authorization"] = "Oauth {0}".format(token)
        if filePath is None:
            raise Exception("No file given for upload to SHOCK!")

        dataFile = open(os.path.abspath(filePath), 'rb')
        m = MultipartEncoder(fields={'upload': (os.path.split(filePath)[-1], dataFile)})
        header['Content-Type'] = m.content_type

        #logger.info("Sending {0} to {1}".format(filePath,shock_service_url))
        try:
            response = requests.post(shock_service_url + "/node", headers=header, data=m, allow_redirects=True, verify=ssl_verify)
            dataFile.close()
        except:
            dataFile.close()
            raise
        if not response.ok:
            response.raise_for_status()
        result = response.json()
        if result['error']:
            raise Exception(result['error'][0])
        else:
            return result["data"]


    def upload_SingleEndLibrary_to_shock_and_ws (self,
                                                 ctx,
                                                 console,  # DEBUG
                                                 workspace_name,
                                                 obj_name,
                                                 file_path,
                                                 provenance,
                                                 sequencing_tech):

        self.log(console,'UPLOADING FILE '+file_path+' TO '+workspace_name+'/'+obj_name)

        # 1) upload files to shock
        token = ctx['token']
        forward_shock_file = self.upload_file_to_shock(
            console,  # DEBUG
            shock_service_url = self.shockURL,
            filePath = file_path,
            token = token
            )
        #pprint(forward_shock_file)
        self.log(console,'SHOCK UPLOAD DONE')

        # 2) create handle
        self.log(console,'GETTING HANDLE')
        hs = HandleService(url=self.handleURL, token=token)
        forward_handle = hs.persist_handle({
                                        'id' : forward_shock_file['id'], 
                                        'type' : 'shock',
                                        'url' : self.shockURL,
                                        'file_name': forward_shock_file['file']['name'],
                                        'remote_md5': forward_shock_file['file']['checksum']['md5']})

        
        # 3) save to WS
        self.log(console,'SAVING TO WORKSPACE')
        single_end_library = {
            'lib': {
                'file': {
                    'hid':forward_handle,
                    'file_name': forward_shock_file['file']['name'],
                    'id': forward_shock_file['id'],
                    'url': self.shockURL,
                    'type':'shock',
                    'remote_md5':forward_shock_file['file']['checksum']['md5']
                },
                'encoding':'UTF8',
                'type':'fasta',
                'size':forward_shock_file['file']['size']
            },
            'sequencing_tech':sequencing_tech
        }
        self.log(console,'GETTING WORKSPACE SERVICE OBJECT')
        ws = workspaceService(self.workspaceURL, token=ctx['token'])
        self.log(console,'SAVE OPERATION...')
        new_obj_info = ws.save_objects({
                        'workspace':workspace_name,
                        'objects':[
                            {
                                'type':'KBaseFile.SingleEndLibrary',
                                'data':single_end_library,
                                'name':obj_name,
                                'meta':{},
                                'provenance':provenance
                            }]
                        })
        self.log(console,'SAVED TO WORKSPACE')

        return new_obj_info[0]

    #END_CLASS_HEADER

    # config contains contents of config file in a hash or None if it couldn't
    # be found
    def __init__(self, config):
        #BEGIN_CONSTRUCTOR
        self.workspaceURL = config['workspace-url']
        self.shockURL = config['shock-url']
        self.handleURL = config['handle-service-url']
        self.scratch = os.path.abspath(config['scratch'])
        # HACK!! temporary hack for issue where megahit fails on mac because of silent named pipe error
        #self.host_scratch = self.scratch
        self.scratch = os.path.join('/kb','module','local_scratch')
        # end hack
        if not os.path.exists(self.scratch):
            os.makedirs(self.scratch)

        #END_CONSTRUCTOR
        pass

    def KButil_Insert_SingleEndLibrary(self, ctx, params):
        # ctx is the context object
        # return variables are: returnVal
        #BEGIN KButil_Insert_SingleEndLibrary
        console = []
        self.log(console,'Running KButil_Insert_SingleEndLibrary with params=')
        self.log(console, "\n"+pformat(params))
        report = ''
#        report = 'Running KButil_Insert_SingleEndLibrary with params='
#        report += "\n"+pformat(params)  # DEBUG


        #### do some basic checks
        #
        if 'workspace_name' not in params:
            raise ValueError('workspace_name parameter is required')
        if 'input_sequence' not in params:
            raise ValueError('input_sequence parameter is required')
        if 'output_name' not in params:
            raise ValueError('output_name parameter is required')


        #### Create the file to upload
        ##
        input_file_name = params['output_name']
        forward_reads_file_path = os.path.join(self.scratch,input_file_name)
        forward_reads_file_handle = open(forward_reads_file_path, 'w', 0)
        self.log(console, 'writing query reads file: '+str(forward_reads_file_path))

        seq_cnt = 0
        fastq_format = False
        input_sequence_buf = params['input_sequence']
        if input_sequence_buf.startswith('@'):
            fastq_format = True
#        self.log(console,"INPUT_SEQ BEFORE: '''\n"+input_sequence_buf+"\n'''")  # DEBUG
        input_sequence_buf = re.sub ('&apos;', "'", input_sequence_buf)
        input_sequence_buf = re.sub ('&quot;', '"', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#39;',  "'", input_sequence_buf)
#        input_sequence_buf = re.sub ('&#34;',  '"', input_sequence_buf)
#        input_sequence_buf = re.sub ('&lt;;',  '<', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#60;',  '<', input_sequence_buf)
#        input_sequence_buf = re.sub ('&gt;',   '>', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#62;',  '>', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#36;',  '$', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#37;',  '%', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#47;',  '/', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#63;',  '?', input_sequence_buf)
##        input_sequence_buf = re.sub ('&#92;',  chr(92), input_sequence_buf)  # FIX LATER
#        input_sequence_buf = re.sub ('&#96;',  '`', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#124;', '|', input_sequence_buf)
#        input_sequence_buf = re.sub ('&amp;', '&', input_sequence_buf)
#        input_sequence_buf = re.sub ('&#38;', '&', input_sequence_buf)
#        self.log(console,"INPUT_SEQ AFTER: '''\n"+input_sequence_buf+"\n'''")  # DEBUG

        DNA_pattern = re.compile("^[acgtuACGTU ]+$")
        space_pattern = re.compile("^[ \t]*$")
        split_input_sequence_buf = input_sequence_buf.split("\n")

        # no header rows, just sequence
        if not input_sequence_buf.startswith('>') and not input_sequence_buf.startswith('@'):
            seq_cnt = 1
            forward_reads_file_handle.write('>'+params['output_name']+"\n")
            for line in split_input_sequence_buf:
                if not space_pattern.match(line):
                    line = re.sub (" ","",line)
                    line = re.sub ("\t","",line)
                    if not DNA_pattern.match(line):
                        self.log(console,"BAD record:\n"+line)
                        raise ValueError ("BAD record:\n"+line+"\n")
                    forward_reads_file_handle.write(line.lower()+"\n")

        else:
            # format checks
            for i,line in enumerate(split_input_sequence_buf):
                if line.startswith('>') or line.startswith('@'):
                    seq_cnt += 1
                    if not DNA_pattern.match(split_input_sequence_buf[i+1]):
                        if fastq_format:
                            bad_record = "\n".join([split_input_sequence_buf[i],
                                                    split_input_sequence_buf[i+1],
                                                    split_input_sequence_buf[i+2],
                                                    split_input_sequence_buf[i+3]])
                        else:
                            bad_record = "\n".join([split_input_sequence_buf[i],
                                                    split_input_sequence_buf[i+1]])
                        self.log(console,"BAD record:\n"+bad_record)
                        raise ValueError ("BAD record:\n"+bad_record+"\n")
                    if fastq_format and line.startswith('@'):
                        format_ok = True
                        seq_len = len(split_input_sequence_buf[i+1])
                        if not seq_len > 0:
                            format_ok = False
                        if not split_input_sequence_buf[i+2].startswith('+'):
                            format_ok = False
                        if not seq_len == len(split_input_sequence_buf[i+3]):
                            format_ok = False
                        if not format_ok:
                            bad_record = "\n".join([split_input_sequence_buf[i],
                                                    split_input_sequence_buf[i+1],
                                                    split_input_sequence_buf[i+2],
                                                    split_input_sequence_buf[i+3]])
                            self.log(console,"BAD record:\n"+bad_record)
                            raise ValueError ("BAD record:\n"+bad_record+"\n")


            # write that sucker, removing spaces
            #
            #forward_reads_file_handle.write(input_sequence_buf)        input_sequence_buf = re.sub ('&quot;', '"', input_sequence_buf)
            for i,line in enumerate(split_input_sequence_buf):
                if line.startswith('>'):
                    record_buf = []
                    record_buf.append(line)
                    for j in range(i+1,len(split_input_sequence_buf)):
                        if split_input_sequence_buf[j].startswith('>'):
                            break
                        seq_line = re.sub (" ","",split_input_sequence_buf[j])
                        seq_line = re.sub ("\t","",seq_line)
                        seq_line = seq_line.lower()
                        record_buf.append(seq_line)
                    record = "\n".join(record_buf)+"\n"
                    forward_reads_file_handle.write(record)
                elif line.startswith('@'):
                    seq_line = re.sub (" ","",split_input_sequence_buf[i+1])
                    seq_line = re.sub ("\t","",seq_line)
                    seq_line = seq_line.lower()
                    qual_line = re.sub (" ","",split_input_sequence_buf[i+3])
                    qual_line = re.sub ("\t","",qual_line)
                    record = "\n".join([line, seq_line, split_input_sequence_buf[i+2], qual_line])+"\n"
                    forward_reads_file_handle.write(record)

        forward_reads_file_handle.close()


        # load the method provenance from the context object
        #
        self.log(console,"SETTING PROVENANCE")  # DEBUG
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        # add additional info to provenance here, in this case the input data object reference
        provenance[0]['input_ws_objects'] = []
        provenance[0]['service'] = 'kb_util_dylan'
        provenance[0]['method'] = 'KButil_Insert_SingleEndLibrary'


        # Upload results
        #
        self.log(console,"UPLOADING RESULTS")  # DEBUG

        sequencing_tech = 'N/A'
        self.upload_SingleEndLibrary_to_shock_and_ws (ctx,
                                                      console,  # DEBUG
                                                      params['workspace_name'],
                                                      params['output_name'],
                                                      forward_reads_file_path,
                                                      provenance,
                                                      sequencing_tech
                                                      )

        # build output report object
        #
        self.log(console,"BUILDING REPORT")  # DEBUG
        report += 'sequences in library:  '+str(seq_cnt)+"\n"

        reportObj = {
            'objects_created':[{'ref':params['workspace_name']+'/'+params['output_name'], 'description':'KButil_Insert_SingleEndLibrary'}],
            'text_message':report
        }

        reportName = 'kbutil_insert_singleendlibrary_report_'+str(hex(uuid.getnode()))
        ws = workspaceService(self.workspaceURL, token=ctx['token'])
        report_obj_info = ws.save_objects({
#                'id':info[6],
                'workspace':params['workspace_name'],
                'objects':[
                    {
                        'type':'KBaseReport.Report',
                        'data':reportObj,
                        'name':reportName,
                        'meta':{},
                        'hidden':1,
                        'provenance':provenance
                    }
                ]
            })[0]

        self.log(console,"BUILDING RETURN OBJECT")
#        returnVal = { 'output_report_name': reportName,
#                      'output_report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
#                      'output_filtered_ref': params['workspace_name']+'/'+params['output_filtered_name']
#                      }
        returnVal = { 'report_name': reportName,
                      'report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
                      }
        self.log(console,"KButil_Insert_SingleEndLibrary DONE")

        #END KButil_Insert_SingleEndLibrary

        # At some point might do deeper type checking...
        if not isinstance(returnVal, dict):
            raise ValueError('Method KButil_Insert_SingleEndLibrary return value ' +
                             'returnVal is not type dict as required.')
        # return the results
        return [returnVal]

    def KButil_FASTQ_to_FASTA(self, ctx, params):
        # ctx is the context object
        # return variables are: returnVal
        #BEGIN KButil_FASTQ_to_FASTA
        console = []
        self.log(console,'Running KButil_FASTQ_to_FASTA with params=')
        self.log(console, "\n"+pformat(params))
        report = ''
#        report = 'Running KButil_FASTQ_to_FASTA with params='
#        report += "\n"+pformat(params)


        #### do some basic checks
        #
        if 'workspace_name' not in params:
            raise ValueError('workspace_name parameter is required')
        if 'input_name' not in params:
            raise ValueError('input_name parameter is required')
        if 'output_name' not in params:
            raise ValueError('output_name parameter is required')


        # Obtain the input object
        #
        forward_reads_file_compression = None
        sequencing_tech = 'N/A'
        try:
            ws = workspaceService(self.workspaceURL, token=ctx['token'])
            objects = ws.get_objects([{'ref': params['workspace_name']+'/'+params['input_name']}])
            data = objects[0]['data']
            info = objects[0]['info']
            # Object Info Contents
            # absolute ref = info[6] + '/' + info[0] + '/' + info[4]
            # 0 - obj_id objid
            # 1 - obj_name name
            # 2 - type_string type
            # 3 - timestamp save_date
            # 4 - int version
            # 5 - username saved_by
            # 6 - ws_id wsid
            # 7 - ws_name workspace
            # 8 - string chsum
            # 9 - int size 
            # 10 - usermeta meta
            type_name = info[2].split('.')[1].split('-')[0]

            if type_name == 'SingleEndLibrary':
                type_namespace = info[2].split('.')[0]
                if type_namespace == 'KBaseAssembly':
                    file_name = data['handle']['file_name']
                elif type_namespace == 'KBaseFile':
                    file_name = data['lib']['file']['file_name']
                else:
                    raise ValueError('bad data type namespace: '+type_namespace)
                #self.log(console, 'INPUT_FILENAME: '+file_name)  # DEBUG
                if file_name[-3:] == ".gz":
                    forward_reads_file_compression = 'gz'
                if 'sequencing_tech' in data:
                    sequencing_tech = data['sequencing_tech']

        except Exception as e:
            raise ValueError('Unable to fetch input_name object from workspace: ' + str(e))
            #to get the full stack trace: traceback.format_exc()
        
        # pull data from SHOCK
        #
        try:
            if 'lib' in data:
                forward_reads = data['lib']['file']
            elif 'handle' in data:
                forward_reads = data['handle']
            else:
                self.log(console,"bad structure for 'forward_reads'")
                raise ValueError("bad structure for 'forward_reads'")

            ### NOTE: this section is what could be replaced by the transform services
            forward_reads_file_path = os.path.join(self.scratch,forward_reads['file_name'])
            forward_reads_file_handle = open(forward_reads_file_path, 'w', 0)
            self.log(console, 'downloading reads file: '+str(forward_reads_file_path))
            headers = {'Authorization': 'OAuth '+ctx['token']}
            r = requests.get(forward_reads['url']+'/node/'+forward_reads['id']+'?download', stream=True, headers=headers)
            for chunk in r.iter_content(1024):
                forward_reads_file_handle.write(chunk)
            forward_reads_file_handle.close();
            self.log(console, 'done')
            ### END NOTE
        except Exception as e:
            print(traceback.format_exc())
            raise ValueError('Unable to download single-end read library files: ' + str(e))


        #### Create the file to upload
        ##
        output_file_name   = params['output_name']+'.fna'
        output_file_path  = os.path.join(self.scratch,output_file_name)
        input_file_handle  = open(forward_reads_file_path, 'r', -1)
        output_file_handle = open(output_file_path, 'w', -1)
        self.log(console, 'PROCESSING reads file: '+str(forward_reads_file_path))

        seq_cnt = 0
        header = None
        last_header = None
        last_seq_buf = None
        last_line_was_header = False
        for line in input_file_handle:
            if line.startswith('@'):
                seq_cnt += 1
                header = line[1:]
                if last_header != None:
                    output_file_handle.write('>'+last_header)
                    output_file_handle.write(last_seq_buf)
                last_seq_buf = None
                last_header = header
                last_line_was_header = True
            elif last_line_was_header:
                last_seq_buf = line
                last_line_was_header = False
            else:
                continue
        if last_header != None:
            output_file_handle.write('>'+last_header)
            output_file_handle.write(last_seq_buf)

        input_file_handle.close()
        output_file_handle.close()
        

        # load the method provenance from the context object
        #
        self.log(console,"SETTING PROVENANCE")  # DEBUG
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        # add additional info to provenance here, in this case the input data object reference
        provenance[0]['input_ws_objects'] = []
        provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_name'])
        provenance[0]['service'] = 'kb_util_dylan'
        provenance[0]['method'] = 'KButil_FASTQ_to_FASTA'


        # Upload results
        #
        self.log(console,"UPLOADING RESULTS")  # DEBUG

        self.upload_SingleEndLibrary_to_shock_and_ws (ctx,
                                                      console,  # DEBUG
                                                      params['workspace_name'],
                                                      params['output_name'],
                                                      output_file_path,
                                                      provenance,
                                                      sequencing_tech
                                                      )

        # build output report object
        #
        self.log(console,"BUILDING REPORT")  # DEBUG
        report += 'sequences in library:  '+str(seq_cnt)+"\n"

        reportObj = {
            'objects_created':[{'ref':params['workspace_name']+'/'+params['output_name'], 'description':'KButil_FASTQ_to_FASTA'}],
            'text_message':report
        }

        reportName = 'kbutil_fastq_to_fasta_report_'+str(hex(uuid.getnode()))
        ws = workspaceService(self.workspaceURL, token=ctx['token'])
        report_obj_info = ws.save_objects({
#                'id':info[6],
                'workspace':params['workspace_name'],
                'objects':[
                    {
                        'type':'KBaseReport.Report',
                        'data':reportObj,
                        'name':reportName,
                        'meta':{},
                        'hidden':1,
                        'provenance':provenance
                    }
                ]
            })[0]

        self.log(console,"BUILDING RETURN OBJECT")
#        returnVal = { 'output_report_name': reportName,
#                      'output_report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
#                      'output_filtered_ref': params['workspace_name']+'/'+params['output_filtered_name']
#                      }
        returnVal = { 'report_name': reportName,
                      'report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
                      }
        self.log(console,"KButil_FASTQ_to_FASTA DONE")

        #END KButil_FASTQ_to_FASTA

        # At some point might do deeper type checking...
        if not isinstance(returnVal, dict):
            raise ValueError('Method KButil_FASTQ_to_FASTA return value ' +
                             'returnVal is not type dict as required.')
        # return the results
        return [returnVal]

    def KButil_Merge_FeatureSet_Collection(self, ctx, params):
        # ctx is the context object
        # return variables are: returnVal
        #BEGIN KButil_Merge_FeatureSet_Collection
        console = []
        self.log(console,'Running KButil_Merge_FeatureSet_Collection with params=')
        self.log(console, "\n"+pformat(params))
        report = ''
#        report = 'Running KButil_FASTQ_to_FASTA with params='
#        report += "\n"+pformat(params)


        #### do some basic checks
        #
        if 'workspace_name' not in params:
            raise ValueError('workspace_name parameter is required')
        if 'desc' not in params:
            raise ValueError('desc parameter is required')
        if 'input_names' not in params:
            raise ValueError('input_names parameter is required')
        if 'output_name' not in params:
            raise ValueError('output_name parameter is required')


        # Build FeatureSet
        #
        element_ordering = []
        elements = {}
        featureSet_seen = dict()
        for featureSet_name in params['input_names']:
            if not featureSet_name in featureSet_seen.keys():
                featureSet_seen[featureSet_name] = 1
            else:
                raise ValueError ("repeat featureSet_name: '"+featureSet_name+"'")

            try:
                ws = workspaceService(self.workspaceURL, token=ctx['token'])
                objects = ws.get_objects([{'ref': params['workspace_name']+'/'+featureSet_name}])
                data = objects[0]['data']
                info = objects[0]['info']
                # Object Info Contents
                # absolute ref = info[6] + '/' + info[0] + '/' + info[4]
                # 0 - obj_id objid
                # 1 - obj_name name
                # 2 - type_string type
                # 3 - timestamp save_date
                # 4 - int version
                # 5 - username saved_by
                # 6 - ws_id wsid
                # 7 - ws_name workspace
                # 8 - string chsum
                # 9 - int size 
                # 10 - usermeta meta
                type_name = info[2].split('.')[1].split('-')[0]

            except Exception as e:
                raise ValueError('Unable to fetch input_name object from workspace: ' + str(e))
                #to get the full stack trace: traceback.format_exc()

            if type_name != 'FeatureSet':
                raise ValueError("Bad Type:  Should be FeatureSet instead of '"+type_name+"'")

            this_featureSet = data
            this_element_ordering = []
            if 'element_ordering' in this_featureSet.keys():
                this_element_ordering = this_featureSet['element_ordering']
            else:
                this_element_ordering = sorted(this_featureSet['elements'].keys())
            element_ordering.extend(this_element_ordering)
            self.log(console,'features in input set '+featureSet_name+': '+str(len(this_element_ordering)))
            report += 'features in input set '+featureSet_name+': '+str(len(this_element_ordering))+"\n"

            for fId in this_featureSet['elements'].keys():
                elements[fId] = this_featureSet['elements'][fId]
            

        # load the method provenance from the context object
        #
        self.log(console,"SETTING PROVENANCE")  # DEBUG
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        # add additional info to provenance here, in this case the input data object reference
        provenance[0]['input_ws_objects'] = []
        for featureSet_name in params['input_names']:
            provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+featureSet_name)
        provenance[0]['service'] = 'kb_util_dylan'
        provenance[0]['method'] = 'KButil_Merge_FeatureSet_Collection'


        # Store output object
        #
        output_FeatureSet = {
                              'description': params['desc'],
                              'element_ordering': element_ordering,
                              'elements': elements
                            }

        new_obj_info = ws.save_objects({
                            'workspace': params['workspace_name'],
                            'objects':[{
                                    'type': 'KBaseCollections.FeatureSet',
                                    'data': output_FeatureSet,
                                    'name': params['output_name'],
                                    'meta': {},
                                    'provenance': provenance
                                }]
                        })


        # build output report object
        #
        self.log(console,"BUILDING REPORT")  # DEBUG
        self.log(console,"features in output set "+params['output_name']+": "+str(len(element_ordering)))
        report += 'features in output set '+params['output_name']+': '+str(len(element_ordering))+"\n"

        reportObj = {
            'objects_created':[{'ref':params['workspace_name']+'/'+params['output_name'], 'description':'KButil_Merge_FeatureSet_Collection'}],
            'text_message':report
        }
        reportName = 'kb_util_dylan_merge_featureset_report_'+str(hex(uuid.getnode()))
        report_obj_info = ws.save_objects({
#                'id':info[6],
                'workspace':params['workspace_name'],
                'objects':[
                    {
                        'type':'KBaseReport.Report',
                        'data':reportObj,
                        'name':reportName,
                        'meta':{},
                        'hidden':1,
                        'provenance':provenance
                    }
                ]
            })[0]


        # Build report and return
        #
        self.log(console,"BUILDING RETURN OBJECT")
        returnVal = { 'report_name': reportName,
                      'report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
                      }
        self.log(console,"KButil_Merge_FeatureSet_Collection DONE")
        #END KButil_Merge_FeatureSet_Collection

        # At some point might do deeper type checking...
        if not isinstance(returnVal, dict):
            raise ValueError('Method KButil_Merge_FeatureSet_Collection return value ' +
                             'returnVal is not type dict as required.')
        # return the results
        return [returnVal]

    def KButil_Build_GenomeSet_from_FeatureSet(self, ctx, params):
        # ctx is the context object
        # return variables are: returnVal
        #BEGIN KButil_Build_GenomeSet_from_FeatureSet
        console = []
        self.log(console,'Running KButil_Build_GenomeSet_from_FeatureSet with params=')
        self.log(console, "\n"+pformat(params))
        report = ''
#        report = 'Running KButil_Build_GenomeSet_from_FeatureSet with params='
#        report += "\n"+pformat(params)


        #### do some basic checks
        #
        if 'workspace_name' not in params:
            raise ValueError('workspace_name parameter is required')
        if 'desc' not in params:
            raise ValueError('desc parameter is required')
        if 'input_name' not in params:
            raise ValueError('input_name parameter is required')
        if 'output_name' not in params:
            raise ValueError('output_name parameter is required')


        # Obtain FeatureSet
        #
        try:
            ws = workspaceService(self.workspaceURL, token=ctx['token'])
            objects = ws.get_objects([{'ref': params['workspace_name']+'/'+params['input_name']}])
            data = objects[0]['data']
            info = objects[0]['info']
            # Object Info Contents
            # absolute ref = info[6] + '/' + info[0] + '/' + info[4]
            # 0 - obj_id objid
            # 1 - obj_name name
            # 2 - type_string type
            # 3 - timestamp save_date
            # 4 - int version
            # 5 - username saved_by
            # 6 - ws_id wsid
            # 7 - ws_name workspace
            # 8 - string chsum
            # 9 - int size 
            # 10 - usermeta meta
            featureSet = data
            type_name = info[2].split('.')[1].split('-')[0]
        except Exception as e:
            raise ValueError('Unable to fetch input_name object from workspace: ' + str(e))
            #to get the full stack trace: traceback.format_exc()
        if type_name != 'FeatureSet':
            raise ValueError("Bad Type:  Should be FeatureSet instead of '"+type_name+"'")


        # Build GenomeSet
        #
        elements = {}
        genome_seen = dict()
        
        for fId in featureSet['elements'].keys():
            for genomeRef in featureSet['elements'][fId]:

                try:
                    already_included = genome_seen[genomeRef]
                except:
                    genome_seen[genomeRef] = True

                    try:
                        ws = workspaceService(self.workspaceURL, token=ctx['token'])
                        objects = ws.get_objects([{'ref': genomeRef}])
                        data = objects[0]['data']
                        info = objects[0]['info']
                        genomeObj = data
                        type_name = info[2].split('.')[1].split('-')[0]
                    except Exception as e:
                        raise ValueError('Unable to fetch input_name object from workspace: ' + str(e))
                    if type_name != 'Genome':
                        raise ValueError("Bad Type:  Should be Genome instead of '"+type_name+"' for ref: '"+genomeRef+"'")
                    
                    genome_id = genomeObj['id']
                    if not genome_id in elements.keys():
                        elements[genome_id] = dict()
                    elements[genome_id]['ref'] = genomeRef  # the key line
                    self.log(console,"adding element "+genome_id+" : "+genomeRef)  # DEBUG
            

        # load the method provenance from the context object
        #
        self.log(console,"SETTING PROVENANCE")  # DEBUG
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        # add additional info to provenance here, in this case the input data object reference
        provenance[0]['input_ws_objects'] = []
        provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+params['input_name'])
        provenance[0]['service'] = 'kb_util_dylan'
        provenance[0]['method'] = 'KButil_Build_GenomeSet_from_FeatureSet'


        # Store output object
        #
        output_GenomeSet = {
                              'description': params['desc'],
                              'elements': elements
                            }

        new_obj_info = ws.save_objects({
                            'workspace': params['workspace_name'],
                            'objects':[{
                                    'type': 'KBaseSearch.GenomeSet',
                                    'data': output_GenomeSet,
                                    'name': params['output_name'],
                                    'meta': {},
                                    'provenance': provenance
                                }]
                        })


        # build output report object
        #
        self.log(console,"BUILDING REPORT")  # DEBUG
        self.log(console,"genomes in output set "+params['output_name']+": "+str(len(elements.keys())))
        report += 'genomes in output set '+params['output_name']+': '+str(len(elements.keys()))+"\n"

        reportObj = {
            'objects_created':[{'ref':params['workspace_name']+'/'+params['output_name'], 'description':'KButil_Build_GenomeSet_from_FeatureSet'}],
            'text_message':report
        }
        reportName = 'kb_util_dylan_build_genomeset_from_featureset_report_'+str(hex(uuid.getnode()))
        report_obj_info = ws.save_objects({
#                'id':info[6],
                'workspace':params['workspace_name'],
                'objects':[
                    {
                        'type':'KBaseReport.Report',
                        'data':reportObj,
                        'name':reportName,
                        'meta':{},
                        'hidden':1,
                        'provenance':provenance
                    }
                ]
            })[0]


        # Build report and return
        #
        self.log(console,"BUILDING RETURN OBJECT")
        returnVal = { 'report_name': reportName,
                      'report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
                      }
        self.log(console,"KButil_Build_GenomeSet_from_FeatureSet DONE")
        #END KButil_Build_GenomeSet_from_FeatureSet

        # At some point might do deeper type checking...
        if not isinstance(returnVal, dict):
            raise ValueError('Method KButil_Build_GenomeSet_from_FeatureSet return value ' +
                             'returnVal is not type dict as required.')
        # return the results
        return [returnVal]


    def KButil_Concat_MSAs(self, ctx, params):
        # ctx is the context object
        # return variables are: returnVal
        #BEGIN KButil_Concat_MSAs
        console = []
        self.log(console,'Running KButil_Concat_MSAs with params=')
        self.log(console, "\n"+pformat(params))
        report = ''
#        report = 'Running KButil_Concat_MSAs with params='
#        report += "\n"+pformat(params)


        #### do some basic checks
        #
        if 'workspace_name' not in params:
            raise ValueError('workspace_name parameter is required')
        if 'desc' not in params:
            raise ValueError('desc parameter is required')
        if 'input_names' not in params:
            raise ValueError('input_names parameter is required')
        if 'output_name' not in params:
            raise ValueError('output_name parameter is required')


        # Build FeatureSet
        #
        row_order = []
        alignment = {}
        curr_pos = 0
        MSA_seen = {}
        discard_set = {}
        sequence_type = None
        for MSA_i,MSA_name in enumerate(params['input_names']):
            if not MSA_name in MSA_seen.keys():
                MSA_seen[MSA_name] = True
            else:
                self.log(console,"repeat MSA_name: '"+MSA_name+"'")
                raise ValueError ("repeat MSA_name: '"+MSA_name+"'")

            try:
                ws = workspaceService(self.workspaceURL, token=ctx['token'])
                objects = ws.get_objects([{'ref': params['workspace_name']+'/'+MSA_name}])
                data = objects[0]['data']
                info = objects[0]['info']
                # Object Info Contents
                # absolute ref = info[6] + '/' + info[0] + '/' + info[4]
                # 0 - obj_id objid
                # 1 - obj_name name
                # 2 - type_string type
                # 3 - timestamp save_date
                # 4 - int version
                # 5 - username saved_by
                # 6 - ws_id wsid
                # 7 - ws_name workspace
                # 8 - string chsum
                # 9 - int size 
                # 10 - usermeta meta
                type_name = info[2].split('.')[1].split('-')[0]

            except Exception as e:
                raise ValueError('Unable to fetch input_name object from workspace: ' + str(e))
                #to get the full stack trace: traceback.format_exc()

            if type_name != 'MSA':
                raise ValueError("Bad Type:  Should be MSA instead of '"+type_name+"'")

            this_MSA = data
            this_genomes_seen = {}

            # set sequence_type
            try:
                this_sequence_type = this_MSA['sequence_type']
                if sequence_type == None:
                    sequence_type = this_sequence_type
                elif this_sequence_type != sequence_type:
                    raise ValueError ("inconsistent sequence type for MSA "+MSA_name+" '"+this_sequence_type+"' doesn't match '"+sequence_type+"'")
            except:
                pass

            # build row_order
            this_row_order = []
            if 'row_order' in this_MSA.keys():
                #self.log(console,"IN row_order A")  # DEBUG
                this_row_order = this_MSA['row_order']
            else:
                #self.log(console,"IN row_order B")  # DEBUG
                this_row_order = sorted(this_MSA['alignment'].keys())

            # DEBUG
            #for row_id in this_row_order:
            #    self.log(console,"ROW_ORDER_ID: '"+row_id+"'")
            #for row_id in sorted(this_MSA['alignment']):
            #    self.log(console,"ALIGNMENT_ID: '"+row_id+"'")


            # concat alignments using base genome_id to unify (input rows are probably gene ids)
            this_aln_len = len(this_MSA['alignment'][this_row_order[0]])
            genome_row_ids_updated = {}
            for row_id in this_row_order:
                id_pieces = re.split('\.', row_id)
                if len(id_pieces) >= 2:
                    genome_id = ".".join(id_pieces[0:2])  # just want genome_id
                else:
                    genome_id = row_id

                # can't have repeat genome_ids (i.e. no paralogs allowed)
                try:
                    genome_id_seen = this_genomes_seen[genome_id]
                    self.log(console,"only one feature per genome permitted in a given MSA.  MSA: "+MSA_name+" genome_id: "+genome_id)
                    raise ValueError("only one feature per genome permitted in a given MSA.  MSA: "+MSA_name+" genome_id: "+genome_id)
                    continue  # DEBUG
                    #sys.exit(0)  
                except:
                    this_genomes_seen[genome_id] = True

                this_row_len = len(this_MSA['alignment'][row_id])
                if this_row_len != this_aln_len:
                    raise ValueError("inconsistent alignment len in "+MSA_name+": first_row_len="+this_aln_len+" != "+this_row_len+" ("+row_id+")")

                # create new rows
                if genome_id not in alignment.keys():
                    row_order.append(genome_id)
                    alignment[genome_id] = ''
                    if MSA_i > 0:
                        self.log(console,"NOT IN OLD MSA: "+genome_id)  # DEBUG
                        discard_set[genome_id] = True
                        alignment[genome_id] += ''.join(['-' for s in range(curr_pos)])
                else:  # DEBUG
                    self.log(console,"SEEN IN MSA: "+genome_id)  # DEBUG

                # add new 
                genome_row_ids_updated[genome_id] = True
                alignment[genome_id] += this_MSA['alignment'][row_id]

            # append blanks for rows that weren't in new MSA
            if MSA_i > 0:
                for genome_id in alignment.keys():
                    try:
                        updated = genome_row_ids_updated[genome_id]
                    except:
                        self.log(console,"NOT IN NEW MSA: "+genome_id)  # DEBUG
                        discard_set[genome_id] = True
                        alignment[genome_id] += ''.join(['-' for s in range(this_aln_len)])
            # update curr_pos
            curr_pos += this_aln_len

            report += 'num rows in input set '+MSA_name+': '+str(len(this_row_order))+"\n"
            self.log(console,'num rows in input set '+MSA_name+': '+str(len(this_row_order)))
            self.log(console,'row_ids in input set '+MSA_name+': '+str(this_row_order))


        # remove incomplete rows if not adding blanks
        if 'blanks_flag' in params and params['blanks_flag'] != None and params['blanks_flag'] == 0:
            new_row_order = []
            new_alignment = {}
            for genome_id in row_order:
                try:
                    discard = discard_set[genome_id]
                except:
                    new_row_order.append(genome_id)
                    new_alignment[genome_id] = alignment[genome_id]
            row_order = new_row_order
            alignment = new_alignment


        # load the method provenance from the context object
        #
        self.log(console,"SETTING PROVENANCE")  # DEBUG
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        # add additional info to provenance here, in this case the input data object reference
        provenance[0]['input_ws_objects'] = []
        for MSA_name in params['input_names']:
            provenance[0]['input_ws_objects'].append(params['workspace_name']+'/'+MSA_name)
        provenance[0]['service'] = 'kb_util_dylan'
        provenance[0]['method'] = 'KButil_Concat_MSAs'


        # DEBUG: check alignment and row_order
        #for genome_id in row_order:
        #    self.log(console,"AFTER ROW_ORDER: "+genome_id)
        #for genome_id in alignment.keys():
        #    self.log(console,"AFTER ALIGNMENT: "+genome_id+",\t"+alignment[genome_id])


        # Store output object
        #
        output_MSA = {
                       'name': params['output_name'],
                       'description': params['desc'],
                       'row_order': row_order,
                       'alignment': alignment,
                       'alignment_length': len(alignment[row_order[0]])
                     }
        if sequence_type != None:
            output_MSA['sequence_type'] = sequence_type

        new_obj_info = ws.save_objects({
                            'workspace': params['workspace_name'],
                            'objects':[{
                                    'type': 'KBaseTrees.MSA',
                                    'data': output_MSA,
                                    'name': params['output_name'],
                                    'meta': {},
                                    'provenance': provenance
                                }]
                        })


        # build output report object
        #
        self.log(console,"BUILDING REPORT")  # DEBUG
        self.log(console,"rows in output MSA "+params['output_name']+": "+str(len(row_order)))
        report += 'rows in output MSA '+params['output_name']+': '+str(len(row_order))+"\n"

        reportObj = {
            'objects_created':[{'ref':params['workspace_name']+'/'+params['output_name'], 'description':'KButil_Concat_MSAs'}],
            'text_message':report
        }
        reportName = 'kb_util_dylan_concat_msas_report_'+str(hex(uuid.getnode()))
        report_obj_info = ws.save_objects({
#                'id':info[6],
                'workspace':params['workspace_name'],
                'objects':[
                    {
                        'type':'KBaseReport.Report',
                        'data':reportObj,
                        'name':reportName,
                        'meta':{},
                        'hidden':1,
                        'provenance':provenance
                    }
                ]
            })[0]


        # Build report and return
        #
        self.log(console,"BUILDING RETURN OBJECT")
        returnVal = { 'report_name': reportName,
                      'report_ref': str(report_obj_info[6]) + '/' + str(report_obj_info[0]) + '/' + str(report_obj_info[4]),
                      }
        self.log(console,"KButil_Concat_MSAs DONE")
        #END KButil_Concat_MSAs

        # At some point might do deeper type checking...
        if not isinstance(returnVal, dict):
            raise ValueError('Method KButil_Concat_MSAs return value ' +
                             'returnVal is not type dict as required.')
        # return the results
        return [returnVal]
