# coding=utf-8
import os
import re
import json

from copy import deepcopy

import urllib2

import pymorphy2

morph = pymorphy2.MorphAnalyzer()

def morphy_word(word):
    word = morph.parse(word)
    if word and len(word) and word[0] and word[0].normal_form:
        word = word[0].normal_form
    return word

def get_html(url):
    headers = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2454.101 Safari/537.36'}
    req = urllib2.Request(url, None, headers)
    html = urllib2.urlopen(req).read()
    return html


def google_utkonos(request):
    url = "http://www.google.com/search?q=" + request + "+site:utkonos.ru"
    result = get_html(url).split('<a href="/url?q=')
    return [result[i].split('&')[0] for i in list(range(1, 6))]


class Action(object):

    def update(self, State):
        pass


class AddItem(Action):

    def __init__(self, **argv):
        self.argv = argv

    def update(self, State):
        State['end'] = 1
        for k, v in self.argv.iteritems():
            State[k] = v


class AddItemWithCount(Action):

    def __init__(self, **argv):
        self.argv = argv

    def update(self, State):
        State['end'] = 1
        for k, v in self.argv.iteritems():
            State[k] = v


class GotoQuestion(Action):

    def __init__(self, next_, **argv):
        self.next_ = next_
        self.argv = argv

    def update(self, State):
        State['CurrentQuestion'] = self.next_
        for k, v in self.argv.iteritems():
            State[k] = v


class DefaultAction(Action):

    def update(self, State):
        pass


class Answer(object):

    def __init__(self):
        pass


class Question(object):

    def __init__(self, Q, Answers, Any=DefaultAction()):
        self.Q = Q
        self.Answers = Answers
        self.Any = Any or DefaultAction()

    def GetItems(self, State):
        items = self.Answers.keys()
        if u'Дальше' in items:
            items = filter(lambda x: x != u'Дальше', items)
            items.append(u'Дальше')
        return items

    def Check(self, State):
        return True

    def Ask(self, State):
        return self.Q, self.GetItems(State)

    def WhatNext(self, answer, State):
        if answer.lower() in set(map(lambda x: x.lower(), self.GetItems(State))):
            arr = [k for k in self.Answers.iterkeys() if k.lower() == answer.lower()]
            return self.Answers[arr[0]]
        else:
            digit = -1
            try:
                digit = int(answer)
            except Exception:
                digit = -1
            if digit == -1:
                return self.Any
            if digit <= len(self.Answers) and digit > 0:
                return self.Answers[self.GetItems(State)[digit - 1]]
            else:
                return self.Any


class QuesitonSelectFew(Question):
    def __init__(self, Q, Targets, Answers, FuncAction, Any=None, saveTo='item'):
        self.Q = Q
        self.Answers = Answers
        self.Any = Any or DefaultAction()
        self.FuncAction = FuncAction
        self.Targets = Targets
        self.saveTo = saveTo

    def getItems(self, State):
        result = []
        for answer, values in self.Answers.iteritems():
            if all([State[k] == values[k] for k in self.Targets['select'] if k in State and k in values]):
                result.append(answer)
        result = sorted(result, key=lambda x: abs(self.Answers[x][self.Targets['sort']] -
            State.get('price', 0)) + 10000 * (x == u'Дальше'))
        # result = map(lambda x: x + u', цена: ' + str(self.Answers[x]['price']), result)
        result = map(lambda x: x, result)
        return result

    def Check(self, State):
        return len(self.getItems(State))

    def Check2(self, State):
        return self.getItems(State)

    def Ask(self, State):
        return self.Q, self.getItems(State)

    def TryMatchPrice(self, real_answer):
        for answer, values in self.Answers.iteritems():
            if 'price' in values and real_answer.startswith(answer):
                return values['price']
        return None

    def WhatNext(self, answer, State):
        items = self.getItems(State)
        if answer in items:
            State[self.saveTo] = answer
            price = self.TryMatchPrice(answer)
            if price is not None:
                State['price'] = price
            return self.FuncAction
        else:
            digit = -1
            try:
                digit = int(answer)
            except Exception:
                pass
            if digit == -1:
                return self.Any
            if digit <= len(items) and digit > 0:
                State[self.saveTo] = items[digit - 1]
                return self.FuncAction
            else:
                return self.Any


