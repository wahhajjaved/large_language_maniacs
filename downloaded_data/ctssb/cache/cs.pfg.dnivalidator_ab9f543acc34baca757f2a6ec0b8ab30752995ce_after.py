from zope.interface import implements
from Products.validation.interfaces.IValidator import IValidator
from Products.validation import validation

class Dni:
    """ Validates a String field to contain a Spanish ID card number
    and letter.

    The verification algorithm is described here:
      http://es.wikibooks.org/wiki/Algoritmo_para_obtener_la_letra_del_NIF

    """
    implements(IValidator)

    name = 'Dni'

    def __init__(self, name, title='', description=''):
        self.name = name
        self.title = title or name
        self.description = description

    def __call__(self, dni, *args, **kwargs):
        tabla = "TRWAGMYFPDXBNJZSQVHLCKE"
        dig_ext = "XYZ"
        reemp_dig_ext = {'X': '0', 'Y': '1', 'Z': '2'}
        numeros = "1234567890"
        dni = dni.upper()
        if len(dni) == 9:
            dig_control = dni[8]
            dni = dni[:8]
            if dni[0] in dig_ext:
                dni = dni.replace(dni[0], reemp_dig_ext[dni[0]])
            if len(dni) == len([n for n in dni if n in numeros]) and tabla[int(dni) % 23] == dig_control:
                return 1
        return ("Validation failed(%s): must be checked." % self.name)

    # def __call__(self, value, *args, **kwargs):
    #     if value[0] not in ['0','1','2','3','4','5','6','7','8','9']:
    #         value=value[1:]
    #     let = value[-1:].upper()
    #     number = value[:-1]
    #     number = int(number)
    #     number = number % 23
    #     letters = 'TRWAGMYFPDXBNJZSQVHLCKET'
    #     letter = letters[number:number + 1]
    #     if let == letter:
    #         return 1
    #     return ("Validation failed(%s): must be checked." % self.name)

validation.register(Dni('dni'))
