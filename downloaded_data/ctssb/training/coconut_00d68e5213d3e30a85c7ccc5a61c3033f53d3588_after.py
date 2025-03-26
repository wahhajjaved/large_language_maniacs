# -*- coding: utf-8 -*-

from datetime import datetime
from bson import ObjectId

from tornado.web import HTTPError

from common.decorators import admin_auth_async, parse_argument

from handlers.base import JsonHandler
from models.ticket import TicketTypeModel, TicketOrderModel, TicketModel
from models.content import ContentModel
from models.user import UserModel

from models import create_user_v2, send_sms

from services.slack import SlackService
from services.config import ConfigService


class TicketTypeHandler(JsonHandler):
    @admin_auth_async
    async def post(self, *args, **kwargs):
        content_oid = self.json_decoded_body.get('content_oid', None)
        if not content_oid or len(content_oid) != 24:
            raise HTTPError(400, self.set_error(1, 'invalid content_oid'))
        content = await ContentModel.get_id(ObjectId(content_oid))
        if not content:
            raise HTTPError(400, self.set_error(2, 'not exist content'))
        ticket_types_count = await TicketTypeModel.count({'content_oid': content['_id'], 'enabled': True})
        if ticket_types_count >= TicketTypeModel.MAX:
            raise HTTPError(400, self.set_error(3, 'exceed max ticket type count'))
        ticket_types = self.json_decoded_body.get('ticket_types', None)
        if not ticket_types:
            raise HTTPError(400, self.set_error(1, 'invalid ticket_types'))
        if len(ticket_types) > TicketTypeModel.MAX - ticket_types_count:
            raise HTTPError(400, self.set_error(3, 'exceed count to make ticket type'))
        res = list()
        for tt in ticket_types:
            ticket_type = self.validate_ticket_type(tt)
            doc = dict(
                type='network',
                content_oid=content['_id'],
                admin_oid=self.current_user['_id'],
                name=ticket_type['name'],
                desc=dict(
                    value=ticket_type['desc'],
                    enabled=True
                ),
                sales_date=ticket_type['sales_date'],
                price=ticket_type['price'],
                color=ticket_type['color'],
                fpfg=ticket_type['fpfg']
            )
            ttm = TicketTypeModel(raw_data=doc)
            res.append(await ttm.insert())
        text = '\n'.join(['<%s> / %s / %d원 / %d장 (스프레드 %s장)' % (content['name'], tt['name'], tt['price'], tt['fpfg']['limit'], tt['fpfg']['spread']) for tt in ticket_types])
        slack_msg = [
            {
                'title': '[%s] 티켓생성' % (ConfigService().client['application']['name']),
                'title_link': '%s://%s:%d/ticket/type;content_oid=%s' % (ConfigService().client['host']['protocol'], ConfigService().client['host']['host'], ConfigService().client['host']['port'], content_oid),
                'fallback': text,
                'text': text,
                'mrkdwn_in': ['text']
            }
        ]
        SlackService().client.chat.post_message(channel='#notice', text=None, attachments=slack_msg, as_user=False)
        self.response['data'] = res
        self.write_json()

    def validate_ticket_type(self, ticket_type):
        if 'name' not in ticket_type:
            raise HTTPError(400, self.set_error(1, 'invalid name'))
        if 'desc' not in ticket_type:
            raise HTTPError(400, self.set_error(1, 'invalid desc'))
        if 'sales_date' not in ticket_type or not isinstance(ticket_type['sales_date'], dict):
            raise HTTPError(400, self.set_error(1, 'invalid sales_date(object)'))
        try:
            ticket_type['sales_date']['start'] = datetime.strptime(ticket_type['sales_date']['start'], '%Y-%m-%dT%H:%M:%S')
            ticket_type['sales_date']['end'] = datetime.strptime(ticket_type['sales_date']['end'], '%Y-%m-%dT%H:%M:%S')
        except ValueError:
            raise HTTPError(400, self.set_error(1, 'invalid sales_date(start/end) format(YYYY-mm-ddTHH:MM:SS)'))
        if 'price' not in ticket_type or not isinstance(ticket_type['price'], int):
            raise HTTPError(400, self.set_error(1, 'invalid price'))
        if 'color' not in ticket_type or ticket_type['color'] not in TicketTypeModel.COLORS:
            raise HTTPError(400, self.set_error(1, 'invalid color (tkit-mint, tkit-coral, hangang-blue, ultra-bora, mustard-norang)'))
        if 'fpfg' not in ticket_type or not isinstance(ticket_type['fpfg'], dict):
            raise HTTPError(400, self.set_error(1, 'invalid fpfg(object)'))
        if 'limit' not in ticket_type['fpfg'] or 'spread' not in ticket_type['fpfg']:
            raise HTTPError(400, self.set_error(1, 'invalid fpfg.limit or fpfg.spread'))
        if ticket_type['fpfg']['limit'] == 0:
            raise HTTPError(400, self.set_error(1, 'invalid fpfg.limit'))
        if ticket_type['fpfg']['spread']:
            if ticket_type['fpfg']['spread'] <= ticket_type['fpfg']['limit']:
                raise HTTPError(400, self.set_error(1, 'invalid fpfg (spread more than limit)'))
        return ticket_type

    @admin_auth_async
    async def get(self, *args, **kwargs):
        _id = kwargs.get('_id', None)
        if not _id or len(_id) != 24:
            raise HTTPError(400, self.set_error(1, 'invalid id'))
        ticket_type = await TicketTypeModel.get_id(ObjectId(_id), fields=[('name'), ('desc'), ('sales_date'), ('price'), ('fpfg'), ('color'), ('content_oid')])
        if not ticket_type:
            raise HTTPError(400, self.set_error(2, 'not exist ticket type'))
        query = {
            '$and': [
                {'enabled': True},
                {'ticket_type_oid': ticket_type['_id']},
                {
                    '$or': [
                        {'status': TicketModel.Status.register.name},
                        {'status': TicketModel.Status.pay.name},
                        {'status': TicketModel.Status.use.name}
                    ]
                }
            ]
        }
        sales_count = await TicketModel.count(query)
        ticket_type['sales'] = {
            'count': sales_count,
            'limit': ticket_type['fpfg']['limit']
        }
        self.response['data'] = ticket_type
        self.write_json()

    @admin_auth_async
    async def put(self, *args, **kwargs):
        _id = kwargs.get('_id', None)
        if not _id or len(_id) != 24:
            raise HTTPError(400, self.set_error(1, 'invalid id'))
        ticket_type = await TicketTypeModel.get_id(ObjectId(_id), fields=[('name'), ('desc'), ('sales_date'), ('price'), ('fpfg'), ('color')])
        if not ticket_type:
            raise HTTPError(400, self.set_error(2, 'not exist ticket type'))
        name = self.json_decoded_body.get('name', None)
        desc = self.json_decoded_body.get('desc', None)
        sales_date = self.json_decoded_body.get('sales_date', None)
        try:
            sales_date['start'] = datetime.strptime(sales_date['start'], '%Y-%m-%dT%H:%M:%S')
            sales_date['end'] = datetime.strptime(sales_date['end'], '%Y-%m-%dT%H:%M:%S')
        except ValueError:
            raise HTTPError(400, self.set_error(1, 'invalid date(sales_date.start/sales_date.end) format(YYYY-mm-ddTHH:MM:SS)'))
        set_doc ={
            'name': name,
            'desc.value': desc,
            'sales_date': sales_date,
            'updated_at': datetime.utcnow()
        }
        query = {
            '$and': [
                {'enabled': True},
                {'ticket_type_oid': ticket_type['_id']},
                {
                    '$or': [
                        {'status': TicketModel.Status.register.name},
                        {'status': TicketModel.Status.pay.name},
                        {'status': TicketModel.Status.use.name}
                    ]
                }
            ]
        }
        sales_count = await TicketModel.count(query)
        fpfg = self.json_decoded_body.get('fpfg', None)
        if 'limit' in fpfg and fpfg['limit'] <= sales_count:
            raise HTTPError(400, set_error(3, 'can\'t set fpfg.limit (sold ticket count: %s)' % sales_count))
        else:
            set_doc['fpfg.limit'] = fpfg['limit']
        spread_count = await TicketModel.count({'ticket_type_oid': ticket_type['_id'], 'enabled': True})
        if 'spread' in fpfg and fpfg['spread'] <= spread_count:
            raise HTTPError(400, set_error(3, 'can\'t set fpfg.spread (spread ticket count: %s)' % spread_count))
        else:
            set_doc['fpfg.spread'] = fpfg['spread']
        updated = await TicketTypeModel.update({'_id': ticket_type['_id']}, {'$set': set_doc}, False, False)
        self.response['data'] = updated
        self.write_json()

    async def options(self, *args, **kwargs):
        self.response['message'] = 'OK'
        self.write_json()