class QuestionCount(Question):

    def __init__(self, Q, field, func, Any=None):
        self.Q = Q
        self.field = field
        self.func = func
        self.Any = Any or DefaultAction()

    def Ask(self, State):
        return self.Q, []

    def WhatNext(self, answer, State):
        digit = -1
        try:
            digit = int(answer)
        except Exception:
            pass
        if digit != -1:
            return self.func({self.field: digit})
        else:
            return self.Any


class State(object):

    def __init__(self):
        pass


class TItem(object):

    def __init__(self, Name, Questions, FirstQuestion, CheckQuestion=None, GotoQuestion=None):
        self.FirstQuestion = FirstQuestion
        self.Questions = Questions
        self.Name = Name
        self.CheckQuestion = CheckQuestion
        self.GotoQuestion = GotoQuestion

    def doFirst(self):
        State = {'CurrentQuestion': self.FirstQuestion}
        q, items = self.Questions[State['CurrentQuestion']].Ask(State)
        return q, items, State

    def do(self, answer, State):
        s = deepcopy(State)
        action = self.Questions[State['CurrentQuestion']].WhatNext(answer, State)
        if action:
            action.update(State)
        if 'end' in State and State['end']:
            return None, (State['item'], State.get('count', 1), State['price']), None
        if self.CheckQuestion and self.CheckQuestion in self.Questions:
            print self.CheckQuestion
            print len(self.Questions[self.CheckQuestion].Check2(State))
            print self.Questions[self.CheckQuestion].Check2(State)
            c = self.Questions[self.CheckQuestion].Check(State)
            if c < 5:
                print self.GotoQuestion
                if c == 0:
                    State = s
                if self.GotoQuestion and c > 1:
                    State['CurrentQuestion'] = self.GotoQuestion
                else:
                    State['CurrentQuestion'] = self.CheckQuestion
                print s
                print len(self.Questions[self.CheckQuestion].Check2(State))
        q, items = self.Questions[State['CurrentQuestion']].Ask(State)
        return q, items, State


class TItemFromNet(TItem):

    def Match(self, query):
        # count = 0
        # if len(query) <= 2:
        #     return 0
        # for title in self.targets:
        #     words = words = re.findall(ur'(?u)\w+', title)[:2]
        #     count += any([morphy_word(query.lower()) == morphy_word(word.lower()) for word in words])
        # return count
        count = 0
        if len(query) <= 2:
            return 0
        q = morphy_word(query.lower())
        for words in self.targets:
            count += any([q == word for word in words])
        return count

    def doFirst(self):
        return self.item.doFirst()

    def do(self, answer, State):
        return self.item.do(answer, State)

    def __init__(self, filename):
        self.data = json.load(open(filename, "rt"))
        self.head = self.data[0]
        self.data = self.data[1:]
        name2id = dict(map(lambda x: (x[1], x[0]), enumerate(self.head)))
        bad_names = ['id', 'link',  "rec_name", "rec_price"]
        target = 'name'
        price = 'price'
        categories = []
        for h in self.head:
            if all([h != bd for bd in bad_names]) and h != target and h != price:
                categories.append(h)
        tovars = {}
        for d in self.data:
            info = {}
            for c in categories:
                info[c] = d[name2id[c]]
            x = d[name2id[price]]
            x = x.replace(" ", "")
            info['price'] = int(x)
            tovars[d[name2id[target]]] = info

        categories = filter(lambda x: x != price and x != u'Страна', categories)

        item_params = {'HowMany': QuestionCount(u"Сколько?", 'count', lambda x: AddItemWithCount(**x)),
                       'ApproxPrice': QuestionCount(u"Приблизительная цена?", 'price', lambda x: GotoQuestion('SelectFew', **x)),
                       'SelectFew': QuesitonSelectFew(u"Сделайте выбор!", {'select': categories,
                           'sort': 'price'}, tovars, GotoQuestion("HowMany"), saveTo='item')}

        if not len(categories):
            self.targets = []
            return

        categories = [cat for i, cat in enumerate(categories) if len(set([d[name2id[cat]] for d in
            self.data if d[name2id[cat]] is not None])) > 1]

        if not len(categories):
            self.targets = []
            return

        first = categories[0]

        for i, cat in enumerate(categories):
            uniq_types = set([d[name2id[cat]] for d in self.data if d[name2id[cat]] is not None])
            answers = {}
            if i + 1 < len(categories):
                NextQuestion = categories[i + 1]
            else:
                NextQuestion = 'ApproxPrice'
            for u in uniq_types:
                answers[u] = GotoQuestion(NextQuestion, **{cat: u})
            answers[u'Дальше'] = GotoQuestion(NextQuestion)
            item_params[cat] = Question(u"Выберете " + cat, answers)

        self.item = TItem(u"", item_params, first, 'SelectFew', 'ApproxPrice')
        self.urls = set([d[name2id['link']] for d in self.data if d[name2id[cat]] is not None])
        self.targets = set([d[name2id[target]] for d in self.data if d[name2id[target]] is not None])

        targets = []
        for title in self.targets:
            words = map(lambda x: morphy_word(x.lower()), re.findall(ur'(?u)\w+', title)[:2])
            targets += [words]
            # if '66' in filename:
            #     for t in words:
            #         print t
        self.targets = targets


