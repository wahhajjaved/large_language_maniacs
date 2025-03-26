#-- coding: utf-8 --
from datetime import date
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext, loader, Context

from djtools.utils.mail import send_mail
from djzbar.utils.informix import do_sql

import datetime

ATHLETIC_IDS = "'S019','S020','S021','S022','S228','S043','S044','S056','S057','S073','S079','S080','S083','S090','S095','S220','S100','S101','S109','S126','S131','S156','S161','S172','S173','S176','S186','S187','S196','S197','S204','S205','S207','S208','S253','S215','S216'"

@login_required
def display(request, student_id):
    #Get information about the alumn(a|us)
    alumni = getStudent(student_id)
    if alumni != None:
        activities = getStudentActivities(student_id, False)
        athletics = getStudentActivities(student_id, True)
        relatives = getRelatives(student_id)
        privacy = getPrivacy(student_id)
    else:
        activities = None
        athletics = None
        relatives = None
        privacy = None

    return render_to_response(
        "manager/display.html",
        {
            'studentID':student_id, 'person':alumni, 'activities':activities,
            'athletics':athletics, 'relatives':relatives,
            'privacy':privacy
        },
        context_instance=RequestContext(request)
    )

@login_required
def update(request):
    #Retrieve the ID of the alumn(a|us)
    studentID = request.POST.get('carthageID')

    #Insert personal information
    alumni_sql = insertAlumni(studentID, request.POST.get('fname'), request.POST.get('lname'), request.POST.get('suffix'), request.POST.get('prefix'),
                   request.POST.get('email'), request.POST.get('maidenname'), request.POST.get('degree'), request.POST.get('class_year'), request.POST.get('business_name'),
                   request.POST.get('major1'), request.POST.get('major2'), request.POST.get('major3'), request.POST.get('masters_grad_year'), request.POST.get('job_title'))

    #Loop through all the relatives' records
    clearRelative(studentID)
    if request.POST.get('relativeCount'):
        for relativeIndex in range (1, int(request.POST.get('relativeCount')) + 1):
            relFname = request.POST.get('relativeFname' + str(relativeIndex))
            relLname = request.POST.get('relativeLname' + str(relativeIndex))
            relRelation = request.POST.get('relativeText' + str(relativeIndex))
    
            #Because of the way relationships are stored in CX, we must identify if the alumn(a|us) matches the first or second role in the relationship
            alumPrimary = 'Y'
            if(relRelation[-1:] == '1'):
                alumPrimary = 'N'
    
            if(relRelation[-1:] == '1' or relRelation[-1:] == '2'):
                relRelation = relRelation[0:-1]
    
            #If the relative has some value in their name and a specified relationship, insert the record
            if(len(relFname + relLname) > 0 and relRelation != ''):
                insertRelative(studentID, relRelation, relFname, relLname, alumPrimary)


    #Insert organizationa and athletic involvement
    if request.POST.get('activityCount'):
        for activityIndex in range (1, int(request.POST.get('activityCount')) + 1):
            activityText = request.POST.get('activity' + str(activityIndex))
    
            if(activityText):
                insertActivity(studentID, activityText)

    if request.POST.get('athleticCount'):
        for athleticIndex in range (1, int(request.POST.get('athleticCount')) + 1):
            athleticText = request.POST.get('athletic' + str(athleticIndex))
    
            if athleticText and (len(athleticText) > 0):
                insertActivity(studentID, athleticText)

    #Insert home and work address information
    insertAddress('WORK', studentID, request.POST.get('business_address'), request.POST.get('business_address2'), '',
                  request.POST.get('business_city'), request.POST.get('business_state'), request.POST.get('business_zip'), '', request.POST.get('business_phone'))

    insertAddress('HOME', studentID, request.POST.get('home_address1'), request.POST.get('home_address2'), request.POST.get('home_address3'),
                  request.POST.get('home_city'), request.POST.get('home_state'), request.POST.get('home_zip'), '', request.POST.get('home_phone'))


    #Clear privacy values
    clearPrivacy(studentID)

    #Insert updated privacy settings
    personal = request.POST.get('privacyPersonal','Y')
    insertPrivacy(studentID, 'Personal', personal)

    family = request.POST.get('privacyFamily','Y')
    insertPrivacy(studentID, 'Family', family)

    academics = request.POST.get('privacyAcademics','Y')
    insertPrivacy(studentID, 'Academics', academics)

    professional = request.POST.get('privacyProfessional','Y')
    insertPrivacy(studentID, 'Professional', professional)

    address = request.POST.get('privacyAddress','Y')
    insertPrivacy(studentID, 'Address', address)

    #Generate an email specifying the differences between the existing information and the newly submitted data
    emailDifferences(studentID)

    #Reuse the edit page
    return HttpResponseRedirect(reverse('manager_user_edit_success', kwargs={'student_id':studentID}))

