'''
Created on Jan 27, 2012

@package: ally core
@copyright: 2011 Sourcefabric o.p.s.
@license: http://www.gnu.org/licenses/gpl-3.0.txt
@author: Gabriel Nistor

Provides the meta creation processor handler.
'''

from ally.api.operator.container import Model
from ally.api.operator.type import TypeModelProperty, TypeModel
from ally.api.type import TypeNone, Iter, Type, IterPart, List, typeFor, Boolean, \
    Integer, Number, Percentage, String, Time, Date, DateTime
from ally.container.ioc import injected
from ally.core.spec.data_meta import returnSame, MetaLink, MetaValue, MetaModel, \
    MetaPath, MetaCollection
from ally.core.spec.resources import ResourcesManager, Path
from ally.core.spec.server import Processor, Request, Response, ProcessorsChain
from ally.support.core.util_resources import nodeLongName
from ally.type_legacy import OrderedDict
from functools import partial
import logging

# --------------------------------------------------------------------

log = logging.getLogger(__name__)

returnTotal = lambda part: part.total
# Function that returns the total count of a part.

rgetattr = lambda prop, obj: getattr(obj, prop)
# A simple lambda that just reverses the getattr parameters in order to be used with partial.

# --------------------------------------------------------------------

@injected
class MetaCreatorHandler(Processor):
    '''
    Provides the meta creation based on the response object type. 
    
    Provides on request: NA
    Provides on response: [objMeta]
    
    Requires on request: resourcePath
    Requires on response: [objType]
    '''

    resourcesManager = ResourcesManager
    # The resources manager used in locating the resource nodes for the id's presented.

    def __init__(self):
        assert isinstance(self.resourcesManager, ResourcesManager), \
        'Invalid resources manager %s' % self.resourcesManager

    def process(self, req, rsp, chain):
        '''
        @see: Processor.process
        '''
        assert isinstance(req, Request), 'Invalid request %s' % req
        assert isinstance(rsp, Response), 'Invalid response %s' % rsp
        assert isinstance(chain, ProcessorsChain), 'Invalid processors chain %s' % chain

        if req.resourcePath is not None and rsp.objType is not None:
            rsp.objMeta = self.meta(rsp.objType, req.resourcePath)

        chain.proceed()

    # ----------------------------------------------------------------

    def meta(self, typ, resourcePath):
        '''
        Create the meta object for the provided type.
        
        @param typ: Type
            The type of the object to create the meta for.
        @param resourcePath: Path
            The resource path from where the value originated.
        @return: object
            The meta object.
        '''
        assert isinstance(resourcePath, Path), 'Invalid resource path %s' % resourcePath

        if isinstance(typ, Type):
            if isinstance(typ, Iter):
                assert isinstance(typ, Iter)

                if isinstance(typ, IterPart): getTotal = returnTotal
                else: getTotal = None

                itype = typ.itemType

                if isinstance(itype, TypeModelProperty):
                    return MetaCollection(self.metaProperty(itype, resourcePath), returnSame, getTotal)

                elif isinstance(itype, TypeModel):
                    assert isinstance(itype, TypeModel)
                    return MetaCollection(self.metaModel(itype, resourcePath), returnSame, getTotal)

                elif itype.isOf(Path):
                    return MetaCollection(MetaLink(returnSame), returnSame, getTotal)
                else:

                    assert log.debug('Cannot encode list item object type %r', itype) or True

            elif isinstance(typ, TypeNone):
                assert log.debug('Nothing to encode') or True

            elif isinstance(typ, TypeModelProperty):
                return self.metaProperty(typ, resourcePath)

            elif isinstance(typ, TypeModel):
                assert isinstance(typ, TypeModel)
                return self.metaModel(typ, resourcePath)

            else:
                assert log.debug('Cannot encode object type %r', typ) or True

    def metaProperty(self, typ, resourcePath, getValue=returnSame):
        '''
        Creates the meta for the provided property type.
        
        @param typ: Type
            The type to convert.
        @param resourcePath: Path
            The path reference to get the paths.
        @param getValue: Callable(object)
            A callable that takes as an argument the object to extract this property value instance.
        @return: Object
            The meta object.
        '''
        assert isinstance(typ, Type), 'Invalid type %s' % typ
        assert isinstance(resourcePath, Path), 'Invalid resource path %s' % resourcePath

        if isinstance(typ, TypeModelProperty):
            assert isinstance(typ, TypeModelProperty)

            if typ.container.propertyId == typ.property:
                path = self.resourcesManager.findGetModel(resourcePath, typ.parent)
                if path: metaLink = MetaPath(path, typ, getValue)
                else: metaLink = None
            else: metaLink = None

            return MetaModel(typ, getValue, metaLink, {typ.property: self.metaProperty(typ.type, resourcePath)})

        if isinstance(typ, TypeModel):
            assert isinstance(typ, TypeModel)
            typId = typeFor(getattr(typ.forClass, typ.container.propertyId))
            assert isinstance(typId, TypeModelProperty)
            path = self.resourcesManager.findGetModel(resourcePath, typ)
            if path: metaLink = MetaPath(path, typId, getValue)
            else: metaLink = None

            return MetaModel(typ, getValue, metaLink, {typId.property: self.metaProperty(typId.type, resourcePath)})

        if isinstance(typ, List):
            assert isinstance(typ, List)
            return MetaCollection(MetaValue(typ.itemType, returnSame), getValue)
        return MetaValue(typ, getValue)

    def metaModel(self, typ, resourcePath, getModel=returnSame):
        '''
        Creates the meta for the provided model.
        
        @param typ: TypeModel
            The model to convert to provide the meta for.
        @param resourcePath: Path
            The path reference to get the paths.
        @param getModel: Callable(object)|None
            A callable that takes as an argument the object to extract the model instance.
        @return: MetaModel
            The meta object.
        '''
        assert isinstance(typ, TypeModel), 'Invalid type model %s' % typ
        assert isinstance(resourcePath, Path), 'Invalid resource path %s' % resourcePath
        model = typ.container
        assert isinstance(model, Model)

        metas = {prop:self.metaProperty(ptyp, resourcePath, partial(rgetattr, prop))
                 for prop, ptyp in model.properties.items()}

        paths = self.resourcesManager.findGetAllAccessible(resourcePath)
        pathsModel = self.resourcesManager.findGetAccessibleByModel(model)
        paths.extend([path for path in pathsModel if path not in paths])
        metas.update({nodeLongName(path.node): MetaPath(path, typ, getModel) for path in paths})

        path = self.resourcesManager.findGetModel(resourcePath, typ)
        if path: metaLink = MetaPath(path, typ, getModel)
        else: metaLink = None

        return MetaModel(typ, getModel, metaLink, sortProperties(model, metas))

