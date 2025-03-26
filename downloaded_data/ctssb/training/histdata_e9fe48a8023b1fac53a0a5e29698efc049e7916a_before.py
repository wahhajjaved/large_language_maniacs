# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import unicode_literals
import copy
import random
import datetime
from line_profiler import LineProfiler
# from .mixin import MAMixin
from module.rate import CurrencyPair, Granularity
from module.genetic.models.parameter import OrderType
from .market_order import MarketOrder, OrderAI
from module.currency import EurUsdMixin
from module.rate.models.base import MultiCandles
from django.utils.six import text_type


class AIInterFace(object):
    LIMIT_POSITION = 10
    buy_limit_time = datetime.timedelta(seconds=3120)
    buy_time = None
    market = None
    generation = None
    currency_pair = None
    ai_dict = {}
    genetic_history_id = None
    ai_id = 0

    def __init__(self, ai_dict, suffix, generation):
        self.ai_dict = ai_dict
        self.name = self.__class__.__name__ + suffix
        self.generation = generation
        self.normalization()
        self._dispatch()

    @classmethod
    def get_ai(cls, ai_param, name, generation, ai_pk):
        """
        AIのdictからAIを生成して返却
        :param : ai_param
        """
        ai = {}
        for key in ai_param:
            if type(ai_param[key]) == list:
                l = ai_param[key]
                ai[key] = [OrderType(l[0]), l[1], l[2]]
                continue
            ai[str(key)] = ai_param[key]
        ai = cls(ai, name, generation)
        ai.pk = ai_pk
        return ai

    def _dispatch(self):
        pass

    def save(self):
        """
        AIを記録する
        """
        from module.genetic.models import GeneticHistory
        GeneticHistory.record_history(self)

    def order(self, market, prev_rates, open_bid, start_at):
        """
        条件に沿って注文する
        :param market: Market
        :param prev_rates: list of Rate
        :param open_bid: float
        :param start_at: datetime
        :rtype market: Market
        """
        # 前回レートがない
        if not prev_rates:
            return market
        # ポジション数による購入制限
        if len(market.open_positions) >= self.LIMIT_POSITION:
            return market
        # 時間による購入制限
        if self.buy_time and start_at < self.buy_time + self.buy_limit_time:
            print "LOCK AS TIME:{}, {}".format(start_at, self.buy_time + self.buy_limit_time)
            return market

        # if self.buy_time:
        #     print "OK BUY AS TIME:{}, {}".format(start_at, self.buy_time + self.buy_limit_time)

        order_ai = self.get_order_ai(prev_rates, open_bid, start_at)
        if not order_ai:
            return market

        if order_ai.order_type != OrderType.WAIT:
            self.buy_time = start_at
            market.order(self.currency_pair, open_bid, MarketOrder(open_bid, self.base_tick, order_ai), start_at)
        return market

    def get_order_ai(self, prev_rates, open_bid, start_at):
        """
        :param prev_rates: list of Rate
        :param open_bid: float
        :param start_at: datetime
        :rtype : OrderAI
        """
        raise NotImplemented

    @classmethod
    def market_order(cls, market, rate, order_ai):
        """
        :param market: Market
        :param rate: Rate
        :param order_ai: OrderAI
        :rtype : Market
        """
        market.order(rate, MarketOrder(rate, order_ai))
        return market

    def update_market(self, market, rate):
        market.profit_result = market.profit_summary(rate)
        self._profit = market.profit_summary(rate)
        self._profit_max = market.profit_max
        self._profit_min = market.profit_min
        self.market = market

    def initial_create(self, num):
        """
        遺伝的アルゴリズム
        初期集団を生成
        :param num : int
        """
        return [copy.deepcopy(self).set_start_data() for x in xrange(num)]
        # return [copy.deepcopy(self) for x in xrange(num)]

    def increment_generation(self):
        """
        世代を1世代増やす
        """
        self.generation += 1
        return self

    def to_dict(self):
        return {
            'NAME': self.name,
            'GENERATION': self.generation,
            'PROFIT': self.profit,
            'SCORE': self.score(0),
            'PROFIT_MAX': self.profit_max,
            'PROFIT_MIN': self.profit_min,
            'AI_LOGIC': self._ai_to_dict(),
            'AI_ID': self.ai_id,
            'CURRENCY_PAIR': self.currency_pair.value,
            'END_AT': text_type(self.end_at),
            'TRADE_COUNT': len(self.market.positions),
            'GENETIC_HISTORY_ID': self.genetic_history_id if self.genetic_history_id else 0
        }

    def _ai_to_dict(self):
        result_dict = {}
        for key in self.ai_dict:
            v = self.ai_dict[key]
            if type(v) == list:
                result_dict[key] = [self._value_to_dict(_v) for _v in v]
            else:
                result_dict[key] = self._value_to_dict(v)
        return result_dict

    def _value_to_dict(self, value):
        if type(value) == OrderType:
            return value.value
        if type(value) == datetime.timedelta:
            return value.total_seconds()
        return value

    def normalization(self):
        """
        過剰最適化するAIの進化に制限を儲ける
        利確, 損切り 800pip先とかを禁止
        """
        raise NotImplementedError

    def score(self, correct_value):
        return self.profit - correct_value

    @property
    def profit(self):
        return self._profit

    @property
    def profit_max(self):
        return self._profit_max

    @property
    def profit_min(self):
        return self._profit_min

    @property
    def start_at(self):
        return self.market.start_at

    @property
    def end_at(self):
        return self.market.end_at


