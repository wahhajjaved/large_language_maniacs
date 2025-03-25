# -*- coding: utf-8 -*-
from datetime import datetime as dt, timedelta as td
import logging

from openerp.osv import orm, fields
from openerp import SUPERUSER_ID
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT as DTF

_logger = logging.getLogger(__name__)


def list2sqlstr(lst):
    res = []
    lst = isinstance(lst, (list, tuple)) and lst or [lst]
    for l in lst:
        if isinstance(l, (int, long)):
            res.append("%s" % int(l))
        elif isinstance(l, basestring):
            res.append("'%s'" % l)
        elif l is None:
            res.append("0")
    return ",".join(res)


class nh_cancel_reason(orm.Model):
    """cancellation reason
    """
    _name = 'nh.cancel.reason'
    _columns = {
        'name': fields.char('Name', size=300),
        'system': fields.boolean('System/User Reason')
    }

    
class nh_activity(orm.Model):
    """ activity
    """
    _name = 'nh.activity'
    _inherit = 'nh.activity'
    
    _columns = {
        # identification
        'user_ids': fields.many2many('res.users', 'activity_user_rel', 'activity_id', 'user_id', 'Users', readonly=True),
        'patient_id': fields.many2one('nh.clinical.patient', 'Patient', readonly=True),
        # 'device_id': fields.many2one('nh.clinical.device', 'Device', readonly=True),
        'location_id': fields.many2one('nh.clinical.location', 'Location', readonly=True),
        'location_name': fields.related('location_id', 'full_name', type='char', size=150, string='Location Name'),
        'pos_id': fields.many2one('nh.clinical.pos', 'POS', readonly=True),
        'spell_activity_id': fields.many2one('nh.activity', 'Spell Activity', readonly=True),
        'cancel_reason_id': fields.many2one('nh.cancel.reason', 'Cancellation Reason'),
        'ward_manager_id': fields.many2one('res.users', 'Ward Manager of the ward on Complete/Cancel')
    }

    def write(self, cr, uid, ids, vals, context=None):
        if not vals:
            vals = {}
        res = super(nh_activity, self).write(cr, uid, ids, vals, context=context)
        if 'location_id' in vals:
            location_pool = self.pool['nh.clinical.location']
            location = location_pool.read(cr, uid, vals['location_id'], ['user_ids'], context=context)
            if location:
                self.write(cr, uid, ids, {'user_ids': [[6, False, location['user_ids']]]}, context=context)
        return res

    def cancel_open_activities(self, cr, uid, parent_id, model, context=None):
        domain = [('parent_id', '=', parent_id),
                  ('data_model', '=', model),
                  ('state', 'not in', ['completed', 'cancelled'])]
        open_activity_ids = self.search(cr, uid, domain, context=context)
        return all([self.cancel(cr, uid, a, context=context) for a in open_activity_ids])

    def update_users(self, cr, uid, user_ids=[]):
        """
        Deletes all passed user_ids from all activities and
        Updates activities with user_ids who are responsible for activity location
        """
        if not user_ids:
            return True

        where_clause = "where user_id in (%s)" % list2sqlstr(user_ids)

        sql = """
            delete from activity_user_rel {where_clause};
            insert into activity_user_rel
            select activity_id, user_id from
                (select distinct on (activity.id, ulr.user_id)
                        activity.id as activity_id,
                        ulr.user_id
                from user_location_rel ulr
                inner join res_groups_users_rel gur on ulr.user_id = gur.uid
                inner join ir_model_access access on access.group_id = gur.gid and access.perm_responsibility = true
                inner join ir_model model on model.id = access.model_id
                inner join nh_activity activity on model.model = activity.data_model
                            and activity.location_id = ulr.location_id and activity.state not in ('completed','cancelled')
                where not exists (select 1 from activity_user_rel where activity_id=activity.id and user_id=ulr.user_id )) pairs
            {where_clause}
        """.format(where_clause=where_clause)
        cr.execute(sql)
        self.update_spell_users(cr, uid, user_ids)

        return True

    def update_spell_users(self, cr, uid, user_ids=[]):
        """
        Updates spell activities with user_ids who are responsible for parent locations of spell location
        """

        if not user_ids:
            return True

        where_clause = "where user_id in (%s)" % list2sqlstr(user_ids)
        sql = """
           with
               recursive route(level, path, parent_id, id) as (
                       select 0, id::text, parent_id, id
                       from nh_clinical_location
                       where parent_id is null
                   union
                       select level + 1, path||','||location.id, location.parent_id, location.id
                       from nh_clinical_location location
                       join route on location.parent_id = route.id
               ),
               parent_location as (
                   select
                       id as location_id,
                       ('{'||path||'}')::int[] as ids
                   from route
                   order by path
               )
           insert into activity_user_rel
           select activity_id, user_id from (
               select distinct on (activity.id, ulr.user_id)
                   activity.id as activity_id,
                   ulr.user_id
               from user_location_rel ulr
               inner join res_groups_users_rel gur on ulr.user_id = gur.uid
               inner join ir_model_access access on access.group_id = gur.gid and access.perm_responsibility = true
               inner join ir_model model on model.id = access.model_id and model.model = 'nh.clinical.spell'
               inner join parent_location on parent_location.ids  && array[ulr.location_id]
               inner join nh_activity activity on model.model = activity.data_model
                   and activity.location_id = parent_location.location_id
               where not exists (select 1 from activity_user_rel where activity_id=activity.id and user_id=ulr.user_id )) pairs
           %s
        """ % where_clause

        cr.execute(sql)
        return True
 
    
