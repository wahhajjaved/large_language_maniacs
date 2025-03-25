from datetime import datetime

class DataValidationError(Exception):
    """ Used for an data validation errors when deserializing """
    pass

class Promotion:

    data = []

    def __init__(self, name=None, promo_type=None, value=None, start_date=datetime.max.date(), end_date=datetime.max.date(), detail=None):
        """ Initialize a Promotion """
        self.id = id(self)
        self.name = name or 'default'
        self.promo_type = promo_type or 'dollars'
        self.value = value or 0
        self.start_date = start_date
        self.end_date = end_date
        self.detail = detail or 'n/a'
    
    def save(self):
        """ Add a Promotion to the collection """
        Promotion.data.append(self)

    def delete(self):
        """ Removes a Promotion from the collection  """
        Promotion.data.remove(self)

    def serialize(self):
        return {
            "id": self.id,
            "name": self.name,
            "promo_type": self.promo_type,
            "value": self.value,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "detail": self.detail    
        }

    @staticmethod
    def __validate_promo_data(data):
        """ 
            validate data of promo
        """
        if not isinstance(data, dict):
            raise DataValidationError('Invalid promo: body of request contained bad or no data.')
        if 'id' in data:
            try:
                data['id']=int(data['id'])
            except ValueError as e:
                raise DataValidationError('Invalid promo: invalid id, int required. '+e.args[0])

        if 'promo_type' in data and data['promo_type'] not in ['$','%']:
            raise DataValidationError('Invalid promo: invalid promo type, $ or % required.')
        if 'value' in data:
            try:
                data['value']=float(data['value'])
            except ValueError as e:
                raise DataValidationError('Invalid promo: invalid value, number required. '+e.args[0])
        if 'start_date' in data:
            try:
                data['start_date']=datetime.strptime(data['start_date'],'%Y-%m-%d %H:%M:%S')
            except ValueError as e:
                raise DataValidationError('Invalid promo: invalid start date format, date format required: YYYY-MM-DD HH:MM:SS. '+e.args[0])
        if 'end_date' in data:
            try:
                data['end_date']=datetime.strptime(data['end_date'],'%Y-%m-%d %H:%M:%S')
            except ValueError as e:
                raise DataValidationError('Invalid promo: invalid end date format, date format required: YYYY-MM-DD HH:MM:SS. '+e.args[0])

    def deserialize(self, data):
        """
        Deserializes a Promotion from a dictionary
        Args:
            data (dict): A dictionary containing the Promotion data
        """
        Promotion.__validate_promo_data(data)
        if 'name' in data:
            self.name = str(data['name'])
        if 'promo_type' in data:
            self.promo_type = data['promo_type']
        if 'value' in data:
            self.value = data['value']
        if 'start_date' in data:
            self.start_date = data['start_date']
        if 'end_date' in data:
            self.end_date = data['end_date']
        if 'detail' in data:
            self.detail = str(data['detail'])

    @staticmethod
    def all():
        '''Return all promotions in the db'''
        return [promo for promo in Promotion.data]

    @staticmethod
    def find(conditions):
        """ conditions is a dictionary including all requirement for finding promos """
        Promotion.__validate_promo_data(conditions)

    @staticmethod
    def find_by_id(promo_id):
        """ Finds a Promo by it's ID """
        promos = [promo for promo in Promotion.data if promo.id == promo_id]
        return promos