class AI1EurUsd(EurUsdMixin, AIInterFace):
    # 進化乱数
    MUTATION_MAX = 60
    MUTATION_MIN = 10

    # 値の制限
    LIMIT_TICK = 60
    LIMIT_LOWER_TICK = 15
    LIMIT_BASE_HIGHER_TICK = 60
    LIMIT_BASE_LOWER_TICK = 10

    def normalization(self):
        """
        過剰最適化するAIの進化に制限を儲ける
        利確, 損切り 800pip先とかを禁止
        """
        ai = copy.deepcopy(self.ai_dict)
        for key in ai:
            if key == 'base_tick':
                if ai[key] <= self.LIMIT_BASE_LOWER_TICK:
                    ai[key] = self.LIMIT_BASE_LOWER_TICK
                if ai[key] >= self.LIMIT_BASE_HIGHER_TICK:
                    ai[key] = self.LIMIT_BASE_HIGHER_TICK
                continue
            # 13は必ずWAIT扱い
            if key == 13:
                ai[key] = [OrderType.WAIT, 0, 0]
            for index in [1, 2]:
                if ai[key][index] >= self.LIMIT_TICK:
                    ai[key][index] = self.LIMIT_TICK
                if ai[key][index] <= self.LIMIT_LOWER_TICK:
                    ai[key][index] = self.LIMIT_LOWER_TICK
        self.ai_dict = ai

    def set_start_data(self):
        """
        初期データを生成する
        """
        # tick 20%
        if random.randint(1, 100) <= 20:
            self.ai_dict['base_tick'] += random.randint(-2, 2)
        # 各パラメータは3%の確率で変異
        for key in self.ai_dict:
            if key == 'base_tick':
                continue
            value = self.ai_dict[key]
            if type(value) != list:
                continue
            for index in range(len(value)):
                self.ai_dict[key][0] = OrderType(random.randint(1, 3) - 2)
        self.normalization()
        return self

    def get_order_ai(self, prev_rates, open_bid, start_at):
        """
        条件に沿って注文する
        :param prev_rates: list of Rate
        :rtype market: Market
        """
        if len(prev_rates) < 3:
            return None
        prev_rate = prev_rates[-2]

        # 前回のレートから型を探す
        candle_type_id = prev_rate.get_candle_type(self.base_tick)
        order_type, limit, stop_limit = self.ai_dict.get(candle_type_id)
        return OrderAI(order_type, limit, stop_limit)