class TItems(object):

    def __init__(self, items, hard_items=[]):
        self.items = dict(map(lambda x: (x.Name.lower(), x), items))
        self.hard_items = hard_items

    def doNotExactSearch(self, query):
        # print query
        # urls = google_utkonos(query.encode('utf-8'))
        # print urls
        saved_index = -1
        saved = -1
        for index, hi in enumerate(self.hard_items):
            tmp = hi.Match(query)
            if tmp > saved and tmp > 2:
                saved = tmp
                saved_index = index
        if saved_index != -1:
            return saved_index

    def filterWords(self, query):
        result = []
        words = re.findall(ur'(?u)\w+', query)
        for word in words:
            word = morphy_word(word)
            if word.lower() in map(lambda x: morphy_word(x.lower()), self.items):
                result.append(word)
                continue
            if self.doNotExactSearch(word) is not None:
                result.append(word)
        return result

    def doNextWord(self, State):
        words = State['words']
        if not words:
            return "Заказываем?", []
        word = words[0]
        words = words[1:]
        State['words'] = words
        if word.lower() in map(lambda x: x.lower(), self.items):
            word = dict(map(lambda x: (morphy_word(x.lower()), x), self.items))[word.lower()]
            q, items, State['State'] = self.items[word].doFirst()
            State['Current'] = word
            State['notExact'] = 1
            del State['notExact']
        else:
            notExact = self.doNotExactSearch(morphy_word(word))
            if notExact is not None:
                State['notExact'] = 1
                State['Current'] = notExact
                q, items, State['State'] = self.hard_items[State['Current']].doFirst()
            else:
                q = u"Я не знаю такого товара"
                items = []
        return q, items

    def do(self, query, State):
        if 'Current' in State:
            if 'notExact' in State:
                Z = self.hard_items[State['Current']].do(query, State['State'])
            else:
                Z = self.items[State['Current']].do(query, State['State'])
            State['State'] = Z[2]
            if Z[0] is not None:
                return Z[0], Z[1], State
            else:
                #  save item to cart
                del State['Current']
                if len(Z[1][0]) > 20:
                    words = ' '.join(Z[1][0].split(' ')[:-1])
                    Z = [Z[0], (words, Z[1][1], Z[1][2])]
                magaz = ord(Z[1][0][0]) % 2
                if magaz:
                    magaz = "utkonos"
                else:
                    magaz = "azbuka"
                Z = (Z[0], (Z[1][0], Z[1][1], Z[1][2], magaz))
                return Z[0], Z[1], State
        else:
            if 'words' not in State or not State['words']:
                State['words'] = self.filterWords(query)
        q, items = self.doNextWord(State)
        return q, items, State


