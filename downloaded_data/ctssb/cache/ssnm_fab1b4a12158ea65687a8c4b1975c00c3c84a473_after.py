import turbogears, cherrypy, urllib
from turbogears import controllers

from ecomap.model import *
from ecomap.helpers import *
from ecomap.helpers.cherrytal import CherryTAL, site_root
from ecomap.helpers import EcomapSchema
from DisablePostParsingFilter import DisablePostParsingFilter

#from cherrypy.lib import httptools
from mx import DateTime
import sys, os.path
import StringIO
import cgitb
import formencode
from formencode import validators
from formencode import htmlfill
from xml.dom.minidom import parseString

UNI_PARAM = "UNI"
AUTH_TICKET_PARAM = "auth_ticket"
#ADMIN_USERS = ("kfe2102","dm2150","ssw12")

def get_uni():
    return cherrypy.session.get("UNI",None)

def get_user():
    return Ecouser.select(Ecouser.q.uni == get_uni().encode('utf8'))[0]

def get_auth():
    return cherrypy.session.get("auth_ticket",None)

def get_fullname():
    return cherrypy.session.get('fullname','')

def message(m):
    cherrypy.session['message'] = m

def build_controllers():
    cherrypy.root             = Eco()
    cherrypy.root.ecomap      = EcomapController()
    cherrypy.root.course      = CourseController()

class EcoControllerBase(CherryTAL):
    _template_dir = "ecomap/templates"
    _globals = {'login_name' : lambda: get_fullname()}

    def referer(self):
        return cherrypy.request.headerMap.get('Referer','/')

    def _cpOnError(self):
        err = sys.exc_info()
        if cherrypy.config.get('DEBUG',False):
            sio = StringIO.StringIO()
            hook = cgitb.Hook(file=sio)
            hook.handle(info=err)
            cherrypy.response.headerMap['Content-Type'] = 'text/html'
            cherrypy.response.body = [sio.getvalue()]
        else:
            # Do something else here.
            cherrypy.response.body = ['Error: ' + str(err[0])]

from windloginfilter import WindLoginFilter

def ensure_list(potential_list):
    if type(potential_list) is str:
        return [int(potential_list)]
    elif type(potential_list) is list:
        return potential_list
    else:
        return []


def admin_only(f):
    def wrapped(*args,**kwargs):
        if get_user().is_admin():
            return f(*args,**kwargs)
        else:
            message("You are not authorized to perform that action.  This event will be reported.")            
            raise cherrypy.HTTPRedirect("/course/")
    return wrapped

def uniq(l):
    u = {}
    for x in l:
        u[x] = 1
    return u.keys()    

def make_filling_parser(defaults,e=None):
    if e == None:
        return htmlfill.FillingParser(defaults)
    else:
        return htmlfill.FillingParser(defaults,errors=e.unpack_errors())    


### callbacks for WindLoginFilter ###

def update_session(auth=False,uni="",groups=[],ticket="",fullname=""):
    cherrypy.session["authenticated"] = auth
    cherrypy.session[UNI_PARAM] = uni
    cherrypy.session["groups"] = groups
    cherrypy.session[AUTH_TICKET_PARAM] = ticket
    cherrypy.session['fullname'] = fullname

def guest_login():
    """ allow someone without a uni to login """
    uni = cherrypy.request.paramMap.get("uni","")
    password = cherrypy.request.paramMap.get("password")
    if uni == "":
        return 
    u = get_user_or_fail(uni)
    if u == None:
        cherrypy.session['message'] = "The user %s does not exist." % uni
        return
    if u.password == password:
        # they're good
        update_session(True,uni,[],"guest ticket",u.fullname())
        raise cherrypy.HTTPRedirect('/course/')
    else:
        message("Login has failed.")
    # give them the login form
    return        

def backdoor():
    """ allow someone in through a special url for testing/debugging purposes"""
    u = get_or_create_user('kfe2102')        
    update_session(True,u.uni,[],"TICKET!!!",u.fullname())
    raise cherrypy.HTTPRedirect('/course/')

def testmode():
    u = get_or_create_user("foo")
    update_session(True,"foo",[],"test ticket",u.fullname())
    return

def is_authenticated():
    return cherrypy.session.get("authenticated",False)

def is_testmode():
    return cherrypy.config.get("TESTMODE",False)    


### end callbacks ###

