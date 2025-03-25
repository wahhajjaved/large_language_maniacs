#-*- coding: utf-8 -*-
##############################################################################
#
#    Smart Solution bvba
#    Copyright (C) 2010-Today Smart Solution BVBA (<http://www.smartsolution.be>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
############################################################################## 

from osv import osv, fields
from tools.translate import _
from datetime import datetime
import base64
import tempfile
import logging
from contextlib import contextmanager
import requests
import nodes
import json
from natuurpunt_tools import compose
from functools import partial

_logger = logging.getLogger(__name__)

def setup_alfresco_rest_api(obj, cr, uid):
    conf_param_obj = obj.pool.get('ir.config_parameter')
    server_url = conf_param_obj.get_param(cr, uid, 'document_cmis.rest_api')
    if not server_url:
       raise osv.except_osv(_('Error!'),_("Cannot connect to the CMIS Server: No CMIS Server URL system property found"))

    # basic auth credentials
    user = obj.pool.get('res.users').browse(cr, uid, uid)
    auth = (user.login, user.password)

    def api_call_wrapper(verb,rest_api_call,files=None,data=None):
        url = server_url + rest_api_call
        if files:
            response = requests.request(verb,url=url,files=files,auth=auth)
        else:
            response = requests.request(verb,url=url,data=data,auth=auth)
        response.raise_for_status()
        return response
    return api_call_wrapper

def alfresco_repository_from_model(obj, cr, uid, vals, context=None):
    """"""
    if 'res_model' in vals and vals['res_model']:
        #Find ressource directories
        model_id = obj.pool.get('ir.model').search(cr, uid, [('model','=',vals['res_model'])])[0]
        dirs = obj.pool.get('document.directory').search(cr, uid, [('ressource_type_id','=',model_id)])
        ressource = obj.pool.get(vals['res_model']).browse(cr, uid, vals['res_id'])
        server_mode = obj.pool.get('ir.config_parameter').get_param(cr, uid, 'document_cmis.server_mode')
        if not dirs and server_mode == 'cmis_only':
            raise osv.except_osv(_("Error!"),_("You cannot add attachments to this record"))

        for directory in obj.pool.get('document.directory').browse(cr, uid, dirs):
            # Process only for CMIS enabled directories
            if directory.cmis_object_id:

                # Check the directory domain
                domain = [('id','=',vals['res_id'])] + eval(directory.domain)
                res_ids = obj.pool.get(vals['res_model']).search(cr, uid, domain)
                if not res_ids:
                    continue

                # Check if the directory is company specific
                if ressource.company_id != directory.company_id and directory.company_id:
                    raise osv.except_osv(_("Error!"),_("You cannot attach a document from the company %s in a directory from the company %s"%(ressource.company_id.name,directory.company_id.name)))

                return (ressource,directory)

    return (False,False)

@contextmanager
def alfresco_api_handler(obj, cr, uid):
    try:
        alfresco_rest_api = setup_alfresco_rest_api(obj, cr, uid)
        yield alfresco_rest_api
    except requests.exceptions.Timeout:
        # Maybe set up for a retry, or continue in a retry loop
        raise osv.except_osv(_("Error!"),_("CMIS Server: Timeout"))
    except requests.exceptions.TooManyRedirects:
        # Tell the user their URL was bad and try a different one
        raise osv.except_osv(_("Error!"),_("CMIS Server: Too many redirects"))
    except requests.exceptions.RequestException as err:
        _logger.exception(err)
        raise osv.except_osv(_("Request Error!"),_(err))
    except requests.exceptions.HTTPError as err:
        _logger.exception(err)
        raise osv.except_osv(_("HTTPError!"),_(err))

def attach_document_from_dropoff_folder(api,vals):
    return compose(partial(check_root_folder,api),
                   partial(get_target_folder,api),
                   partial(move_from_dropoff_folder_to_target_folder,api))(vals)

def attach_document_from_disk(api,vals):
    return compose(partial(check_root_folder,api),
                   partial(get_target_folder,api),
                   partial(upload_file_from_disk,api))(vals)

def rename_draft_invoice_folder(api,vals):
    return compose(partial(check_root_folder,api),
                   partial(rename_draft_folder_to_target_folder,api))(vals)

def check_root_folder(api,vals):
    # check if directory exists on cmis server
    response = api('GET',nodes.node(vals['cmis_object_id']))
    return vals

def get_target_folder(api,vals):
    response = api('GET',nodes.queries(vals['cmis_object_id'],vals['target_folder']))
    query_res = [entry['entry'] for entry in response.json()['list']['entries']]
    if not(any([r['isFolder'] for r in query_res]) if query_res else False):
       folder = {"nodeType":"cm:folder"}
       folder['name'] = vals['target_folder']
       request_body = json.dumps(folder)
       response = api('POST',nodes.children(vals['cmis_object_id']),data=request_body)
       vals['target_folder_id'] = response.json()['entry']['id']
    else:
       vals['target_folder_id'] = [r['id'] for r in query_res if r['isFolder']][0]
    return vals