class nh_activity_data(orm.AbstractModel):
    _inherit = 'nh.activity.data'
    _transitions = {
        'new': ['schedule', 'start', 'complete', 'cancel', 'submit', 'assign', 'unassign'],
        'scheduled': ['schedule', 'start', 'complete', 'cancel', 'submit', 'assign', 'unassign'],
        'started': ['complete', 'cancel', 'submit', 'assign', 'unassign'],
        'completed': ['cancel'],
        'cancelled': []
    }
    _POLICY = {'activities': []}

    def _audit_ward_manager(self, cr, uid, activity_id, context=None):
        """
        Looks for the Activity Location and the Ward Manager responsible for the Ward where the Location is.
        If there is a Ward Manager then it is stored in the 'ward_manager_id' field. If there is no location or
        the location is not within a ward or there is not a ward manager assigned to the ward, then nothing will be
        audited.
        :return: True if the ward_manager_id is stored. False in any other case.
        """
        if isinstance(activity_id, list) and len(activity_id) == 1:
            activity_id = activity_id[0]
        activity_pool = self.pool['nh.activity']
        location_pool = self.pool['nh.clinical.location']
        activity = activity_pool.browse(cr, uid, activity_id, context=context)
        if activity.location_id:
            if activity.location_id.usage != 'ward':
                ward_id = location_pool.get_closest_parent_id(cr, uid, activity.location_id.id, 'ward', context=context)
                ward = location_pool.browse(cr, uid, ward_id, context=context)
            else:
                ward = activity.location_id
            if ward.assigned_wm_ids:
                ward_manager_id = ward.assigned_wm_ids[0].id
                activity_pool.write(cr, uid, activity_id, {'ward_manager_id': ward_manager_id}, context=context)
                return True
        return False

    def complete(self, cr, uid, activity_id, context=None):
        """
        Extension of the complete method to Audit the Ward Manager responsible for the ward where the activity was
        completed.
        """
        res = super(nh_activity_data, self).complete(cr, uid, activity_id, context=context)
        self._audit_ward_manager(cr, uid, activity_id, context=context)
        return res

    def cancel(self, cr, uid, activity_id, context=None):
        """
        Extension of the cancel method to Audit the Ward Manager responsible for the ward where the activity was
        cancelled.
        """
        res = super(nh_activity_data, self).cancel(cr, uid, activity_id, context=context)
        self._audit_ward_manager(cr, uid, activity_id, context=context)
        return res

    def update_activity(self, cr, uid, activity_id, context=None):
        activity_pool = self.pool['nh.activity']
        activity = activity_pool.browse(cr, uid, activity_id, context=context)
        activity_vals = {}
        location_id = self.get_activity_location_id(cr, uid, activity_id)
        patient_id = self.get_activity_patient_id(cr, uid, activity_id)
        pos_id = self.get_activity_pos_id(cr, uid, activity_id)

        if 'patient_id' in self._columns.keys():
            activity_vals.update({'patient_id': patient_id})

        activity_vals.update({'location_id': location_id,
                              'pos_id': pos_id})
        activity_pool.write(cr, uid, activity_id, activity_vals, context=context)
        activity_ids = activity_pool.search(cr, uid, [
            ['patient_id', '=', patient_id], ['data_model', '=', 'nh.clinical.spell'],
            ['state', '=', 'started']], context=context)
        spell_activity_id = activity_ids[0] if activity_ids else False
        # user_ids depend on location_id, thus separate updates
        user_ids = self.get_activity_user_ids(cr, uid, activity_id, context=context)
        activity_pool.write(cr, uid, activity_id, {'user_ids': [(6, 0, user_ids)],
                                                   'spell_activity_id': spell_activity_id}, context=context)
        _logger.debug(
            "activity '%s', activity.id=%s updated with: %s" % (activity.data_model, activity.id, activity_vals))
        return True

    def get_activity_pos_id(self, cr, uid, activity_id, context=None):
        """
        Returns pos_id for activity calculated based on activity data
        """
        pos_id = False
        patient_pool = self.pool['nh.clinical.patient']

        data_ids = self.search(cr, uid, [('activity_id', '=', activity_id)])
        data = self.browse(cr, uid, data_ids, context=context)[0]

        if 'pos_id' in self._columns.keys():
            pos_id = data.pos_id.id if data.pos_id else False
        if pos_id:
            return pos_id
        location_id = self.get_activity_location_id(cr, uid, activity_id)
        patient_id = self.get_activity_patient_id(cr, uid, activity_id)

        if not location_id:
            patient = patient_pool.browse(cr, uid, patient_id, context=context)
            location_id = patient.current_location_id.id if patient.current_location_id else False
            if location_id:
                location = self.pool['nh.clinical.location'].browse(cr, uid, location_id, context)
                pos_id = location.pos_id.id if location.pos_id else False
                if pos_id:
                    return pos_id
        spell_pool = self.pool['nh.clinical.spell']
        spell_id = spell_pool.get_by_patient_id(cr, uid, patient_id, context=context)
        spell = spell_pool.browse(cr, uid, spell_id, context=context) if spell_id else False
        pos_id = spell.pos_id.id if spell else False
        return pos_id

    def get_activity_device_id(self, cr, uid, activity_id, context=None):       
        """
        """
        device_id = False
        data_ids = self.search(cr, uid, [('activity_id', '=', activity_id)])
        data = self.browse(cr, uid, data_ids, context)[0]

        if 'device_id' in self._columns.keys():
            device_id = data.device_id and data.device_id.id or False
        return device_id

    def get_activity_location_id(self, cr, uid, activity_id, context=None):       
        """
        Returns pos_id for activity calculated based on activity data
        Logic:
        1. If activity_data has 'location_id' field and it is not False, returns value of the field
        2. 
        """
        location_id = False
        data_ids = self.search(cr, uid, [('activity_id', '=', activity_id)])
        data = self.browse(cr, uid, data_ids, context=context)[0]

        if 'location_id' in self._columns.keys():
            location_id = data.location_id.id if data.location_id else False
        if not location_id:
            location_id = data.activity_id.patient_id.current_location_id.id
        if not location_id:
            location_id = data.activity_id.spell_activity_id and data.activity_id.spell_activity_id.location_id.id or False
        if not location_id:
            location_id = data.activity_id.parent_id.location_id.id if data.activity_id.parent_id else False
        return location_id

    def get_activity_patient_id(self, cr, uid, activity_id, context=None):
        patient_id = False
        data_ids = self.search(cr, uid, [('activity_id', '=', activity_id)])
        data = self.browse(cr, uid, data_ids, context)[0]

        if 'patient_id' in self._columns.keys():
            patient_id = data.patient_id and data.patient_id.id or False
        return patient_id
    
    def get_activity_user_ids(self, cr, uid, activity_id, context=None):
        activity_pool = self.pool['nh.activity']
        cr.execute("select location_id from nh_activity where id = %s" % activity_id)
        if not cr.fetchone()[0]:
            return []
        sql = """
                select 
                    activity_id,
                    array_agg(user_id) as user_ids
                from     
                    (select distinct on (activity.id, ulr.user_id)
                        activity.id as activity_id,
                        ulr.user_id
                    from user_location_rel ulr
                    inner join res_groups_users_rel gur on ulr.user_id = gur.uid
                    inner join ir_model_access access on access.group_id = gur.gid and access.perm_responsibility = true
                    inner join ir_model model on model.id = access.model_id
                    inner join nh_activity activity on model.model = activity.data_model 
                        and activity.location_id = ulr.location_id
                        and activity.id = {activity_id}) data
                group by activity_id                
                """.format(activity_id=activity_id)
        cr.execute(sql)
        res = cr.dictfetchone()
        user_ids = list(res and set(res['user_ids']) or [])
        activity = activity_pool.browse(cr, uid, activity_id, context=context)
        follower_ids = [user.id for user in activity.patient_id.follower_ids]
        user_ids += follower_ids
        return list(set(user_ids))

    def trigger_policy(self, cr, uid, activity_id, location_id=None, case=False, context=None):
        """
        triggers the list of activities in the _POLICY['activities'] list.
        location_id [optional]. Required for context checking.
        - Every element in the list is a dictionary that contain the following keys:
            model: name of the data_model of the activity that is going to be triggered
            context: name of the context if the activity is only triggered in a specific context
            type: start, schedule, complete or recurring. Will do different actions with the created activity.
            data: data to submit.
            create_data: data to add on creation. Dictionary that contains the following structure:
                key: value
                being key the name of the attribute where we want to store the value and value the place to browse it from
                the current activity. i.e. 'location_id': 'data_ref.location_id.id' will add vals {'location_id': activity.data_ref.location_id.id}
        """
        activity_pool = self.pool['nh.activity']
        spell_pool = self.pool['nh.clinical.spell']
        location_pool = self.pool['nh.clinical.location']
        if self._POLICY.get('activities', []):
            activity = activity_pool.browse(cr, SUPERUSER_ID, activity_id, context)
            spell_id = spell_pool.get_by_patient_id(cr, SUPERUSER_ID, activity.data_ref.patient_id.id, context=context)
            spell_activity_id = spell_pool.browse(cr, uid, spell_id, context=context).activity_id.id if spell_id else False
        else:
            return True
        for trigger_activity in self._POLICY.get('activities', []):
            if case and trigger_activity.get('case') != case:
                continue
            pool = self.pool[trigger_activity['model']]
            if trigger_activity.get('context') and location_id:
                location = location_pool.browse(cr, uid, location_id, context=context)
                if not any([c.name == trigger_activity.get('context') for c in location.context_ids]):
                    continue
            if trigger_activity.get('domains'):
                break_trigger = False
                for domain in trigger_activity.get('domains'):
                    domain_pool = self.pool.get(domain['object'])
                    search_domain = domain['domain'] + [['parent_id', '=', spell_activity_id]]
                    if domain_pool.search(cr, uid, search_domain, context=context):
                        break_trigger = True
                if break_trigger:
                    continue
            if trigger_activity.get('cancel_others'):
                activity_pool.cancel_open_activities(cr, uid, spell_activity_id, pool._name, context=context)
            data = {
                'patient_id': activity.data_ref.patient_id.id
            }
            if trigger_activity.get('create_data'):
                for key in trigger_activity['create_data'].keys():
                    data[key] = eval(trigger_activity['create_data'][key])
            ta_activity_id = pool.create_activity(cr, SUPERUSER_ID, {
                'patient_id': activity.patient_id.id,
                'parent_id': spell_activity_id,
                'creator_id': activity_id
            }, data, context=context)
            if trigger_activity['type'] == 'recurring':
                frequency = activity_pool.browse(cr, SUPERUSER_ID, ta_activity_id, context=context).data_ref.frequency
                date_schedule = (dt.now()+td(minutes=frequency)).strftime(DTF)
            else:
                date_schedule = dt.now()+td(minutes=30)
            if trigger_activity['type'] == 'start':
                activity_pool.start(cr, SUPERUSER_ID, ta_activity_id, context=context)
            elif trigger_activity['type'] == 'complete':
                if trigger_activity.get('data'):
                    activity_pool.submit(cr, SUPERUSER_ID, ta_activity_id, trigger_activity['data'], context=context)
                activity_pool.complete(cr, SUPERUSER_ID, ta_activity_id, context=context)
            else:
                activity_pool.schedule(cr, SUPERUSER_ID, ta_activity_id, date_schedule, context=context)
        return True


