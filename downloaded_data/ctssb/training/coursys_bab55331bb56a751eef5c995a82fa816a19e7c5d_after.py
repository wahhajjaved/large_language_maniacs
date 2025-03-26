from django.contrib.auth.decorators import login_required
from coredata.models import Member, Person, CourseOffering
from groups.models import *
from grades.models import Activity
from django.shortcuts import render_to_response, get_object_or_404, redirect
from django.template import RequestContext
from groups.forms import *
from django.forms.models import modelformset_factory
from django.forms.formsets import formset_factory
from django.forms.util import ErrorList
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.core.urlresolvers import reverse
from django.contrib import messages
from django.conf import settings
from courselib.auth import *
from log.models import *
from django.db.models import Q
from collections import defaultdict

@login_required
def groupmanage(request, course_slug, activity_slug=None):
    if is_course_staff_by_slug(request, course_slug):
        return _groupmanage_staff(request, course_slug, activity_slug)
    elif is_course_student_by_slug(request, course_slug):
        return _groupmanage_student(request, course_slug)
    else:
        return HttpResponseForbidden()

def _groupmanage_student(request, course_slug):
    course = get_object_or_404(CourseOffering, slug=course_slug)

    groups = Group.objects.filter(courseoffering=course, groupmember__student__person__userid=request.user.username)
    groups = set(groups) # all groups student is a member of

    groupList = []
    my_membership = []
    for group in groups:
        members = group.groupmember_set.all().select_related('activity', 'student', 'student__person')
        need_conf = members.filter(student__person__userid=request.user.username, confirmed=False).count() != 0
        all_act = all_activities(members)
        unique_members = []
        for s in set(m.student for m in members):
            # confirmed in group?
            confirmed = False not in (m.confirmed for m in members if m.student==s)
            # not a member for any activities?
            missing = all_act - set(m.activity for m in members if m.student==s)
            missing = list(missing)
            missing.sort()
            unique_members.append( {'member': s, 'confirmed': confirmed, 'missing': missing} )

        all_act = list(all_act)
        all_act.sort()
        groupList.append({'group': group, 'activities': all_act, 'unique_members': unique_members, 'memb': members, 'need_conf': need_conf})

    return render_to_response('groups/student.html', {'course':course, 'groupList':groupList}, context_instance = RequestContext(request))

def _groupmanage_staff(request, course_slug, activity_slug=None):
    course = get_object_or_404(CourseOffering, slug=course_slug)
    groups = Group.objects.filter(courseoffering=course)
    activities = Activity.objects.filter(offering=course, group=True, deleted=False)

    allmembers = GroupMember.objects.filter(group__courseoffering=course).select_related('group', 'student', 'student__person', 'activity')
    if activity_slug:
        activity = get_object_or_404(Activity, offering=course, slug=activity_slug, deleted=False)
        members = allmembers.filter(activity=activity)
    else:
        activity = None
        members = allmembers
    # create dictionary for student lookup:
    members_dict = defaultdict(list)
    for m in members:
        members_dict[m.student.id].append(m)
    
    # find the students not in any group, and keep track of groups with members
    students = Member.objects.filter(offering=course, role='STUD').select_related('person')
    groups_populated = set() # groups with (relevant) members
    studentsNotInGroup = []
    for s in students:
        memberships = members_dict[s.id]
        if len(memberships) == 0:
            studentsNotInGroup.append(s)
        else:
            for m in memberships:
                groups_populated.add(m.group)
    
    groups_populated = list(groups_populated)
    groups_populated.sort()

    groupList = []
    for group in groups_populated:
        gmembers = members.filter(group=group)
        all_act = all_activities(gmembers)
        unique_members = []
        for s in set(m.student for m in gmembers):
            # confirmed in group?
            confirmed = False not in (m.confirmed for m in gmembers if m.student==s)
            # not a member for any activities?
            missing = all_act - set(m.activity for m in gmembers if m.student==s)
            missing = list(missing)
            missing.sort()
            unique_members.append( {'member': s, 'confirmed': confirmed, 'missing': missing} )
        all_act = list(all_act)
        all_act.sort()
        # other attributes for easy display
        email = ",".join(["%s <%s>" % (m['member'].person.name(), m['member'].person.email()) for m in unique_members])
        userids = ",".join([m['member'].person.userid for m in unique_members if m['member'].person.userid])
        
        groupList.append({'group': group, 'activities': all_act, 'unique_members': unique_members, 'memb': members, 'email': email, 'userids': userids})

    return render_to_response('groups/instructor.html', \
                              {'course':course, 'groupList':groupList, 'studentsNotInGroup':studentsNotInGroup,
                              'activity':activity, 'activities':activities}, \
                              context_instance = RequestContext(request))

