# -*- coding: utf-8 -*-
import uuid
from datetime import datetime, date, timedelta

from flask import request
from sqlalchemy import cast, Date, extract

from planet.common.error_response import StatusError, ParamsError, NotFound
from planet.common.params_validates import parameter_required
from planet.common.success_response import Success
from planet.common.token_handler import token_required, get_current_user
from planet.extensions.register_ext import db
from planet.extensions.validates.activty import GuessNumCreateForm, GuessNumGetForm, GuessNumHistoryForm
from planet.models import GuessNum, CorrectNum, ProductSku, ProductItems, GuessAwardFlow, Products, ProductBrand, \
    UserAddress, AddressArea, AddressCity, AddressProvince, OrderMain, OrderPart, OrderPay, GuessNumAwardApply
from planet.config.enums import ActivityRecvStatus, OrderFrom, Client, PayType
from planet.extensions.register_ext import alipay, wx_pay
from .COrder import COrder


class CGuessNum(COrder):

    @token_required
    def creat(self):
        """参与活动"""
        date_now = datetime.now()
        if date_now.hour > 15:
            raise StatusError('15点以后不开放')
        form = GuessNumCreateForm().valid_data()
        gnnum = form.gnnum.data
        usid = request.user.id

        # if date_now.hour > 15:  # 15点以后参与次日的
        #     gndate = date.today() + timedelta(days=1)
        # else:
        #     gndate = date.today()

        with db.auto_commit():
            today = date.today()

            today_raward = GuessNumAwardApply.query.filter_by_().filter_(
                GuessNumAwardApply.AgreeStartime <= today,
                GuessNumAwardApply.AgreeEndtime >= today,
                GuessNumAwardApply.GNAAstatus == 10
            ).first_('今日活动不开放')

            guess_instance = GuessNum.create({
                'GNid': str(uuid.uuid1()),
                'GNnum': gnnum,
                'USid': usid,
                'PRid': today_raward.PRid,
                'SKUid': today_raward.SKUid,
                'Price': today_raward.SKUprice,
                # 'GNdate': gndate
            })
            db.session.add(guess_instance)
        return Success('参与成功')

    @token_required
    def get(self):
        """获得单日个人参与"""
        form = GuessNumGetForm().valid_data()
        usid = request.user.id
        join_history = GuessNum.query.filter_(
            GuessNum.USid == usid,
            cast(GuessNum.createtime, Date) == form.date.data,
            GuessNum.isdelete == False
        ).first_()
        if not join_history:
            if form.date.data.date() == date.today():
                return Success('今日未参与')
            elif form.date.data.date() == date.today() - timedelta(days=1):
                raise NotFound('昨日未参与')
            else:
                raise NotFound('未参与')
        if join_history:
            correct_num = CorrectNum.query.filter(
                CorrectNum.CNdate == join_history.GNdate
            ).first()
            join_history.fill('correct_num', correct_num)
            if not correct_num:
                result = 'not_open'
            else:
                correct_num.hide('CNid')
                if correct_num.CNnum.strip('0') == join_history.GNnum.strip('0'):
                    result = 'correct'
                else:
                    result = 'uncorrect'
            join_history.fill('result', result).hide('USid', 'PRid')

            product = Products.query.filter_by_({'PRid': join_history.PRid}).first()
            product.fields = ['PRid', 'PRmainpic', 'PRtitle']
            join_history.fill('product', product)
        return Success(data=join_history)

    @token_required
    def history_join(self):
        """获取历史参与记录"""
        form = GuessNumHistoryForm().valid_data()
        year = form.year.data
        month = form.month.data
        try:
            year_month = datetime.strptime(year + '-' + month,  '%Y-%m')
        except ValueError as e:
            raise ParamsError('时间参数异常')
        usid = request.user.id
        join_historys = GuessNum.query.filter(
            extract('month', GuessNum.GNdate) == year_month.month,
            extract('year', GuessNum.GNdate) == year_month.year,
            GuessNum.USid == usid
        ).order_by(GuessNum.GNdate.desc()).group_by(GuessNum.GNdate).all()
        correct_count = 0  # 猜对次数
        for join_history in join_historys:
            correct_num = CorrectNum.query.filter(
                CorrectNum.CNdate == join_history.GNdate
            ).first()
            join_history.fill('correct_num', correct_num)
            if not correct_num:
                result = 'not_open'
            else:
                correct_num.hide('CNid')
                if correct_num.CNnum.strip('0') == join_history.GNnum.strip('0'):
                    result = 'correct'
                    correct_count += 1
                else:
                    result = 'uncorrect'
            join_history.fill('result', result).hide('USid', 'PRid')

            product = Products.query.filter_by_({'PRid': join_history.PRid}).first()
            product.fields = ['PRid', 'PRmainpic', 'PRtitle']
            join_history.fill('product', product)
        return Success(data=join_historys).get_body(correct_count=correct_count)

    @token_required
    def recv_award(self):
        data = parameter_required(('gnid', 'skuid', 'omclient', 'uaid', 'opaytype'))
        gnid = data.get('gnid')
        skuid = data.get('skuid')
        usid = request.user.id
        uaid = data.get('uaid')
        opaytype = data.get('opaytype')
        try:
            omclient = int(data.get('omclient', Client.wechat.value))  # 下单设备
            Client(omclient)
        except Exception as e:
            raise ParamsError('客户端或商品来源错误')

        with db.auto_commit():
            s_list = []
            # 参与记录
            guess_num = GuessNum.query.filter_by_().filter_by_({
                'SKUid': skuid,
                'USid': usid,
                'GNid': gnid
            }).first_('未参与')
            price = guess_num.Price

            # 领奖流水
            guess_award_flow_instance = GuessAwardFlow.query.filter_by_({
                'GNid': gnid,
                'GAFstatus': ActivityRecvStatus.wait_recv.value,
            }).first_('未中奖或已领奖')
            sku_instance = ProductSku.query.filter_by_({"SKUid": skuid}).first_('sku: {}不存在'.format(skuid))
            product_instance = Products.query.filter_by_({"PRid": sku_instance.PRid}).first_('商品已下架')
            pbid = product_instance.PBid
            product_brand_instance = ProductBrand.query.filter_by({'PBid': pbid}).first_()
            # 领奖状态改变
            guess_award_flow_instance.GAFstatus = ActivityRecvStatus.ready_recv.value
            s_list.append(guess_award_flow_instance)
            # 用户的地址信息
            user_address_instance = UserAddress.query.filter_by_({'UAid': uaid, 'USid': usid}).first_('地址信息不存在')
            omrecvphone = user_address_instance.UAphone
            areaid = user_address_instance.AAid
            # 地址拼接
            area, city, province = db.session.query(AddressArea, AddressCity, AddressProvince).filter(
                AddressArea.ACid == AddressCity.ACid, AddressCity.APid == AddressProvince.APid).filter(
                AddressArea.AAid == areaid).first_('地址有误')
            address = getattr(province, "APname", '') + getattr(city, "ACname", '') + getattr(
                area, "AAname", '')
            omrecvaddress = address + user_address_instance.UAtext
            omrecvname = user_address_instance.UAname

            # 创建订单
            omid = str(uuid.uuid1())
            opayno = self.wx_pay.nonce_str
            # 主单
            order_main_dict = {
                'OMid': omid,
                'OMno': self._generic_omno(),
                'OPayno': opayno,
                'USid': usid,
                'OMfrom': OrderFrom.guess_num_award.value,
                'PBname': product_brand_instance.PBname,
                'PBid': pbid,
                'OMclient': omclient,
                'OMfreight': 0,  # 运费暂时为0
                'OMmount': price,
                'OMmessage': data.get('ommessage'),
                'OMtrueMount': price,
                # 收货信息
                'OMrecvPhone': omrecvphone,
                'OMrecvName': omrecvname,
                'OMrecvAddress': omrecvaddress,
            }
            order_main_instance = OrderMain.create(order_main_dict)
            s_list.append(order_main_instance)
            user = get_current_user()
            order_part_dict = {
                'OMid': omid,
                'OPid': str(uuid.uuid1()),
                'SKUid': skuid,
                'PRattribute': product_instance.PRattribute,
                'SKUattriteDetail': sku_instance.SKUattriteDetail,
                'PRtitle': product_instance.PRtitle,
                'SKUprice': sku_instance.SKUprice,
                'PRmainpic': product_instance.PRmainpic,
                'OPnum': 1,
                'PRid': product_instance.PRid,
                'OPsubTotal': price,
                # 副单商品来源
                'PRfrom': product_instance.PRfrom,
                'PRcreateId': product_instance.CreaterId,
                'UPperid': user.USsupper1,
                'UPperid2': user.USsupper2,
                # todo 活动佣金设置
            }
            order_part_instance = OrderPart.create(order_part_dict)
            s_list.append(order_part_instance)
            # 支付数据表
            order_pay_dict = {
                'OPayid': str(uuid.uuid1()),
                'OPayno': opayno,
                'OPayType': opaytype,
                'OPayMount': price,
            }
            order_pay_instance = OrderPay.create(order_pay_dict)
            s_list.append(order_pay_instance)
            db.session.add_all(s_list)
        # 生成支付信息
        body = product_instance.PRtitle
        user = get_current_user()
        openid = user.USopenid1 or user.USopenid2
        pay_args = self._pay_detail(omclient, opaytype, opayno, float(price), body, openid=openid)
        response = {
            'pay_type': PayType(opaytype).name,
            'opaytype': opaytype,
            'args': pay_args
        }
        return Success('创建订单成功', data=response)