class TicketTypeListHandler(JsonHandler):
    @admin_auth_async
    @parse_argument([('start', int, 0), ('size', int, 10), ('content_oid', str, None)])
    async def get(self, *args, **kwargs):
        parsed_args = kwargs.get('parsed_args')
        content_oid = parsed_args['content_oid']
        if not content_oid or len(content_oid) != 24:
            raise HTTPError(400, self.set_error(1, 'invalid content_oid'))
        query = {
            'content_oid': ObjectId(content_oid)
        }
        count = await TicketTypeModel.count(query)
        ticket_types = await TicketTypeModel.find(query, fields=[('name'), ('desc'), ('sales_date'), ('price'), ('fpfg'), ('color')], skip=parsed_args['start'], limit=parsed_args['size'])
        for tt in ticket_types:
            query = {
                '$and': [
                    {'enabled': True},
                    {'ticket_type_oid': tt['_id']},
                    {
                        '$or': [
                            {'status': TicketModel.Status.register.name},
                            {'status': TicketModel.Status.pay.name},
                            {'status': TicketModel.Status.use.name}
                        ]
                    }
                ]
            }
            sales_count = await TicketModel.count(query)
            tt['sales'] = {
                'count': sales_count,
                'limit': tt['fpfg']['limit']
            }
        self.response['data'] = ticket_types
        self.response['count'] = count
        self.write_json()

    async def options(self, *args, **kwargs):
        self.response['message'] = 'OK'
        self.write_json()


