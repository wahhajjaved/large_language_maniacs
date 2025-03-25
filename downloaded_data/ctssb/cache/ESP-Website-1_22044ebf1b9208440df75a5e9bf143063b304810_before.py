
__author__    = "MIT ESP"
__date__      = "$DATE$"
__rev__       = "$REV$"
__license__   = "GPL v.2"
__copyright__ = """
This file is part of the ESP Web Site
Copyright (c) 2007 MIT ESP

The ESP Web Site is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

Contact Us:
ESP Web Group
MIT Educational Studies Program,
84 Massachusetts Ave W20-467, Cambridge, MA 02139
Phone: 617-253-4882
Email: web@esp.mit.edu
"""
from esp.program.modules.base import ProgramModuleObj, needs_teacher, needs_student, needs_admin, usercheck_usetl, needs_onsite
from esp.program.modules import module_ext
from esp.web.util        import render_to_response
from django.contrib.auth.decorators import login_required
from esp.users.models    import ESPUser, UserBit, User
from esp.datatree.models import GetNode
from esp.money.models    import Transaction
from esp.program.models  import Class
from esp.users.views     import get_user_list, search_for_user
from esp.web.util.latex  import render_to_latex

class ProgramPrintables(ProgramModuleObj):
    """ This is extremely useful for printing a wide array of documents for your program.
    Things from checklists to rosters to attendance sheets can be found here. """
    
    @needs_admin
    def printoptions(self, request, tl, one, two, module, extra, prog):
        """ Display a teacher eg page """
        context = {'module': self}

        return render_to_response(self.baseDir()+'options.html', request, (prog, tl), context)

    @needs_admin
    def catalog(self, request, tl, one, two, module, extra, prog):
        " this sets the order of classes for the catalog. "

        if request.GET.has_key('ids') and request.GET.has_key('op') and \
           request.GET.has_key('clsid'):
            try:
                clsid = int(request.GET['clsid'])
                cls   = Class.objects.get(parent_program = self.program,
                                          id             = clsid)
            except:
                raise ESPError(), 'Could not get the class object.'

            classes = Class.objects.filter(parent_program = self.program)
            classes = [cls for cls in classes
                       if cls.isAccepted() ]

            cls_dict = {}
            for cur_cls in classes:
                cls_dict[str(cur_cls.id)] = cur_cls
            

            clsids = request.GET['ids'].split(',')
            found  = False
            
            if request.GET['op'] == 'up':
                for i in range(1,len(clsids)):
                    if not found and str(clsids[i]) == request.GET['clsid']:
                        tmp         = str(clsids[i-1])
                        clsids[i-1] = str(clsids[i])
                        clsids[i]   = tmp
                        found       = True
                        
            elif request.GET['op'] == 'down':
                for i in range(len(clsids)-1):
                    if not found and str(clsids[i]) == request.GET['clsid']:
                        tmp         = str(clsids[i])
                        clsids[i]   = str(clsids[i+1])
                        clsids[i+1] = tmp
                        found       = True
            else:
                raise ESPError(), 'Received invalid operation for class list.'

            
            classes = []

            for clsid in clsids:
                classes.append(cls_dict[clsid])

            clsids = ','.join(clsids)
            return render_to_response(self.baseDir()+'catalog_order.html',
                                      request,
                                      (self.program, tl),
                                      {'clsids': clsids, 'classes': classes})

        
        classes = Class.objects.filter(parent_program = self.program)

        classes = [cls for cls in classes
                   if cls.isAccepted()    ]

        classes.sort(Class.catalog_sort)

        clsids = ','.join([str(cls.id) for cls in classes])

        return render_to_response(self.baseDir()+'catalog_order.html',
                                  request,
                                  (self.program, tl),
                                  {'clsids': clsids, 'classes': classes})
        

    @needs_admin
    def coursecatalog(self, request, tl, one, two, module, extra, prog):
        " This renders the course catalog in LaTeX. "

        classes = Class.objects.filter(parent_program = self.program)


        classes = [cls for cls in classes
                   if cls.isAccepted()   ]

        if request.GET.has_key('clsids'):
            clsids = request.GET['clsids'].split(',')
            cls_dict = {}
            for cls in classes:
                cls_dict[str(cls.id)] = cls
            classes = [cls_dict[clsid] for clsid in clsids]
            classes.sort(Class.catalog_sort)
            
        else:
            classes.sort(Class.catalog_sort)

        context = {'classes': classes, 'program': self.program}

        if extra is None or len(str(extra).strip()) == 0:
            extra = 'pdf'

        return render_to_latex(self.baseDir()+'catalog.tex', context, extra)

    @needs_admin
    def classesbyFOO(self, request, tl, one, two, module, extra, prog, sort_exp = lambda x,y: cmp(x,y)):
        " This renders the course catalog in LaTeX. "

        classes = Class.objects.filter(parent_program = self.program)

        classes = [cls for cls in classes
                   if cls.isAccepted()   ]

        if request.GET.has_key('clsids'):
            clsids = request.GET['clsids'].split(',')
            cls_dict = {}
            for cls in classes:
                cls_dict[str(cls.id)] = cls
            classes = [cls_dict[clsid] for clsid in clsids]
            classes.sort(sort_exp)
            
        else:
            classes.sort(sort_exp)

        context = {'classes': classes, 'program': self.program}

        return render_to_response(self.baseDir()+'classes_list.html', request, (prog, tl), context)

    @needs_admin
    def classesbytime(self, request, tl, one, two, module, extra, prog):
        def cmp_time(one, other):
            if (one.meeting_times.count() > 0 and other.meeting_times.count() > 0):
                cmp0 = cmp(one.meeting_times.all()[0].id, other.meeting_times.all()[0].id)
            else:
                cmp0 = cmp(one.meeting_times.count(), other.meeting_times.count())

            if cmp0 != 0:
                return cmp0

            return cmp(one, other)
        
        return self.classesbyFOO(request, tl, one, two, module, extra, prog, cmp_time)

    @needs_admin
    def classesbytitle(self, request, tl, one, two, module, extra, prog):
        def cmp_title(one, other):
            cmp0 = cmp(one.anchor.friendly_name, other.anchor.friendly_name)

            if cmp0 != 0:
                return cmp0

            return cmp(one, other)
        
        return self.classesbyFOO(request, tl, one, two, module, extra, prog, cmp_title)


    @needs_admin
    def satprepStudentCheckboxes(self, request, tl, one, two, module, extra, prog):
        students = [ESPUser(student) for student in self.program.students_union() ]
        students.sort()
        return render_to_response(self.baseDir()+'satprep_students.html', request, (prog, tl), {'students': students})

    @needs_admin
    def teacherschedules(self, request, tl, one, two, module, extra, prog):
        """ generate teacher schedules """

        filterObj, found = get_user_list(request, self.program.getLists(True))
        if not found:
            return filterObj


        context = {'module': self     }
        teachers = [ ESPUser(user) for user in filterObj.getList(User).distinct()]
        teachers.sort()


        scheditems = []

        for teacher in teachers:
            # get list of valid classes
            classes = [ cls for cls in teacher.getTaughtClasses()
                    if cls.parent_program == self.program
                    and cls.isAccepted()                       ]
            # now we sort them by time/title
            classes.sort()            
            for cls in classes:
                scheditems.append({'name': teacher.name(),
                                   'cls' : cls})

        context['scheditems'] = scheditems

        return render_to_response(self.baseDir()+'teacherschedule.html', request, (prog, tl), context)

    @needs_admin
    def teacherlist(self, request, tl, one, two, module, extra, prog):
        """ generate list of teachers """

        filterObj, found = get_user_list(request, self.program.getLists(True))
        if not found:
            return filterObj


        context = {'module': self     }
        teachers = [ ESPUser(user) for user in filterObj.getList(User).distinct() ]
        teachers.sort()


        scheditems = []

        for teacher in teachers:
            # get list of valid classes
            classes = [ cls for cls in teacher.getTaughtClasses()
                    if cls.parent_program == self.program
                    and cls.isAccepted()                       ]
            # now we sort them by time/title
            classes.sort()            

            from esp.users.models import ContactInfo
            for cls in classes:

                # aseering 9-29-2007, 1:30am: There must be a better way to do this...
                ci = ContactInfo.objects.filter(user=teacher, phone_cell__isnull=False).exclude(phone_cell='').order_by('id')
                if ci.count() > 0:
                    phone_cell = ci[0].phone_cell
                else:
                    phone_cell = '-'

                scheditems.append({'name': teacher.name(),
                                   'phonenum': phone_cell,
                                   'cls' : cls})

        def cmpsort(one,other):
            if (one['cls'].meeting_times.count() > 0 and other['cls'].meeting_times.count() > 0):
                cmp0 = cmp(one['cls'].meeting_times.all()[0].id, other['cls'].meeting_times.all()[0].id)
            else:
                cmp0 = cmp(one['cls'].meeting_times.count(), other['cls'].meeting_times.count())
                
            if cmp0 != 0:
                return cmp0

            return cmp(one, other)

        scheditems.sort(cmpsort)

        context['scheditems'] = scheditems

        return render_to_response(self.baseDir()+'teacherlist.html', request, (prog, tl), context)

    def get_msg_vars(self, user, key):
        User = ESPUser(user)
        if key == 'schedule':
            return ProgramPrintables.getSchedule(self.program, user)
        if key == 'transcript':
            return ProgramPrintables.getTranscript(self.program, user, 'text')
        if key == 'transcript_html':
            return ProgramPrintables.getTranscript(self.program, user, 'html')
        if key == 'transcript_latex':
            return ProgramPrintables.getTranscript(self.program, user, 'latex')

        return ''

    @needs_admin
    def refund_receipt(self, request, tl, one, two, module, extra, prog):
        from esp.money.models import Transaction
        from esp.web.util.latex import render_to_latex
        from esp.program.modules.forms.printables_refund import RefundInfoForm
        
        user, found = search_for_user(request, self.program.students_union())
        if not found:
            return user

        initial = {'userid': user.id }

        if request.GET.has_key('payer_post'):
            form = RefundInfoForm(request.GET, initial=initial)
            if form.is_valid():
                transactions = Transaction.objects.filter(fbo = user, anchor = self.program.anchor)
                if transactions.count() == 0:
                    transaction = Transaction()
                else:
                    transaction = transactions[0]

                context = {'user': user, 'transaction': transaction}
                context['program'] = prog

                context['payer_name'] = form.clean_data['payer_name']
                context['payer_address'] = form.clean_data['payer_address']                

                context['amount'] = '%.02f' % (transaction.amount)

                if extra:
                    file_type = extra.strip()
                else:
                    file_type = 'pdf'

                return render_to_latex(self.baseDir()+'refund_receipt.tex', context, file_type)
        else:
            form = RefundInfoForm(initial = initial)

        transactions = Transaction.objects.filter(fbo = user, anchor = self.program.anchor)
        if transactions.count() == 0:
            transaction = Transaction()
        else:
            transaction = transactions[0]

        return render_to_response(self.baseDir()+'refund_receipt_form.html', request, (prog, tl), {'form': form,'student':user,
                                                                                                   'transaction': transaction})
    @staticmethod
    def get_student_classlist(program, student):
        
        # get list of valid classes
        classes = [ cls for cls in student.getEnrolledClasses()]

        # add taugtht classes
        classes += [ cls for cls in student.getTaughtClasses()  ]
            
        classes = [ cls for cls in classes
                    if cls.parent_program == program
                    and cls.isAccepted()                       ]
        # now we sort them by time/title
        classes.sort()
        
        return classes

    @staticmethod
    def getTranscript(program, student, format='text'):
        from django.template import Template, Context
        from django.template.loader import get_template

        template_keys = {   'text': 'program/modules/programprintables/transcript.txt',
                            'latex': 'program/modules/programprintables/transcript.tex',
                            'html': 'program/modules/programprintables/transcript.html',
                            'latex_desc': 'program/modules/programprintables/courses_inline.tex'
                        }
                        
        if format in template_keys:
            template_filename = template_keys[format]
        else:
            return ESPError('Attempted to get transcript with nonexistent format: %s' % format)

        t = get_template(template_filename)

        context = {'classlist': ProgramPrintables.get_student_classlist(program, student)}

        return t.render(Context(context))

    @staticmethod
    def getSchedule(program, student):
        
        
        schedule = """
Student schedule for %s:

 Time               | Class                   | Room""" % student.name()

        
        classes = ProgramPrintables.get_student_classlist(program, student)
        
        for cls in classes:
            rooms = cls.prettyrooms()
            if len(rooms) == 0:
                rooms = 'N/A'
            else:
                rooms = ", ".join(rooms)
                
            schedule += """
%s|%s|%s""" % (",".join(cls.friendly_times()).ljust(20),
               cls.title().ljust(25),
               rooms)
               
        return schedule

    @needs_admin
    def studentschedules(self, request, tl, one, two, module, extra, prog):
        """ generate student schedules """

        filterObj, found = get_user_list(request, self.program.getLists(True))

        if not found:
            return filterObj

        context = {'module': self     }
        students = [ ESPUser(user) for user in User.objects.filter(filterObj.get_Q()).distinct()]

        students.sort()
        
        scheditems = []

        for student in students:
            # get list of valid classes
            classes = [ cls for cls in student.getEnrolledClasses()
                                if cls.parent_program == self.program
                                and cls.isAccepted()                       ]
            # now we sort them by time/title
            classes.sort()

            student.classes = classes
            
        context['students'] = students
        return render_to_response(self.baseDir()+'studentschedule.html', request, (prog, tl), context)

    @needs_admin
    def onsiteregform(self, request, tl, one, two, module, extra, prog):

        # Hack together a pseudocontext:
        context = { 'onsiteregform': True,
                    'students': [{'classes': [{'friendly_times': [i.anchor.friendly_name],
                                               'classrooms': [''],
                                               'prettyrooms': ['______'],
                                               'title': '________________________________________',
                                               'getTeacherNames': [' ']} for i in prog.getTimeSlots()]}]
                    }
        return render_to_response(self.baseDir()+'studentschedule.html', request, (prog, tl), context)

    @needs_admin
    def studentschedules_finaid(self, request, tl, one, two, module, extra, prog):
        """ generate student schedules """
        from esp.program.models import FinancialAidRequest
        
        filterObj, found = get_user_list(request, self.program.getLists(True))

        if not found:
            return filterObj

        context = {'module': self     }
        students = [ ESPUser(user) for user in User.objects.filter(filterObj.get_Q()).distinct()]

        students.sort()
        
        scheditems = []

        for student in students:
            # get list of valid classes
            classes = [ cls for cls in student.getEnrolledClasses()
                                if cls.parent_program == self.program
                                and cls.isAccepted()                       ]
            # now we sort them by time/title
            classes.sort()
            #   add financial aid information
            default_cost = 200
            if len(classes) == 2:
                default_cost = 300
                
            finaid = FinancialAidRequest.objects.filter(program=prog, user=student)
            if len(finaid) > 1:
                raise ESPError('There are multiple financial aid requests for %s' % student)
            elif len(finaid) == 1:
                if finaid[0].reviewed and finaid[0].amount_needed is not None:
                    default_cost = finaid[0].amount_needed
        
            #if default_cost is None:
            #    default_cost = 0
                
            student.cost = default_cost
            student.payment_info = True
            student.classes = classes
            
        context['students'] = students
        return render_to_response(self.baseDir()+'studentschedule.html', request, (prog, tl), context)


    @needs_admin
    def flatstudentschedules(self, request, tl, one, two, module, extra, prog):
        """ generate student schedules """

        filterObj, found = get_user_list(request, self.program.getLists(True))
        if not found:
            return filterObj

        context = {'module': self     }
        students = [ ESPUser(user) for user in User.objects.filter(filterObj.get_Q()).distinct()]

        students.sort()
        
        scheditems = []

        for student in students:
            # get list of valid classes
            classes = [ cls for cls in student.getEnrolledClasses()
                    if cls.parent_program == self.program
                    and cls.isAccepted()                       ]
            # now we sort them by time/title
            classes.sort()
            
            for cls in classes:
                scheditems.append({'name': student.name(),
                                   'cls' : cls})

        context['scheditems'] = scheditems
        return render_to_response(self.baseDir()+'flatstudentschedule.html', request, (prog, tl), context)


    @needs_admin
    def roomschedules(self, request, tl, one, two, module, extra, prog):
        """ generate class room rosters"""
        classes = [ cls for cls in self.program.classes()
                    if cls.isAccepted()                      ]
        context = {}
        classes.sort()

        rooms = {}
        scheditems = ['']

        for cls in classes:
            cls_rooms = cls.classroomassignments()
            for roomassignment in roomassignments:
                update_dict = {'room': roomassignment.resource.name,
                               'cls': cls,
                               'timeblock': roomassignment.resource.event.short_description}
                if rooms.has_key(roomassignment.resource.id):
                    rooms[roomassignment.resource.id].append(update_dict)
                else:
                    rooms[roomassignment.resource.id] = [update_dict]
            
        for scheditem in rooms.values():
            for dictobj in scheditem:
                scheditems.append(dictobj)
                
        context['scheditems'] = scheditems

        return render_to_response(self.baseDir()+'roomrosters.html', request, (prog, tl), context)            
        

    @needs_admin
    def satprepreceipt(self, request, tl, one, two, module, extra, prog):
        from esp.money.models import Transaction
        
        filterObj, found = get_user_list(request, self.program.getLists(True))
        if not found:
            return filterObj

        context = {'module': self     }
        students = [ ESPUser(user) for user in User.objects.filter(filterObj.get_Q()).distinct()]

        students.sort()

        receipts = []
        for student in students:
            transactions = Transaction.objects.filter(fbo = student, anchor = self.program.anchor)
            if transactions.count() == 0:
                transaction = Transaction()
            else:
                transaction = transactions[0]

            receipts.append({'user': student, 'transaction': transaction})

        context['receipts'] = receipts
        
        return render_to_response(self.baseDir()+'studentreceipts.html', request, (prog, tl), context)
    
    @needs_admin
    def satpreplabels(self, request, tl, one, two, module, extra, prog):
        filterObj, found = get_user_list(request, self.program.getLists(True))
        if not found:
            return filterObj

        context = {'module': self     }
        students = [ ESPUser(user) for user in User.objects.filter(filterObj.get_Q()).distinct()]

        students.sort()
                                    
        finished_verb = GetNode('V/Finished')
        finished_qsc  = self.program.anchor.tree_create(['SATPrepLabel'])
        
        #if request.GET.has_key('print'):
            
        #    if request.GET['print'] == 'all':
        #        students = self.program.students_union()
        #    elif request.GET['print'] == 'remaining':
        #        printed_students = UserBit.bits_get_users(verb = finished_verb,
        #qsc  = finished_qsc)
        #        printed_students_ids = [user.id for user in printed_students ]
        #        if len(printed_students_ids) == 0:
        #            students = self.program.students_union()
        #        else:
        #            students = self.program.students_union().exclude(id__in = printed_students_ids)
        #    else:
        #        students = ESPUser.objects.filter(id = request.GET['print'])

        #    for student in students:
        #        ub, created = UserBit.objects.get_or_create(user      = student,
        #                                                    verb      = finished_verb,
        #                                                    qsc       = finished_qsc,
        #                                                    recursive = False)

        #        if created:
        #            ub.save()
                    
        #    students = [ESPUser(student) for student in students]
        #    students.sort()

        numperpage = 10
            
        expanded = [[] for i in range(numperpage)]

        users = students
            
        for i in range(len(users)):
            expanded[(i*numperpage)/len(users)].append(users[i])

        users = []
                
        for i in range(len(expanded[0])):
            for j in range(len(expanded)):
                if len(expanded[j]) <= i:
                    users.append(None)
                else:
                    users.append(expanded[j][i])
        students = users
        return render_to_response(self.baseDir()+'SATPrepLabels_print.html', request, (prog, tl), {'students': students})
    #return render_to_response(self.baseDir()+'SATPrepLabels_options.html', request, (prog, tl), {})
            
        
    @needs_admin
    def classrosters(self, request, tl, one, two, module, extra, prog):
        """ generate class rosters """


        filterObj, found = get_user_list(request, self.program.getLists(True))
        if not found:
            return filterObj



        context = {'module': self     }
        teachers = [ ESPUser(user) for user in User.objects.filter(filterObj.get_Q()).distinct()]
        teachers.sort()

        scheditems = []

        for teacher in teachers:
            for cls in teacher.getTaughtClasses().filter(parent_program = self.program):
                if cls.isAccepted():
                    scheditems.append({'teacher': teacher,
                                       'cls'    : cls})

        context['scheditems'] = scheditems
        if extra == 'attendance':
            tpl = 'classattendance.html'
        else:
            tpl = 'classrosters.html'
        return render_to_response(self.baseDir()+tpl, request, (prog, tl), context)
        

    @needs_admin
    def teacherlabels(self, request, tl, one, two, module, extra, prog):
        context = {'module': self}
        teachers = self.program.teachers()
        teachers.sort()
        context['teachers'] = teachers
        return render_to_response(self.baseDir()+'teacherlabels.html', request, (prog, tl), context)

    @needs_admin
    def studentchecklist(self, request, tl, one, two, module, extra, prog):
        context = {'module': self}
        filterObj, found = get_user_list(request, self.program.getLists(True))
        if not found:
            return filterObj


        students= [ ESPUser(user) for user in User.objects.filter(filterObj.get_Q()).distinct() ]
        students.sort()

        studentList = []
        for student in students:
            t = Transaction.objects.filter(fbo = student, anchor = self.program.anchor)
            
            paid_symbol = ''
            if t.count() > 0:
                paid_symbol = '?'
                for tr in t:
                    if tr.executed is True:
                        paid_symbol = 'X'

            studentList.append({'user': student, 'paid': paid_symbol})

        context['students'] = students
        context['studentList'] = studentList
        return render_to_response(self.baseDir()+'studentchecklist.html', request, (prog, tl), context)

    @needs_admin
    def classchecklists(self, request, tl, one, two, module, extra, prog):
        """ Gives you a checklist for each classroom with the students that are supposed to be in that
            classroom.  The form has boxes for payment and forms.  This is useful for the first day 
            of a program. """
        context = {'module': self}

        students= [ ESPUser(user) for user in self.program.students()['confirmed']]
        students.sort()
    
        class_list = []

        for c in self.program.classes():
            c.update_cache_students()
            class_dict = {'cls': c}
            student_list = []
            
            for student in c.students():
                t = Transaction.objects.filter(fbo = student, anchor = self.program.anchor)
                
                paid_symbol = ''
                if t.count() > 0:
                    paid_symbol = '?'
                    for tr in t:
                        if tr.executed is True:
                            paid_symbol = 'X'
    
                student_list.append({'user': student, 'paid': paid_symbol})
            
            class_dict['students'] = student_list
            class_list.append(class_dict)

        context['class_list'] = class_list
        
        return render_to_response(self.baseDir()+'classchecklists.html', request, (prog, tl), context)

    @needs_admin
    def adminbinder(self, request, tl, one, two, module, extra, prog):
        
        if extra not in ['teacher','classid','timeblock']:
            return self.goToCore()
        context = {'module': self}

        scheditems = []

        
        if extra == 'teacher':
            teachers = self.program.teachers()
            teachers.sort()
            map(ESPUser, teachers)
            
            scheditems = []

            for teacher in teachers:
                classes = [ cls for cls in teacher.getTaughtClasses()
                            if cls.isAccepted() and
                               cls.parent_program == self.program     ]
                for cls in classes:
                    scheditems.append({'teacher': teacher,
                                       'class'  : cls})

            context['scheditems'] = scheditems
            return render_to_response(self.baseDir()+'adminteachers.html', request, (prog, tl), context)


        
        if extra == 'classid':
            classes = [cls for cls in self.program.classes()
                       if cls.isAccepted()                   ]

            classes.sort(Class.idcmp)

            for cls in classes:
                for teacher in cls.teachers():
                    teacher = ESPUser(teacher)
                    scheditems.append({'teacher': teacher,
                                      'class'  : cls})
            context['scheditems'] = scheditems                    
            return render_to_response(self.baseDir()+'adminclassid.html', request, (prog, tl), context)


        if extra == 'timeblock':
            classes = [cls for cls in self.program.classes()
                       if cls.isAccepted()                   ]

            classes.sort()
            
            for cls in classes:
                for teacher in cls.teachers():
                    teacher = ESPUser(teacher)
                    scheditems.append({'teacher': teacher,
                                      'cls'  : cls})

            context['scheditems'] = scheditems
            return render_to_response(self.baseDir()+'adminclasstime.html', request, (prog, tl), context)        

    @needs_admin
    def certificate(self, request, tl, one, two, module, extra, prog):
        from esp.web.util.latex import render_to_latex
        
        user, found = search_for_user(request, self.program.students_union())
        if not found:
            return user

        if extra:
            file_type = extra.strip()
        else:
            file_type = 'pdf'

        context = {'user': user, 'prog': prog, 
                    'schedule': ProgramPrintables.getTranscript(prog, user, 'latex'),
                    'descriptions': ProgramPrintables.getTranscript(prog, user, 'latex_desc')}

        return render_to_latex(self.baseDir()+'completion_certificate.tex', context, file_type)
        