@login_required
def search(request, messageSent = False, permissionDenied = False):
    fieldlist = [] #Collection of fieldnames used in search
    terms = [] #Collection of terms used in search
    matches = [] #Recordset of the alumni who match the search criteria
    message = ''
    sql = ''
    if request.method == 'POST':
        orSQL = ''
        andSQL = ''
        #Sport/activities are searched via "OR", all other fields are "AND" so assemble the list of fields to run through the logic to create the appropriate filters
        for rowNum in range (0, int(request.POST.get('maxCriteria')) + 1):
            fieldname = request.POST.get('within' + str(rowNum))
            searchterm = request.POST.get('term' + str(rowNum))

            if fieldname is not None and searchterm is not None and searchterm != '':
                fieldlist += (fieldname,)
                terms += (searchterm,)

                if fieldname == 'activity':
                    if len(orSQL) > 0:
                        orSQL += ' OR'
                    orSQL += ' LOWER(invl_table.txt) LIKE "%%%s%%"' % (searchterm.lower())
                elif fieldname == 'alum.cl_yr' or fieldname == 'ids.id':
                    if len(andSQL) > 0:
                        andSQL += ' AND'
                    andSQL += ' %s = %s' % (fieldname, searchterm)
                else:
                    if len(andSQL) > 0:
                        andSQL += ' AND'
                    andSQL += ' LOWER(TRIM(%s::varchar(250))) LIKE "%%%s%%"' % (fieldname, searchterm.lower())

        #Based on the criteria specified by the user, add the necessary tables to the search query
        selectFromSQL = ('SELECT alum.cl_yr AS class_year, ids.firstname, maiden.lastname AS maiden_name, ids.lastname, ids.id,'
                     ' NVL(TRIM(aaEmail.line1) || TRIM(aaEmail.line2) || TRIM(aaEmail.line3), "") AS email, LOWER(ids.lastname) AS sort1, LOWER(ids.firstname) AS sort2'
                     ' FROM alum_rec alum INNER JOIN id_rec ids ON alum.id = ids.id '
                     ' LEFT JOIN (SELECT prim_id, MAX(active_date) active_date FROM addree_rec WHERE style = "M" GROUP BY prim_id) prevmap ON ids.id = prevmap.prim_id'
                     ' LEFT JOIN addree_rec maiden ON maiden.prim_id = prevmap.prim_id AND maiden.active_date = prevmap.active_date AND maiden.style = "M"'
                     ' LEFT JOIN aa_rec aaEmail ON alum.id = aaEmail.id AND aaEmail.aa = "EML2" AND TODAY BETWEEN aaEmail.beg_date AND NVL(aaEmail.end_date, TODAY)'
                     ' LEFT JOIN hold_rec holds ON alum.id = holds.id AND holds.hld = "DDIR" AND CURRENT BETWEEN holds.beg_date AND NVL(holds.end_date, CURRENT)')
        #If search criteria includes activity or sport add the involvement tables
        if 'activity' in fieldlist:
            selectFromSQL += (
                     ' LEFT JOIN involve_rec ON ids.id = involve_rec.id'
                     ' LEFT JOIN invl_table ON involve_rec.invl = invl_table.invl')

        #If search criteria includes the student's major
        #QUESTION - Should we check all three major fields for each major specified or is sequence important?
        if 'major1.txt' in fieldlist or 'major2.txt' in fieldlist:
            selectFromSQL += (' LEFT JOIN prog_enr_rec progs ON ids.id = progs.id AND progs.acst = "GRAD"')
            if 'major1.txt' in fieldlist:
                selectFromSQL += (' LEFT JOIN major_table major1 ON progs.major1 = major1.major')
            if 'major2.txt' in fieldlist:
                selectFromSQL += (' LEFT JOIN major_table major2 ON progs.major2 = major2.major')

        #Privacy Settings - only add the restrictions for the fields actually included in the search criteria
        personal = ['ids.firstname', 'ids.lastname', 'maiden.lastname', 'ids.id', 'alum.cl_yr']
        if bool(set(personal) & set(fieldlist)) == True:
            selectFromSQL += ' LEFT JOIN stg_aludir_privacy per_priv ON ids.id = per_priv.id AND per_priv.fieldname = "Personal"'
            if len(andSQL) > 0:
                andSQL += ' AND'
            andSQL += ' NVL(per_priv.display, "N") = "N"'

        academics = ['activity', 'major1.txt', 'major2.txt']
        if bool(set(academics) & set(fieldlist)) == True:
            selectFromSQL += ' LEFT JOIN stg_aludir_privacy acad_priv ON ids.id = acad_priv.id AND acad_priv.fieldname = "Academics"'
            if len(andSQL) > 0:
                andSQL += ' AND'
            andSQL += ' NVL(acad_priv.display, "N") = "N"'

        professional = ['job_title']
        if bool(set(professional) & set(fieldlist)) == True:
            selectFromSQL += ' LEFT JOIN stg_aludir_privacy pro_priv ON ids.id = pro_priv.id AND pro_priv.fieldname = "Professional"'
            if len(andSQL) > 0:
                andSQL += ' AND'
            andSQL += ' NVL(pro_priv.display, "N") = "N"'

        address = ['home_city', 'home_state']
        if bool(set(address) & set(fieldlist)) == True:
            selectFromSQL += ' LEFT JOIN stg_aludir_privacy add_priv ON ids.id = add_priv.id AND add_priv.fieldname = "Address"'
            if len(andSQL) > 0:
                andSQL += ' AND'
            andSQL += ' NVL(add_priv.display, "N") = "N"'

        #If search criteria were submitted, flesh out the sql query. Include "and's", "or's" and sorting
        if len(andSQL + orSQL) > 0:
            if len(orSQL) > 0:
                orSQL = '(%s)' % (orSQL)
            if len(andSQL) > 0 and len(orSQL) > 0:

                andSQL = ' AND %s' % (andSQL)
            sql = '%s WHERE %s %s AND holds.hld_no IS NULL GROUP BY class_year, firstname, maiden_name, lastname, id, email, sort1, sort1 ORDER BY lastname, firstname, alum.cl_yr' % (selectFromSQL, orSQL, andSQL)

            objs = do_sql(sql)
            if objs:
                matches = objs.fetchall()

    if messageSent == True:
        message = "Your message was sent successfully!"

    if permissionDenied == True:
        message = "You do not have permission to edit this record."

    return render_to_response(
        "manager/search.html",
        {'message':message, 'searching':dict(zip(fieldlist, terms)), 'matches':matches, 'debug':sql},
        context_instance=RequestContext(request)
    )

