__author__ = 'RobinB'

from handlers.error_checks import *


class AllDeclarationsForEmployeeHandler(BaseRequestHandler):
    def get(self):
        if self.is_logged_in():
            query = Declaration.query(Declaration.created_by == self.logged_in_person().key).order(Declaration.created_at)
            respond_with_object_collection_with_query(self, query)


class AllDeclarationsForSupervisorHandler(BaseRequestHandler):
    def get(self):
        if self.is_logged_in():
            declaration_query = Declaration.query(ndb.OR(Declaration.class_name == 'open_declaration',
                                                         Declaration.class_name == 'locked_declaration'),
                                                  self.logged_in_person().key == Declaration.assigned_to).order(Declaration.created_at)
            respond_with_object_collection_with_query(self, declaration_query)


class AllHistoryDeclarationsForSupervisorHandler(BaseRequestHandler):
    def get(self):
        if self.is_logged_in():
            declaration_query = Declaration.query(ndb.OR(Declaration.class_name == 'supervisor_declined_declaration',
                                                         Declaration.class_name == 'supervisor_approved_declaration',
                                                         Declaration.class_name == 'human_resources_declined_declaration',
                                                         Declaration.class_name == 'human_resources_approved_declaration'),
                                                  self.logged_in_person().key == Declaration.assigned_to).order(-Declaration.created_at)
            respond_with_object_collection_with_query(self, declaration_query)


class AllDeclarationsForHumanResourcesHandler(BaseRequestHandler):
    def get(self):
        self.is_logged_in()
        self.check_hr()

        declaration_query = Declaration.query(Declaration.class_name == "supervisor_approved_declaration").order(Declaration.created_at)
        respond_with_object_collection_with_query(self, declaration_query)


class AllHistoryDeclarationsForHumanResourcesHandler(BaseRequestHandler):
    def get(self):
        self.is_logged_in()
        self.check_hr()

        declaration_query = Declaration.query(ndb.OR(Declaration.class_name == 'human_resources_declined_declaration',
                                                     Declaration.class_name == 'human_resources_approved_declaration')).order(-Declaration.created_at)
        respond_with_object_collection_with_query(self, declaration_query)
