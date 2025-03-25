##############################################################################
#
# Copyright (c) 2002 Nexedi SARL and Contributors. All Rights Reserved.
#                    Jean-Paul Smets-Solanes <jp@nexedi.com>
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
##############################################################################

from Products.ERP5Type.Globals import InitializeClass, PersistentMapping
from Acquisition import aq_base
from AccessControl import ClassSecurityInfo
from Products.ERP5Type import Permissions
from Products.ERP5Type.Core.Folder import Folder
from Products.ERP5Type.Utils import cartesianProduct
from Products.ERP5Type.Base import TempBase
from Products.ERP5Type.Accessor.Constant import PropertyGetter as ConstantGetter

from zLOG import LOG

class XMLMatrix(Folder):
    """
        A mix-in class which provides a matrix like
        access to objects. Matrices are of any dimension.
        A single XMLMatrix may contain multiple matrices,
        of different dimension. Each matrix is associated to
        a so-called 'base_id'.

        We still must make XMLMatrix a subclass of Base so
        that we can inherit from ExtensionClass.Base
        which is required for multiple inheritance to work
        as expected. Read this for more information:

        http://www.daa.com.au/pipermail/pygtk/2001-May/001180.html

        In our case, we will use Folder because we want to inherit
        from Folder consistency checking

    """

    # Declarative security
    security = ClassSecurityInfo()

    # Matrix Methods
    security.declareProtected( Permissions.AccessContentsInformation,
                               'getCell' )
    def getCell(self, *kw , **kwd):
      """
          Access a cell at row and column
      """
      if getattr(aq_base(self), 'index', None) is None:
        return None

      base_id = kwd.get('base_id', "cell")
      if not self.index.has_key(base_id):
        return None

      cell_id = self.keyToId(kw, base_id = base_id)
      if cell_id is None:
        return None
      return self.get(cell_id)

    security.declareProtected( Permissions.AccessContentsInformation,
                               'getCellProperty' )
    def getCellProperty(self, *kw , **kwd):
      """
          Get a property of a cell at row and column
      """
      base_id= kwd.get('base_id', "cell")
      cell = self.getCell(*kw, **kwd)
      if cell is None:
        return None

      return cell.getProperty(base_id)

    security.declareProtected( Permissions.AccessContentsInformation,
                               'hasCell' )
    def hasCell(self, *kw , **kwd):
      """
          Checks if matrix corresponding to base_id contains cell specified
          by *kw coordinates.
      """
      return self.getCell(*kw, **kwd) is not None

    security.declareProtected( Permissions.AccessContentsInformation,
                               'hasCellContent' )
    def hasCellContent(self, base_id='cell'):
      """
          Checks if matrix corresponding to base_id contains cells.
      """
      aq_self = aq_base(self)

      if getattr(aq_self, 'index', None) is None:
        return 0

      if not self.index.has_key(base_id):
        return 0

      for i in self.getCellIds(base_id=base_id):
        if hasattr(self, i): # We should try to use aq_self if possible but XXX
          return 1

      return 0

    security.declareProtected( Permissions.AccessContentsInformation,
                               'hasInRange' )
    def hasInRange(self, *kw , **kwd):
      """
          Checks if *kw coordinates are in the range of the
        matrix in kwd['base_id'].
      """
      if getattr(aq_base(self), 'index', None) is None:
        return 0

      base_id = kwd.get('base_id', "cell")
      if not self.index.has_key(base_id):
        return 0
      base_item = self.index[base_id]
      for i, my_id in enumerate(kw):
        if not base_item.has_key(i) or not base_item[i].has_key(my_id):
          return 0

      return 1

    security.declareProtected( Permissions.ModifyPortalContent,
                               '_setCellRange' )
    def _setCellRange(self, *kw, **kwd):
      """
          Set a new range for a matrix.
          If needed, it will resize and/or reorder matrix content.
      """
      movement = {} # Maps original cell id to its new id for each moved cell.
      new_index = PersistentMapping()

      base_id = kwd.get('base_id', 'cell')
      if getattr(aq_base(self), 'index', None) is None:
        self.index = PersistentMapping()

      # Return if previous range is the same
      current_range = self.getCellRange(base_id=base_id)
      if current_range == list(kw): # kw is a tuple
        return

      # Create the new index for the range given in *kw
      for i, index_ids in enumerate(kw):
        temp = PersistentMapping()
        for j, my_id in enumerate(index_ids):
          temp[my_id] = j
        new_index[i] = temp

      if self.index.has_key(base_id):
        # Compute cell movement from their position in previous range to their
        # position in the new range.
        for i, i_value in self.index[base_id].iteritems():
          if new_index.has_key(i):
            temp = {}
            for my_id, my_value in i_value.iteritems():
              temp[my_value] = new_index[i].get(my_id)
            movement[i] = temp

      # List all valid cell ids for current base_id.
      object_id_list = []
      for obj in self.objectValues():
        object_id = obj.getId()
        if object_id.find(base_id) == 0:
          # Check that all '_'-separated fields are of int type.
          if (object_id) > len(base_id):
            try:
              int(object_id[len(base_id)+1:].split('_')[0])
              test = self._getOb(object_id) # If the object was created
                                            # during this transaction,
                                            # then we do not need to
                                            # work on it
              object_id_list.append(object_id)
            except (ValueError, KeyError):
              pass

      # Prepend 'temp_' to all cells, to avoid id conflicts while renaming.
      for object_id in object_id_list:
        new_name = 'temp_' + object_id
        obj = self._getOb(object_id)
        self._delObject(object_id)
        obj.id = new_name
        self._setObject(new_name, aq_base(obj))

      # Rename all cells to their final name.
      for object_id in object_id_list:
        # Retrieve the place of the object, for movement_0_0 it is ['0','0']
        object_place = object_id[len(base_id)+1:].split('_')
        to_delete = 1
        # We must have the same number of dimensions
        if len(object_place) == len(new_index):
          # Let us browse each dimension of the previous index
          for i in range(len(object_place)):
            # Build each part of the nex id by looking up int. values
            old_place = int(object_place[i])
            # We are looking inside the movement dictionnary where
            # we should move the object, so for example
            # 'qantity_2_5' is renamed as 'quantity_4_3'
            if movement.has_key(i):
              if movement[i].has_key(old_place):
                # Replace the place of the cell only if there where a change
                if (movement[i][old_place]) != None:
                  object_place[i] = str(movement[i][old_place])
                  to_delete = 0
                else:
                  object_place[i] = None

            # XXX In this case, we delete every cell wich are not in the
            # movement dictionnary, may be this is very bad, so may be
            # we need to add an extra check here, ie if
            # if movement[i].has_key(old_place) returns None,
            # We may want to keep the cell, but only if we are sure
            # the movement dictionnary will not define a new cell with this id

        new_object_id_list = []

        temp_object_id = 'temp_' + object_id
        o = self._getOb(temp_object_id)
        if not to_delete and not (None in object_place):
          self._delObject(temp_object_id) # In all cases, we have
                                          # to remove the temp object
          object_place.insert(0, base_id)
          new_name = '_'.join(object_place)
          o.id = new_name
          new_object_id_list.extend(new_name)
          self._setObject(new_name, aq_base(o))

          if new_name != object_id:
            # Theses two lines are very important, if the object is renamed
            # then we must uncatalog the previous one
            o.unindexObject(path='%s/%s' % (self.getUrl() , object_id))
            # Force a new uid to be allocated, because unindexObject creates
            # an activity which will later delete lines from catalog based
            # on their uid, and it is not garanted that indexation will happen
            # after this deletion.
            # It is bad to waste uids, but this data structure offers no
            # alternative because cell id gives its index in the matrix,
            # so reordering axes requires the cell id to change.
            # XXX: It can be improved, but requires most of this file to be
            # rewritten, and compatibility code must be written as data
            # structure would most probably change.
            o.uid = None
          o.reindexObject() # we reindex in case position has changed
                            # uid should be consistent
        else:
          # In all cases, we have to remove the temp object
          LOG("Del2 Object",0, temp_object_id)
          LOG("Del2 Object",0, str(o.uid))
          #ATTENTION -> if path is not good, it will not be able to uncatalog !!!
          #o.immediateReindexObject() # STILL A PROBLEM -> getUidForPath XXX

          if object_id not in new_object_id_list: # do not unindex a new object
            o.isIndexable = ConstantGetter('isIndexable', value=True)
            o.unindexObject(path='%s/%s' % (self.getUrl() , object_id))
            # unindexed already forced
            o.isIndexable = ConstantGetter('isIndexable', value=False)
          self._delObject(temp_object_id) # object will be removed
                                               # from catalog automaticaly
      # We don't need the old index any more, we
      # can set the new index
      self.index[base_id] = new_index

    security.declareProtected( Permissions.ModifyPortalContent, 'setCellRange' )
    def setCellRange(self, *kw, **kwd):
      """
          Update the matrix ranges using provided lists of indexes (kw).

          Any number of list can be provided
      """
      self._setCellRange(*kw, **kwd)
      self.reindexObject()

    security.declareProtected(Permissions.ModifyPortalContent,
                              '_updateCellRange')
    def _updateCellRange(self, base_id, **kw):
      """
        The asCellRange script is Portal Type dependent
        which is not the case with this kind of code
        a better implementation consists in defining asCellRange as a
        generic method at matrix level (OverridableMethod(portal_type))
        which lookups for script in class, meta_type and PT form
        interaction could be implemented with interaction workflow
        this method should be renamed updateCellRange or updateMatrixCellRange
        base_id is parameter of updateCellRange

        asCellRange scripts should be unified if possible
      """
      script = self._getTypeBasedMethod('asCellRange', **kw)
      try:
        cell_range = script(base_id=base_id, matrixbox=0, **kw)
      except UnboundLocalError:
        raise UnboundLocalError,\
              "Did not find cell range script for portal type: %r" %\
              self.getPortalType()
      self._setCellRange(base_id=base_id, *cell_range)

    security.declareProtected(Permissions.ModifyPortalContent,
                              'updateCellRange')
    def updateCellRange(self, base_id='cell', **kw):
      """ same as _updateCellRange, but reindex the object. """
      self._updateCellRange(base_id=base_id, **kw)
      self.reindexObject()


    security.declareProtected( Permissions.ModifyPortalContent,
                               '_renameCellRange' )
    def _renameCellRange(self, *kw, **kwd):
      """
          Rename a range for a matrix, this method can
          also handle a changement of the size of a matrix
      """
      base_id = kwd.get('base_id', 'cell')

      if getattr(aq_base(self), 'index', None) is None:
        self.index = PersistentMapping()

      # Return if previous range is the same
      current_range = self.getCellRange(base_id=base_id) or []
      if current_range == list(kw): # kw is a tuple
        LOG('XMLMatrix',0,'return form _setCellRange - no need to change range')
        return

      current_len = len(current_range)
      new_len = len(kw)
      len_delta = new_len - current_len

      # We must make sure the base_id exists
      # in the event of a matrix creation for example
      if not self.index.has_key(base_id):
        # Create an index for this base_id
        self.index[base_id] = PersistentMapping()

      cell_id_list = []
      for cell_id in self.getCellIdList(base_id = base_id):
        if self.get(cell_id) is not None:
          cell_id_list.append(cell_id)

      # First, delete all cells which are out of range.
      size_list = map(len, kw)
      if len_delta < 0:
        size_list.extend([1] * (-len_delta))
      def is_in_range(cell_id):
        for i, index in enumerate(cell_id[len(base_id)+1:].split('_')):
          if int(index) >= size_list[i]:
            self._delObject(cell_id)
            return False
        return True
      cell_id_list = filter(is_in_range, cell_id_list)

      # Secondly, rename coordinates. This does not change cell ids.
      for i in range(max(new_len, current_len)):
        if i >= new_len:
          del self.index[base_id][i]
        else:
          if i >= current_len:
            self.index[base_id][i] = PersistentMapping()
          for place in self.index[base_id][i].keys():
            if place not in kw[i]:
              del self.index[base_id][i][place]

          for j, place in enumerate(kw[i]):
            self.index[base_id][i][place] = j

      # Lastly, rename ids and catalog/uncatalog everything.
      if len_delta > 0:
        # Need to move, say, base_1_2 -> base_1_2_0
        appended_id = '_0' * len_delta
        for old_id in cell_id_list:
          cell = self.get(old_id)
          if cell is not None:
            new_id = old_id + appended_id
            self._delObject(old_id)
            cell.isIndexable = ConstantGetter('isIndexable', value=False)
            cell.id = new_id
            self._setObject(new_id, aq_base(cell))
            cell.isIndexable = ConstantGetter('isIndexable', value=True)
            cell.reindexObject()
            #cell.unindexObject(path='%s/%s' % (self.getUrl(), old_id))
      elif len_delta < 0:
        # Need to move, say, base_1_2_0 -> base_1_2
        removed_id_len = 2 * (-len_delta)
        for old_id in cell_id_list:
          cell = self.get(old_id)
          if cell is not None:
            new_id = old_id[:-removed_id_len]
            self._delObject(old_id)
            cell.isIndexable = ConstantGetter('isIndexable', value=False)
            cell.id = new_id
            self._setObject(new_id, aq_base(cell))
            cell.isIndexable = ConstantGetter('isIndexable', value=True)
            cell.reindexObject()
            #cell.unindexObject(path='%s/%s' % (self.getUrl(), old_id))

    security.declareProtected( Permissions.ModifyPortalContent,
                               'renameCellRange' )
    def renameCellRange(self, *kw, **kwd):
      """
          Update the matrix ranges using provided lists of indexes (kw).
          This keep cell values if we add/remove dimensions
          Any number of list can be provided
      """
      self._renameCellRange(*kw, **kwd)
      self.reindexObject()

    security.declareProtected(Permissions.AccessContentsInformation,
                              'getCellRange')
    def getCellRange(self, base_id='cell'):
      """
          Returns the cell range as a list of index ids
      """
      if getattr(aq_base(self), 'index', None) is None:
        return []
      cell_range = self.index.get(base_id, None)
      if cell_range is None:
        return None

      result = []
      for value in cell_range.itervalues():
        result_items = sorted(value.iteritems(), key=lambda x:x[1])
        result.extend(x[0] for x in result_items)
      return result

    security.declareProtected( Permissions.ModifyPortalContent, 'newCell' )
    def newCell(self, *kw, **kwd):
      """
          This method creates a new cell
      """
      if getattr(aq_base(self), 'index', None) is None:
        return None
      base_id = kwd.get('base_id', "cell")
      if not self.index.has_key(base_id):
        return None

      cell_id = self.keyToId(kw, base_id = base_id)
      if cell_id is None:
        raise KeyError, 'Invalid key: %s' % str(kw)

      cell = self.get(cell_id)
      if cell is not None:
        return cell
      else:
        return self.newCellContent(cell_id,**kwd)

    security.declareProtected( Permissions.ModifyPortalContent, 'newCellContent' )
    def newCellContent(self, cell_id, portal_type=None, **kw):
      """
        Creates a new content as a cell. This method is
        meant to be overriden by subclasses.
      """
      if portal_type is None:
        for x in self.allowedContentTypes():
          portal_type_id = x.getId()
          if id.endswith(' Cell'):
            portal_type = portal_type_id
            break

      return self.newContent(id=cell_id, portal_type=portal_type, **kw)

    security.declareProtected( Permissions.AccessContentsInformation,
                               'getCellKeyList' )
    def getCellKeyList(self, base_id = 'cell'):
      """
        Returns a list of possible keys as tuples
      """
      if getattr(aq_base(self), 'index', None) is None:
        return ()
      if not self.index.has_key(base_id):
        return ()
      index = self.index[base_id]
      id_tuple = [v.keys() for v in index.itervalues()]
      if len(id_tuple) == 0:
        return ()
      return cartesianProduct(id_tuple)

    security.declareProtected( Permissions.AccessContentsInformation,
                               'getCellKeys' )
    getCellKeys = getCellKeyList

    # We should differenciate in future existing tuples from possible tuples
    security.declareProtected( Permissions.AccessContentsInformation,
                               'getCellRangeKeyList' )
    getCellRangeKeyList = getCellKeyList

    security.declareProtected( Permissions.AccessContentsInformation, 'keyToId' )
    def keyToId(self, kw, base_id = 'cell'):
      """
        Converts a key into a cell id
      """
      index = self.index[base_id]
      cell_id_list = [base_id]
      append = cell_id_list.append
      for i, item in enumerate(kw):
        try:
          append(str(index[i][item]))
        except KeyError:
          return None
      return '_'.join(cell_id_list)

    security.declareProtected( Permissions.AccessContentsInformation,
                               'getCellIdList' )
    def getCellIdList(self, base_id = 'cell'):
      """
        Returns a list of possible ids as tuples
      """
      if getattr(aq_base(self), 'index', None) is None:
        return ()
      if not self.index.has_key(base_id):
        return ()
      result = []
      append = result.append
      for kw in self.getCellKeys(base_id = base_id):
        cell_id = self.keyToId(kw, base_id = base_id )
        if cell_id is not None:
          append(cell_id)

      return result

    security.declareProtected( Permissions.AccessContentsInformation,
                               'getCellIds' )
    getCellIds = getCellIdList

    security.declareProtected( Permissions.AccessContentsInformation, 'cellIds' )
    cellIds = getCellIdList

    # We should differenciate in future all possible ids for existing ids
    security.declareProtected( Permissions.AccessContentsInformation,
                               'getCellRangeIdList' )
    getCellRangeIdList = getCellIdList

    security.declareProtected( Permissions.AccessContentsInformation,
                               'getCellValueList' )
    def getCellValueList(self, base_id = 'cell'):
      """
        Returns a list of cell values as tuples
      """
      result = []
      append = result.append
      for id in self.getCellIdList(base_id=base_id):
        o = self.get(id)
        if o is not None:
          append(o)
      return result

    security.declareProtected( Permissions.AccessContentsInformation,
                               'cellValues' )
    cellValues = getCellValueList

    security.declareProtected( Permissions.AccessContentsInformation,
                               'getMatrixList' )
    def getMatrixList(self):
      """
        Return possible base_id values
      """
      if getattr(aq_base(self), 'index', None) is None:
        return ()
      return self.index.keys()

    security.declareProtected( Permissions.ModifyPortalContent, 'delMatrix' )
    def delMatrix(self, base_id = 'cell'):
      """
        Delete all cells for a given base_id

        XXX BAD NAME: make a difference between deleting matrix and matrix cells
      """
      ids = self.getCellIds(base_id = base_id)
      my_ids = []
      append = my_ids.append
      for i in self.objectIds():
        if i in ids:
          append(i)

      if len(my_ids) > 0:
        self.manage_delObjects(ids=my_ids)

    security.declareProtected( Permissions.AccessContentsInformation,
                               'delCells' )
    delCells = delMatrix

    security.declareProtected( Permissions.AccessContentsInformation,
                               '_checkConsistency' )
    def _checkConsistency(self, fixit=0):
      """
        Constraint API.
      """
      # Check useless cells
      to_delete_set = set()
      error_list = []
      def addError(error_message):
        if fixit:
          error_message += ' (fixed)'
        error = (self.getRelativeUrl(),
                 'XMLMatrix inconsistency',
                 102,
                 error_message)

        error_list.append(error)

      # We make sure first that there is an index
      if getattr(aq_base(self), 'index', None) is None:
        self.index = PersistentMapping()
      # We will check each cell of the matrix the matrix
      for obj in self.objectValues():
        object_id = obj.getId()
        # obect_id is equal to something like 'something_quantity_3_2'
        # So we need to check for every object.id if the value
        # looks like good or not. We split the name
        # check each key in index
        # First we make sure this is a cell
        object_id_split = object_id.split('_')

        base_id = None
        cell_coordinate_list = []
        while object_id_split:
          coordinate = None
          try:
            coordinate = int(object_id_split[-1])
          except ValueError:
            # The last item is not a coordinate, object_id_split hence
            # only contains the base_id elements
            base_id = '_'.join(object_id_split)
            break
          else:
            cell_coordinate_list.insert(0, coordinate)
            # the last item is a coordinate not part of base_id
            object_id_split.pop()

        if base_id is not None:
            if not self.index.has_key(base_id):
              # The matrix does not have this base_id
              addError("There is no index for base_id %s" % base_id)
              to_delete_set.add(object_id)
              continue

            # Check empty indices.
            empty_list = []
            base_item = self.index[base_id]
            for key, value in base_item.iteritems():
              if value is None or len(value) == 0:
                addError("There is no id for the %dth axis of base_id %s" % (key, base_id))
                empty_list.append(key)
            if fixit:
              for i in empty_list:
                del base_item[key]

            len_id = len(base_item)
            current_dimension = len(cell_coordinate_list)
            if current_dimension != len_id:
              addError("Dimension of cell is %s but should be %s" % (current_dimension,
                                                                     len_id))
              to_delete_set.add(object_id)
            else :
              for i, coordinate in enumerate(cell_coordinate_list):
                if coordinate >= len(base_item[i]):
                  addError("Cell %s is out of bound" % object_id)
                  to_delete_set.add(object_id)
                  break

      if fixit and len(to_delete_set) > 0:
        self.manage_delObjects(list(to_delete_set))

      return error_list

    security.declareProtected( Permissions.ModifyPortalContent, 'notifyAfterUpdateRelatedContent' )
    def notifyAfterUpdateRelatedContent(self, previous_category_url, new_category_url):
      """
        We must do some matrix range update in the event matrix range
        is defined by a category
      """
      LOG('XMLMatrix notifyAfterUpdateRelatedContent', 0, str(new_category_url))
      update_method = self.portal_categories.updateRelatedCategory
      for base_id in self.getMatrixList():
        cell_range = self.getCellRange(base_id=base_id)
        new_cell_range = []
        for range_item_list in cell_range:
          new_range_item_list = map(lambda c: update_method(c, previous_category_url, new_category_url), range_item_list)
          new_cell_range.append(new_range_item_list)
        kwd = {'base_id': base_id}
        LOG('XMLMatrix notifyAfterUpdateRelatedContent matrix', 0, str(base_id))
        LOG('XMLMatrix notifyAfterUpdateRelatedContent _renameCellRange', 0, str(new_cell_range))
        self._renameCellRange(*new_cell_range,**kwd)

class TempXMLMatrix(XMLMatrix):
  """
    Temporary XMLMatrix.

    If we need Base services (categories, edit, etc) in temporary objects
    we shoud used TempBase
  """
  isIndexable = ConstantGetter('isIndexable', value=False)

  def newCellContent(self, id):
    """
       Creates a new content in a cell.
    """
    new_temp_object = TempBase(id)
    self._setObject(id, new_temp_object)
    return self.get(id)

  def reindexObject(self, *args, **kw):
    pass

  def unindexObject(self, *args, **kw):
    pass

  def activate(self):
    return self

InitializeClass(XMLMatrix)