@login_required
def edit(request, student_id, success = False):
    if int(student_id) == int(request.user.id) or request.user.is_superuser:
        #Retrieve relevant information about the alumni
        alumni = getStudent(student_id)
        activities = getStudentActivities(student_id, False)
        athletics = getStudentActivities(student_id, True)
        relatives = getRelatives(student_id)
        privacy = getPrivacy(student_id)

        #Assemble collections for the user to make choices
        majors = getMajors()
        prefixes = dict([('',''),('DR','Dr'),('MR','Mr'),('MRS','Mrs'),('MS','Ms'),('REV','Rev')])
        suffixes = ('','II','III','IV','JR','MD','PHD','SR')
        year_range = range(1900, date.today().year + 1)
        relationships = getRelationships()
        states = getStates()
        countries = getCountries()

        return render_to_response(
            "manager/edit.html",
            {'submitted':success,'studentID':student_id, 'person':alumni, 'activities':activities, 'athletics':athletics,
             'relatives':relatives, 'privacy':privacy, 'majors':majors, 'prefixes':prefixes, 'suffixes':suffixes,
             'years':year_range, 'relationships':relationships, 'states':states, 'countries':countries},
            context_instance=RequestContext(request)
        )
    else:
        return HttpResponseRedirect(reverse('manager_search_denied'))

@login_required
def message(request, student_id, recipientHasEmail = True):
    recipient = getMessageInfo(student_id)
    recipientHasEmail = len(recipient.email) > 0
    return render_to_response(
        "manager/create_message.html",
        {'validRecipient':recipientHasEmail, 'recipient':recipient},
        context_instance=RequestContext(request)
    )

@login_required
def send_message(request):
    recipient_id = request.POST.get('recipientID')
    recipient = getMessageInfo(recipient_id)

    attachEmail = request.POST.get('addEmail', 'N')
    emailBody = request.POST.get('emailBody')

    sender = getMessageInfo(request.user.id)

    #If the inforamation about the sender is unavailable, create empty/default values
    if sender == None or len(sender) == 0:
        sender = {
            'id':0,
            'email':'confirmation@carthage.edu',
            'firstname':'a',
            'lastname':'friend',
        }

    autoAddOn = ''
    if attachEmail == 'Y':
        autoAddOn = 'Y'

    #Initialize necessary components to generate email
    data = {'body':emailBody,'recipient':recipient,'auto':autoAddOn,'sender':sender}

    subject_line = "Message from %s %s via the Carthage Alumni Directory" % (sender.firstname, sender.lastname)
    send_mail(
        request, [recipient.email,], subject_line, sender.email,
        'manager/send_message.html', data, settings.MANAGERS
    )

    #Reuse the search page
    return HttpResponseRedirect(reverse('manager_search_sent', kwargs={'messageSent':True}))

