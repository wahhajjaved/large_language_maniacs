import os, sys, random, csv
from flask import Flask, render_template, url_for, request, redirect, session, make_response
from utils import auth
from utils import db_manager
import hashlib
#oauth imports and stuff
from oauth2client.client import flow_from_clientsecrets, OAuth2Credentials # OAuth library, import the function and class that this uses
from httplib2 import Http # The http library to issue REST calls to the oauth api

import json # Json library to handle replies

app = Flask(__name__)
app.secret_key = os.urandom(32)
app.config.update(dict( # Make sure the secret key is set for use of the session variable
    SECRET_KEY = 'secret'
    ))

#oauth login
@app.route('/login/', methods = ['POST', 'GET'])
def oauth_testing():
    flow = flow_from_clientsecrets('client_secrets.json',
                                   scope = ['https://www.googleapis.com/auth/userinfo.profile', 'https://www.googleapis.com/auth/userinfo.email'],
                                   redirect_uri = url_for('oauth_testing', _external = True))

    if 'code' not in request.args:
        auth_uri = flow.step1_get_authorize_url() # This is the url for the nice google login page
        return redirect(auth_uri) # Redirects to that page
    else: # That login page will redirect to this page but with a code in the request arguments
        auth_code = request.args.get('code')
        credentials = flow.step2_exchange(auth_code) # This is step two authentication to get the code and store the credentials in a credentials object
        session['credentials'] = credentials.to_json() # Converts the credentials to json and stores it in the session variable
        # session["logintype"] = request.form["submit"]
        return redirect(url_for('sample_info_route'))

#oauth stuff
@app.route('/auth/', methods = ['POST', 'GET'])
def sample_info_route():
    if 'credentials' not in session: # If the credentials are not here, user must login
        return redirect(url_for('oauth_testing'))

    credentials = OAuth2Credentials.from_json(session['credentials']) # Loads the credentials from the session

    if credentials.access_token_expired: # If the credentials have expired, login
        return redirect(url_for('oauth_testing'))
    else:
        http_auth = credentials.authorize(Http()) # This will authorize this http_auth object to make authenticated calls to an oauth api

        response, content = http_auth.request('https://www.googleapis.com/oauth2/v1/userinfo?alt=json') # Issues a request to the google oauth api to get user information

        c = json.loads(content) # Load the response
        # for thing in c:
        #     print "this is the key below"
        #     print thing
            # print
            # print "this is the value below"
            # print c[thing]
        # return c['email'] # Return the email
        #print session["logintype"]
        if c["hd"] and c["hd"] == "stuy.edu":
            if "logintype" in session:
                if db_manager.get_admin_list() and c["email"] in db_manager.get_admin_list():
                    return redirect(url_for("home"))
                else:
                    session['student'] = c["email"]
            else:
                if db_manager.get_admin_list() and c['email'] in db_manager.get_admin_list():
                    session["admin"] = c["email"]
            return redirect("/")

            # if db_manager.get_admin_list() and c['email'] in db_manager.get_admin_list():
            #     session['admin'] = c["email"]
            # else:
            #     session['student'] = c["email"]
            # return redirect("/")

        else:
            return redirect(url_for("/"), message="please login with your stuy.edu email")

@app.route('/slogin/', methods = ["POST"])
def slogin():
    session["logintype"] = "student"
    return redirect(url_for('oauth_testing'))
#home; redirects where you should be
@app.route('/')
def home():
    if 'admin' in session:
        return redirect(url_for('admin_home'))
    elif 'student' in session:
        return redirect(url_for('student_home'))
    elif 'super_admin' in session:
        return redirect(url_for('superAdmin_home'))
    else:
        on = (db_manager.get_site_status() == 'on')
        return render_template('student_login.html', on=on, isStudent = True)

@app.route('/superman/')
def superAdminLogin():
    if 'admin' in session:
        return redirect(url_for('admin_home'))
    elif 'student' in session:
        return redirect(url_for('student_home'))
    return render_template('super_admin_login.html')

@app.route('/auth-sal/', methods = ["POST"])
def auth_superAdmin():
    super_admin = db_manager.get_super_admin()
    inputted_password = request.form['password']
    if hashlib.sha512(inputted_password).hexdigest() == super_admin["password"]:
        session["super_admin"] = "super_admin"
        return redirect(url_for("superAdmin_home"))
    else:
        return render_template("super_admin_login.html", error="Incorrect Password")

