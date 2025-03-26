import os
import csv
from reports.core import BaseTendersUtility, NEW_ALG_DATE
from reports.helpers import (
    value_currency_normalize
)


class TendersUtility(BaseTendersUtility):

    def __init__(self):
        super(TendersUtility, self).__init__('tenders')
        self.headers = ["tender", "tenderID", "lot",
                        "status", "lot_status", "currency",
                        "kind", "value", "rate", "bill"]
        [self.headers.remove(col) for col in self.skip_cols if col in self.headers]

    def row(self, record):
        rate = None
        tender = record.get('tender', '')
        lot = record.get('lot', '')
        status = record.get('status', '')
        lot_status = record.get('lot_status', '')
        date = record.get('startdate', '')
        if date < self.threshold_date:
            version = 1
        elif date > NEW_ALG_DATE:
            version = 3
        else:
            version = 2
        if lot:
            if ','.join([tender, lot]) in self.ignore:
                self.Logger.info(
                    'Skip tender {} with lot {} by'
                    ' ignore list'.format(tender, lot))
                return '', ''
        else:
            if '{},'.format(tender) in self.ignore:
                self.Logger.info(
                    'Skip tender {} by ignore list'.format(tender)
                )
                return '', ''
        if record.get('kind') not in self.kinds and version != 3:
            self.Logger.info('Skip tender {} by kind'.format(tender))
            return '', ''
        if self.check_status(status, lot_status) and version != 3:
            self.Logger.info('Skip tender {} by status {}'.format(tender, status))
            return '', ''
        row = list(record.get(col, '') for col in self.headers[:-2])
        value = float(record.get(u'value', 0))
        if record[u'currency'] != u'UAH':
            old = value
            value, rate = value_currency_normalize(
                value, record[u'currency'], record[u'startdate']
            )
            msg = "Changed value {} {} by exgange rate {} on {}"\
                " is  {} UAH in {}".format(
                    old, record[u'currency'], rate,
                    record[u'startdate'], value, record['tender']
                )
            self.Logger.info(msg)
        r = str(rate) if rate else ''
        row.append(r)
        row.append(self.get_payment(value, record.get('startdate', '') < self.threshold_date))
        self.Logger.info(
            "Refund {} for tender {} with value {}".format(
                row[-1], row[0], value
            )
        )
        return row, version

    def write_csv(self):
        is_added = False
        second_version = []
        new_version = []
        splitter_before = [u'before_2017']
        splitter_after = [u'after_2017-01-01']
        splitter_new = [u'after {}'.format(NEW_ALG_DATE)]
        if not self.headers:
            raise ValueError
        if not os.path.exists(os.path.dirname(os.path.abspath(self.put_path))):
            os.makedirs(os.path.dirname(os.path.abspath(self.put_path)))
        with open(self.put_path, 'w') as out_file:
            writer = csv.writer(out_file)
            writer.writerow(self.headers)
            for row, ver in self.rows():
                if ver == 1:
                    if not is_added:
                        writer.writerow(splitter_before)
                        is_added = True
                    writer.writerow(row)
                elif ver == 2:
                    second_version.append(row)
                else:
                    new_version.append(row)
            if second_version:
                writer.writerow(splitter_after)
                for row in second_version:
                    writer.writerow(row)
            if new_version:
                writer.writerow(splitter_new)
                for row in new_version:
                    writer.writerow(row)

    def rows(self):
        for resp in self.response:
            r, ver = self.row(resp['value'])
            if r:
                yield r, ver


def run():
    utility = TendersUtility()
    utility.run()

if __name__ == "__main__":
    run()