# --------------------------------------------------------------------


def sortProperties(model, metas):
    '''
    Used for sorting the metas properties dictionary.
    '''
    assert isinstance(model, Model), 'Invalid model %s' % model
    assert isinstance(metas, dict), 'Invalid metas dictionary %s' % metas

    idName = model.propertyId
    ordered = [(name, meta) for name, meta in metas.items() if isinstance(meta, MetaValue) and name != idName]
    ordered.sort(key=__sortKey)
    if idName in metas:
        ordered.insert(0, (idName, metas[model.propertyId]))

    sortedByName = [(name, meta) for name, meta in metas.items() if name not in ordered]
    sortedByName.sort(key=lambda pack: pack[0])

    ordered.extend((name, meta) for name, meta in sortedByName if isinstance(meta, MetaCollection))
    ordered.extend((name, meta) for name, meta in sortedByName if not isinstance(meta, (MetaValue, MetaCollection)))
    return OrderedDict(ordered)

TYPE_ORDER = [Boolean, Integer, Number, Percentage, String, Time, Date, DateTime]
def __sortKey(item):
    '''
    FOR INTERNAL USE.
    Provides the sorting key.
    '''
    name, meta = item
    assert isinstance(meta, MetaValue)
    for k, ord in enumerate(TYPE_ORDER, 1):
        if typeFor(ord) == meta.type:
            break
    return '%02d%s' % (k, name)