def getStudent(student_id):
    #Compile all the one-to-one information about the alumn(a|us)
    sql = ('SELECT DISTINCT'
           '    ids.id AS carthage_id, TRIM(ids.firstname) AS fname, TRIM(ids.lastname) AS lname, TRIM(ids.suffix) AS suffix, TRIM(INITCAP(ids.title)) AS prefix, TRIM(NVL(email.line1,"")) email,'
           '    CASE'
           '        WHEN    NVL(ids.decsd, "N")    =    "Y"                THEN    1'
           '                                                               ELSE    0'
           '    END    AS is_deceased,'
           '    TRIM(NVL(maiden.lastname,"")) AS birth_lname, TRIM(NVL(progs.deg,"")) AS degree,'
           '    CASE'
           '        WHEN    TRIM(progs.deg)    IN    ("BA","BS")           THEN    alum.cl_yr'
           '                                                               ELSE    0'
           '    END    AS    class_year, TRIM(NVL(aawork.line1, "")) AS business_name, TRIM(NVL(aawork.line2,"")) AS business_address, TRIM(NVL(aawork.line3,"")) AS business_address2,'
           '    TRIM(NVL(aawork.city,"")) AS business_city, TRIM(aawork.st) AS business_state, TRIM(NVL(aawork.zip,"")) AS business_zip, TRIM(aawork.ctry) AS business_country,'
           '    TRIM(NVL(aawork.phone,"")) AS business_phone, TRIM(ids.addr_line1) AS home_address1, TRIM(ids.addr_line2) AS home_address2, TRIM(ids.addr_line3) AS home_address3,'
           '    TRIM(ids.city) AS home_city, TRIM(ids.st) AS home_state, TRIM(ids.zip) AS home_zip, TRIM(ids.ctry) AS home_country, TRIM(ids.phone) AS home_phone,'
           '    TRIM('
           '        CASE'
           '              WHEN    TRIM(progs.deg) IN    ("BA","BS")        THEN    major1.txt'
           '                                                               ELSE    conc1.txt'
           '       END'
           '    )    AS    major1,'
           '    TRIM('
           '        CASE'
           '               WHEN    TRIM(progs.deg)    IN    ("BA","BS")    THEN    major2.txt'
           '                                                               ELSE    conc2.txt'
           '        END'
           '    )    AS    major2,'
           '    TRIM('
           '        CASE'
           '               WHEN    TRIM(progs.deg)    IN    ("BA","BS")    THEN    major3.txt'
           '                                                               ELSE    ""'
           '        END'
           '    )    AS    major3,'
           '    CASE'
           '        WHEN    TRIM(progs.deg)    NOT IN ("BA","BS")          THEN    alum.cl_yr'
           '                                                               ELSE    0'
           '    END    AS    masters_grad_year, "" AS job_title'
           ' FROM    alum_rec    alum   INNER JOIN    id_rec            ids     ON    alum.id                =        ids.id'
           '                            LEFT JOIN    ('
           '                                SELECT prim_id, MAX(active_date) active_date'
           '                                FROM addree_rec'
           '                                WHERE style = "M"'
           '                                GROUP BY prim_id'
           '                            )                            prevmap    ON    ids.id                =       prevmap.prim_id'
           '                            LEFT JOIN    addree_rec      maiden     ON    maiden.prim_id        =       prevmap.prim_id'
           '                                                                    AND   maiden.active_date    =       prevmap.active_date'
           '                                                                    AND   maiden.style          =       "M"'
           '                            LEFT JOIN    aa_rec          email      ON    ids.id                =       email.id'
           '                                                                    AND   email.aa              =       "EML2"'
           '                                                                    AND   TODAY                 BETWEEN email.beg_date    AND    NVL(email.end_date, TODAY)'
           '                            LEFT JOIN    aa_rec          aawork     ON    ids.id                =       aawork.id'
           '                                                                    AND   aawork.aa             =       "WORK"'
           '                                                                    AND   TODAY                 BETWEEN aawork.beg_date   AND    NVL(aawork.end_date, TODAY)'
           '                            LEFT JOIN    prog_enr_rec    progs      ON    ids.id                =       progs.id'
           '                                                                    AND   progs.acst            =       "GRAD"'
           '                            LEFT JOIN    major_table     major1     ON    progs.major1          =       major1.major'
           '                            LEFT JOIN    major_table     major2     ON    progs.major2          =       major2.major'
           '                            LEFT JOIN    major_table     major3     ON    progs.major3          =       major3.major'
           '                            LEFT JOIN    conc_table      conc1      ON    progs.conc1           =       conc1.conc'
           '                            LEFT JOIN    conc_table      conc2      ON    progs.conc2           =       conc2.conc'
           ' WHERE   NVL(ids.decsd, "N") =   "N"'
           ' AND     ids.id              =   %s' %   (student_id)
    )
    student = do_sql(sql)
    obj = student.fetchone()
    if obj:
        stu = dict(obj)
        # we need to sanitize strings which may contain funky
        # windows characters that informix does not convert to
        # utf-8
        for key, value in stu.iteritems():
            if type(value) is str:
                stu[key] = value.decode('cp1252').encode('utf-8')
        return stu
    else:
        return None