class nh_clinical_activity_access(orm.Model):    
    _name = 'nh.clinical.activity.access'
    _auto = False
    _columns = {
        'user_id': fields.many2one('res.users', 'User'),
        'location_ids_text': fields.text('Location IDS Text'),
        'parent_location_ids_text': fields.text('Parent Location IDS Text'),
        'location_activity_ids_text': fields.text('Activity IDS Text'),
        'parent_location_activity_ids_text': fields.text('Parent Location Activity IDS Text'),      
                }

    def init(self, cr):
         
        cr.execute("""  
            drop view if exists nh_clinical_activity_access;
            create or replace view 
            nh_clinical_activity_access as(
    with 
        recursive route(level, path, parent_id, id) as (
                select 0, id::text, parent_id, id 
                from nh_clinical_location 
                where parent_id is null
            union
                select level + 1, path||','||location.id, location.parent_id, location.id 
                from nh_clinical_location location 
                join route on location.parent_id = route.id
        ),
        location_parents as (
            select 
                id as location_id, 
                ('{'||path||'}')::int[] as ids 
            from route
            order by path
        ),
        user_access as (
            select
                u.id as user_id,
                array_agg(access.model_id) as model_ids -- can be responsible for
            from res_users u
            inner join res_groups_users_rel gur on u.id = gur.uid

            inner join ir_model_access access on access.group_id = gur.gid and access.perm_responsibility = true
            group by u.id
        ),
        
        user_location as (
            select
                ulr.user_id,
                array_agg(ulr.location_id) as location_ids
            from user_location_rel ulr
            group by ulr.user_id
        ),
        
       user_location_parents_map as (
           select distinct
                   user_location.user_id,
                   parent_location_id
           from user_location
           inner join location_parents on user_location.location_ids && array[location_parents.location_id]
           inner join unnest(location_parents.ids) as parent_location_id on array[parent_location_id] && location_parents.ids
       ),
       user_location_parents as (
               select
                   user_id,
                array_agg(parent_location_id) as ids
            from user_location_parents_map
            group by user_id
        ),
        user_activity as (
            select
                user_location.user_id,
                array_agg(activity.id) as activity_ids
            from user_location
            inner join user_access on user_location.user_id = user_access.user_id
            inner join nh_activity activity on array[activity.location_id] && user_location.location_ids
            inner join ir_model model on model.model = activity.data_model and array[model.id] && user_access.model_ids

            group by user_location.user_id            
        ),
        user_parent_location_activity as(
            select
                user_location_parents.user_id,
                array_agg(activity.id) as ids
            from user_location_parents
            inner join nh_activity activity on array[activity.location_id] && user_location_parents.ids
            group by user_location_parents.user_id
        )
        
select
    user_access.user_id as id,
    user_access.user_id,
    user_location.location_ids::text as location_ids_text,
    user_location_parents.ids::text as parent_location_ids_text,
    user_activity.activity_ids::text as location_activity_ids_text,
    user_parent_location_activity.ids::text as parent_location_activity_ids_text,
    user_location.location_ids as location_ids,
    user_location_parents.ids as parent_location_ids,
    user_activity.activity_ids as location_activity_ids,
    user_parent_location_activity.ids as parent_location_activity_ids
from user_access
inner join user_location on user_location.user_id = user_access.user_id
inner join user_activity on user_activity.user_id = user_access.user_id
inner join user_location_parents on user_location_parents.user_id = user_access.user_id
inner join user_parent_location_activity on user_parent_location_activity.user_id = user_access.user_id
            );                 
        """)






