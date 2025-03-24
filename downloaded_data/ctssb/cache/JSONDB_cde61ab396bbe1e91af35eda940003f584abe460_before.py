import json


class JSONDBSelection(object):

    def __init__(self, row_indexes, db):
        self._db = db
        self._rows = row_indexes

    def __getitem__(self, i):
        return self._db.get_row(self._rows[i])

    def __iter__(self):
        for row in self._rows:
            yield self._db.get_row(row)

    def __len__(self):
        return len(self._rows)

    def __str__(self):
        return json.dumps(map(self._db.get_row, self._rows))

    def update(self, key, value):
        for row in self._rows:
            self._db.update_row(row, key, value)
        self._db.save()

    def select(self, expression):
        indexes = []
        for row in self._rows:
            if expression(self[row]):
                indexes.append(row)
        return JSONDBSelection(indexes, self._db)
