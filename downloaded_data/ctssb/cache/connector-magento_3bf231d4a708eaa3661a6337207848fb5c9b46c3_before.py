from osv import osv, fields
import datetime

class magerp_osv(osv.osv):
    _MAGE_FIELD = 'magento_id'
    _LIST_METHOD = False
    _mapping = {}
    
    def website_get(self, cr, uid, ids, context=None):
        if not len(ids):
            return []
        reads = self.read(cr, uid, ids, [context['field'],'instance'], context)
        res = []
        for record in reads:
            rid = self.pool.get('magerp.websites').mage_to_oe(cr, uid, record[context['field']],record['instance'][0])
            res.append((record['id'], rid))
        return res
    
    def store_get(self, cr, uid, ids, context=None):
        if not len(ids):
            return []
        reads = self.read(cr, uid, ids, [context['field'],'instance'], context)
        res = []
        for record in reads:
            rid = self.pool.get('magerp.storeviews').mage_to_oe(cr, uid, record[context['field']],record['instance'][0])
            res.append((record['id'], rid))
        return res

    def group_get(self, cr, uid, ids, context=None):
        if not len(ids):
            return []
        reads = self.read(cr, uid, ids, [context['field'],'instance'], context)
        res = []
        for record in reads:
            rid = self.pool.get('magerp.groups').mage_to_oe(cr, uid, record[context['field']],record['instance'][0])
            res.append((record['id'], rid))
        return res
        
    def mage_to_oe(self, cr, uid, mageid, instance, *args):
        #Arguments as a list of tuple
        search_params = []
        if mageid:
            search_params = [(self._MAGE_FIELD, '=', mageid), ]
        if instance:
            search_params.append(('instance', '=', instance))
        for each in args:
            if each:
                if type(each) == type((1, 2)):
                    search_params.append(each)
                if type(each) == type([1, 2]):
                    for each_tup in each:
                        search_params.append(each_tup)
        if search_params:
            oeid = self.search(cr, uid, search_params)
            if oeid:
                    read = self.read(cr, uid, oeid, [self._rec_name])
                    return (read[0]['id'], read[0][self._rec_name])
        return False
    
    def sync_import(self, cr, uid, mage_ip, instance, debug=False,defaults={}, *attrs):
        #Attrs of 0 should be mage2oe_filters
        if mage_ip:
            mapped_keys = self._mapping.keys()
            mage2oe_filters = False
            if attrs:
                mage2oe_filters = attrs[0]
            for each_record in mage_ip:
                #Transform Record objects
                each_record = self.transform(each_record)
                #Check if record exists
                if mage2oe_filters:
                    rec_id = self.mage_to_oe(cr, uid, each_record[self._MAGE_FIELD], instance, mage2oe_filters)
                else:
                    if self._MAGE_FIELD:
                        rec_id = self.mage_to_oe(cr, uid, each_record[self._MAGE_FIELD], instance)
                    else:
                        rec_id = False
                #Generate Vals
                vals = {}
                space = {
                    'self':self,
                    'uid':uid,
                    'rec_id':rec_id,
                    'cr':cr,
                    'instance':instance,
                    'temp_vars':{},
                    'mage2oe_filters':mage2oe_filters
                                         }
                for each_valid_key in self._mapping:
                    if each_valid_key in each_record.keys():
                        try:
                            if len(self._mapping[each_valid_key])==2 or self._mapping[each_valid_key][2]==False:#Only Name & type
                                vals[self._mapping[each_valid_key][0]] = self._mapping[each_valid_key][1](each_record[each_valid_key]) or False
                            elif len(self._mapping[each_valid_key])==3:# Name & type & expr
                                #get the space ready for expression to run
                                #Add current type casted value to space if it exists or just the value
                                if self._mapping[each_valid_key][1]:
                                    space[each_valid_key] = self._mapping[each_valid_key][1](each_record[each_valid_key]) or False
                                else:
                                    space[each_valid_key] = each_record[each_valid_key] or False
                                space['vals'] = vals
                                exec self._mapping[each_valid_key][2] in space
                                if 'result' in space.keys():
                                    if self._mapping[each_valid_key][0]:
                                        vals[self._mapping[each_valid_key][0]] = space['result']
                                    else:
                                        #If mapping is a function return values is of type [('key','value')]
                                        if type(space['result'])==type([1,2]) and space['result']:#Check type
                                            for each in space['result']:
                                                if type(each)==type((1,2)) and each:#Check type
                                                    if len(each)==2:#Assert length
                                                        vals[each[0]] = each[1]#Assign
                                else:
                                    if self._mapping[each_valid_key][0]:
                                        vals[self._mapping[each_valid_key][0]] = False
                        except Exception,e:
                            if self._mapping[each_valid_key][0]:#if not function mapping
                                vals[self._mapping[each_valid_key][0]] = each_record[each_valid_key] or False
                vals['instance'] = instance
                if debug:
                    print vals
                if self._MAGE_FIELD:
                    if self._MAGE_FIELD in vals.keys() and vals[self._MAGE_FIELD]:
                        self.record_save(cr,uid,rec_id,vals,defaults)
                else:
                    self.record_save(cr,uid,rec_id,vals,defaults)
                            
    def record_save(self,cr,uid,rec_id,vals,defaults):
        if defaults:
            for key in defaults.keys():
                vals[key] = defaults[key]
        if rec_id:
            #Record exists, now update it
            self.write(cr, uid, rec_id[0], vals)
        else:
            #Record is not there, create it
            self.create(cr, uid, vals,)
            
    def transform(self, subject):
        #This function will convert string objects to the data type required
        for key in subject.keys():
            if key[0:3] == "is_":
                if subject[key] == '0':
                    subject[key] = False
                else:
                    subject[key] = True
        return subject
    
    def mage_import(self, cr, uid, ids_or_filter, conn, instance, debug=False,defaults={}, *attrs):
        if self._LIST_METHOD:
            result = conn.call(self._LIST_METHOD, ids_or_filter)
            if attrs:
                self.sync_import(cr, uid, result, instance, debug,defaults, attrs)
            else:
                self.sync_import(cr, uid, result, instance, debug,defaults)
        else:
            raise osv.except_osv(_('Undefined List method !'),_("list method is undefined for this object!"))
    
    def getall_mageids(self, cr, uid, ids=[],instance=False):
        search_param = []
        if instance:
            search_param = [('instance','=',instance)]
        if not ids:
            ids = self.search(cr, uid, search_param)
        reads = self.read(cr, uid, ids, [self._MAGE_FIELD])
        mageids = []
        for each in reads:
            mageids.append(each[self._MAGE_FIELD])
        return mageids
        