class TicketTypeInfoHandler(JsonHandler):
    @admin_auth_async
    async def get(self, *args, **kwargs):
        _id = kwargs.get('_id', None)
        if not _id or len(_id) != 24:
            raise HTTPError(400, self.set_error(1, 'invalid id'))
        ticket_type = await TicketTypeModel.get_id(ObjectId(_id), fields=[('fpfg')])
        if not ticket_type:
            raise HTTPError(400, self.set_error(2, 'not exist ticket type'))
        ticket_count = await TicketModel.count({'ticket_type_oid': ticket_type['_id'], 'enabled': True})
        self.response['data'] = {
            'spread': ticket_type['fpfg']['spread'],
            'ticket_count': ticket_count
        }
        self.write_json()

    async def options(self, *args, **kwargs):
        self.response['message'] = 'OK'
        self.write_json()


class TicketOrderHandler(JsonHandler):
    @admin_auth_async
    async def post(self, *args, **kwargs):
        ticket_type_oid = self.json_decoded_body.get('ticket_type_oid', None)
        if not ticket_type_oid or len(ticket_type_oid) != 24:
            raise HTTPError(400, self.set_error(1, 'invalid ticket_type_oid'))
        ticket_type = await TicketTypeModel.get_id(ObjectId(ticket_type_oid))
        if not ticket_type:
            raise HTTPError(400, self.set_error(2, 'not exist ticket type'))
        qty = self.json_decoded_body.get('qty', None)
        if not qty:
            raise HTTPError(400, self.set_error(1, 'invalid qty'))
        ticket_count = await TicketModel.count({'ticket_type_oid': ticket_type['_id'], 'enabled': True})
        if ticket_type['fpfg']['spread'] and qty > (ticket_type['fpfg']['spread'] - ticket_count):
            raise HTTPError(400, self.set_error(3, 'exceed available qty'))
        name = self.json_decoded_body.get('name', None)
        if not name or len(name) == 0:
            raise HTTPError(400, self.set_error(1, 'invalid name'))
        mobile = self.json_decoded_body.get('mobile', None)
        if not mobile or not isinstance(mobile, dict):
            raise HTTPError(400, self.set_error(1, 'invalid mobile(object)'))
        sms = self.json_decoded_body.get('sms', None)
        if not sms or len(sms) == 0:
            raise HTTPError(400, self.set_error(1, 'invalid sms'))
        user_oid = await create_user_v2(mobile, name)
        doc = {
            'type': 'network',
            'content_oid': ticket_type['content_oid'],
            'admin_oid': self.current_user['_id'],
            'ticket_type_oid': ticket_type['_id'],
            'receiver': {
                'mobile': mobile,
                'name': name
            },
            'qty': qty,
            'user_oid': user_oid
        }
        ticket_order = TicketOrderModel(raw_data=doc)
        ticket_order_oid = await ticket_order.insert()
        for i in range(qty):
            doc = {
                'type': 'network',
                'content_oid': ticket_type['content_oid'],
                'ticket_type_oid': ticket_type['_id'],
                'ticket_order_oid': ticket_order_oid,
                'price': ticket_type['price'],
                'status': 'send',
                'receive_user_oid': user_oid
            }
            ticket = TicketModel(raw_data=doc)
            await ticket.insert()
        if mobile['number'].startswith('0'):
            to_mobile_number = '%s%s' % (mobile['country_code'], mobile['number'][1:])
        else:
            to_mobile_number = '%s%s' % (mobile['country_code'], mobile['number'])
        is_sent_receiver = await send_sms(
            {
                'type': 'unicode',
                'from': 'tkit',
                'to': to_mobile_number,
                'text': sms
            }
        )
        content = await ContentModel.get_id(ticket_type['content_oid'], fields=[('name')])
        slack_msg = [
            {
                'title': '[%s] 티켓전송' % (ConfigService().client['application']['name']),
                'title_link': '%s://%s:%d/ticket/order;ticket_type_oid=%s' % (ConfigService().client['host']['protocol'], ConfigService().client['host']['host'], ConfigService().client['host']['port'], ticket_type_oid),
                'fallback': '[%s] 티켓전송 / <%s> / %s / %d원 / %d장 / %s 전달' % (ConfigService().client['application']['name'], content['name'], ticket_type['name'], ticket_type['price'], qty, name),
                'text': '<%s> / %s / %d원 / %d장 / %s 전달' % (content['name'], ticket_type['name'], ticket_type['price'], qty, name),
                'mrkdwn_in': ['text']
            }
        ]
        SlackService().client.chat.post_message(channel='#notice', text=None, attachments=slack_msg, as_user=False)
        self.response['data'] = {
            'ticket_order_oid': ticket_order_oid,
            'ticket_count': i+1,
            'sms': is_sent_receiver
        }
        self.write_json()

    async def options(self, *args, **kwargs):
        self.response['message'] = 'OK'
        self.write_json()