def rename_draft_folder_to_target_folder(api,vals):
    response = api('GET',nodes.queries(vals['cmis_object_id'],vals['draft_folder']))
    query_res = [entry['entry'] for entry in response.json()['list']['entries']]
    if any([r['isFolder'] for r in query_res]) if query_res else False:
       draft_folder = [r['name'] for r in query_res][0]
       _logger.info("found draft folder {} with search term {}".format(draft_folder,vals['draft_folder']))
       if vals['draft_folder'] == draft_folder:
           _logger.info("draft folder rename {} to {}".format(vals['draft_folder'],vals['target_folder']))
           vals['draft_folder_id'] = [r['id'] for r in query_res if r['isFolder']][0]
           request_body = json.dumps({'name':vals['target_folder']})
           response = api('PUT',nodes.node(vals['draft_folder_id']),data=request_body)
    return response

def move_from_dropoff_folder_to_target_folder(api,vals):
    request_body = json.dumps({'targetParentId':vals['target_folder_id']})
    response = api('POST',nodes.move(vals['object_id']),data=request_body)
    return response

def upload_file_from_disk(api,vals):
    fname = vals['datas_fname']
    extension =  fname.split(".")
    # Keep the last extension (for .tar.gz it will be .gz)
    # If not extension found, set as txt
    extension = ".txt" if len(extension) == 1 else "." + extension[-1]
    fp = tempfile.NamedTemporaryFile(delete=False, suffix=extension)
    fp.write(base64.decodestring(vals['datas']))
    fp.write(vals['datas'])
    fp.close()
    node = nodes.children(vals['target_folder_id'])
    # automatic closing of file 
    with open(fp.name, 'r') as fdata:
       response = api('POST',node,files={'filedata': fdata})
    #renaming it to the original name
    object_id = response.json()['entry']['id']
    node_rename = nodes.node(object_id)
    request_body = json.dumps({'name':fname})
    response = api('PUT',node_rename,data=request_body)
    return response

class account_invoice(osv.osv):

    _inherit = "account.invoice"

    def invoice_validate(self, cr, uid, ids, context=None):
        res =  super(account_invoice, self).invoice_validate(cr, uid, ids, context=context)
        for invoice in self.browse(cr, uid, ids):
            if self.pool.get('ir.attachment').search(cr, uid, [('res_id','=',invoice.id)]):
                vals = {'res_model':'account.invoice', 'res_id':invoice.id}
                ressource, directory = alfresco_repository_from_model(self, cr, uid, vals, context=context)
                if directory.cmis_object_id:
                    cmis_vals = {
                        'cmis_object_id':directory.cmis_object_id.split('/')[-1],
                        'draft_folder':invoice.id,
                        'target_folder':invoice.internal_number,
                    }
                    with alfresco_api_handler(self, cr, uid) as api:
                        response = rename_draft_invoice_folder(api,cmis_vals)
        return res