class AI2EurUsd(AI1EurUsd):
    """
    数時間前にさかのぼってレートを参照する
    """
    currency_pair = CurrencyPair.EUR_USD
    # 進化乱数
    MUTATION_MAX = 70
    MUTATION_MIN = 10

    # 値の制限
    LIMIT_TICK = 70
    LIMIT_LOWER_TICK = 10
    LIMIT_BASE_HIGHER_TICK = 60
    LIMIT_BASE_LOWER_TICK = 10
    LIMIT_DEPTH = 48
    LIMIT_LOWER_DEPTH = 1

    # 対象とするローソク足のスパン
    RATE_SPAN = Granularity.H1

    def _dispatch(self):
        if 'depth' not in self.ai_dict:
            self.ai_dict['depth'] = 10

    def set_start_data(self):
        """
        初期データを生成する
        """
        # tick 20%
        if random.randint(1, 100) <= 20:
            self.ai_dict['base_tick'] += random.randint(-2, 2)
        # depth 100%
        self.ai_dict['depth'] = random.randint(self.LIMIT_LOWER_DEPTH, self.LIMIT_DEPTH)
        # 各パラメータは3%の確率で変異
        for key in self.ai_dict:
            if key == 'base_tick':
                continue
            value = self.ai_dict[key]
            if type(value) != list:
                continue
            for index in range(len(value)):
                self.ai_dict[key][0] = OrderType(random.randint(1, 3) - 2)
        self.normalization()
        return self

    def normalization(self):
        """
        過剰最適化するAIの進化に制限を儲ける
        利確, 損切り 800pip先とかを禁止
        """
        ai = copy.deepcopy(self.ai_dict)
        for key in ai:
            if key == 'base_tick':
                if ai[key] <= self.LIMIT_BASE_LOWER_TICK:
                    ai[key] = self.LIMIT_BASE_LOWER_TICK
                if ai[key] >= self.LIMIT_BASE_HIGHER_TICK:
                    ai[key] = self.LIMIT_BASE_HIGHER_TICK
                continue
            if key == 'depth':
                if self.LIMIT_LOWER_DEPTH > ai['depth']:
                    ai['depth'] = self.LIMIT_LOWER_DEPTH
                if self.LIMIT_DEPTH < ai['depth']:
                    ai['depth'] = self.LIMIT_DEPTH
                continue
            # 13は必ずWAIT扱い
            if key == 13:
                ai[key] = [OrderType.WAIT, 0, 0]
            for index in [1, 2]:
                if ai[key][index] >= self.LIMIT_TICK:
                    ai[key][index] = self.LIMIT_TICK
                if ai[key][index] <= self.LIMIT_LOWER_TICK:
                    ai[key][index] = self.LIMIT_LOWER_TICK
        self.ai_dict = ai

    def get_order_ai(self, prev_rates, open_bid, start_at):
        """
        条件に沿って注文する
        :param prev_rates: list of Rate
        :param open_bid: int
        :rtype market: Market
        """
        rates = convert_rate(prev_rates, self.RATE_SPAN)

        if len(rates) - 1 < self.depth:
            return None
        c = len(rates)
        prev_rates = rates[c - self.depth:c]
        assert len(prev_rates) == self.depth, (len(prev_rates), self.depth)
        prev_rate = MultiCandles(prev_rates, Granularity.UNKNOWN)

        # 前回のレートから型を探す
        candle_type_id = prev_rate.get_candle_type(self.base_tick)
        order_type, limit, stop_limit = self.ai_dict.get(candle_type_id)
        return OrderAI(order_type, limit, stop_limit)

    def incr_depth(self, x):
        self.ai_dict['depth'] += x
        return self

    def incr_base_tick(self, x):
        self.ai_dict['base_tick'] += x
        return self

    def mutation(self):
        """
        AIの変化耐性を調べるために突然変異させる
        """
        for key in self.ai_dict:
            if key in ('base_tick', 'depth'):
                continue
            value = self.ai_dict[key]
            if type(value) != list:
                continue
            # 20%で変わる
            if random.randint(1, 5) == 1:
                self.ai_dict[key][1] += random.randint(-10, 10)
                self.ai_dict[key][2] += random.randint(-10, 10)
        self.normalization()
        return self

    @property
    def depth(self):
        return self.ai_dict['depth']


