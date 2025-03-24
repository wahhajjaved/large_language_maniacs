# -*- coding: utf-8 -*-

'''
author:       Jimmy
contact:      234390130@qq.com
file:         liao.py
time:         2017/12/25 上午11:22
description: 

'''

__author__ = 'Jimmy'
from trade.tradeStrategy import *
from utils.ta import *
import utils.tools as tl
import logging as log
from utils import message as msg
from datetime import datetime as dt


class Liao(TradeStrategy):
    def initialize(self):
        self.context.universe = ['y1805',"SF805","al1802","v1805",'rb1805']
        self.context.strategy_name = 'liao_trend'
        self.context.strategy_id = 'liao_trend_v1.0'
        self.context.bar_frequency = '30M'
        self.context.init_cash = 100000
        self.context.vars = {}

        self.context.user_id = '00300508'
        self.context.password = 'zhouyu123'
        self.context.broker_id = '6000'
        self.context.trade_front = 'tcp://101.231.162.58:41205'
        self.context.market_front = 'tcp://101.231.162.58:41213'

        var = Variables("y1805")
        var.slippage = 2
        var.open_thres = 12  # 开仓tick倍数
        var.open_num_from_big_bar = 4 # 从大阳线后第5个开始判断是否开仓
        var.max_open_num_from_big_bar = 24 # 最多判断连续25个
        var.stop_gain_thres = 0.4     # 止盈后回撤系数
        var.gain_thres = 1.01         # 止盈开始系数
        var.two_big_bar_stop_thres = 5 # 两根大阳线后续按tick 跌破5*tick_size止损
        var.stop_loss_thres = 0.02    # 按账户收益止损系数
        var.second_big_bar_open_thres = 20 # 第二根大阳线开仓系数
        var.max_reverse_count = 5  # 最大反手次数
        self.context.vars["y1805"] = var

        var = Variables("SF805")
        var.slippage = 2
        var.open_thres = 20  # 开仓tick倍数
        var.open_num_from_big_bar = 4  # 从大阳线后第5个开始判断是否开仓
        var.max_open_num_from_big_bar = 24  # 最多判断连续25个
        var.stop_gain_thres = 0.4  # 止盈后回撤系数
        var.gain_thres = 1.01  # 止盈开始系数
        var.two_big_bar_stop_thres = 5  # 两根大阳线后续按tick 跌破5*tick_size止损
        var.stop_loss_thres = 0.02  # 按账户收益止损系数
        var.second_big_bar_open_thres = 30  # 第二根大阳线开仓系数
        var.max_reverse_count = 5  # 最大反手次数
        self.context.vars["SF805"] = var

        var = Variables("al1802")
        var.slippage = 2
        var.open_thres = 20  # 开仓tick倍数
        var.open_num_from_big_bar = 4  # 从大阳线后第5个开始判断是否开仓
        var.max_open_num_from_big_bar = 24  # 最多判断连续25个
        var.stop_gain_thres = 0.4  # 止盈后回撤系数
        var.gain_thres = 1.01  # 止盈开始系数
        var.two_big_bar_stop_thres = 5  # 两根大阳线后续按tick 跌破5*tick_size止损
        var.stop_loss_thres = 0.02  # 按账户收益止损系数
        var.second_big_bar_open_thres = 30  # 第二根大阳线开仓系数
        var.max_reverse_count = 5  # 最大反手次数
        self.context.vars["al1802"] = var

        var = Variables("v1805")
        var.slippage = 2
        var.open_thres = 10  # 开仓tick倍数
        var.open_num_from_big_bar = 4  # 从大阳线后第5个开始判断是否开仓
        var.max_open_num_from_big_bar = 24  # 最多判断连续25个
        var.stop_gain_thres = 0.4  # 止盈后回撤系数
        var.gain_thres = 1.01  # 止盈开始系数
        var.two_big_bar_stop_thres = 5  # 两根大阳线后续按tick 跌破5*tick_size止损
        var.stop_loss_thres = 0.02  # 按账户收益止损系数
        var.second_big_bar_open_thres = 12 # 第二根大阳线开仓系数
        var.max_reverse_count = 5  # 最大反手次数
        self.context.vars["v1805"] = var

        var = Variables("rb1805")
        var.slippage = 2
        var.open_thres = 20  # 开仓tick倍数
        var.open_num_from_big_bar = 4  # 从大阳线后第5个开始判断是否开仓
        var.max_open_num_from_big_bar = 24  # 最多判断连续25个
        var.stop_gain_thres = 0.4  # 止盈后回撤系数
        var.gain_thres = 1.01  # 止盈开始系数
        var.two_big_bar_stop_thres = 5  # 两根大阳线后续按tick 跌破5*tick_size止损
        var.stop_loss_thres = 0.02  # 按账户收益止损系数
        var.second_big_bar_open_thres = 30  # 第二根大阳线开仓系数
        var.max_reverse_count = 5  # 最大反手次数
        self.context.vars["rb1805"] = var

        tl.config_logging()


    def on_trade(self, trade):
        var = self.context.vars[trade.symbol]
        symbol_obj = self.context.symbol_infos[trade.symbol]
        if trade.offset == OPEN:
            var.direction = trade.direction
            var.open_vol += trade.vol
            var.open_price = trade.price
            var.open_margin = var.open_vol * symbol_obj.contract_size * var.open_price * symbol_obj.broker_margin * 0.01
        else:
            var.open_vol -= trade.vol
            if var.open_vol == 0:
                # 清仓初始化各种中间变量
                var.initialize()
                if var.reverse_flag:
                    var.reverse_flag = False
                    var.reverse_count += 1
                    if trade.direction == SHORT and var.reverse_count <= var.max_reverse_count:
                        msg.send('%s 空单止损后反相开多' % trade.symbol)
                        log.info('%s 空单止损后反相开多' % trade.symbol)

                        self.order(trade.symbol, LONG, OPEN, var.limit_vol,
                                   limit_price=var.last_price + var.slippage * symbol_obj.tick_size)
                    elif var.direction == LONG and var.reverse_count <= var.max_reverse_count:
                        msg.send('%s 多单止损后反相开空' % trade.symbol)
                        log.info('%s 多单止损后反相开空' % trade.symbol)

                        self.order(trade.symbol, SHORT, OPEN, var.limit_vol,
                                   limit_price=var.last_price - var.slippage * symbol_obj.tick_size)
                else:
                    # 平仓、止盈时 清空反手计数器
                    var.reverse_count = 0

    def handle_tick(self, tick):
        var = self.context.vars[tick.symbol]
        var.last_price = tick.last_price
        symbol_obj = self.context.symbol_infos[tick.symbol]
        # 止盈
        if self.pre_close(var, tick.symbol):
            self.stop_gain(var, tick)
            self.stop_loss(var, tick, symbol_obj)


    def handle_bar(self, bar):
        print('时间:%s %s' %(dt.now(), bar))
        # 撤单
        for sys_id, order in self.context.orders.items():
            if order.symbol == bar.symbol:
                self.cancel_order(order)
        var = self.context.vars[bar.symbol]
        symbol_obj = self.context.symbol_infos[var.symbol]
        # 判断是否需要平仓
        if self.pre_close(var, bar.symbol):
            self.close_signal(var, bar, symbol_obj)

        # 判断最大利润
        if var.open_vol > 0:
            delta = var.open_price - bar.close
            if var.direction == LONG:
                delta = bar.close - var.open_price
            if delta / var.open_price > var.gain_thres:
                var.gain_over_flag = True
                if delta > var.max_gain:
                    var.max_gain = delta

        if var.pre_bar_direction_flag == LONG:
            if bar.close - bar.open > var.open_thres * symbol_obj.tick_size and bar.close - var.big_bar_open < var.second_big_bar_open_thres * symbol_obj.tick_size:
                log.info('%s 按barj+k.close开多' % bar.symbol)
                msg.send('%s 按barj+k.close开多' % bar.symbol)

                if self.pre_open(var, bar.symbol):
                    self.order(bar.symbol, LONG, OPEN, var.limit_vol,
                               limit_price=bar.close + var.slippage * symbol_obj.tick_size)
                    var.open_by_two_big_bar_flag = True
                else:
                    msg.send('%s 按barj+k.close开多 有持仓或挂单舍弃开仓信号' % bar.symbol)
                    log.info('%s 按barj+k.close开多 有持仓或挂单舍弃开仓信号' % bar.symbol)

            if var.num_from_big_bar < var.open_num_from_big_bar:
                var.exchange_peak(bar.open)
                var.exchange_peak(bar.close)
                var.num_from_big_bar += 1
            elif var.num_from_big_bar < var.max_open_num_from_big_bar:
                var.exchange_peak(bar.open)
                var.exchange_peak(bar.close)
                var.num_from_big_bar += 1
                if bar.close > var.big_bar_close and var.min_price > var.big_bar_open and var.max_price > var.big_bar_close:
                    msg.send('%s 大阳线 N-J>=5开多' % bar.symbol)
                    log.info('%s 大阳线 N-J>=5开多' % bar.symbol)

                    if self.pre_open(var, bar.symbol):
                        self.order(bar.symbol, LONG,OPEN, var.limit_vol,limit_price=bar.close + var.slippage * symbol_obj.tick_size)
                    else:
                        msg.send('%s 大阳线 N-J>=5开多仓 有持仓或挂单舍弃开仓信号' % bar.symbol)
                        log.info('%s 大阳线 N-J>=5开多仓 有持仓或挂单舍弃开仓信号' % bar.symbol)

                elif var.min_price < var.big_bar_open and var.max_price < var.big_bar_close and bar.close < var.big_bar_open:
                    msg.send('%s 大阳线 N-J>=5开空' % bar.symbol)
                    log.info('%s 大阳线 N-J>=5开空' % bar.symbol)

                    if self.pre_open(var, bar.symbol):
                        self.order(bar.symbol, SHORT,OPEN, var.limit_vol,limit_price=bar.close - var.slippage * symbol_obj.tick_size)
                    else:
                        msg.send('%s 大阳线 N-J>=5开多空 有持仓或挂单舍弃开仓信号' % bar.symbol)
                        log.info('%s 大阳线 N-J>=5开多空 有持仓或挂单舍弃开仓信号' % bar.symbol)

                if var.num_from_big_bar == var.max_open_num_from_big_bar:
                    msg.send('%s 大阳线第25个bar重置清空信号' % bar.symbol)
                    log.info('%s 大阳线第25个bar重置清空信号' % bar.symbol)

                    var.clear_signal()
        elif var.pre_bar_direction_flag == SHORT:
            if bar.open - bar.close > var.open_thres * symbol_obj.tick_size and var.big_bar_open - bar.close < var.second_big_bar_open_thres * symbol_obj.tick_size:
                msg.send('%s 大阴线按barj+k.close开空' % bar.symbol)
                log.info('%s 大阴线按barj+k.close开空' % bar.symbol)

                if self.pre_open(var, bar.symbol):
                    self.order(bar.symbol, SHORT, OPEN, var.limit_vol,
                               limit_price=bar.close - var.slippage * symbol_obj.tick_size)
                    var.open_by_two_big_bar_flag = True
                else:
                    msg.send('%s 大阴线按barj+k.close开空 有持仓或挂单舍弃开仓信号' % bar.symbol)
                    log.info('%s 大阴线按barj+k.close开空 有持仓或挂单舍弃开仓信号' % bar.symbol)

            if var.num_from_big_bar < var.open_num_from_big_bar:
                var.exchange_peak(bar.open)
                var.exchange_peak(bar.close)
                var.num_from_big_bar += 1
            elif var.num_from_big_bar < var.max_open_num_from_big_bar:
                var.exchange_peak(bar.open)
                var.exchange_peak(bar.close)
                var.num_from_big_bar += 1
                if bar.close < var.big_bar_close and var.min_price < var.big_bar_close and var.max_price < var.big_bar_open:
                    msg.send('%s 大阴线 N-J>=5开空' % bar.symbol)
                    log.info('%s 大阴线 N-J>=5开空' % bar.symbol)

                    if self.pre_open(var, bar.symbol):
                        self.order(bar.symbol, SHORT,OPEN, var.limit_vol,limit_price=bar.close - var.slippage * symbol_obj.tick_size)
                    else:
                        msg.send('%s 大阴线 N-J>=5开空 有持仓或挂单舍弃开仓信号' % bar.symbol)
                        log.info('%s 大阴线 N-J>=5开空 有持仓或挂单舍弃开仓信号' % bar.symbol)

                elif var.min_price > var.big_bar_close and var.max_price > var.big_bar_open and bar.close > var.big_bar_open:
                    msg.send('%s 大阴线 N-J>=5开多' % bar.symbol)
                    log.info('%s 大阴线 N-J>=5开多' % bar.symbol)

                    if self.pre_open(var, bar.symbol):
                        self.order(bar.symbol, LONG,OPEN, var.limit_vol,limit_price=bar.close + var.slippage * symbol_obj.tick_size)
                    else:
                        msg.send('%s 大阴线 N-J>=5开多 有持仓或挂单舍弃开仓信号' % bar.symbol)
                        log.info('%s 大阴线 N-J>=5开多 有持仓或挂单舍弃开仓信号' % bar.symbol)

                if var.num_from_big_bar == var.max_open_num_from_big_bar:
                    msg.send('%s 大阴线第25个bar重置清空信号' % bar.symbol)
                    log.info('%s 大阴线第25个bar重置清空信号' % bar.symbol)

                    var.clear_signal()

        # msg.send('%s check 是否要转变信号' % bar.symbol)
        self.pre_bar_direction_flag(var,bar,symbol_obj)
        log.info(var)


    # 平仓
    def close_signal(self, var, bar, symbol_obj):
        if var.open_vol > 0:
            if var.direction == LONG:
                if bar.open - bar.close > var.open_thres * symbol_obj.tick_size:
                    msg.send('%s 持有多单后大阴线平仓' % bar.symbol)
                    log.info('%s 持有多单后大阴线平仓' % bar.symbol)

                    self.order(bar.symbol,LONG,CLOSE,var.open_vol,limit_price=bar.close -  var.slippage * symbol_obj.tick_size)
            elif var.direction == SHORT:
                if bar.close - bar.open > var.open_thres * symbol_obj.tick_size:
                    msg.send('%s 持有空单后大阳线平仓' % bar.symbol)
                    log.info('%s 持有空单后大阳线平仓' % bar.symbol)

                    self.order(bar.symbol,SHORT,CLOSE,var.open_vol,limit_price=bar.close +  var.slippage * symbol_obj.tick_size)
    # 止盈
    def stop_gain(self, var, tick):
        if var.direction != '':
            delta = var.open_price - tick.last_price
            if var.direction == LONG:
                delta = tick.last_price - var.open_price

            if var.gain_over_flag and delta / var.max_gain < var.stop_gain_thres:
                symbol_obj = self.context.symbol_infos[tick.symbol]
                if var.direction == LONG:
                    msg.send('%s 多单止盈 max_gain %s gain_now %s' % (tick.symbol,var.max_gain, delta))
                    log.info('%s 多单止盈 max_gain %s gain_now %s' % (tick.symbol,var.max_gain, delta))

                    self.order(tick.symbol,LONG,CLOSE,var.open_vol,limit_price=tick.last_price -  var.slippage * symbol_obj.tick_size)
                else:
                    msg.send('%s 空单止盈 max_gain %s gain_now %s' % (tick.symbol,var.max_gain, delta))
                    log.info('%s 空单止盈 max_gain %s gain_now %s' % (tick.symbol,var.max_gain, delta))

                    self.order(tick.symbol,SHORT,CLOSE,var.open_vol,limit_price=tick.last_price +  var.slippage * symbol_obj.tick_size)


    def stop_loss(self, var ,tick, symbol_obj):
        if var.direction != '':
            # 止损 1
            if var.open_by_two_big_bar_flag:
                if var.direction == SHORT:
                    if tick.last_price - var.open_price > var.two_big_bar_stop_thres * symbol_obj.tick_size:
                        msg.send('%s 两根大阴线开仓 5 tick_size 止损' % tick.symbol)
                        log.info('%s 两根大阴线开仓 5 tick_size 止损' % tick.symbol)

                        self.order(tick.symbol, SHORT, CLOSE, var.open_vol,
                                   limit_price=tick.last_price + var.slippage * symbol_obj.tick_size)
                        var.reverse_flag = True

                elif var.direction == LONG:
                    if var.open_price - tick.last_price > var.two_big_bar_stop_thres * symbol_obj.tick_size:
                        msg.send('%s 两根大阳线开仓 5 tick_size 止损' % tick.symbol)
                        log.info('%s 两根大阳线开仓 5 tick_size 止损' % tick.symbol)

                        self.order(tick.symbol,LONG,CLOSE,var.open_vol,limit_price=tick.last_price - var.slippage * symbol_obj.tick_size)
                    var.reverse_flag = True

            # 止损 2
            upnl = (var.open_price - tick.last_price) * var.open_vol * symbol_obj.contract_size
            if var.direction == SHORT:
                upnl = (tick.last_price - var.open_price) * var.open_vol * symbol_obj.contract_size
            if upnl < 0 and abs(upnl)/ var.open_margin > var.stop_loss_thres:
                if var.direction == SHORT:
                    msg.send('%s 空单损失超过0.02止损' % tick.symbol)
                    log.info('%s 空单损失超过0.02止损' % tick.symbol)

                    self.order(tick.symbol, SHORT, CLOSE, var.open_vol,
                               limit_price=tick.last_price + var.slippage * symbol_obj.tick_size)
                    var.reverse_flag = True

                elif var.direction == LONG:
                    msg.send('%s 多单损失超过0.02止损' % tick.symbol)
                    log.info('%s 多单损失超过0.02止损' % tick.symbol)

                    self.order(tick.symbol, LONG, CLOSE, var.open_vol,
                               limit_price=tick.last_price - var.slippage * symbol_obj.tick_size)
                    var.reverse_flag = True

    # 开仓方向判断
    def pre_bar_direction_flag(self, var, bar, symbol_obj):

        # check 是否要转变信号 无持仓无挂单
        if self.pre_signal(var, bar.symbol):
            if bar.close - bar.open > var.open_thres * symbol_obj.tick_size:
                if var.pre_bar_direction_flag == SHORT:
                    if bar.close > var.big_bar_open:
                        var.clear_signal()
                        var.pre_bar_direction_flag = LONG
                        var.big_bar_close = bar.close
                        var.big_bar_open = bar.open
                else:
                    var.clear_signal()
                    var.pre_bar_direction_flag = LONG
                    var.big_bar_close = bar.close
                    var.big_bar_open = bar.open

            elif bar.open - bar.close > var.open_thres * symbol_obj.tick_size:
                if var.pre_bar_direction_flag == LONG:
                    if bar.close < var.big_bar_open:
                        var.clear_signal()
                        var.pre_bar_direction_flag = SHORT
                        var.big_bar_close = bar.close
                        var.big_bar_open = bar.open
                else:
                    var.clear_signal()
                    var.pre_bar_direction_flag = SHORT
                    var.big_bar_close = bar.close
                    var.big_bar_open = bar.open


    def pre_close(self, var, symbol):
        flag = True
        # 无持仓 忽略
        if var.open_vol == 0:
            flag = False
        # 已有挂单 忽略
        for sys_id, order in self.context.orders.items():
            if order.symbol == symbol and order.offset != OPEN:
                flag = False
        return flag

    def pre_open(self, var, symbol):
        flag = True
        # 已有持仓 忽略
        if var.open_vol > 0:
            flag = False
        # 已有挂单 忽略
        for sys_id, order in self.context.orders.items():
            if order.symbol == symbol and order.offset == OPEN:
                flag = False
        return flag

    def pre_signal(self, var ,symbol):
        flag = True
        # 已有持仓 忽略
        if var.open_vol > 0:
            flag = False
        # 已有挂单 忽略
        for sys_id, order in self.context.orders.items():
            if order.symbol == symbol:
                flag = False
        return flag