@app.route("/sa-home/")
def superAdmin_home():
    if not "super_admin" in session:
        return redirect(url_for("home"))
    success = ""
    if 'success' in session:
        success = session['success']
        session.pop('success')
    return render_template("super_admin_home.html",success=success)

@app.route('/addsuccess/')
def addsuccess():
    if not "super_admin" in session:
        return redirect(url_for("home"))
    session['success'] = "Successfully added administrator!"
    return redirect(url_for('superAdmin_home'))

#admin login
@app.route('/admin-login/')
def adminLogin():
    if 'admin' in session:
        return redirect(url_for('admin_home'))
    elif 'student' in session:
        return redirect(url_for('student_home'))
    else:
        return render_template('admin_login.html')

#checks if all your information checks out
@app.route('/adddeptadmin/', methods=["POST"])
def addadmin():
    if len(request.form['email1']) == 0:
        ret = "Please fill in e-mail."
    elif not request.form['email1'].endswith("@stuy.edu"):
        ret = "Please use your stuy.edu e-mail."
    elif request.form['email1'] != request.form['email2']:
        ret = "E-mails don't match."
    else:
        ret = ''
        email = request.form["email1"]
        #p = hashlib.sha512(request.form["pass1"])
        lis = db_manager.get_admin_list()
        lis.append(email)
        db_manager.set_admin_list(lis)
        session['success'] = "Admin successfully added."
    return ret

@app.route('/changePass/', methods=['POST'])
def changePass():
    if len(request.form['pass']) == 0:
        return "Please enter password."
    if len(request.form['pass2']) == 0:
        return "Please confirm password."
    if request.form['pass'] != request.form['pass2']:
        return "Passwords do not match."
    if not passCheck(request.form['pass']):
        return "Please choose a stronger password. Passwords must be at least 8 characters, and contain one uppercase letter, one lowercase letter, and one number."
    db_manager.set_super_admin_password(hashlib.sha512(request.form['pass']).hexdigest())
    session['success'] = "Password changed successfully."
    return ''

#checks if your password is good
def passCheck(password):
    #length
    if len(password) < 8:
        return False
    #diff categories
    lower = 'abcdefghijklmnopqrstuvwxyz'
    upper = 'ABCDEFGHIJKLMNOPQRSTUVQXYZ'
    nums = '0123456789'
    #check
    ret = [0 if x in lower else 1 if x in upper else 2 if x in nums else 3 for x in password]
    return 0 in ret and 1 in ret and 2 in ret

#will only be run *after* Check Match, which accounts for checking info
# @app.route('/adddeptadmin/', methods=["POST"])
# def addadmin():
#     email = request.form["email1"]
#     db_manager.set_admin_list(db_manager.get_admin_list().append(email))
#     session['success'] = "%s successfully added as admin."%str(email)
#     return redirect(url_for('home'))

@app.route('/logout/')
def logout():
    if 'super_admin' in session:
        session.pop('super_admin')
    if 'admin' in session:
        session.pop('admin')
    if 'student' in session:
        session.pop('student')
        session.pop('logintype')
    return redirect(url_for('home'))

#student home
@app.route('/student_home/')
def student_home():
    if 'student' not in session:
        return redirect(url_for('home'))

    print session["student"]
    osis = db_manager.get_id(session["student"])

    student = db_manager.get_student(osis)
    num = db_manager.get_num_APs(osis)
    #print student
    #overallavg = student["overall_average"]
    #aps = ['one','two','three','four','five']
    selectedCourses = student["selections"]
    #student = db_manager.get_student(db_manager.get_id(session["student"]))
    #get_applicable_APs(student_id)
    #student["id"] for osis
    aps = db_manager.get_applicable_APs(osis)
    depts = db_manager.list_departments()
    print depts
    return render_template('student_home.html', numAps = num, aps=aps, myfxn=db_manager.get_course, selectedCourses=selectedCourses, student = student, depts=depts)