class Eco(EcoControllerBase):
    strict_allowed_paths = ["/","flashConduit","/help","/contact","favicon.ico","/add_guest_account",
                            "/add_guest_account_form"]
    allowed_paths = ["/css/","/images/","/flash/"]
    
    _cpFilterList = [ DisablePostParsingFilter(),
                      WindLoginFilter(update_session,get_or_create_user,testmode,is_authenticated,is_testmode,
                                      after_login="/course/",allowed_paths=allowed_paths,
                                      strict_allowed_paths=strict_allowed_paths,
                                      special_paths={'/guest_login' : guest_login,
                                                     '/zerocool' : backdoor})]

    @cherrypy.expose()
    def index(self):
        return self.template("index.pt",{})

    @cherrypy.expose()
    def about(self):
        return self.template("about.pt",{})

    @cherrypy.expose()
    def help(self):
        return self.template("help.pt",{})

    @cherrypy.expose()
    def contact(self):
        return self.template("contact.pt",{})


    #legacy redirect for flash
    @cherrypy.expose()
    def myList(self):
        raise cherrypy.HTTPRedirect("/course")

    @cherrypy.expose()
    def flashConduit(self,HTMLid="",HTMLticket=""):
        #First, check to make sure there's a session established
        if not get_uni() and get_auth():
            return "<response>Session error</response>"

        user = get_user()
        post_length = int(cherrypy.request.headerMap.get('Content-Length',0))
        post_data = cherrypy.request.rfile.read(post_length)

        #post_data is going to have a ticket and an id to parse out

        try:
            doc = parseString(post_data)
        except:
            raise ParseError

        root = doc.getElementsByTagName("data")[0]

        #Check this data for reasonable stuff coming in
        ticketid  = safe_get_element_child(root,"ticket")
        ecoid     = safe_get_element_child(root,"id")
        action    = safe_get_element_child(root,"action")

        if ticketid != get_auth():
            print "This in't a valid session you little hacker! ;)"
            return "<data><response>Your session may have timed out.</response></data>"

        #tickets match, so the session is valid
        if ecoid == "":
            print "not a valid ecomap id"
            return "<data><response>That social support network map ID doesn't exist.</response></data>"
            
        this_ecomap = Ecomap.get(ecoid)
        # if this is public or it's yours or Susan, Debbie or I am logged in, allow the data to Flash
        if not (this_ecomap.public or this_ecomap.owner.uni == user.uni or user.is_admin()):
            print "not your ecomap and not public"
            return "<data><response>This is not your social support network map. Also, it isn't public.</response></data>"

        if action == "load":
            readonly = "true"
            if this_ecomap.owner.uni == user.uni:
                readonly = "false"
            return this_ecomap.load_ecomap(readonly)
        elif action == "save":
            if this_ecomap.owner.uni != user.uni:
                return "<data><response>This is not your social support network map.</response></data>"
            return this_ecomap.save_ecomap(root)
        else:
            print "unknown data action"
            return "<data><response>Unknown data action</response></data>"

    @cherrypy.expose()
    def logout(self,**kwargs):
        return self.template("logout.pt",{})

    def course_form(self,name,description,instructor,e=None):
        defaults = {'name' : name, 'description' : description, 'instructor' : instructor}
        parser = make_filling_parser(defaults,e)
        parser.feed(self.template("create_course.pt",{'all_instructors' : list(Ecouser.select(orderBy=['firstname']))}))
        parser.close()
        return parser.text()


    @cherrypy.expose()
    @admin_only
    def create_course_form(self):
        return self.course_form("","","")

    @cherrypy.expose()
    @admin_only
    def create_course(self,name="",description="",instructor="",students=""):
        es = CourseSchema()

        # MUST sanitize this comma delimited list
        uni_list = uniq(students.split(","))

        try:
            d = es.to_python({'name' : name, 'description' : description, 'instructor' : instructor})
            this_course = Course(name=d['name'],description=d['description'],instructor=d['instructor'])
            invalid_ids = this_course.add_students(uni_list)

            m = "The new course '" + name + "' has been created."
            if len(invalid_ids) > 0:
                m += " but the following UNIs were not valid: %s" % invalid_ids
            message(m)
            raise cherrypy.HTTPRedirect("/course")
        except formencode.Invalid, e:
            return self.course_form(name,description,instructor,e)

    @cherrypy.expose()
    def guest_login(self,uni="",password=""):
        return self.template("guest_login.pt",{})

    @cherrypy.expose()
    @admin_only
    def add_guest_account_form(self):
        return self.template("add_guest_account.pt",{})

    @cherrypy.expose()
    @admin_only
    def add_guest_account(self,uni="",firstname="",lastname="",password="",pass2=""):
        # TODO: this should be done with formencode
        if password != pass2:
            message("Those passwords don't match")
            raise cherrypy.HTTPRedirect("/add_guest_account_form")
        if uni == "":
            message("A user name is required")
            raise cherrypy.HTTPRedirect("/add_guest_account_form")
        u = Ecouser(uni=uni, securityLevel=2, password=password, firstname=firstname, lastname=lastname)
        message("New user has been created.  Please log in")
        raise cherrypy.HTTPRedirect("/guest_login")

    @cherrypy.expose()
    @admin_only
    def admin_users_form(self):
        return self.template("admin_users.pt",{'allUsers' : list(Ecouser.select(orderBy=['securityLevel','firstname']))})

    def delete_users(self,users):
        names = []
        for id in users:
            # get the user, remove him from all his courses and delete him
            user = Ecouser.get(id)
            names.append(user.fullname())
            user.delete()
        message("'" + ', '.join(names) + "' has been deleted.")
        raise cherrypy.HTTPRedirect("/admin_users_form")

    def toggle_admin(self,users):
        for id in users:
            # get the user and toggle his admin status
            user = Ecouser.get(id)
            user.toggle_admin()

        message("Users have had their status changed.")
        raise cherrypy.HTTPRedirect("/admin_users_form")
        

    def add_user(self,uni):
        try:
            u = create_user(uni)
            message("'" + u.fullname() + "' has been added")
        except InvalidUNI:
            message("That is not a valid UNI.")

    @cherrypy.expose()
    @admin_only
    def admin_users(self,**kwargs):
        person_list = ensure_list(kwargs.get('user_id',None))
        action = kwargs['action']

        if action == 'Delete Selected':
            return self.delete_users(person_list)
        
        if action == 'Change Security Level':
            return self.toggle_admin(person_list)

        elif action == 'Add User':
            self.add_user(kwargs.get('user_uni',None))
            raise cherrypy.HTTPRedirect("/admin_users_form")
        elif action == 'Add Guest Account':
            raise cherrypy.HTTPRedirect("/add_guest_account_form")
        