def ExtendDict(**argv):
    return argv


def CreateBeer(b, c, p):
    return {'bankatype': b, 'color': c, 'price': p}


def CreateMilk(fast, fat, price):
    return {'fast': fast, 'fat': fat, 'price': price}


Beer = TItem(u"Пиво",
             {'Usual': Question(u"Как обычно?",
                                {u"Да": AddItem(item=u"Жигули 4.9% 0.5 литра", price='40'),
                                 u"Нет": GotoQuestion("BeerType")}),
              'BeerType': Question(u"Какое хотите?", {
                  u"Жигули": GotoQuestion("HowMany", item="Жигули 4.9% 0.5 литра", price=40),
                  u"Балтика№0": GotoQuestion("HowMany", item=u"Балтика 0.5% 0.5 литра", price=50),
                  u"Балтика№3": GotoQuestion("HowMany", item=u"Балтика 4.8% 0.5 литра", price=80),
                  u"Другое": GotoQuestion("Other")}),
              'HowMany': QuestionCount(u"Сколько?", 'count',
                  lambda x: AddItemWithCount(**x)),
              'ApproxPrice': QuestionCount(u"Приблизительная цена?", 'price', lambda x:
                  GotoQuestion('SelectFew', **x)),
              'Other': Question(u"Темное или светлое?",
                                {u"Темное": GotoQuestion("BankaType", color="black"),
                                 u"Светлое": GotoQuestion("BankaType", color="white")}),
              'BankaType': Question("Банка или бутылка?",
                                    {u"Банка": GotoQuestion("ApproxPrice", bankatype="banka"),
                                     u"Бутылка": GotoQuestion("ApproxPrice", bankatype="butilka")}),
                                    'SelectFew': QuesitonSelectFew(u"Сделайте выбор!", {'select':
                                        ['color', 'bankatype'], 'sort': 'price'}, {
                    u'Жигули 3%': CreateBeer("banka", "black", 30),
                    u'Жигули a 3%': CreateBeer("banka", "white", 50),
                    u'Балтика 3%': CreateBeer("butilka", "black", 80),
                    u'Балтика a 3%': CreateBeer("butilka", "white", 90),
                    u'Балтика 9%': CreateBeer("banka", "black", 102),
                    u'Жигули 9%': CreateBeer("banka", "white", 30),
                    u'Жигули a 9%': CreateBeer("butilka", "black", 50),
                    u'Жигули b 9%': CreateBeer("butilka", "white", 20)},
                                             GotoQuestion("HowMany"), saveTo='item')}, "BeerType")

Sosige = TItem(u"Сосиска",
             {'Usual': Question(u"Как обычно?",
                                {u"Да": AddItem(item=u"Сосиски Клинские 300 грамм", price='130'),
                                 u"Нет": AddItem(item=u"Сосиски НеКлинские не любимые 300 грамм", price='70')})}, 'Usual')

Naggets = TItem(u"Наггетс",
             {'Usual': Question(u"Как обычно?",
                                {u"Да": AddItem(item=u"Наггетсы c сыром Клинские 300 грамм", price='130'),
                                 u"Нет": AddItem(item=u"Наггетсы НеКлинские не любимые 300 грамм", price='70')})}, 'Usual')