@requires_course_by_slug
def create(request,course_slug):
    person = get_object_or_404(Person,userid=request.user.username)
    course = get_object_or_404(CourseOffering, slug = course_slug)
    group_manager=Member.objects.exclude(role="DROP").get(person = person, offering = course)
    groupForSemesterForm = GroupForSemesterForm()
    activities = Activity.objects.exclude(status='INVI').filter(offering=course, group=True, deleted=False)
    activityList = []
    for activity in activities:
        activityForm = ActivityForm(prefix = activity.slug)
        activityList.append({'activityForm': activityForm, 'name' : activity.name,\
                             'percent' : activity.percent, 'due_date' : activity.due_date})

    if is_course_student_by_slug(request, course_slug):
        return render_to_response('groups/create_student.html', \
                                  {'manager':group_manager, 'course':course, 'groupForSemester':groupForSemesterForm, 'activityList':activityList},\
                                  context_instance = RequestContext(request))

    elif is_course_staff_by_slug(request, course_slug):
        #For instructor page, there is a student table for him/her to choose the students who belong to the new group
        students = Member.objects.select_related('person').filter(offering = course, role = 'STUD')
        studentList = []
        for student in students:
            studentForm = StudentForm(prefix = student.person.userid)
            studentList.append({'studentForm': studentForm, 'first_name' : student.person.first_name,\
                                 'last_name' : student.person.last_name, 'userid' : student.person.userid,\
                                 'emplid' : student.person.emplid})

        return render_to_response('groups/create_instructor.html', \
                          {'manager':group_manager, 'course':course,'groupForSemester':groupForSemesterForm, 'activityList':activityList, \
                           'studentList':studentList}, context_instance = RequestContext(request))
    else:
        return HttpResponseForbidden()
    
def _validateIntegrity(request, isStudentCreatedGroup, groupForSemester, course, studentList, activityList):
    """
    If one student is in a group for an activity, he/she cannot be in another group for the same activity.
    """
    integrityError = False
    error_info = ""
    for student in studentList:
        groupMembers = GroupMember.objects.filter(group__courseoffering = course, student = student)
        skipIterationFlag = False
        #check if the student is already in a group for all group activities of the semester
        for group in set(groupMember.group for groupMember in groupMembers):
            if groupForSemester == True and group.groupForSemester == True:
                integrityError = True
                skipIterationFlag = True
                #if this group is created by student
                if isStudentCreatedGroup:
                    error_info = "You cannot create this group, \
                    because you are already in the group: %s for all activities of the semester" % (group.name)
                    messages.add_message(request, messages.ERROR, error_info)
                #if this group is created by instructor 
                else: 
                    error_info = "Student %s %s (%s)can not be assigned to this new group,\
                    because he/she is already in group %s for all activities of the semester." \
                               % (student.person.first_name, student.person.last_name, student.person.userid, group.name)
                    messages.add_message(request, messages.ERROR, error_info)
        if skipIterationFlag == True:
            continue
        #check if the student is in a group that already has one or more than one activities in the activityList
        for activity in activityList:
            for groupMember in groupMembers:
                if groupMember.activity == activity:
                    integrityError = True
                    #if this group is created by student
                    if isStudentCreatedGroup:
                        error_info = "You cannot create this group for %s, \
                        because you are already in the group: %s for %s."\
                                   % (activity.name, groupMember.group.name, activity.name)
                        messages.add_message(request, messages.ERROR, error_info)
                    #if this group is created by instructor 
                    else: 
                        error_info = "Student %s %s (%s)can not be assigned to this new group for %s,\
                        because he/she is already in group %s for %s." \
                                   % (student.person.first_name, student.person.last_name, student.person.userid,\
                                    activity.name, groupMember.group.name, activity.name)
                        messages.add_message(request, messages.ERROR, error_info)
    return not integrityError