class RESTContent:
    @cherrypy.expose()
    def default(self, *vpath, **params):
        #import pdb; pdb.set_trace()
        if len(vpath) == 1:
            identifier = vpath[0]
            action = self.show
        elif len(vpath) == 2:
            identifier, verb = vpath
            verb = verb.replace('.', '_')
            action = getattr(self, verb, None)
            if not action:
                raise cherrypy.NotFound
            if not action.exposed:
                raise cherrypy.NotFound
        else:
            raise cherrypy.NotFound
        item = self.query(identifier)
        if item == None:
            raise cherrypy.NotFound
        else:
            return action(item, **params)


class EcomapController(EcoControllerBase,RESTContent):
    # convenience redirect to the RIGHT place
    @cherrypy.expose()
    def index(self):
        raise cherrypy.HTTPRedirect("/course")

    def query(self,id):
        return Ecomap.get(int(id))

    @cherrypy.expose()
    def show(self,ecomap,**kwargs):
        #import pdb; pdb.set_trace()
        server = '/'.join(cherrypy.request.browserUrl.split('/')[:3]) + '/'
        data = {
            'ecomap'     : ecomap,
            'id'         : ecomap.id,
            'ticket'     : get_auth(),
            'myName'     : get_fullname(),
            'server'     : server,
            'returnPath' : "course/%s" % ecomap.course.id,
            }
        return self.template("view_ecomap.pt",data)


def restrict_to_instructor_or_admin(f):
    def decorator(self,course,*args,**kwargs):
        if admin_or_instructor(get_user(),course):
            return f(self,course,*args,**kwargs)
        else:
            message("You don't have authorization to perform that action.  This event will be reported.")
            raise cherrypy.HTTPRedirect("/course")
    return decorator

def admin_or_instructor(user,course):
    return user.is_admin() or is_instructor(user,course)

