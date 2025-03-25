
class User():
    def __init__(self):
        self.computer_riddles_completed = 0;

    @property
    def name(self):
        '''Name of current player'''
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    @property
    def purple_raider(self):
        '''Identifies as a member of the University of Mount Union'''
        return self._purple_raider

    @purple_raider.setter
    def purple_raider(self, attend_umu):
        self._purple_raider = bool('yes' in attend_umu.lower())

    @property
    def business_grades(self):
        '''Grades received on business questions in EBB'''
        return self._business_grades
    
    @business_grades.setter
    def business_grades(self, grades_dict):
        self._business_grades = grades_dict

    @property
    def engineering_grades(self):
        '''Grades received on engineering questions in EBB'''
        return self._engineering_grades

    @engineering_grades.setter
    def engineering_grades(self, grades_dict):
        self._engineering_grades = grades_dict

    @property
    def psychology_grades(self):
        '''Grades received on psychology questions in EBB'''
        return self._psychology_grades

    @psychology_grades.setter
    def psychology_grades(self, grades_dict):
        self._psychology_grades = grades_dict

    # @property
    # def computer_riddles_completed(self):
    #     '''Number of riddles completed in the EBB computer lab'''
    #     return self._computer_riddles_completed

    # @computer_riddles_completed.setter
    # def computer_riddles_completed(self):
    #     self._computer_riddles_completed += 1