@requires_course_by_slug
def submit(request,course_slug):
    #TODO: validate activity?
    person = get_object_or_404(Person,userid=request.user.username)
    course = get_object_or_404(CourseOffering, slug = course_slug)
    member = Member.objects.get(person = person, offering = course)
    error_info=None
    name = request.POST.get('GroupName')
    if name:
        name = name[:30]
    #Check if group has a unique name
    if Group.objects.filter(name=name,courseoffering=course):
        error_info="A group named \"%s\" already exists" % (name)
        messages.add_message(request, messages.ERROR, error_info)
        return HttpResponseRedirect(reverse('groups.views.groupmanage', kwargs={'course_slug': course_slug}))
    #Check if the group name is empty, these two checks may need to be moved to forms later.
    if name == "":
        error_info = "Group name cannot be empty: please enter a group name."
        messages.add_message(request, messages.ERROR, error_info)
        return HttpResponseRedirect(reverse('groups.views.groupmanage', kwargs={'course_slug': course_slug}))
    

    else:
        # find selected activities
        selected_act = []
        activities = Activity.objects.filter(offering=course, group=True, deleted=False)
        if not is_course_staff_by_slug(request, course_slug):
            activities = activities.exclude(status='INVI')

        for activity in activities:
            activityForm = ActivityForm(request.POST, prefix=activity.slug)
            if activityForm.is_valid() and activityForm.cleaned_data['selected'] == True:
                selected_act.append(activity)
        
        # no selected activities: fail.
        if not selected_act:
            messages.add_message(request, messages.ERROR, "Group not created: no activities selected.")
            return HttpResponseRedirect(reverse('groups.views.groupmanage', kwargs={'course_slug': course_slug}))
        
        #groupForSemesterForm = GroupForSemesterForm(request.POST)
        #if groupForSemesterForm.is_valid():
        #    groupForSemester = groupForSemesterForm.cleaned_data['selected']
        groupForSemester = False
        
        #validate database integrity before saving anything. 
        #If one student is in a group for an activity, he/she cannot be in another group for the same activity.
        if is_course_student_by_slug(request, course_slug):
            isStudentCreatedGroup = True
            studentList = []
            studentList.append(member)
        elif is_course_staff_by_slug(request, course_slug):
            isStudentCreatedGroup = False
            studentList = []
            students = Member.objects.select_related('person').filter(offering = course, role = 'STUD')
            for student in students:
                studentForm = StudentForm(request.POST, prefix = student.person.userid)
                if studentForm.is_valid() and studentForm.cleaned_data['selected'] == True:
                    studentList.append(student)
        #Check if students has already in a group
        if _validateIntegrity(request,isStudentCreatedGroup, groupForSemester, course, studentList, selected_act) == False:
            return HttpResponseRedirect(reverse('groups.views.groupmanage', kwargs={'course_slug': course_slug}))
        #No selected members,group creating will fail.        
        if not studentList:
            messages.add_message(request, messages.ERROR, "Group not created: no members selected.")
            return HttpResponseRedirect(reverse('groups.views.groupmanage', kwargs={'course_slug': course_slug}))
        
        group = Group(name=name, manager=member, courseoffering=course, groupForSemester = groupForSemester)
        group.save()
        #LOG EVENT#
        l = LogEntry(userid=request.user.username,
        description="created a new group %s for %s." % (group.name, course),
        related_object=group )
        l.save()

        if is_course_student_by_slug(request, course_slug):
            for activity in selected_act:
                groupMember = GroupMember(group=group, student=member, confirmed=True, activity=activity)
                groupMember.save()
                #LOG EVENT#
                l = LogEntry(userid=request.user.username,
                description="automatically became a group member of %s for activity %s." % (group.name, groupMember.activity),
                    related_object=groupMember )
                l.save()

            messages.add_message(request, messages.SUCCESS, 'Group Created')
            return HttpResponseRedirect(reverse('groups.views.groupmanage', kwargs={'course_slug': course_slug}))

        elif is_course_staff_by_slug(request, course_slug):
            students = Member.objects.select_related('person').filter(offering = course, role = 'STUD')
            for student in students:
                studentForm = StudentForm(request.POST, prefix = student.person.userid)
                if studentForm.is_valid() and studentForm.cleaned_data['selected'] == True:
                    for activity in selected_act:
                        groupMember = GroupMember(group=group, student=student, confirmed=True, activity=activity)
                        groupMember.save()
                        #LOG EVENT#
                        l = LogEntry(userid=request.user.username,
                        description="added %s as a group member to %s for activity %s." % (student.person.userid,group.name, groupMember.activity),
                            related_object=groupMember )
                        l.save()
                    
                    n = NewsItem(user=student.person, author=member.person, course=group.courseoffering,
                     source_app="group", title="Added to Group",
                     content="You have been added the group %s." % (group.name),
                     url=reverse('groups.views.groupmanage', kwargs={'course_slug':course.slug})
                    )
                    n.save()
                    
            messages.add_message(request, messages.SUCCESS, 'Group Created')
            return HttpResponseRedirect(reverse('groups.views.groupmanage', kwargs={'course_slug': course_slug}))
        else:
            return HttpResponseForbidden()