Milk = TItem(u"Молоко",
             {'Usual': Question(u"Как обычно?",
                                {u"Да": AddItem(item=u"Молоко 1 литр пастеризованное", price='60'),
                                 u"Нет": GotoQuestion("MilkType")} ),
              'HowMany': QuestionCount(u"Сколько?", 'count',
                  lambda x: AddItemWithCount(**x)),
              'MilkType': Question('Какое хотите?', {
                  u'Ясный луч 3.2% 1л, ультрапастеризованное': GotoQuestion("HowMany", item=u'Ясный луч 3.2% 1л, ультрапастеризованное', price=80),
                  u'Простоквашно 3,4-4,5% пастеризованое': GotoQuestion("HowMany",
                      item=u'Простоквашно 3,4-4,5% пастеризованое', price=75),
                  u'Домик в деревне ультрапастеризованное, 3.2%': GotoQuestion("HowMany",
                      item=u'Простоквашно 3,4-4,5% пастеризованое', price=75),
                  u'Другое':GotoQuestion("Other")}),
              'Other': Question(u"Скоропортящееся?",
                                {u"Да": GotoQuestion("fat", fast='1'),
                                 u"Нет": GotoQuestion("fat", fast='2')}),
              'ApproxPrice': QuestionCount(u"Приблизительная цена?", 'price', lambda x:
                  GotoQuestion('select', **x)),
              'fat': Question(u'Жирность?', {
                                  u'Диетическое': GotoQuestion("ApproxPrice", fat='0'),
                                  u'Средней жирности': GotoQuestion("ApproxPrice", fat='1'),
                                  u'Жирное': GotoQuestion("ApproxPrice", fat='2')}),
              'select':  QuesitonSelectFew(u"Время делать выбор!", {'select': ['fat', 'fast'],
                  'sort': 'price'}, {
                    u'Ясный луч 3.2% 1л, ультрапастеризованное': CreateMilk("1", "0", 60),
                    u'Простоквашно 3,4-4,5% пастеризованое': CreateMilk("1", "1", 60),
                    u'Самое лучше молоко': CreateMilk("1", "2", 60),
                    u'Самое худшее молоко': CreateMilk("2", "0", 60),
                    u'Домик в деревне ультрапастеризованное, 3.2%': CreateMilk("2", "1", 60),
                    u'Неизвестная марка молока': CreateMilk("2", "2", 60),
                      }, GotoQuestion("HowMany"), saveTo='item')
              }, 'Usual')

ALCO = TItemFromNet(os.path.dirname(os.path.abspath(__file__)) + "/126")

arr1 = [118, 119, 120, 121, 122, 123, 125, 126, 127, 128, 129, 130, 131, 132, 1692, 66, 69, 70, 903, 904, 906]

arr2 = [1977, 20, 22, 23, 24, 25, 26, 28, 29, 3, 30, 31, 32, 33, 34, 35, 4, 42, 43, 44, 45, 46, 47, 48, 49]

arr = list(set(arr1 + arr2))

LIST = map(lambda x: TItemFromNet(os.path.dirname(os.path.abspath(__file__)) + "/" + str(x)), arr)

def Print(All):
    if All[0]:
        print All[0]
        for i, x in enumerate(All[1]):
            print i + 1, x
    else:
        print u"Добавили товар", All[1][0], u"в количестве", All[1][1]


def build(name, price, magaz):
    return {"shop_name": name, 'price': price, 'magaz': magaz}


def GetSosigeList():
    return [build(u"Сосиски Клинские 300 грамм", 130, "utkonos"), build(u"Сосиски Молочные 300 грамм", 180, "utkonos"), build(u"Сосиски Докторские 250г", 310, "azbuka")]


def GetMilkList():
    return [build(u'Ясный луч 3.2% 1л', 80, "utkonos"), build(u'Простоквашно 3,4-4,5%', 300, "azbuka"), build(u'Домик в деревне', 80, "utkonos"), build(u'Самое лучше молоко', 310, "azbuka")]


def GetBeerList():
    return [build(u'Жигули 3% 0.5л', 80, "utkonos"), build(u'Балтика 3% 0.5л', 30, "utkonos"),
            build(u'Hougarden 3% 0.5л', 70, "azbuka")]


def GetQuery(query):
    words = re.findall(ur'(?u)\w+', query.lower())
    if any([u'пиво' in word for word in words]):
        return GetBeerList()
    if any([u'сосиск' in word for word in words]):
        return GetSosigeList()
    if any([u'молок' in  word for word in words]):
        return GetMilkList()

Items = TItems([Beer, Sosige, Naggets, Milk], LIST)
