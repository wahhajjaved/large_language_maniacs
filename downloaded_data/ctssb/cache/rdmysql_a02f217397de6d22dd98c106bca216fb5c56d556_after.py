# -*- coding: utf-8 -*-

from .database import Database
from .expr import Expr, And, Or


class Table(object):
    """ 数据表 """
    __dbkey__ = 'default'
    __tablename__ = ''
    __indexes__ = ['id']

    def __init__(self, tablename=''):
        if tablename:
            self.__tablename__ = tablename
        self.reset()

    @property
    def db(self):
        if not hasattr(self, '_db') or not self._db:
            db = Database(self.__dbkey__)
            self.set_db(db)
        return self._db

    def set_db(self, db):
        if isinstance(db, Database):
            self._db = db
        return self

    def get_tablename(self):
        return self.__tablename__

    def reset(self, or_cond=False):
        self.condition = Or() if or_cond else And()
        self.additions = {}
        return self

    def filter(self, expr, *args):
        if isinstance(expr, str):
            expr = Expr(expr).op(*args)
        self.condition.append(expr)
        return self

    def filter_by(self, **where):
        self.condition.extend(**where)
        return self

    def order_by(self, field, direction='ASC'):
        if 'ORDER BY' not in self.additions:
            self.additions['ORDER BY'] = []
        order = '%s %s' % (field, direction)
        self.additions['ORDER BY'].append(order)
        return self

    def group_by(self, field):
        if 'GROUP BY' not in self.additions:
            self.additions['GROUP BY'] = []
        self.additions['GROUP BY'].append(field)
        return self

    def build_group_order(self):
        group_order = ''
        for key, vals in self.additions.items():
            item = ' %s %s' % (key, ', '.join(vals))
            group_order += item
        return group_order

    @staticmethod
    def unzip_pairs(row, keys=[]):
        if isinstance(row, dict):
            keys = row.keys()
        if len(keys) > 0:
            fields = "(`%s`)" % "`,`".join(keys)
            values = [row[key] for key in keys]
        else:
            fields = ''
            values = list(row)
        return keys, values, fields

    def insert(self, *rows, **kwargs):
        action = kwargs.get('action', 'INSERT INTO')
        if len(rows) == 0:
            return 0
        elif len(rows) > 10:
            action = action.replace('INTO', 'DELAYED')
        rows = list(rows)
        row = rows.pop(0)
        keys, params, fields = self.unzip_pairs(row)
        holders = ",".join(["%s"] * len(params))
        sql = "%s `%s` %s VALUES (%s)" % (action,
                                          self.get_tablename(), fields, holders)
        if len(rows) > 0:  # 插入更多行
            sql += (", (%s)" % holders) * len(rows)
            for row in rows:
                keys, values, _fields = self.unzip_pairs(row, keys)
                params.extend(values)
        rs = self.db.execute_write(sql, And(), *params)
        return rs[1] if rs else 0  # 最后的自增ID

    def delete(self, **where):
        sql = "DELETE FROM `%s`" % self.get_tablename()
        condition = self.condition
        if len(where) > 0:
            condition = condition.clone().extend(**where)
        rs = self.db.execute_write(sql, condition)
        return rs[0] if rs else -1  # 影响的行数

    def update(self, changes, **where):
        assert isinstance(changes, dict)
        keys, values, _fields = self.unzip_pairs(changes)
        fields = ",".join(["`%s`=%%s" % key for key in keys])
        sql = "UPDATE `%s` SET %s" % (self.get_tablename(), fields)
        condition = self.condition
        if len(where) > 0:
            condition = condition.clone().extend(**where)
        rs = self.db.execute_write(sql, condition, *values)
        return rs[0] if rs else -1  # 影响的行数

    def save(self, row, indexes=None):
        assert hasattr(row, 'iteritems')
        if indexes is None:  # 使用主键
            indexes = self.__indexes__
        data, where = {}, {}
        for key, value in row.iteritems():
            if key not in indexes:
                data[key] = value
            elif value is not None:
                where[key] = value
        affect_rows = 0
        if len(where) > 0:  # 先尝试更新
            affect_rows = self.update(data, **where)
        if not affect_rows:  # 再尝试插入/替换
            data.update(where)
            insert_id = self.insert(data, action='REPLACE INTO')
            return True, insert_id
        else:
            return False, affect_rows

    def iter(self, coulmns='*', model=dict, **kwargs):
        """
        分批读取数据，注意设置step或limit的值
            Error: Socket receive buffer full
            当一次读取的内容超长时，需要设置step为较小值
        """
        limit = int(kwargs.get('limit', -1))
        offset = int(kwargs.get('offset', 0))
        step = int(kwargs.get('step', 250000))
        total = 0
        if limit > 0:
            total = offset + limit
            if step > 0:
                step = min(limit, step)
            else:
                step = limit
        if isinstance(coulmns, (list, tuple, set)):
            coulmns = ",".join(coulmns)
        sql = "SELECT %s FROM `%s`" % (coulmns, self.get_tablename())
        group_order = self.build_group_order()
        while limit <= 0 or offset < total:
            addition = group_order
            if step > 0:
                addition += " LIMIT %d, %d" % (offset, step)
                offset += step
            rs = self.db.execute_read(sql, self.condition, addition)
            if len(rs.rows) == 0:
                break
            for row in self.db.fetch(rs, model=model):
                yield row
            if step <= 0:
                break

    def all(self, coulmns='*', model=dict, index=None, **kwargs):
        if index is None:
            return [row for row in self.iter(coulmns, model, **kwargs)]
        else:
            result = []
            for row in self.iter(coulmns, model, **kwargs):
                key = row.get(index, None)
                if key is not None:
                    result.append((key, row))
            return result

    def one(self, coulmns='*', model=dict):
        rows = self.all(coulmns, model=model, limit=1)
        if rows and len(rows) > 0:
            return rows[0]
        elif model is dict:
            return {}

    def apply(self, name, *args, **kwargs):
        name = name.strip().upper()
        if name == 'COUNT' and len(args) == 0:
            column = 'COUNT(*)'
        else:
            column = '%s(%s)' % (name, ', '.join(args))
        row = self.one(column, dict)
        if row and row.has_key(column):
            result = row[column]
        else:
            result = kwargs.pop('default', None)
        if kwargs.has_key('coerce'):
            result = kwargs['coerce'](result)
        return result

    def count(self, *args, **kwargs):
        kwargs['coerce'] = int
        if not kwargs.has_key('default'):
            kwargs['default'] = 0
        return self.apply('count', *args, **kwargs)

    def sum(self, *args, **kwargs):
        if not kwargs.has_key('default'):
            kwargs['default'] = 0
        return self.apply('sum', *args, **kwargs)

    def max(self, *args, **kwargs):
        return self.apply('max', *args, **kwargs)

    def min(self, *args, **kwargs):
        return self.apply('min', *args, **kwargs)

    def avg(self, *args, **kwargs):
        return self.apply('avg', *args, **kwargs)