#NOTE: should allow students to sign up for class
@app.route('/signup/', methods=["POST"])
def signup():
    #print request.form["ap0"]
    session['signedUp'] = True
    signedup = []
    osis = db_manager.get_id(session["student"])
    for i in request.form:
        signedup.append(request.form[i])

    db_manager.edit_student(osis, "selections", signedup)
    print db_manager.get_student(osis)["selections"]
    return redirect(url_for('home'))

#admin home
@app.route('/admin_home/')
def admin_home():
    if 'admin' not in session:
        return redirect(url_for('oauth_testing'))
    courses = db_manager.get_APs()
    #print courses
    getdept = db_manager.list_departments_AP()
    cohorts = [db_manager.grade_to_cohort(9),db_manager.grade_to_cohort(10),db_manager.grade_to_cohort(11),db_manager.grade_to_cohort(12)]

    problems = db_manager.get_problematic_courses()
    if len(problems) > 0:
        problems = True
    else:
        problems = False

    success = False

    if 'success' in session:
        success = session['success']
        session.pop('success')

    on = (db_manager.get_site_status()=='on')

    print getdept

    return render_template('admin_home.html', courses= courses, login=True, depts=getdept, cohorts=cohorts, myfxn=db_manager.get_course, problems=problems, success=success, on=on)

#generate categorize form
@app.route('/categorize/')
def categorize():
    noProblems = False
    courses = db_manager.get_problematic_courses()
    if len(courses) <= 0:
        noProblems = True
    depts = db_manager.list_departments()
    return render_template('categorize.html',courses=courses, depts=depts, noProblems = noProblems, fxn=db_manager.get_course)

#categorize problematic courses
@app.route('/categorizeForm/', methods=['POST'])
def categorizeForm():
    #print request.form
    for course in request.form:
        db_manager.edit_course(course, "department", request.form[course])
    session['success'] = "Courses successfully categorized!"
    return redirect(url_for('home'))

#all settings functions
@app.route("/settings/", methods=['POST'])
def settings():
    if 'shut_down' in request.form:
        db_manager.set_site_status('off')
        session['success'] = 'Site shut down successfully'
    elif 'turn_on' in request.form:
        db_manager.set_site_status('on')
        session['success'] = 'Site turned on successfully'
    elif 'clear_db' in request.form:
        db_manager.clear_db()
        session['success'] = 'DB Cleared'
    elif 'clear_students' in request.form:
        db_manager.drop_students()
        session['success'] = "Students Cleared"
    elif 'export' in request.form:
        response = make_response(db_manager.export())
        cd = 'attachment; filename=studentSelections.csv'
        response.mimetype='text/csv'
        response.headers['Content-Disposition'] = cd
        return response

    return redirect(url_for('admin_home'))

#search
@app.route("/search/")
def search():
    query = request.query_string[7:]
    results = db_manager.get_student(query)
    courses = db_manager.get_APs()
    getdept = db_manager.list_departments_AP()
    return render_template("search.html",student=results, osis=query, courses=courses, depts=getdept, myfxn=db_manager.get_course)

#modify student
@app.route("/modify_student/", methods = ['POST'])
def modify_student():
    osis = request.form["osis"]
    #cohort
    if 'cohort' in request.form:
        cohort = request.form['cohort']
        db_manager.edit_student(osis, "cohort", cohort)
        print cohort
    #selections; returns list
    if 'selections' in request.form:
        selections = request.form.getlist('selections')
        db_manager.edit_student(osis, "selections", selections)
        print selections
    #exceptions; returns list
    if 'exceptions' in request.form:
        exceptions = request.form.getlist('exceptions')
        if exceptions != "":
            db_manager.edit_student(osis, "exceptions", exceptions)
        print exceptions
    #number of aps
    if 'extra' in request.form:
        extra = request.form['extra'] #UNICORN
        if extra.isdigit():
            db_manager.edit_student(osis, "extra", extra)

    session['success'] = "Student successfully modified!"
    return redirect(url_for('home'))

#delete students
@app.route("/delete_student/", methods = ['POST'])
def delete_student(): #UNICORN
    db_manager.remove_student(request.form['osis'])
    session['success'] = "%s successfully removed."%str(request.form['osis'])
    return redirect(url_for('home'))