class AI3EurUsd(AI2EurUsd):
    """
    MAを見て判断
    """
    ai_id = 3
    MA_KEYS = [
        # 'h1',
        'h4',
        'h24',
        'd5',
        # 'd10',
        'd25',
        # 'd75',
        # 'd200',
    ]

    def _dispatch(self):
        if 'depth' not in self.ai_dict:
            self.ai_dict['depth'] = 10
        if 'base_tick_ma' not in self.ai_dict:
            self.ai_dict['base_tick_ma'] = 50

    def normalization(self):
        pass

    def get_order_ai(self, prev_rates, open_bid, start_at):
        """
        条件に沿って注文する
        :param prev_rates: list of Rate
        :param open_bid: float
        :param start_at: datetime
        :rtype market: Market
        """
        rates = convert_rate(prev_rates, self.RATE_SPAN)

        if not rates:
            return None

        rate_type = self.get_ratetype(open_bid, rates)

        # rateがNoneのとき注文しない
        if rate_type is None:
            return None

        if rate_type in self.ai_dict:
            order_type, limit, stop_limit = self.ai_dict.get(rate_type)
        else:
            # AIがない場合はデフォルトデータをロード
            self.ai_dict[rate_type] = [OrderType.get_random(), 50, 50]
            order_type, limit, stop_limit = self.ai_dict.get(rate_type)
        return OrderAI(order_type, limit, stop_limit)

    def get_ratetype(self, open_bid, rates):
        if rates[-1].ma is None:
            return None

        # keyの生成
        l = []
        ma = rates[-1].ma
        for key in self.MA_KEYS:
            ma_bid = getattr(ma, key)
            if ma_bid is None:
                return None

            l.append(str(get_ma_type(open_bid, ma_bid, self.base_tick_ma, rates[-1])))
        key_value = ":".join(l)
        return str('MA:{}'.format(key_value))

    @property
    def base_tick_ma(self):
        return self.ai_dict['base_tick_ma']


class AI4EurUsd(AI3EurUsd):
    """
    MAを見て判断
    """
    ai_id = 4
    MA_KEYS = [
        # 'h1',
        'h4',
        'h24',
        'd5',
        # 'd10',
        'd25',
        # 'd75',
        # 'd200',
    ]