def getStudentActivities(student_id, isSports = False):
    #Conditional statements to provide the correct logic and terminology depending whether activities or athletics are being returned
    fieldname = 'activity' if not isSports else 'sport'
    comparison = 'NOT' if not isSports else ''

    activities_sql = (
        'SELECT TRIM(invl_table.txt)    AS  %s'
        ' FROM   invl_table  INNER JOIN  involve_rec ON  invl_table.invl =   involve_rec.invl'
        ' WHERE  involve_rec.id  =       %s'
        ' AND    invl_table.invl MATCHES "S[0-9][0-9][0-9]"'
        ' AND    invl_table.invl %s IN  (%s)'
        ' ORDER BY   TRIM(invl_table.txt)'   %   (fieldname, student_id, comparison, ATHLETIC_IDS)
    )
    objs = do_sql(activities_sql)
    if objs:
        return objs.fetchall()
    else:
        return objs

def getRelatives(student_id):
    #Retrieve collection of relatives (regardless of whether the alumn(a|us) is the primary or secondary relationship)
    relatives_sql = (' SELECT'
                     '    TRIM('
                     '      CASE'
                     '            WHEN    rel.prim_id    =    %s    THEN    sec.firstname'
                     '                                              ELSE    prim.firstname'
                     '      END'
                     '    )    AS    firstName,'
                     '    TRIM('
                     '        CASE'
                     '            WHEN    rel.prim_id    =    %s    THEN    sec.lastname'
                     '                                              ELSE    prim.lastname'
                     '        END'
                     '    )    AS    lastName,'
                     '    TRIM('
                     '        CASE'
                     '            WHEN    rel.prim_id    =    %s    THEN    reltbl.sec_txt'
                     '                                              ELSE    reltbl.prim_txt'
                     '        END'
                     '    )    AS    relText,'
                     '    TRIM(reltbl.rel) ||'
                     '    CASE'
                     '        WHEN    rel.prim_id   =   %s  THEN    "2"'
                     '                                      ELSE    "1"'
                     '    END AS relCode'
                     ' FROM    relation_rec    rel    INNER JOIN    id_rec      prim    ON    rel.prim_id   =    prim.id'
                     '                                INNER JOIN    id_rec      sec     ON    rel.sec_id    =    sec.id'
                     '                                INNER JOIN    rel_table   reltbl  ON    rel.rel       =    reltbl.rel'
                     ' WHERE'
                     '      TODAY   BETWEEN rel.beg_date    AND NVL(rel.end_date, TODAY)'
                     '      AND'
                     '      rel.rel IN  ("AUNN","COCO","GPGC","HW","HWNI","PC","SBSB")'
                     '      AND'
                     ' ('
                     '      prim_id =   %s'
                     '      OR'
                     '      sec_id  =   %s'
                     ' )' % (student_id, student_id, student_id, student_id, student_id, student_id)
    )
    objs = do_sql(relatives_sql)
    if objs:
        return objs.fetchall()
    else:
        return objs

def getPrivacy(student_id):
    privacy_sql = ("SELECT TRIM(fieldname) AS fieldname, TRIM(display) AS display FROM stg_aludir_privacy WHERE id = %s ORDER BY fieldname") % (student_id)
    privacy = do_sql(privacy_sql)
    field = []
    setting = []
    for row in privacy:
        field += (row.fieldname,)
        setting += (row.display)
    return dict(zip(field, setting))

def getRelationships():
    #Hardcoded collection of relationships because the entire collection of values in rel_table are not valid for the alumni directory
    relationships = dict([('',''),('HW1','Husband'),('HW2','Wife'),('PC1','Parent'),('PC2','Child'),('SBSB','Sibling'),('COCO','Cousin'),('GPGC1','Grandparent'),('GPGC2','Grandchild'),('AUNN1','Aunt/Uncle'),('AUNN2','Niece/Nephew')])
    return relationships

def getMajors():
    major_sql = 'SELECT DISTINCT TRIM(major) AS major_code, TRIM(txt) AS major_name FROM major_table ORDER BY TRIM(txt)'
    objs = do_sql(major_sql)
    if objs:
        return objs.fetchall()
    else:
        return objs

def getStates():
    states_sql = 'SELECT TRIM(st) AS st FROM st_table WHERE NVL(high_zone, 0) >= 100 ORDER BY TRIM(txt)'
    objs = do_sql(states_sql)
    if objs:
        return objs.fetchall()
    else:
        return objs

def getCountries():
    countries_sql = 'SELECT TRIM(ctry) AS ctry, TRIM(txt) AS txt FROM ctry_table ORDER BY web_ord, TRIM(txt)'
    objs = do_sql(countries_sql)
    if objs:
        return objs.fetchall()
    else:
        return objs

def getMessageInfo(studentID):
    message_sql = (
        'SELECT ids.id, NVL(TRIM(email.line1) || TRIM(email.line2) || TRIM(email.line3), "") AS email, TRIM(ids.firstname) AS firstname, TRIM(ids.lastname) AS lastname'
        ' FROM id_rec ids LEFT JOIN aa_rec email ON ids.id = email.id AND email.aa = "EML2" AND TODAY BETWEEN email.beg_date AND NVL(email.end_date, TODAY)'
        ' WHERE ids.id = %s' % (studentID)
    )
    message = do_sql(message_sql)
    return message.fetchone()