class Variables(object):
    def __init__(self, symbol, limit_vol=1):
        self.symbol = symbol
        self.limit_vol = limit_vol
        self.num_from_big_bar=0  # 大阳线后第N个bar
        self.big_bar_close = 0
        self.big_bar_open = 0       # 大阳线open、close
        self.max_price=-999999999
        self.min_price=999999999   # 大阳线后的最高最低价
        self.pre_bar_direction_flag = ''    # 第一根大阳/阴线
        self.open_by_two_big_bar_flag = False  # 两根大阳线开仓flag
        self.open_margin = 0   # 开仓时的账户总权益
        self.reverse_flag = False      # 反手flag
        self.reverse_count = 0          # 反手计数器

        self.last_price = 0

        self.open_price = 0
        self.direction = ''
        self.open_vol = 0

        self.gain_over_flag = False # 是否达到1.5%收益
        self.max_gain = 0
        self.close_count = 0
        self.signal_count=0

        self.slippage = 2 # 开仓价上下浮动1个变动单位

        self.open_thres = 10  # 开仓tick倍数
        self.open_num_from_big_bar = 4 # 从大阳线后第5个开始判断是否开仓
        self.max_open_num_from_big_bar = 24 # 最多判断连续25个
        self.stop_gain_thres = 0.6      # 止盈后回撤系数
        self.gain_thres = 1.01         # 止盈开始系数
        self.two_big_bar_stop_thres = 5 # 两根大阳线后续按tick 跌破5*tick_size止损
        self.stop_loss_thres = 0.02    # 按账户收益止损系数
        self.second_big_bar_open_thres = 5 # 第二根大阳线开仓系数
        self.max_reverse_count = 5  # 最大反手次数



    def exchange_peak(self, price):
        if price > self.max_price:
            self.max_price = price
        if price < self.min_price:
            self.min_price = price

    def clear_signal(self):
        self.min_price = 999999999
        self.max_price = -999999999
        self.num_from_big_bar = 0
        self.big_bar_close = 0
        self.big_bar_open = 0
        self.pre_bar_direction_flag = ''

    def initialize(self):
        self.clear_signal()

        self.open_price = 0
        self.direction = ''
        self.open_vol = 0
        self.gain_over_flag = False
        self.max_gain = 0
        self.open_by_two_big_bar_flag = False
        self.open_margin = 0

    def __str__(self):
        return ('%s:信号 %s %s' % (self.symbol, self.pre_bar_direction_flag, self.num_from_big_bar))


if __name__ == '__main__':
    s = Liao()
    s.run()