class AI5EurUsd(EurUsdMixin, AIInterFace):
    """
    MAを見て判断
    """
    # 対象とするローソク足のスパン
    RATE_SPAN = Granularity.H1
    ai_id = 5
    MA_KEYS = [
        # 'h1',
        # 'h4',
        'h24',
        # 'd5',
        # 'd10',
        # 'd25',
        # 'd75',
        # 'd200',
    ]
    MUTATION_MAX = 100
    MUTATION_MIN = 10

    def _dispatch(self):
        if 'base_tick' not in self.ai_dict:
            self.ai_dict['base_tick'] = 20
        if 'depth' not in self.ai_dict:
            self.ai_dict['depth'] = 24
        if 'base_tick_ma' not in self.ai_dict:
            self.ai_dict['base_tick_ma'] = 50

    def normalization(self):
        """
        過剰最適化するAIの進化に制限を儲ける
        利確, 損切り 800pip先とかを禁止
        """
        ai = copy.deepcopy(self.ai_dict)
        for key in ai:
            if type(ai[key]) == list:
                for index in [1, 2]:
                    ai[key][index] = self.adjust(ai[key][index])
                continue
            ai[key] = self.adjust(ai[key])
        self.ai_dict = ai

    def adjust(self, value):
        if self.MUTATION_MAX < value:
            return self.MUTATION_MAX
        if self.MUTATION_MIN > value:
            return self.MUTATION_MIN
        return value

    def set_start_data(self):
        return self

    def get_order_ai(self, prev_rates, open_bid, start_at):
        """
        条件に沿って注文する
        :param prev_rates: list of Rate
        :param open_bid: float
        :param start_at: datetime
        :rtype market: Market
        """
        rates = convert_rate(prev_rates, self.RATE_SPAN)

        if not rates:
            return None

        if len(rates) - 1 < self.depth:
            return None

        rate_type = self.get_ratetype(open_bid, rates, start_at)

        # rateがNoneのとき注文しない
        if rate_type is None:
            return None

        if rate_type in self.ai_dict:
            order_type, limit, stop_limit = self.ai_dict.get(rate_type)
        else:
            # AIがない場合はデフォルトデータをロード
            self.ai_dict[rate_type] = [OrderType.get_random(), random.randint(15, 50), random.randint(15, 50)]
            order_type, limit, stop_limit = self.ai_dict.get(rate_type)
        return OrderAI(order_type, limit, stop_limit)

    def get_ratetype(self, open_bid, rates, start_at):
        if rates[-1].ma is None:
            return None

        # key_maの生成
        l = []
        ma = rates[-1].ma
        for key in self.MA_KEYS:
            ma_bid = getattr(ma, key)
            if ma_bid is None:
                return None

            l.append(str(get_ma_type(open_bid, ma_bid, self.base_tick_ma, rates[-1])))
        key_value = ":".join(l)
        key_ma = str('MA:{}'.format(key_value))

        # key_candleの生成
        c = len(rates)
        prev_rates = rates[c - self.depth:c]
        assert len(prev_rates) == self.depth, (len(prev_rates), self.depth)
        prev_rate = MultiCandles(prev_rates, Granularity.UNKNOWN)
        key_candle = prev_rate.get_candle_type(self.base_tick)
        return "CANDLE:{}:{}".format(key_candle, key_ma)

    @property
    def depth(self):
        return self.ai_dict['depth']


class AI6EurUsd(AI5EurUsd):
    ai_id = 6
    buy_span = datetime.timedelta(seconds=3120)
    buy_time = None
    MA_KEYS = [
        # 'h1',
        # 'h4',
        'h24',
        # 'd5',
        # 'd10',
        # 'd25',
        # 'd75',
        # 'd200',
    ]

    def _dispatch(self):
        if 'base_tick' not in self.ai_dict:
            self.ai_dict['base_tick'] = 20
        if 'depth' not in self.ai_dict:
            self.ai_dict['depth'] = 24
        if 'base_tick_ma' not in self.ai_dict:
            self.ai_dict['base_tick_ma'] = 50

    def get_ratetype(self, open_bid, rates, start_at):
        if rates[-1].ma is None:
            return None

        # key_ma_diffの生成
        prev_rate = rates[-1]
        error_range = datetime.timedelta(hours=24)   # 許容する後方誤差
        error_range2 = datetime.timedelta(hours=48)   # 許容する後方誤差
        # print '~~~~~~~~~~~~~~~~~~'
        # print 'START AT:{}'.format(start_at)
        # print 'PREV START AT:{} RATE:{}'.format(prev_rate.start_at, prev_rate.ma.h24)
        rate24h_ago = get_range_rates(rates, start_at - datetime.timedelta(days=1), error_range)
        rate96h_ago = get_range_rates(rates, start_at - datetime.timedelta(days=4), error_range2)
        if rate24h_ago and rate24h_ago.ma and rate24h_ago.ma.h24:
            # print 'T1:RATE START AT:{} RATE:{}'.format(rate24h_ago.start_at, rate24h_ago.ma.h24)
            pass
        else:
            return None

        if rate96h_ago and rate96h_ago.ma and rate96h_ago.ma.h24:
            # print 'T2:RATE START AT:{} RATE:{}'.format(rate96h_ago.start_at, rate96h_ago.ma.h24)
            pass
        else:
            return None
        # print '~~~~~~~~~~~~~~~~~~'

        if rate24h_ago and rate96h_ago and prev_rate.ma and prev_rate.ma.h24:
            key1 = get_tick_category(prev_rate.ma.h24 - open_bid, self.base_tick)
            key2 = get_tick_category(rate24h_ago.ma.h24 - open_bid, self.base_tick)
            key3 = get_tick_category(rate96h_ago.ma.h24 - open_bid, self.base_tick)
            key_ma_diff = '{}:{}:{}'.format(key1, key2, key3)
        else:
            return None
        #
        #
        # # key_maの生成
        # l = []
        # ma = rates[-1].ma
        # for key in self.MA_KEYS:
        #     ma_bid = getattr(ma, key)
        #     if ma_bid is None:
        #         return None
        #
        #     l.append(str(get_ma_type(open_bid, ma_bid, self.base_tick_ma, rates[-1])))
        # key_value = ":".join(l)
        # key_ma = str('MA:{}'.format(key_value))
        #
        # key_candleの生成
        c = len(rates)
        prev_rates = rates[c - self.depth:c]
        assert len(prev_rates) == self.depth, (len(prev_rates), self.depth)
        prev_rate = MultiCandles(prev_rates, Granularity.UNKNOWN)
        key_candle = 'CANDLE:{}'.format(prev_rate.get_candle_type(self.base_tick))
        return ':'.join([key_ma_diff, key_candle])
    pass


