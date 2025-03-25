#--- Utilities -------------------------------------------------------#
# Row factory classes, based on sqlite3's DBAPI implementation
# They take a 'row' tuple and the Cursor instance and return a row
# If collections is supported (2.6+ for namedtuple, 2.7+ for OrderedDict)
#
# Generic Constructor: RowFactoryClass(cursor, row)
#
# Use like this:
# >>> cursor.row_factory = NamedTupleRow
#
# the fetch* functions will then return nicer named rows
#
# TODO: Break out all row_factories to a compiled module for speed?
#
import collections


class NamedTupleRow(object):
    """
    A row_factory function for nice fast namedtuple rows
    
    Notes
    -----
    EXCEPT IT DOESN'T WORK WITH VIEWS due to Datascope 'dot' table.field View
    syntax!!
    
    To fix this, periods are replaced with underscores, which is better, but
    for programs that access the fields by named attribute, a little more
    esoteric...

    """
    def __new__(cls, cursor, row):
        Tuple = collections.namedtuple('NamedTupleRow', [d.name.replace('.','_') for d in cursor.description])
        return Tuple(*row)
        

class OrderedDictRow(collections.OrderedDict):
    """
    A row_factory function to make OrderedDict rows from row tuple
    
    Not as fast, but supports getitem syntax and the 'get' function, and can
    access duplicate-named fields in views with the dot-syntax names
    """
    # Have to build key/value tuple pairs...
    def __init__(self, cursor, row):
        super(OrderedDictRow,self).__init__([(d.name, row[n]) for n, d in enumerate(cursor.description)])
        
try:
    from obspy.core.utcdatetime import UTCDateTime
except ImportError:
    pass


class UTCOrdDictRow(collections.OrderedDict):
    """
    A row_factory function to make OrderedDict rows from row tuple
   
    This uses the UTCDateTime class to convert any type object that
    compares to dbTIME to a utcdatetime object.
    """
    def __init__(self, cursor, row):
        kv = [(d.name, (d.type_code==4 and row[n] is not None) and UTCDateTime(row[n]) or row[n]) for n, d in enumerate(cursor.description)]
        super(UTCOrdDictRow, self).__init__(kv)


class _SQLValues(object):
    @staticmethod
    def _sql_str(value):
        """
        Convert a value to a string suitable for an sql statement
        """
        if isinstance(value, str):
            v = "'{0}'".format(value.replace("'","''"))
        elif isinstance(value, float) or isinstance(value, int):
            v = str(value)
        elif value is None:
            v = 'NULL'
        else:
            raise TypeError("Your type not supported in SQLValuesRow!")
        return v

    @classmethod
    def _values(cls, row):
        """
        row : seq of values from a database
        
        Return
        ------
        list of strings formatted for SQL

        """
        return [cls._sql_str(r) for r in row]
    
    @staticmethod
    def values_str(values):
        return '(' + ', '.join(values) + ')'
        
    def __str__(self):
        """
        String of the tuple used as input for VALUES

        Input : sequence of SQL value strings

        """
        return self.values_str(self)


class SQLValuesRow(_SQLValues):
    """
    A row_factory function to provide SQL values
    
    Instance is a namedtuple with: field names as attributes.
                                   SQL strings as values
    
    Methods
    -------
    __str__ : The 'str' function will return a string suitable for passing after
              'VALUES' in an SQL statement

    Class Methods
    -------------
    values_str : class version of the __str__ function, if one would like to
                 make a subset of the returned values (for an UPDATE, e.g.)
                 from a custom sequence.
    
    """

    def __new__(cls, cursor, row):
        Tuple = collections.namedtuple(cls.__name__, [d.name.replace('.','_') for d in cursor.description])
        class_ = type(cls.__name__, (_SQLValues, Tuple,), {})
        return class_( *super(SQLValuesRow, cls)._values(row) )

#
#---------------------------------------------------------------------#

