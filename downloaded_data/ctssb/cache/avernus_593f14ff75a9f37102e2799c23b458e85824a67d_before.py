from avernus import data_sources, objects
from avernus.gui import threads
from avernus.objects import asset as asset_model, container, position
import datetime
import logging
import re


logger = logging.getLogger(__name__)
sources = data_sources.sources
current_searches = []
search_callback = None

# FIXME where is this used?
ASSET_TYPES = {
               asset_model.Bond: _('Bond'),
               asset_model.Etf: _('ETF'),
               asset_model.Fund: _('Fund'),
               asset_model.Stock: _('Stock'),
               }

TYPES ={
       "bond": asset_model.Bond,
       "etf": asset_model.Etf,
       "fund": asset_model.Fund,
       "stock": asset_model.Stock,
       }

def get_source_count():
    return len(sources.items())


def search(searchstring, callback=None, complete_cb=None, threaded=True):
    stop_search()
    global search_callback
    search_callback = callback
    for name, source in sources.iteritems():
        # check whether search function exists
        func = getattr(source, "search", None)
        if func:
            if threaded:
                try:
                    task = threads.GeneratorTask(func, _item_found_callback, complete_cb, args=searchstring)
                    current_searches.append(task)
                    task.start()
                except:
                    import traceback
                    traceback.print_exc()
                    logger.error("data source " + name + " not working")
            else:
                for res in func(searchstring):
                    item, source, source_info = res
                    _item_found_callback(item, source, source_info)


def stop_search():
    global current_searches
    for search in current_searches:
        search.stop()
    current_searches = []


def _item_found_callback(item, source, source_infos=None):
    # mandatory: isin, type, name
    if not validate_isin(item['isin']):
        return
    new = False
    existing_asset = check_asset_existance(source=source.name,
                                           isin=item['isin'],
                                           currency=item['currency'])
    # FIXME ugly
    if not existing_asset:
        new = True
        item['source'] = source.name
        assettype = item['type']
        del item['type']
        if 'yahoo_id' in item:
            del item['yahoo_id']
        if 'volume' in item:
            del item['volume']
        if assettype not in TYPES:
            return
        existing_asset = TYPES[assettype](**item)
        if source_infos is not None:
            for source_info in source_infos:
                asset_model.SourceInfo(source=source.name,
                               asset=existing_asset,
                               info=source_info)
    if new and search_callback:
        search_callback(existing_asset, 'source')


def validate_isin(isin):
    return re.match('^[A-Z]{2}[A-Z0-9]{9}[0-9]$', isin)


def update_assets(assets):
    if not assets:
        return
    for name, source in sources.iteritems():
        temp = filter(lambda s: s.source == name, assets)
        if temp:
            logger.debug("updating %s using %s" % (temp, source.name))
            for ret in source.update_stocks(temp):
                ret.emit("updated")
                yield ret


def update_asset(asset):
    update_assets([asset])


def get_historical_prices(asset, start_date=None, end_date=None):
    # detach asset from current sqlalchemy session
    try:
        objects.session.expunge(asset)
        other_session = True
    except:
        other_session = False

    if end_date is None:
        end_date = datetime.date.today() - datetime.timedelta(days=1)
    start_date = asset.get_date_of_newest_quotation()
    if start_date is None:
        start_date = datetime.date(end_date.year - 20, end_date.month, end_date.day)
    if start_date < end_date:
        for qt in sources[asset.source].update_historical_prices(asset, start_date, end_date):
            # qt : (stock, exchange, date, open, high, low, close, vol)
            if qt is not None:
                yield asset_model.Quotation(asset=asset, exchange=qt[1], \
                        date=qt[2], open=qt[3], high=qt[4], \
                        low=qt[5], close=qt[6], volume=qt[7])
    # needed to run as generator thread
    yield 1

    # merge asset into session again
    if other_session:
        objects.Session().commit()
        objects.session.merge(asset, load=False)


def update_historical_prices_asset(asset):
    end_date = datetime.date.today() - datetime.timedelta(days=1)
    start_date = asset.get_date_of_newest_quotation()
    if start_date == None:
        start_date = datetime.date(end_date.year - 20, end_date.month, end_date.day)
    yield get_historical_prices(asset, start_date, end_date)


def update_historical_prices(*args):
    assets = position.get_all_used_assets()
    l = len(assets)
    i = 0.0
    for asset in assets:
        for qt in get_historical_prices(asset):
            yield i / l
        i += 1.0
        yield i / l
    objects.Session().commit()
    yield 1


def check_asset_existance(source, isin, currency):
    return 0 < objects.session.query(asset_model.Asset).filter_by(isin=isin,
                                            source=source,
                                            currency=currency).count()


def update_all(*args):
    items = position.get_all_used_assets()
    itemcount = len(items)
    count = 0.0
    for item in update_assets(items):
        count += 1
        yield count / itemcount
    for item in objects.Session().query(container.Container).all():
        item.last_update = datetime.datetime.now()
    db.Session().commit()
    yield 1



def update_positions(portfolio):
    items = set(pos.asset for pos in portfolio if pos.quantity > 0)
    itemcount = len(items)
    count = 0.0
    for i in update_assets(items):
        count += 1
        yield count / itemcount
    portfolio.last_update = datetime.datetime.now()
    portfolio.emit("updated")
    yield 1