class TicketOrderListHandler(JsonHandler):
    @admin_auth_async
    @parse_argument([('start', int, 0), ('size', int, 10), ('ticket_type_oid', str, None)])
    async def get(self, *args, **kwargs):
        parsed_args = kwargs.get('parsed_args')
        ticket_type_oid = parsed_args['ticket_type_oid']
        if not ticket_type_oid or len(ticket_type_oid) != 24:
            raise HTTPError(400, self.set_error(1, 'invalid ticket_type_oid'))
        query = {
            'ticket_type_oid': ObjectId(ticket_type_oid),
            'enabled': True
        }
        count = await TicketOrderModel.count(query)
        ticket_orders = await TicketOrderModel.find(query, fields=[('created_at'), ('qty'), ('receiver'), ('user_oid')], skip=parsed_args['start'], limit=parsed_args['size'])
        self.response['data'] = ticket_orders
        self.response['count'] = count
        self.write_json()

    async def options(self, *args, **kwargs):
        self.response['message'] = 'OK'
        self.write_json()


class TicketListHandler(JsonHandler):
    @admin_auth_async
    @parse_argument([('start', int, 0), ('size', int, 10), ('ticket_order_oid', str, None)])
    async def get(self, *args, **kwargs):
        parsed_args = kwargs.get('parsed_args')
        ticket_order_oid = parsed_args['ticket_order_oid']
        if not ticket_order_oid or len(ticket_order_oid) != 24:
            raise HTTPError(400, self.set_error(1, 'invalid ticket_order_oid'))
        query = {
            'ticket_order_oid': ObjectId(ticket_order_oid),
            'enabled': True
        }
        count = await TicketModel.count(query)
        tickets = await TicketModel.find(query, fields={'updated_at': True, 'receive_user_oid': True}, skip=parsed_args['start'], limit=parsed_args['size'], sort=[('updated_at', -1)])
        for t in tickets:
            user = await UserModel.get_id(t['receive_user_oid'], fields={'_id': False, 'mobile': True, 'name': True, 'last_name': True})
            t['receive_user'] = user
            t.pop('receive_user_oid')
        self.response['data'] = tickets
        self.response['count'] = count
        self.write_json()

    async def options(self, *args, **kwargs):
        self.response['message'] = 'OK'
        self.write_json()


class TicketHistoryListHandler(JsonHandler):
    @admin_auth_async
    @parse_argument([('ticket_oid', str, None)])
    async def get(self, *args, **kwargs):
        parsed_args = kwargs.get('parsed_args')
        ticket_oid = parsed_args['ticket_oid']
        if not ticket_oid or len(ticket_oid) != 24:
            raise HTTPError(400, self.set_error(1, 'invalid ticket_oid'))
        ticket = await TicketModel.get_id(ObjectId(ticket_oid), fields={'send_user_oid': True, 'receive_user_oid': True, 'history_send_user_oids': True})
        if not ticket:
            raise HTTPError(400, self.set_error(2, 'not exsit ticket'))
        history = list()
        if 'history_send_user_oids' in ticket:
            ticket['history_send_user_oids'].append(ticket['receive_user_oid'])
            for user_oid in ticket['history_send_user_oids']:
                user = await UserModel.get_id(user_oid, fields={'mobile': True, 'name': True, 'last_name': True, '_id': False})
                if user:
                    history.append(user)
        history.reverse()
        self.response['data'] = history
        self.write_json()

    async def options(self, *args, **kwargs):
        self.response['message'] = 'OK'
        self.write_json()