@login_required
def search_activity(request):
    search_string = request.GET.get("term","Football")
    activity_search_sql = 'SELECT TRIM(invl_table.txt) txt FROM invl_table WHERE invl_table.invl MATCHES "S[0-9][0-9][0-9]" AND LOWER(invl_table.txt) LIKE "%%%s%%" ORDER BY TRIM(invl_table.txt)' % (search_string.lower())
    objs = do_sql(activity_search_sql)
    if objs:
        return HttpResponse(objs.fetchall())
    else:
        return HttpResponse(objs)

def clearRelative(carthageID):
    clear_sql = "UPDATE stg_aludir_relative SET approved = 'N' WHERE id = %s AND NVL(approved,'') = ''" % (carthageID)
    do_sql(clear_sql)

def insertRelative(carthageID, relCode, fname, lname, alumPrimary):
    relation_sql = "INSERT INTO stg_aludir_relative (id, relCode, fname, lname, alum_primary, submitted_on) VALUES (%s, '%s', '%s', '%s', '%s', TO_DATE('%s', '%%Y-%%m-%%d'))" % (carthageID, relCode, fname, lname, alumPrimary, getNow())
    do_sql(relation_sql)
    return relation_sql

def insertAlumni(carthageID, fname, lname, suffix, prefix, email, maidenname, degree, class_year, business_name, major1, major2, major3, masters_grad_year, job_title):
    if class_year == '':
        class_year = 0
    if masters_grad_year == '':
        masters_grad_year = 0
    clear_sql = "UPDATE stg_aludir_alumni SET approved = 'N' WHERE id = %s AND NVL(approved,'') = ''" % (carthageID)
    do_sql(clear_sql)
    alumni_sql = ('INSERT INTO stg_aludir_alumni (id, fname, lname, suffix, prefix, email, maidenname, degree, class_year, business_name, major1, major2, major3, masters_grad_year, '
                  'job_title, submitted_on) '
                  'VALUES (%s, "%s", "%s", "%s", "%s", "%s", "%s", "%s", %s,  "%s", "%s", "%s", "%s", %s, "%s", TO_DATE("%s", "%%Y-%%m-%%d"))'
                  % (carthageID, fname, lname, suffix, prefix, email, maidenname.replace("(","").replace(")",""), degree, class_year, business_name, major1, major2, major3, masters_grad_year, job_title, getNow())
    )
    do_sql(alumni_sql)
    return alumni_sql

def insertAddress(aa_type, carthageID, address_line1, address_line2, address_line3, city, state, postalcode, country, phone):
    clear_sql = "UPDATE stg_aludir_address SET approved = 'N' WHERE id = %s AND aa = '%s' AND NVL(approved,'') = ''" % (carthageID, aa_type)
    do_sql(clear_sql)
    address_sql = ('INSERT INTO stg_aludir_address (aa, id, address_line1, address_line2, address_line3, city, state, zip, country, phone, submitted_on)'
                   'VALUES ("%s", %s, "%s", "%s", "%s", "%s", "%s", "%s", "%s", "%s", TO_DATE("%s", "%%Y-%%m-%%d"))'
                   % (aa_type, carthageID, address_line1, address_line2, address_line3, city, state, postalcode, country, phone, getNow())
    )
    do_sql(address_sql)
    return address_sql

def insertActivity(carthageID, activityText):
    clear_sql = "UPDATE stg_aludir_activity SET approved = 'N' WHERE id = %s AND NVL(approved,'') = ''" % (carthageID)
    do_sql(clear_sql)
    activity_sql = 'INSERT INTO stg_aludir_activity (id, activityText, submitted_on) VALUES (%s, "%s", TO_DATE("%s", "%%Y-%%m-%%d"))' % (carthageID, activityText, getNow())
    do_sql(activity_sql)
    return activity_sql

def clearPrivacy(carthageID):
    privacy_sql = 'DELETE FROM stg_aludir_privacy WHERE id = %s' % (carthageID)
    do_sql(privacy_sql)
    return privacy_sql

def insertPrivacy(carthageID, field, display):
    privacy_sql = 'INSERT INTO stg_aludir_privacy (id, fieldname, display, lastupdated) VALUES (%s, "%s", "%s", TO_DATE("%s", "%%Y-%%m-%%d"))' % (carthageID, field, display, getNow())
    do_sql(privacy_sql)
    return privacy_sql

def getNow():
    return datetime.datetime.now().strftime('%Y-%m-%d')