class CourseController(EcoControllerBase,RESTContent):
    def query(self,id):
        return Course.get(int(id))

    @cherrypy.expose()
    def index(self):
        """ course list """
        # retreive the courses in which this user is a student
        user = get_user()
        my_courses = user.courses

        # retreive the course in which this user is an instructor
        instructor_of = user.instructor_courses()
        if instructor_of.count() == 0:
            instructor_of = None

        if len(my_courses) == 1 and not instructor_of:
            # This is a student with only one course.  Redirect to that course
            raise cherrypy.HTTPRedirect("/course/%s/" % my_courses[0].id)

        all_courses = []
        if user.is_admin():
            all_courses = get_all_courses()

        return self.template("list_courses.pt",{'all_courses' : all_courses, 'my_courses' : my_courses, 'instructor_of' : instructor_of})

    @cherrypy.expose()
    @admin_only
    def delete(self,course,confirm=""):
        course.delete()
        message("deleted")
        raise cherrypy.HTTPRedirect("/course")
        
    @cherrypy.expose()
    def show(self,course,**kwargs):
        """ This shows the list of ecomaps """
        user = get_user()

        if admin_or_instructor(user,course):
            all_ecos = course.ecomaps
        else:
            all_ecos = []
        return self.template("list_ecomaps.pt",
                             {'my_ecomaps' : user.course_ecos(course),
                              'public_ecomaps' : user.public_ecos_in_course(course),
                              'all_ecomaps' : all_ecos,
                              'course_name' : course.name,})


    def course_form(self,course, e=None):
        defaults = {'name' : course.name, 'description' : course.description, 'instructor' : course.instructor.id}
        parser = make_filling_parser(defaults,e)
        parser.feed(self.template("edit_course.pt",{'is_admin': get_user().is_admin(),
                                                    'course_name' : course.name, 'course' : course,
                                                    'all_instructors' : [i for i in Ecouser.select(orderBy=['firstname'])]}))
        parser.close()
        return parser.text()


    @cherrypy.expose()
    @admin_only
    def edit_form(self,course):
        return self.course_form(course)

    @cherrypy.expose()
    @admin_only
    def edit(self,course,name="",description="",instructor=""):
        es = CourseSchema()

        try:
            d = es.to_python({'name' : name, 'description' : description, 'instructor' : instructor})
            course.name = d['name']
            course.description = d['description']
            course.instructor = d['instructor']
            message("changes saved")
            raise cherrypy.HTTPRedirect("/course/" + str(course.id) + "/")

        except formencode.Invalid, e:
            return self.course_form(course,e)


    @cherrypy.expose()
    @restrict_to_instructor_or_admin
    def students(self,course):
        course_name = course.name
        return self.template("list_students.pt",{'students' : course.students, 'course_name' : course_name,})



    @cherrypy.expose()
    @restrict_to_instructor_or_admin
    def update_students(self,course,**kwargs):
        action = kwargs['action']
        if action == 'Delete Selected':
            removed = course.remove_students([Ecouser.get(id) for id in ensure_list(kwargs.get('student_id',None))])
            message("'" + ", ".join(removed) + "' has been deleted.")
            raise cherrypy.HTTPRedirect("/course/%s/students" % course.id)
        else:
            # unknown action
            raise cherrypy.HTTPRedirect("/course/%s/" % course.id)      

    @cherrypy.expose()
    def create_new(self,course):
        d = {
            'name'        : 'Enter Subject Name Here',
            'description' : 'Enter Description here',
            'owner'       : get_user().id,
            'course'      : course.id
            }

        this_ecomap = Ecomap(name=d['name'],description=d['description'],owner=d['owner'],course=d['course'])
        raise cherrypy.HTTPRedirect("/ecomap/%s/" % this_ecomap.id)

    @cherrypy.expose()
    def update(self,course,**kwargs):
        action = kwargs['action']
        item_list = [Ecomap.get(id) for id in uniq(ensure_list(kwargs.get('ecomap_id',None)))]
        if action == 'Delete Selected':
            # TODO:
            # if you are the owner or you're the instructor or an admin
            self.delete_ecomaps(item_list)
            
        elif action == 'share':
            for item in item_list:
                item.public = not item.public
            message("shared")

        raise cherrypy.HTTPRedirect("/course/%s/" % course.id)

    def delete_ecomaps(self,ecomaps):
        for ecomap in ecomaps:
            description = ecomap.description
            ecomap.destroySelf()
            message("'" + description + "' has been deleted.")