@requires_course_by_slug
def join(request, course_slug, group_slug):
    course = get_object_or_404(CourseOffering, slug=course_slug)
    group = get_object_or_404(Group, courseoffering = course, slug = group_slug)
    person = get_object_or_404(Person, userid = request.user.username)
    member = get_object_or_404(Member, person = person, offering=course)
    
    if request.method != "POST":
        return HttpResponseForbidden()

    for groupMember in GroupMember.objects.filter(group = group, student = member):
        groupMember.confirmed = True
        groupMember.save()

    #LOG EVENT#
    l = LogEntry(userid=request.user.username,
    description="joined group %s." % (group.name,),
    related_object=group )
    l.save()
    messages.add_message(request, messages.SUCCESS, 'You have joined the group "%s".' % (group.name))
    return HttpResponseRedirect(reverse('groups.views.groupmanage', kwargs={'course_slug': course_slug}))

@requires_course_by_slug
def reject(request, course_slug, group_slug):
    course = get_object_or_404(CourseOffering, slug=course_slug)
    group = get_object_or_404(Group, courseoffering = course, slug = group_slug)
    person = get_object_or_404(Person, userid = request.user.username)
    member = get_object_or_404(Member, person = person, offering=course)

    if request.method != "POST":
        return HttpResponseForbidden()

    # delete membership on reject
    GroupMember.objects.filter(group = group, student = member).delete()

    #LOG EVENT#
    l = LogEntry(userid=request.user.username,
    description="rejected membership in group %s." % (group.name,),
    related_object=group )
    l.save()
    messages.add_message(request, messages.SUCCESS, 'You have left the group "%s".' % (group.name))
    return HttpResponseRedirect(reverse('groups.views.groupmanage', kwargs={'course_slug': course_slug}))

