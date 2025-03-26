from Classes.Parser import Parser
from Classes.ScholarshipPackageRequirementFormat import ScholarshipPackageRequirement


class GPA(Parser):
    def __init__(self, stringToScan, scholarshipPackageId='0'):
        self.stringToScan = stringToScan
        Parser.__init__(self, self.stringToScan, '\s[^$\d\.]?[1234]\.\d+')
        self.resultList = []
        self.attributeId = '1'
        self.requirementValue = ''
        self.logicGroup = '0'
        self.requirementTypeCode = '>='
        self.scholarshipPackageId = scholarshipPackageId

    def checkContext(self, contextCriteria):
        contextChecker = Parser(self.stringToScan.lower(), contextCriteria)
        return contextChecker.doesMatchExist()

    def getGPA(self):
        if self.checkContext('g\.?p\.?a\.?|grade\spoint\saverage|maintain\sa') and self.doesMatchExist():
            for i in self.getResult():
                self.resultList.append(i.strip())
        elif self.doesMatchExist():
            if not self.checkContext('million|billion|trillion|version|dollar|pound|euro'):
                for i in self.getResult():
                    self.resultList.append(i.strip())

        self.resultList = list(set(self.resultList))

        self.requirementValue = ', '.join(self.resultList)
        return self.requirementValue

    def updateLogicGroup(self):
        if self.checkContext('gpa|grade\spoint\saverage|maintain') and self.doesMatchExist():
            for i in self.getResult():
                self.resultList.append(i.strip())

        self.resultList = list(set(self.resultList))

        if len(self.resultList) >= 2:
            self.logicGroup = '1'

        return None

    def getScholarshipPackageRequirementFormat(self):
        self.updateLogicGroup()
        if self.getGPA() != '':
            GPA_SPRF = ScholarshipPackageRequirement(self.scholarshipPackageId, self.attributeId,
                                                     self.requirementTypeCode, self.getGPA(), self.logicGroup)

            return GPA_SPRF