class ir_attachment(osv.osv):

    _inherit = 'ir.attachment'

    def _data_get(self, cr, uid, ids, name, arg, context=None):
        return super(ir_attachment, self)._data_get(cr, uid, ids, name, arg, context=context)

    def _data_set(self, cr, uid, id, name, value, arg, context=None):
        # We dont handle setting data to null
        if not value:
            return True
        if context is None:
            context = {}
        server_mode = self.pool.get('ir.config_parameter').get_param(cr, uid, 'document_cmis.server_mode')
        if server_mode == 'cmis_only':
            return True
        return super(ir_attachment, self)._data_set(cr, uid, id, name, value, arg, context=context)


    _columns = {
        'cmis_object_id': fields.char('CMIS Directory ID', size=256),
        'datas': fields.function(_data_get, fnct_inv=_data_set, string='File Content', type="binary", nodrop=True),
    }

    def create(self, cr, uid, vals, context=None):
        """Send the document to the CMIS server and create the attachment"""

        ressource, directory = alfresco_repository_from_model(self, cr, uid, vals, context=context)

        # For Static directories, of a CMIS Object ID is specified, it put all files in that directory (IOW, it does not create subdirs)
        # For Folders per ressources, search if the ressource directory exists or creates it
        if directory and directory.type == "ressource":

           vals['cmis_object_id'] = directory.cmis_object_id.split('/')[-1]
           cmis_vals = vals.copy()

           # Check which field to use to find the name
           if directory.resource_field:
              name_field = directory.resource_field.name
              name = str(getattr(ressource, name_field))
           else:
              name = str(ressource.name)
           if vals['res_model'] == 'account.invoice':
              name = ressource.internal_number or ressource.number or str(ressource.id)

           # If no name is found
           if name:
              name = str(name).replace('/','_')
              cmis_vals['target_folder'] = name
           else:
              raise osv.except_osv(_('Error!'),_("Cannot find a document name for this ressource (model:%s / id:%s)"%(vals['res_model'],vals['res_id'])))

           # check if document is already exsists with this model/res_id
           if self.search(cr, uid, [('name','=',vals['name']),('res_id','=',vals['res_id'])]):
              raise osv.except_osv(_("Error!"),_("A document already exists with the same name for this ressource (model:%s / id:%s)"%(vals['res_model'],vals['res_id'])))

           with alfresco_api_handler(self, cr, uid) as api:
              if 'object_id' in cmis_vals:
                  response = attach_document_from_dropoff_folder(api,cmis_vals)
              else:
                  response = attach_document_from_disk(api,cmis_vals)

           #Get the cmis object id and store it in the attachment
           protocol = 'workspace://SpacesStore/'
           link_url = self.pool.get('ir.config_parameter').get_param(cr, uid, 'document_cmis.server_link_url')
           url = link_url + protocol + response.json()['entry']['id']
           vals['type'] = 'url'
           vals['url'] = url
           vals['cmis_object_id'] = protocol + response.json()['entry']['id']
           vals['db_datas'] = ""

        else:
           # Does not attach document if no CMIS ID is specified and server mode is cmis_only
           # Or else fallback to OpenERP DMS
           raise osv.except_osv(_("Error!"),_("You cannot add attachments to this record"))

        return super(ir_attachment, self).create(cr, uid, vals, context)

    def unlink(self, cr, uid, ids, context=None):
        """Delete the cmis document when a ressource is deleted"""
        for doc in self.pool.get('ir.attachment').browse(cr, uid, ids):
            if doc.type == 'url':
               cmis_object_id = doc.cmis_object_id.split('/')[-1]
               with alfresco_api_handler(self, cr, uid) as api:
                  response = api('DELETE',nodes.node(cmis_object_id))

        return super(ir_attachment, self).unlink(cr, uid, ids, context=context)


class document_directory(osv.osv):

    _inherit = 'document.directory'

    _columns = {
        'cmis_object_id': fields.char('CMIS Object ID', size=256),
    }

    def cmis_sync(self, cr, uid, ids, context=None):
        """Try to create directories in the DMS"""
        for directory in self.browse(cr, uid, ids):

            if not directory.cmis_object_id and directory.type == "ressource":

                if not directory.company_id:
                    raise osv.except_osv(_('Error!'),_("You must assign a company to this directory (%s) to use the Sync with DMS feature."%(dir.name)))

                company = self.pool.get('res.company').browse(cr, uid, directory.company_id.id)
                if not company.cmis_base_dir:
                    raise osv.except_osv(_('Error!'),_("You must assign a CMIS base directory to this company (%s) to use the Sync with DMS feature."%(company.name)))

                repo = cmis_connect(cr, uid)
                if not repo:
                    raise osv.except_osv(_('Error!'),_("Cannot find the default repository in the CMIS Server."))

                # Find the company base CMIS directory
                try:
                    cmisDir = repo.getObject(company.cmis_base_dir)
                except:
                    raise osv.except_osv(_('Error!'),_("Cannot find that company base directory (%s) in the DMS. You may not have the right to access it."%(company.cmis_base_dir)))

                childrenRS = cmisDir.getChildren()
                children = childrenRS.getResults()
                res_found = False

                # Check if the folder already exists
                for child in children:
                    if directory.name == child.properties['cmis:name']:
                        # Use the ressource folder
                        cmisDir = repo.getObject(child.properties['cmis:objectId'])
                        self.write(cr, uid, [directory.id], {'cmis_object_id':cmisDir})
                        res_found = True
                if not res_found:
                    # Create the ressouce folder
                    cmisDir = repo.createFolder(cmisDir, directory.name)
                    dirID = repo.getObject(cmisDir.properties['cmis:objectId'])
                    self.write(cr, uid, [directory.id], {'cmis_object_id':dirID})

        return True


class res_company(osv.osv):

    _inherit = 'res.company'

    _columns = {
        'cmis_base_dir': fields.char('CMIS Base Directory', size=256),
    }

class document_directory_cmis_sync(osv.osv_memory):

    _name= "document.directory.cmis.sync"

    def cmis_sync(self, cr, uid, ids, context=None):
        return self.pool.get('document.directory').cmis_sync(cr, uid, context['active_ids'], context=context)




# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
