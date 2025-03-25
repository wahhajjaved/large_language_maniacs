#!/usr/bin/env python
# -*- coding: utf-8
from goobi.goobi_step import Step
import os
from tools import tools
from tools import errors
from tools.filesystem import fs
import tools.limb as limb_tools

class CopyToLimb( Step ):

    def setup(self):
        self.name = 'Kopiering af billeder til LIMB'
        self.config_main_section = 'copy_to_limb'
        self.limb_output_section = 'limb_output'
        self.valid_exts_section = 'valid_file_exts'
        self.folder_structure_section = 'process_folder_structure'
        self.essential_config_sections.update([self.folder_structure_section, 
                                               self.limb_output_section,
                                               self.valid_exts_section] )
        self.essential_commandlines = {
            "process_id" : "number",
            "process_path" : "folder",
            "process_title" : "string"
        }

    def getVariables(self):
        '''
        Get all required vars from command line + config
        and confirm their existence.
        '''
        
        process_title = self.command_line.process_title
        process_path = self.command_line.process_path
        rel_master_image_path = self.getConfigItem('img_master_path',None,self.folder_structure_section) 
        self.source_folder = os.path.join(process_path,rel_master_image_path)
        self.transit_dir = os.path.join(self.getConfigItem('limb_transit'),process_title)
        self.sleep_interval = int(self.getConfigItem('sleep_interval'))
        self.retries = int(self.getConfigItem('retries'))
        
        #=======================================================================
        # Variable to check if ALTO, PDF and TOC files already exists on Goobi
        #=======================================================================
        limb = self.getConfigItem('limb_output',None,self.limb_output_section)
        alto = self.getConfigItem('alto',None,self.limb_output_section)
        toc = self.getConfigItem('toc',None,self.limb_output_section)
        pdf = self.getConfigItem('pdf',None,self.limb_output_section)
        
        # join paths to create absolute paths
        self.limb_dir = os.path.join(limb, process_title)
        self.alto_dir = os.path.join(self.limb_dir, alto)
        self.toc_dir = os.path.join(self.limb_dir, toc)
        self.pdf_input_dir = os.path.join(self.limb_dir, pdf)
        
        # Set destination for paths
        
        self.goobi_altos = os.path.join(process_path, 
            self.getConfigItem('metadata_alto_path', None, 'process_folder_structure'))
        self.goobi_toc = os.path.join(process_path, 
            self.getConfigItem('metadata_toc_path', None, 'process_folder_structure'))
        self.goobi_pdf = os.path.join(process_path, 
            self.getConfigItem('doc_limbpdf_path', None, 'process_folder_structure'))
        self.valid_exts = self.getConfigItem('valid_file_exts',None, self.valid_exts_section).split(';')
        input_files = self.getConfigItem('img_master_path',None, self.folder_structure_section) 
        self.input_files = os.path.join(process_path,input_files)
        
        #=======================================================================
        # Get the correct LIMB workflow hotfolder for the issue - BW or Color
        #=======================================================================
        limb_workflow_type = self.getSetting('limb_workflow_type')
        if limb_workflow_type == 'bw':
            limb_hotfolder = self.getSetting('limb_bw_hotfolder')
        elif limb_workflow_type == 'color':
            limb_hotfolder = self.getSetting('limb_color_hotfolder')
        self.hotfolder_dir = os.path.join(limb_hotfolder,process_title)
        self.overwrite_destination_files = self.getSetting('overwrite_files', bool , default= True)

    def step(self):
        error = None
        self.getVariables()
        msg = ('Copying files from {0} to {1} via transit {2}.')
        msg = msg.format(self.source_folder, self.hotfolder_dir, self.transit_dir)
        self.debug_message(msg)
        try:
            if not self.overwrite_destination_files:
                if limb_tools.alreadyMoved(self.goobi_toc,self.goobi_pdf,
                                           self.input_files,self.goobi_altos,
                                           self.valid_exts):
                    return error
                if (tools.folderExist(self.hotfolder_dir) and
                    fs.compareDirectories(self.source_folder, self.hotfolder_dir)):
                    return error
            tools.copy_files(source = self.source_folder,
                             dest = self.hotfolder_dir,
                             transit = self.transit_dir,
                             delete_original = False,
                             wait_interval = self.sleep_interval,
                             max_retries = self.retries,
                             logger = self.glogger)
        except errors.TransferError as e:
            error = e.strerror
        except errors.TransferTimedOut as e:
            error = e.strerror
        except Exception as e:
            error = str(e)
        return error

if __name__ == '__main__':    
    CopyToLimb().begin()
