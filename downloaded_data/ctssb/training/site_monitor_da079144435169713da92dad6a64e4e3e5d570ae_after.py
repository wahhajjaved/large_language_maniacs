import re

from monitor.deduplicator.base import DeduplicatorBase


class DescriptionBasedDeduplicator(DeduplicatorBase):
    """
    Extract de-duplication data based on item description.
    """
    def __init__(self):
        self.regex = re.compile('\d{2,15}')

    def _extract_dedup_key(self, item):
        if 'description' not in item.attributes or not item.attributes['description']:
            return None

        description = item.attributes['price'] + ' ' + item.attributes['description']

        description = description\
            .replace(' ', '')\
            .replace('-', '')\
            .replace('/', '') \
            .replace('\\', '')

        numbers = self.regex.findall(description)

        if len(numbers) <= 2:
            # The price usually is at least 2 set of digits, i.e. two numbers. So having only two numbers should not be
            # sufficient for identifying two items as duplicated.
            return None

        numbers.sort()

        return ','.join(numbers)


if __name__ == '__main__':
    from monitor.storage.shelve import ShelveStorage
    from monitor.deduplicator.image import ImageBasedDeduplicator
    items = ShelveStorage('properties.db').load()
    desc_dedup = DescriptionBasedDeduplicator().procecss(items)
    img_dedup = ImageBasedDeduplicator().procecss(items)

    img_keysets = {}
    for itemlist in img_dedup.values():
        s = set([item.key for item in itemlist])
        for key in s:
            img_keysets[key] = s

    for _, value in desc_dedup.items():
        if len(value) > 1:
            s = img_keysets.get(value[0].key, None)
            img_found = True

            if not s:
                img_found = False
            else:
                for key in [v.key for v in value]:
                    if key not in s:
                        img_found = False

            if img_found:
                continue

            print '\n\nFound:'
            for item in value:
                print item.attributes['description']
                print item.link

    # print len([len(v) for v in dedup_dic.values() if len(v) > 1])
    # print sum(len(v) for v in dedup_dic.values() if len(v) > 1)
