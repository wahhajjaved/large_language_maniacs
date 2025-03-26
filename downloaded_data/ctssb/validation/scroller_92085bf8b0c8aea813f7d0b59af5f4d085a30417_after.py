"""
This class holds game object classes
"""
class BaseGameObj(object):
    """Basic game object template"""
    def __init__(self, name='', description='', getsound='', dropsound='', effects=[], *args, **kwargs):
        if not name and description and getsound and dropsound  and effects:
            self.name, self.description = kwargs['name'], kwargs['description']
            self.getsound, self.dropsound = kwargs['getsound'], kwargs['dropsound']
            self.effects = kwargs['effects']
        else:
            self.name=name
            self.description=description
            self.getsound=getsound
            self.dropsound=dropsound
            self.effects=effects

class Weapon(BaseGameObj):
    """Class for most weapons. 
        If you need to add any more attributes / methods, just subclass / inherit this.
        the Fire method does the spesified damage, and plays the swingsound. If you're custom weapon needs to do anything different, such as adding an affect, running a function, just use super and append you're code, or just overwrite it.
    """
    def __init__(self, swingsound='', equipsound='', damage='', *args, **kwargs):
        super(Weapon, self).__init__(self, *args, **kwargs) # inherit code from the BaseObj class
        """This class inherits from BaseGameObj, adding a few weapon spesific parameters and methods."""
        self.swingsound=swingsound
        self.equipsound=equipsound
        self.damage=damage
        


    def fire(self):
        """Fire this weapon.
            By default it plays the swingsound and does the spesified damage, you can modify or overwrite it as you're weapon needs.
        """
        # play sound here... not sure how to do
        # do damage in percentage
        # not yet implemented