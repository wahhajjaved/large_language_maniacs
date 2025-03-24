from decimal import Decimal
import simplejson

from zope.interface import implements
from zope.component import getMultiAdapter
from plone.app.layout.viewlets import ViewletBase

from simplelayout.base.interfaces import ISimpleLayoutListingViewlet

from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile


class VariationJSViewlet(ViewletBase):
    render = ViewPageTemplateFile('variationjs.pt')
    implements(ISimpleLayoutListingViewlet)

    def getItemDatas(self):
        result = []
        context = self.view.context
        objects = context.objectValues()
        for obj in objects:
            if obj.portal_type == "ShopItemBlock":
                shop_item = obj.getField('item').get(obj)
                shopitem_view = getMultiAdapter((shop_item, context.request),
                                                 name="view")
                item_datas = shopitem_view.getItemDatas()
                result.append(item_datas[0])
        return result

    def getVarDictsJSON(self):
        """Returns a JSON serialized dict with UID:varDict pairs, where UID
        is the ShopItem's UID and varDict is the item's variation dict.
        This is being used for the compact category view where inactive
        item variations must not be buyable.
        """
        varDicts = {}
        items = self.getItemDatas()
        for item in items:
            uid = item['uid']
            varConf = item['varConf']
            if varConf is not None:
                varDicts[uid] = dict(varConf.getVariationDict())
            else:
                varDicts[uid] = {}

            # Convert Decimals to Strings for serialization
            varDict = varDicts[uid]
            for vcode in varDict.keys():
                i = varDict[vcode]
                for k in i.keys():
                    val = i[k]
                    if isinstance(val, Decimal):
                        val = str(val)
                        i[k] = val

        return simplejson.dumps(varDicts)