@requires_course_by_slug
def invite(request, course_slug, group_slug):
    #TODO need to validate the student who is invited, cannot be the invitor him/herself.
    course = get_object_or_404(CourseOffering, slug = course_slug)
    group = get_object_or_404(Group, courseoffering = course, slug = group_slug)
    person = get_object_or_404(Person, userid = request.user.username)
    invitor = get_object_or_404(Member, person = person, offering=course)
    error_info=None
    from django import forms
    class StudentReceiverForm(forms.Form):
        name = forms.CharField()

    if request.method == "POST":
        student_receiver_form = StudentReceiverForm(request.POST)
        #student_receiver_form.activate_addform_validation(course_slug,group_slug)
        if student_receiver_form.is_valid():
            name = student_receiver_form.cleaned_data['name']
            members = Member.objects.filter(person__userid = name, offering = course, role="STUD")
            if not members:
                messages.add_message(request, messages.ERROR, 'Could not find userid "%s".' % (name))
                return HttpResponseRedirect(reverse('groups.views.groupmanage', kwargs={'course_slug': course_slug}))
            member = members[0]
            
            # find out if this person is already in a group
            gms = group.groupmember_set.all()
            all_act = all_activities(gms)
            existing_memb = GroupMember.objects.filter(student=member, activity__in=all_act)
            
            if GroupMember.objects.filter(student=member, group=group):
                messages.add_message(request, messages.ERROR, "%s is already in this group" % (member.person.userid))
            elif existing_memb:
                error="%s is already in a group for %s" % (member.person.userid, ", ".join(m.activity.name for m in existing_memb))
                messages.add_message(request, messages.ERROR, error)
            else:
                #member = Member.objects.get(person = member.person, offering = course)
                for invitorMembership in GroupMember.objects.filter(group = group, student = invitor):
                    newGroupMember = GroupMember(group = group, student = member, \
                                          activity = invitorMembership.activity, confirmed = False)
                    newGroupMember.save(member.person)

                    #LOG EVENT#
                    l = LogEntry(userid=request.user.username,
                    description="invited %s to join group %s for activity %s." % (newGroupMember.student.person.userid,group.name, newGroupMember.activity),
                    related_object=newGroupMember )
                    l.save()
                    
                n = NewsItem(user=member.person, author=person, course=group.courseoffering,
                     source_app="group", title="Group Invitation",
                     content="You have been invited to join group %s." % (group.name),
                     url=reverse('groups.views.groupmanage', kwargs={'course_slug':course.slug})
                    )
                n.save()
                messages.add_message(request, messages.SUCCESS, 'Your invitation to %s has been sent out.' % (member.person.name()))

            return HttpResponseRedirect(reverse('groups.views.groupmanage', kwargs={'course_slug': course_slug}))
        else:
            messages.add_message(request, messages.ERROR, "Invalid userid.")
            return HttpResponseRedirect(reverse('groups.views.groupmanage', kwargs={'course_slug': course_slug}))
    else:
        student_receiver_form = StudentReceiverForm()
        context = {'course': course, 'form': student_receiver_form}
        return render_to_response("groups/invite.html", context, context_instance=RequestContext(request))

