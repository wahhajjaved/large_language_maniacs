#!/usr/bin/python
"""
WSGI GeoNetwork to OOI Resource Registry Metadata Synchronization Service
"""
from gevent.pywsgi import WSGIServer
import httplib2
import json
import requests
from bs4 import *
import yaml
import logging
import psycopg2
import simplejson as json
import numpy as np

__author__ = "abird"

# USAGE: See the following for reference:
# http://geonetwork-opensource.org/manuals/trunk/eng/developer/xml_services/metadata_xml_search_retrieve.html#search-metadata-xml-search

# Content headers
headers = {'content-type': 'application/xml'}

SYNC_HARVESTERS = "syncharvesters"
ALIVE = "alive"

KEY_SERVICE = 'service'
KEY_NAME = 'name'
KEY_ID = 'id'
PARAMS = 'params'


class DataProductImporter():
    def __init__(self):
        logger = logging.getLogger('resync_service')
        hdlr = logging.FileHandler('resync_service.log')
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        hdlr.setFormatter(formatter)
        logger.addHandler(hdlr)
        logger.setLevel(logging.DEBUG)

        self.logger = logger
        self.logger.info("Setting up geonetwork to RR resync service...")
        self.startup()

    def startup(self):
        stream = open("extern.yml", 'r')
        ion_config = yaml.load(stream)
        self.logger.info("opened yml file")

        self.RR_PORT = ion_config['eoi']['resync_service']['port']
        self.SGS_URL = self.url = ion_config['eoi']['resync_service']['sgs_url']
        self.HARVESTER_LIST = self.url = ion_config['eoi']['resync_service']['harvester_list']

        self.GEONETWORK_BASE_URL = ion_config['eoi']['geonetwork']['base_url']
        self.GEONETWORK_USER = ion_config['eoi']['geonetwork']['user_name']
        self.GEONETWORK_PASS = ion_config['eoi']['geonetwork']['password']

        self.GEONETWORK_DB_SERVER = ion_config['eoi']['geonetwork']['database_server']
        self.GEONETWORK_DB_NAME = ion_config['eoi']['geonetwork']['database_name']
        self.GEONETWORK_DB_USER = ion_config['eoi']['geonetwork']['database_user']
        self.GEONETWORK_DB_PASS = ion_config['eoi']['geonetwork']['database_password']

        self.EXTERNAL_CATEGORY = 3

        self.logger.info('Serving on '+str(self.RR_PORT)+'...')
        server = WSGIServer(('', self.RR_PORT), self.application).serve_forever()

    def application(self, env, start_response):
        request = env['PATH_INFO']
        request = request[1:]
        output = ''
        if request == '/':
            start_response('404 Not Found', [('Content-Type', 'text/html')])
            return ["<h1>Error<b>please add request information</b>"]
        else:
            req = request.split("&")
            param_dict = {}
            if len(req) > 1:
                for param in req:
                    params = param.split("=")
                    param_dict[params[0]] = params[1]

                if param_dict.has_key(KEY_SERVICE):
                    if param_dict[KEY_SERVICE] == ALIVE:
                        start_response('200 ok', [('Content-Type', 'text/html')])
                        return ['<b>RESYNC SERVICE IS ALIVE<BR>' + request + '<br>' + output + '</b>']
                    elif param_dict[KEY_SERVICE] == SYNC_HARVESTERS:
                        try:
                            self.logger.info("requested sync harvesters:")
                            site_dict = self.get_harvester_list()
                            self.get_meta_data_records_for_harvester(site_dict)

                            start_response('200 ok', [('Content-Type', 'text/html')])
                            return ['<b>ALIVE<BR>' + request + '</b>']
                        except Exception, e:
                            start_response('400 Bad Request', [('Content-Type', 'text/html')])
                            return ['<b>ERROR IN HARVESTER, CHECK CONNECTION<BR>' + request + '<br>' + output + '</b>']
                else:
                    start_response('400 Bad Request', [('Content-Type', 'text/html')])
                    return ['<b>ERROR IN PARAMS<BR>' + request + '<br>' + output + '</b>']
            else:
                start_response('400 Bad Request', [('Content-Type', 'text/html')])
                return ['<b>ERROR NO PARAMS<BR>' + request + '<br>' + output + '</b>']

    def get_harvester_list(self):
        """
        Creates a dict of valid harvester names and id's using GeoNetwork's XML REST service
        """
        site_dict = dict()
        try:    
            self.logger.info("accessing: "+self.GEONETWORK_BASE_URL)
            r = requests.get(self.GEONETWORK_BASE_URL+'xml.harvesting.get', auth=(self.GEONETWORK_USER, self.GEONETWORK_PASS), headers=headers)                        
            soup = BeautifulSoup(r.text)            
            site_list = soup.find_all("site")            
            #accept_list = self.HARVESTER_LIST #removed as ioos names will be added via the catalog
            for site in site_list:
                name = site.find("name").text               
                uuid = site.find("uuid").text
                site_dict[uuid] = name
            return site_dict

        except Exception, e:
            self.logger.info("accessing error: "+str(e))

    def get_meta_data_records_for_harvester(self, site_dict):
        """
        Lookup and extract metadata records from GeoNetwork and add to the RR
        """
        records = []
        self.logger.info("getting meta data records for harvester...")
        try:
            conn = psycopg2.connect(database=self.GEONETWORK_DB_NAME, user=self.GEONETWORK_DB_USER, password=self.GEONETWORK_DB_PASS, host=self.GEONETWORK_DB_SERVER)
            cursor = conn.cursor()
            self.logger.info("cursor obtained...")
            # execute our Query
            for site_uuid in site_dict.keys():
                cursor.execute("SELECT m.uuid,m.changedate,mr.registerdate,mr.rruuid,m.changedate NOT LIKE mr.registerdate AS mchanged FROM metadata m FULL JOIN metadataregistry mr ON m.uuid=mr.gnuuid WHERE m.harvestuuid='" + site_uuid + "'")
                records = cursor.fetchall()
                self.logger.info("number of records..." + str(len(records)))
                for rec in records:
                    uuid = rec[0]

                    # Get the metadata record
                    soup = BeautifulSoup(self.get_metadata_payload(uuid))
                    #get the identification information for the place             
                    rec_name = uuid
                    rec_descrip = ""
                    try: 
                        #fix names if they contain invalid characters                   
                        rec_name = self.get_name_info(soup).replace('\\r\\n', "").rstrip()
                        rec_descrip = self.get_ident_info(soup).replace('\\r\\n', "").rstrip()
                        #self.getkeywords(soup)
                        #self.getgeoextent(soup)
                        #dt = self.get_temporal_extent(soup)
                        #print rec_name, rec_descrip
                    except Exception, e:
                        #print "error getting nodes:", e, "\nUSING:", rec_name, "\n", rec_descrip
                        self.logger.info(str(e))
                        raise ValueError('Error getting name and description nodes from metadata record.')

                    # Create RR entries and add/modify/delete lookups in metadataregistry table
                    rec_changedate = rec[2]
                    #rec_registerdate = rec[3]
                    rec_rruuid = rec[4]
                    rec_mchanged = rec[5]

                    ref_url = self.get_reference_url(site_dict, site_uuid, uuid)

                    try:                       
                        #add the data to the RR
                        if rec_rruuid == None:
                            # The metadata record is new                            
                            gwresponse = self.request_resource_action('resource_registry', 'create', object={"category":self.EXTERNAL_CATEGORY,
                                                                                                                "name": rec_name, 
                                                                                                                "description": rec_descrip, 
                                                                                                                "type_": "DataProduct",
                                                                                                                "reference_urls":[ref_url]
                                                                                                            })
                            self.logger.info("new meta data record:"+str(gwresponse))
                            if gwresponse is None:
                                self.logger.info("resource record was not created in SGS:"+str(gwresponse))
                            else:    
                                rruuid = gwresponse[0]                   
                                self.logger.info("part 2 new meta data record:")         
                                # Add record to metadataregistry table with registerdate and rruuid
                                insert_values = {'uuid': uuid, 'rruuid': rruuid, 'changedate': rec_changedate}
                                insert_stmt = "INSERT INTO metadataregistry (gnuuid,rruuid,registerdate) VALUES ('%(uuid)s','%(rruuid)s','%(changedate)s')" % insert_values
                                cursor.execute(insert_stmt)
                                self.logger.info("update meta data registry:"+str(insert_stmt))
                        elif rec_mchanged:
                            pass
                            # The metadata record has changed
                            # Delete existing Resource from the RR
                            self.request_resource_action('resource_registry', 'delete', object_id=rec_rruuid)

                            # Create new resource in the RR
                            gwresponse = rruuid = self.request_resource_action('resource_registry', 'create', object={"category":self.EXTERNAL_CATEGORY,
                                                                                                                        "name": rec_name, 
                                                                                                                        "description": rec_descrip, 
                                                                                                                        "type_": "DataProduct",
                                                                                                                        "reference_urls":[ref_url]
                                                                                                                    })
                            rruuid = gwresponse[0]

                            # UPDATE metadataregistry table record with updated registerdate and rruuid
                            update_values = {'uuid': uuid, 'rruuid': rruuid, 'changedate': rec_changedate}
                            update_stmt = ("UPDATE metadataregistry SET rruuid='%(rruuid)s', registerdate='%(changedate)s' WHERE gnuuid='%(uuid)s'" % update_values)
                            cursor.execute(update_stmt)
                        elif uuid == None:
                            # Metadata record was deleted by the harvester, cleanup the lookup table and the OOI RR
                            # Delete from RR
                            self.request_resource_action('resource_registry', 'delete', object_id=rec_rruuid)

                            # Delete from metadataregistry
                            delete_values = {'rruuid': rec_rruuid}
                            delete_stmt = ("DELETE FROM metadataregistry WHERE rruuid='%(rruuid)s'" % delete_values)
                            cursor.execute(delete_stmt)
                    except Exception, e:
                         self.logger.info(str(e)+ ": error performining sql commands")       
                                        
        except Exception, e:
            self.logger.info(str(e)+ ": I am unable to connect to the database...")

    def get_reference_url(self,site_dict,site_uuid,uuid):
        ref_url = ""
        if site_dict[site_uuid] == "neptune":
            temp_device_id =11206
            ref_url = "http://dmas.uvic.ca/DeviceListing?DeviceId="+str(temp_device_id)
        else:
            ref_url ="http://r3-pg-test02.oceanobservatories.org:8080/geonetwork/srv/eng/main.home?uuid="+str(uuid)    
            self.logger.info("uuid:"+ref_url)

        self.logger.info("uuid:"+str(uuid)) 

        return ref_url  

    def get_metadata_payload(self, uuid):
        try: 
            conn = psycopg2.connect(database=self.GEONETWORK_DB_NAME, user=self.GEONETWORK_DB_USER, password=self.GEONETWORK_DB_PASS, host=self.GEONETWORK_DB_SERVER)
            cursor = conn.cursor()   
            get_values = {'uuid': uuid}
            query = "SELECT m.data FROM metadata m WHERE m.uuid='"+uuid+"'"       
            cursor.execute(query)
            record = cursor.fetchall()
            if len(record) == 1:
                return str(record[0])
            else:
                raise ValueError('More than one metadata record was returned.  The metadataregistry table has duplicates!')
            self.logger.info("record: "+record)              
        except Exception, e:
             self.logger.info("error getting data: "+str(e))          

    def request_resource_action(self, service_name, op, **kwargs):  

        url = self.SGS_URL
        url = "/".join([url, service_name, op])
        self.logger.info("url:"+url)
             
        r = {"serviceRequest": {
            "serviceName": service_name,
            "serviceOp": op,
            "params": kwargs}
        }

        resp = requests.post(url, data={'payload': Serializer.encode(r)})

        self.logger.info("service gateway service not found")     

        if "<h1>Not Found</h1>" in resp.text:
             self.logger.info("service gateway service not found")     
        else:
            if resp.status_code == 200:
                data = resp.json()
                if 'GatewayError' in data['data']:
                    error = GatewayError(data['data']['Message'])
                    self.logger.info("GATEWAY ERROR:"+str(error))     
                if 'GatewayResponse' in data['data']:
                    return data['data']['GatewayResponse']

    def get_name_info(self, soup):
        ab_info = soup.find("gmd:abstract")
        pur_info = soup.find("gmd:purpose")
        file_ident = soup.find("gmd:fileidentifier")
        return file_ident.text.replace("\n", "")

    def get_ident_info(self, soup):
        indent_info = soup.find("gmd:identificationinfo")
        title = indent_info.find("gmd:title").text.rstrip()
        #alt_title = indent_info.find("gmd:alternatetitle").text.replace("\n", "")
        #iden = indent_info.find("gmd:identifier").text.replace("\n", "")
        #org_name = indent_info.find("gmd:organisationname").text.replace("\n", "")
        #poc = indent_info.find("gmd:pointofcontact")
        return title

    def getkeywords(self, soup):
        keywords = soup.find("gmd:md_keywords")
        deskeywords = soup.find("gmd:descriptivekeywords")

    def getgeoextent(self, soup):
        bound_list = ["westboundlongitude", "eastboundlongitude", "northboundlatitude", "southboundlatitude"]
        bbox = dict()
        geo_extent = soup.find("gmd:geographicelement")
        for i in bound_list:
            pos = geo_extent.find("gmd:"+i).text.replace("\n","")
            bbox[i] = float(pos)
        return bbox

    def get_temporal_extent(self, soup):
        temporal_extent = soup.find("gmd:temporalelement")
        start_dt = temporal_extent.find("gml:beginposition").text.replace("\n", "")
        end_dt = temporal_extent.find("gml:endposition").text.replace("\n", "")
        return [start_dt, end_dt]


class Serializer:
    """
    Serializes JSON data
    """

    def __init__(self):
        pass

    @classmethod
    def encode(cls, message):
        return json.dumps(message)

    @classmethod
    def decode(cls, message):
        return json.loads(message, object_hook=cls._obj_hook)

    @classmethod
    def _obj_hook(cls, dct):
        if '__np__' in dct:
            dct = dct['__np__']
            return np.array(dct['data'], dtype=dct['dtype'])
        return dct