def convert_rate(rates, g):
    """
    キャンドル足を対象のスパンのキャンドル足に変換する
    5分足36本から1時間足3本とか
    :param rates: list of Rate
    :param g: Granularity
    :rtype: list of Rate
    """
    if rates[0].granularity == g:
        return rates

    # 4時間足から1時間足は生成できない
    if rates[0].granularity.value > g.value:
        raise ValueError

    count = g.value / rates[0].granularity.value
    if len(rates) < count:
        return []

    # MultiCandlesに取りまとめて返却
    r = []
    limit = 200
    range_max = limit if count * limit > len(rates) else int(len(rates) / count)
    print 'range_max is..', range_max
    for index in xrange(0, range_max):
        target_rates = list(reversed(rates[len(rates) - count - index * count:len(rates) - index * count]))
        r.append(MultiCandles(target_rates, g))
        if random.randint(1, 100) == 1:
            print len(rates) - count - index * count, len(rates) - index * count

    return list(reversed(r))


def get_ma_type(open_bid, ma_bid, base_tick_ma, prev_rate):
    """
    ma値からタイプを返却
    100を基準に上下
    :param open_bid: float
    :param ma_bid: float
    :param base_tick_ma: float
    :param prev_rate: Rate
    :rtype : int
    """
    tick = (open_bid - ma_bid) / prev_rate.tick
    ans = 100 + get_tick_category(tick, base_tick_ma)
    return ans


def get_tick_category(tick, base_tick):
    """
    base_tickが50のとき

    1 - 50: RETURN 1
    51 - 200: RETURN 2
    201 - 450: RETURN 3
    451 - 800: RETURN 4
    801 - 1250: RETURN 5
    -50 - 0: RETURN 0
    -200 - -51: RETURN -1
    -450 - -201 : RETURN -2
    -800 - -451 : RETURN -3
    :param tick: int
    :param base_tick: int
    :return:
    """
    result = 1
    _tick = tick
    is_minus = False
    if tick < 0:
        _tick = tick * -1
        result = 0
        is_minus = True
    prev_calc_rate = 0
    ct = 1
    for x in range(1000):
        calc_rate = base_tick * ct + prev_calc_rate
        if calc_rate >= _tick:
            if result > 5:
                return 5
            if result < -4:
                return -4
            return result
        ct += 2
        if is_minus:
            result -= 1
        else:
            result += 1
        prev_calc_rate = calc_rate
    print tick, base_tick
    raise ValueError


def get_range_rates(rates, target_date, error_range):
    """
    誤差内のレートを返却
    :param rates: Rate
    :param target_date: datetime
    :param error_range: timedelta
    :rtype :rate
    """
    _from = target_date - error_range
    _to = target_date
    for rate in reversed(rates):
        if _from <= rate.start_at <= _to:
            if rate.ma:
                return rate
        if rate.start_at < _from:
            return None
    return None