def emailDifferences(studentID):
    #Retrieve the existing information about the alumn(a|us)
    student = getStudent(studentID)

    if student['fname']:
        fname = student['fname']
    else:
        fname = '[missing first name]'
    subject = "Alumni Directory Update for {} {} ({})".format(
        fname, student['lname'], studentID
    )

    #Get the most recent unapproved information about the person
    alumni_sql = ("SELECT FIRST 1 TRIM(fname) AS fname, TRIM(lname) AS lname, TRIM(suffix) AS suffix, TRIM(prefix) AS prefix, TRIM(email) AS email, TRIM(maidenname) AS maidenname,"
                  "TRIM(degree) AS degree, class_year, TRIM(business_name) AS business_name, TRIM(major1.txt) AS major1, TRIM(major2.txt) AS major2, TRIM(major3.txt) AS major3, masters_grad_year,"
                  "TRIM(job_title) AS job_title "
                  "FROM stg_aludir_alumni alum LEFT JOIN major_table major1 ON alum.major1 = major1.major "
                  "LEFT JOIN major_table major2 ON alum.major2 = major2.major "
                  "LEFT JOIN major_Table major3 ON alum.major3 = major3.major "
                  "WHERE id = %s AND NVL(approved, '') = '' ORDER BY alum_no DESC") % (studentID)
    alum = do_sql(alumni_sql)
    alumni = alum.fetchone()

    #Get information about the alum's relatives
    relatives_sql = ("SELECT TRIM(fname) AS fname, TRIM(lname) AS lname, "
                     "  CASE "
                     "      WHEN    TRIM(relcode)    =    'HW'    AND    alum_primary    =    'N'    THEN    'Husband'"
                     "      WHEN    TRIM(relcode)    =    'HW'    AND    alum_primary    =    'Y'    THEN    'Wife'"
                     "      WHEN    TRIM(relcode)    =    'PC'    AND    alum_primary    =    'N'    THEN    'Parent'"
                     "      WHEN    TRIM(relcode)    =    'PC'    AND    alum_primary    =    'Y'    THEN    'Child'"
                     "      WHEN    TRIM(relcode)    =    'SBSB'                                THEN    'Sibling'"
                     "      WHEN    TRIM(relcode)    =    'COCO'                                THEN    'Cousin'"
                     "      WHEN    TRIM(relcode)    =    'GPGC'    AND    alum_primary    =    'N'    THEN    'Grandparent'"
                     "      WHEN    TRIM(relcode)    =    'GPGC'    AND    alum_primary    =    'Y'    THEN    'Grandchild'"
                     "      WHEN    TRIM(relcode)    =    'AUNN'    AND    alum_primary    =    'N'    THEN    'Aunt/Uncle'"
                     "      WHEN    TRIM(relcode)    =    'AUNN'    AND    alum_primary    =    'Y'    THEN    'Niece/Nephew'"
                     "                                                                      ELSE    TRIM(relcode)"
                     "  END    AS    relcode "
                     "FROM stg_aludir_relative "
                     "WHERE id = %s AND NVL(approved, '') = '' "
                    ) % (studentID)
    #relatives_sql = ("SELECT TRIM(fname) AS fname, TRIM(lname) AS lname, TRIM(relcode) AS relcode FROM stg_aludir_relative WHERE id = %s AND NVL(approved, '') = ''") % (studentID)
    relatives = do_sql(relatives_sql).fetchall()

    #Get address information (work and home)
    homeaddress_sql = ("SELECT FIRST 1 TRIM(address_line1) AS address_line1, TRIM(address_line2) AS address_line2, TRIM(address_line3) AS address_line3, TRIM(city) AS city, TRIM(state) AS state,"
                       "TRIM(zip) AS zip, TRIM(country) AS country, TRIM(phone) AS phone FROM stg_aludir_address WHERE id = %s AND aa = '%s' AND NVL(approved, '') = '' ORDER BY aa_no DESC") % (studentID, 'HOME')
    homeaddress = do_sql(homeaddress_sql)
    if(homeaddress != None):
        home_address = homeaddress.fetchone()
    else:
        home_address = []

    workaddress_sql = ("SELECT FIRST 1 TRIM(address_line1) AS address_line1, TRIM(address_line2) AS address_line2, TRIM(address_line3) AS address_line3, TRIM(city) AS city, TRIM(state) AS state,"
                       "TRIM(zip) AS zip, TRIM(country) AS country, TRIM(phone) AS phone FROM stg_aludir_address WHERE id = %s AND aa = '%s' AND NVL(approved, '') = '' ORDER BY aa_no DESC") % (studentID, 'WORK')
    workaddress = do_sql(workaddress_sql)
    if(workaddress != None):
        work_address = workaddress.fetchone()
    else:
        work_address = []

    #Get organization information
    activities_sql = ("SELECT activityText FROM stg_aludir_activity WHERE id = %s AND NVL(approved, '') = ''") % (studentID)
    alum_activities = do_sql(activities_sql).fetchall()

    data = {'studentID':studentID,'personal':False,'academics':False,'business':False,'home':False}
    #Section for personal information
    if(student['prefix'].lower() != alumni.prefix.lower()):
        data["prefix"] = alumni.prefix
        data["original_prefix"] = student['prefix']
        data["personal"] = True
    if(fname != alumni.fname):
        data["fname"] = alumni.fname
        data["original_fname"] = fname
        data["personal"] = True
    if(student['birth_lname'] != alumni.maidenname):
        data["maidenname"] = alumni.maidenname
        data["original_maidenname"] = student['birth_lname']
        data["personal"] = True
    if(student['lname'] != alumni.lname):
        data["lname"] = alumni.lname
        data["original_lname"] = student['lname']
        data["personal"] = True
    if(student['suffix'].lower() != alumni.suffix.lower()):
        data["suffix"] = alumni.suffix
        data["original_suffix"] = student['suffix']
        data["personal"] = True

    #Section for relatives
    data["relatives"] = relatives

    #Section for academics
    if(student['degree'] != alumni.degree):
        data["degree"] = alumni.degree
        data["original_degree"] = student['degree']
        data["academics"] = True
    if(student['major1'] != alumni.major1):
        data["major1"] = alumni.major1
        data["original_major1"] = student['major1']
        data["academics"] = True
    if(student['major2'] != alumni.major2):
        data["major2"] = alumni.major2
        data["original_major2"] = student['major2']
        data["academics"] = True
    if(student['major3'] != alumni.major3):
        data["major3"] = alumni.major3
        data["original_major3"] = student['major3']
        data["academics"] = True
    if(student['masters_grad_year'] != alumni.masters_grad_year):
        data["masters_grad_year"] = alumni.masters_grad_year
        data["original_mastersgradyear"] = student['masters_grad_year']
        data["academics"] = True

    #Section for activities (this may get split out into organizations vs athletics in the future)
    data["organizations"] = alum_activities

    if(student['business_name'] != alumni.business_name):
        data["business_name"] = alumni.business_name
        data["original_businessname"] = student['business_name']
        data["business"] = True
    if(student['job_title'] != alumni.job_title):
        data["job_title"] = alumni.job_title
        data["original_jobtitle"] = student['job_title']
        data["business"] = True

    #Section for work address
    if (work_address != None and len(work_address) > 0):
        if(student['business_address'] != work_address.address_line1):
            data["business_address"] = work_address.address_line1
            data["original_businessaddress"] = student['business_address']
            data["business"] = True
        if(student['business_address2'] != work_address.address_line2):
            data["business_address"] = work_address.address_line2
            data["original_businessaddress2"] = student['business_address2']
            data["business"] = True
        if(student['business_city'] != work_address.city):
            data["business_city"] = work_address.city
            data["original_businesscity"] = student['business_city']
            data["business"] = True
        if(student['business_state'] != work_address.state):
            data["business_state"] = work_address.state
            data["original_businessstate"] = student['business_state']
            data["business"] = True
        if(student['business_zip'] != work_address.zip):
            data["business_zip"] = work_address.zip
            data["original_businesszip"] = student['business_zip']
            data["business"] = True
        if(student['business_country'] != work_address.country):
            data["business_country"] = work_address.country
            data["original_businesscountry"] = student['business_country']
            data["business"] = True
        if(student['business_phone'] != work_address.phone):
            data["business_phone"] = work_address.phone
            data["original_businessphone"] = student['business_phone']
            data["business"] = True
    else:
        data["business"] = True
        data["business_address"] = workaddress_sql

    #Section for home address
    if(student['email'] != alumni.email):
        data["email"] = alumni.email
        data["original_email"] = student['email']
        data["home"] = True
    if(home_address != None and len(home_address) > 0):
        if(student['home_address1']!= home_address.address_line1):
            data["home_address"] = home_address.address_line1
            data["original_homeaddress"] = student['home_address1']
            data["home"] = True
        if(student['home_address2'] != home_address.address_line2):
            data["home_address2"] = home_address.address_line2
            data["original_homeaddress2"] = student['home_address2']
            data["home"] = True
        if(student['home_address3'] != home_address.address_line3):
            data["home_address3"] = home_address.address_line3
            data["original_homeaddress3"] = student['home_address3']
            data["home"] = True
        if(student['home_city'] != home_address.city):
            data["home_city"] = home_address.city
            data["original_homecity"] = student['home_city']
            data["home"] = True
        if(student['home_state'] != home_address.state):
            data["home_state"] = home_address.state
            data["original_homestate"] = student['home_state']
            data["home"] = True
        if(student['home_zip'] != home_address.zip):
            data["home_zip"] = home_address.zip
            data["original_homezip"] = student['home_zip']
            data["home"] = True
        if(student['home_country'] != home_address.country):
            data["home_country"] = home_address.country
            data["original_homecountry"] = student['home_country']
            data["home"] = True
        if(student['home_phone'] != home_address.phone):
            data["home_phone"] = home_address.phone
            data["original_homephone"] = student['home_phone']
            data["home"] = True

    if settings.DEBUG:
        recipients = ["mkishline@carthage.edu",]
    else:
        recipients = settings.MANAGER_RECIPIENTS

    send_mail(
        None, recipients, subject, 'confirmation@carthage.edu',
        'manager/email.html', data, [settings.MANAGERS[0][1],]
    )