#remove courses
@app.route('/rm_courses/', methods=["POST"])
def rm_course():
    #returns list
    for i in request.form:
        db_manager.remove_course(i)
    session['succes'] = "Courses removed." #UNICORN
    return redirect(url_for('home'))

#remove cohort
@app.route('/rm_cohort/', methods=["POST"])
def rm_cohort():
    cohort = request.form['cohort'] #UNICORN
    db_manager.remove_cohort(cohort)
    session['success'] = "Cohort %s successfully deleted!"%cohort
    return redirect(url_for('home'))

#options for editing course
@app.route('/mod/<course>/')
def mod(course):
    #NOTE: will eventually be list of courses in same dep't that can be prereqs
    #courses = db_manager.get_department_courses
    clist = {}
    course_info = db_manager.get_course(course)

    cohorts = [db_manager.grade_to_cohort(9),db_manager.grade_to_cohort(10),db_manager.grade_to_cohort(11),db_manager.grade_to_cohort(12)]
    depts = db_manager.list_departments()
    for dept in depts:
        clist[dept]=db_manager.get_department_courses(dept)
    print course_info
    return render_template('modify.html',course=str(course),courses=clist,course_info = course_info, special=True, cohorts=cohorts, depts=depts)

#does actual editing of course
@app.route('/modifyCourse/', methods = ['POST'])
def modifyCourse():
    dept = db_manager.list_departments()

    course = request.form['course']
    print "\n\n\nCOURSE" ,course

    if 'minGPA' in request.form:
        minGPA = request.form["minGPA"]
        db_manager.edit_course(course, "prereq_overall_average", minGPA)
    if 'minDept' in request.form:
        minDept = request.form["minDept"]
        db_manager.edit_course(course, "prereq_department_averages", minDept)
    if 'cohort' in request.form:
        cohort = request.form.getlist("cohort")
        cohortlist = []
        for i in cohort:
            if i:
                cohortlist.append(i)
        db_manager.edit_course(course, "grade_levels", cohortlist)
    if 'prereq' in request.form:
        prereqs = request.form.getlist("prereq")
        prereqlist = []
        for i in prereqs:
            if i:
                prereqlist.append(i)
        db_manager.edit_course(course, "prereq_courses", prereqlist)

    deptlist = []
    for i in request.form:
        if i in dept and request.form[i]:
            #i is dept, request.form[i] is grade
            #bc of weird storage format
            deptlist.append({i:request.form[i]})
            #db_manager.edit_course(course, "prereq_department_averages", minDept)
    db_manager.edit_course(course,"prereq_department_averages",deptlist)
    session['success'] = "Courses modified successfully!"
    return redirect(url_for('home'))

#function to add courses
@app.route('/validateCSV/', methods=['POST'])
def validateCSV():
    try:
        #read file
        fil = request.files['f'].read()
        fil = fil.replace("\r\n", "\n")
        #return file
        ret = []
        #split file by lines
        data = fil.split('\n')
        #get headers
        headers = []
        for i in data[0].split(','):
            headers.append(i.strip())
        for line in data[1:]:
            l = line.split(',')
            info = {}
            i = 0
            for category in headers:
                info[category] = l[i].strip()
                i += 1
                if i >= len(l):
                    break
            ret.append(info)
        db_manager.add_departments(ret)
        print "dept"
        db_manager.add_courses(ret)
        print "course"
        msg = "Courses uploaded succesfully!"
        session['success'] = msg
        return ''
    #bad file
    except:
        return 'Error. CSV is in invalid form.'

#functions to add students
@app.route('/validateTranscript/', methods=['POST'])
def validateTranscript():
    try:#read file
        fil = request.files['f'].read()
        fil = fil.replace("\r\n", "\n")
        #return file
        ret = []
        #split file by lines
        data = fil.split('\n')
        #get headers
        headers = []
        for i in data[0].split(','):
            headers.append(i.strip())
        for line in data[1:]:
            l = line.split(',')
            info = {}
            i = 0
            for category in headers:
                info[category] = l[i].strip()
                i += 1
                if i >= len(l):
                    break
            ret.append(info)
        print ret
        db_manager.add_students(ret)
        session['success'] = "Transcripts uploaded succesfully!"
        return ''
    except:
        return "Error. CSV is in invalid form."

if __name__ == '__main__':
    app.debug = True
    app.run()