@login_required
def remove_student(request, course_slug, group_slug):
    course = get_object_or_404(CourseOffering, slug = course_slug)
    group = get_object_or_404(Group, courseoffering = course, slug = group_slug)
    members = GroupMember.objects.filter(group = group).select_related('group', 'student', 'student__person', 'activity')

    # check permissions
    if is_course_staff_by_slug(request, course_slug):
        is_staff = True
    elif is_course_student_by_slug(request, course_slug):
        is_staff = False
        memberships = [m for m in members if m.student.person.userid == request.user.username]
        if not memberships:
            # student must be in this group
            return HttpResponseForbidden()
    else:
        return HttpResponseForbidden()

    if request.method == "POST":
        for m in members:
            f = StudentForm(request.POST, prefix = m.student.person.userid + '_' + m.activity.slug)
            if (is_staff or m.student_editable(request.user.username)=="") \
                and f.is_valid() and f.cleaned_data['selected'] == True:
            
                m.delete()

                #LOG EVENT#
                l = LogEntry(userid=request.user.username,
                description="deleted %s in group %s for %s." % (m.student.person.userid, group.name, m.activity),
                related_object=m.group)
                l.save()
                #LOG EVENT#

        return HttpResponseRedirect(reverse('groups.views.groupmanage', kwargs={'course_slug': course_slug}))

    else:
        data = []
        for m in members:
            editable = m.student_editable(request.user.username)
            if is_staff or editable == "":
                f = StudentForm(prefix = m.student.person.userid + '_' + m.activity.slug)
                data.append({'form': f, 'member': m})
            else:
                data.append({'form': None, 'member': m, 'reason': editable})

        return render_to_response('groups/remove_student.html', \
                          {'course':course, 'group' : group, 'data':data, 'is_staff':is_staff}, \
                          context_instance = RequestContext(request))

@requires_course_staff_by_slug
def change_name(request, course_slug, group_slug):
    "Change the group's name"
    course = get_object_or_404(CourseOffering, slug=course_slug)
    group = get_object_or_404(Group, courseoffering=course, slug=group_slug)
    oldname = group.name #used for log information
    if request.method == "POST":
        groupForm = GroupNameForm(request.POST, instance=group)
        if groupForm.is_valid():
            groupForm.save()
            #LOG EVENT#
            l = LogEntry(userid=request.user.username,
            description="changed name of group %s to %s for course %s." % (oldname, group.name, group.courseoffering),
            related_object=group)
            l.save()
            return HttpResponseRedirect(reverse('groups.views.groupmanage', kwargs={'course_slug': course_slug}))

    else:
        groupForm = GroupNameForm(instance=group)

    return render_to_response("groups/change_name.html", \
                                  {'groupForm': groupForm, 'course': course, 'group': group}, 
                                  context_instance=RequestContext(request))


@requires_course_staff_by_slug
def assign_student(request, course_slug, group_slug):
    course = get_object_or_404(CourseOffering, slug=course_slug)
    group = get_object_or_404(Group, slug=group_slug, courseoffering=course)
    activities = Activity.objects.filter(offering=course, group=True, deleted=False)
    members = Member.objects.filter(offering=course, role='STUD').select_related('person')

    if request.method == "POST":
        add_act = []
        for a in activities:
            form = ActivityForm(request.POST, prefix=a.slug)
            if form.is_valid() and form.cleaned_data['selected'] == True:
                add_act.append(a)

        for m in members:
            form = StudentForm(request.POST, prefix=m.person.userid)
            if form.is_valid() and form.cleaned_data['selected'] == True:
                for a in add_act:
                    old_gm = GroupMember.objects.filter(activity=a, student=m)
                    if len(old_gm) > 0:
                        messages.error(request, "%s is already in a group for %s." % (m.person.name(), a.name))
                    else:
                        gm = GroupMember(group=group, student=m, confirmed=True, activity=a)
                        gm.save()
                        messages.success(request, "%s added to group %s for %s." % (m.person.name(), group.name, a.name))
                        #LOG EVENT#
                        l = LogEntry(userid=request.user.username,
                        description="added %s to group %s for %s." % (m.person.userid, group.name, a), related_object=gm)
                        l.save()

        return HttpResponseRedirect(reverse('groups.views.groupmanage', kwargs={'course_slug': course.slug}))
        
    else:
        activity_data = []
        for a in activities:
            form = ActivityForm(prefix=a.slug)
            activity_data.append( {'form': form, 'act': a} )

        student_data = []
        for m in members:
            form = StudentForm(prefix=m.person.userid)
            student_data.append( {'form': form, 'member': m} )

        return render_to_response('groups/assign_student.html', \
                          {'course':course, 'group':group, 'activity_data': activity_data, 'student_data': student_data}, \
                          context_instance = RequestContext(request))

