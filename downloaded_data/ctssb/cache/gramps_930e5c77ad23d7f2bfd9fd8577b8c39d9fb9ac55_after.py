from DataViews import register, Gadget
from BasicUtils import name_displayer
import DateHandler
import gen.lib
import sys
import os
import time
import string

#
# Hello World, in Gramps Gadgets
#
# First, you need a function or class that takes a single argument
# a GuiGadget:

#from DataViews import register
#def init(gui):
#    gui.set_text("Hello world!")

# In this function, you can do some things to update the gadget,
# like set text of the main scroll window.

# Then, you need to register the gadget:

#register(type="gadget", # case in-senstitive keyword "gadget"
#         name="Hello World Gadget", # gadget name, unique among gadgets
#         height = 20,
#         content = init, # function/class; takes guigadget
#         title="Sample Gadget", # default title, user changeable
#         )

# There are a number of arguments that you can provide, including:
# name, height, content, title, expand, state

# Here is a Gadget object. It has a number of method possibilities:
#  init- run once, on construction
#  active_changed- run when active-changed is triggered
#  db_changed- run when db-changed is triggered
#  main- run once per db change, main process (for fast code)
#  background- run once per db change, main process (for slow code)

# You can also call update() to run main and background

class CalendarGadget(Gadget):
    def init(self):
        import gtk
        self.gui.calendar = gtk.Calendar()
        self.gui.calendar.connect('day-selected-double-click', self.double_click)
        self.gui.calendar.connect('month-changed', self.refresh)
        self.gui.scrolledwindow.remove(self.gui.textview)
        self.gui.scrolledwindow.add_with_viewport(self.gui.calendar)
        self.gui.calendar.show()
        self.birthdays = True
        self.dates = {}

    def refresh(self, *obj):
        self.gui.calendar.freeze()
        self.gui.calendar.clear_marks()
        year, month, day = self.gui.calendar.get_date()
        for date in self.dates:
            if date[1] == month - 1:
                if date[2] > 0 and date[2] <= day:
                    self.gui.calendar.mark_day(date[2])
        self.gui.calendar.thaw()

    def background(self):
        self.dates = {}
        # for each day in events
        people = self.gui.dbstate.db.get_person_handles(sort_handles=False)
        cnt = 0
        for person_handle in people:
            if cnt % 350 == 0:
                yield True
            person = self.gui.dbstate.db.get_person_from_handle(person_handle)
            birth_ref = person.get_birth_ref()
            birth_date = None
            if birth_ref:
                birth_event = self.gui.dbstate.db.get_event_from_handle(birth_ref.ref)
                birth_date = birth_event.get_date_object()
            if self.birthdays and birth_date != None:
                year = birth_date.get_year()
                month = birth_date.get_month()
                day = birth_date.get_day()
                #age = self.year - year
                self.dates[(year, month, day)] = 1
            cnt += 1
        self.refresh()

    def double_click(self, obj):
        # bring up events on this day
        pass

class LogGadget(Gadget):
    def db_changed(self):
        self.dbstate.db.connect('person-add', self.log_person_add)
        self.dbstate.db.connect('person-delete', self.log_person_delete)
        self.dbstate.db.connect('person-update', self.log_person_update)
        self.dbstate.db.connect('family-add', self.log_family_add)
        self.dbstate.db.connect('family-delete', self.log_family_delete)
        self.dbstate.db.connect('family-update', self.log_family_update)
    
    def on_load(self):
        if len(self.gui.data) > 0:
            self.show_duplicates = self.gui.data[0]

    def on_save(self):
        self.gui.data = [self.show_duplicates]

    def active_changed(self, handle):
        self.log_active_changed(handle)

    def init(self):
        self.set_text("Log for this Session\n--------------------\n")
        self.history = {}

    def log_person_add(self, handles):
        self.get_person(handles, "person-add")
    def log_person_delete(self, handles):
        self.get_person(handles, "person-delete")
    def log_person_update(self, handles):
        self.get_person(handles, "person-update")
    def log_family_add(self, handles):
        self.append_text("family-add: %s" % handles)
    def log_family_delete(self, handles):
        self.append_text("family-delete: %s" % handles)
    def log_family_update(self, handles):
        self.append_text("family-update: %s" % handles)
    def log_active_changed(self, handles):
        self.get_person([handles], "active-changed")

    def get_person(self, handles, ltype):
        for person_handle in handles:
            if ((self.show_duplicates == "no" and 
                 ltype + ": " + person_handle not in self.history) or
                self.show_duplicates == "yes"):
                self.append_text("%s: " % ltype)
                self.history[ltype + ": " + person_handle] = 1
                person = self.dbstate.db.get_person_from_handle(person_handle)
                if person:
                    self.link(name_displayer.display(person), person_handle)
                else:
                    self.link("Unknown", person_handle)
                self.append_text("\n")

class TopSurnamesGadget(Gadget):
    def init(self):
        self.top_size = 10 # will be overwritten in load
        self.set_text("No Family Tree loaded.")

    def db_changed(self):
        self.dbstate.db.connect('person-add', self.update)
        self.dbstate.db.connect('person-delete', self.update)
        self.dbstate.db.connect('person-update', self.update)

    def on_load(self):
        if len(self.gui.data) > 0:
            self.top_size = int(self.gui.data[0])

    def on_save(self):
        self.gui.data = [self.top_size]

    def main(self):
        self.set_text("Processing...\n")

    def background(self):
        people = self.dbstate.db.get_person_handles(sort_handles=False)
        surnames = {}
        cnt = 0
        for person_handle in people:
            person = self.dbstate.db.get_person_from_handle(person_handle)
            if person:
                surname = person.get_primary_name().get_surname().strip()
                surnames[surname] = surnames.get(surname, 0) + 1
            if cnt % 350 == 0:
                yield True
            cnt += 1
        total_people = cnt
        surname_sort = []
        total = 0
        cnt = 0
        for surname in surnames:
            surname_sort.append( (surnames[surname], surname) )
            total += surnames[surname]
            if cnt % 350 == 0:
                yield True
            cnt += 1
        total_surnames = cnt
        surname_sort.sort(lambda a,b: -cmp(a,b))
        line = 0
        ### All done!
        self.set_text("")
        for (count, surname) in surname_sort:
            self.append_text("  %d. %s, %d%% (%d)\n" % 
                             (line + 1, surname, 
                              int((float(count)/total) * 100), count))
            line += 1
            if line >= self.top_size:
                break
        self.append_text("\nTotal unique surnames: %d\n" % total_surnames)
        self.append_text("Total people: %d" % total_people)
        
class StatsGadget(Gadget):
    def db_changed(self):
        self.dbstate.db.connect('person-add', self.update)
        self.dbstate.db.connect('person-delete', self.update)
        self.dbstate.db.connect('family-add', self.update)
        self.dbstate.db.connect('family-delete', self.update)

    def init(self):
        self.set_text("No Family Tree loaded.")

    def background(self):
        self.set_text("Processing...")
        database = self.dbstate.db
        personList = database.get_person_handles(sort_handles=False)
        familyList = database.get_family_handles()

        with_photos = 0
        total_photos = 0
        incomp_names = 0
        disconnected = 0
        missing_bday = 0
        males = 0
        females = 0
        unknowns = 0
        bytes = 0
        namelist = []
        notfound = []

        pobjects = len(database.get_media_object_handles())
        for photo_id in database.get_media_object_handles():
            photo = database.get_object_from_handle(photo_id)
            try:
                bytes = bytes + posixpath.getsize(photo.get_path())
            except:
                notfound.append(photo.get_path())

        cnt = 0
        for person_handle in personList:
            person = database.get_person_from_handle(person_handle)
            if not person:
                continue
            length = len(person.get_media_list())
            if length > 0:
                with_photos = with_photos + 1
                total_photos = total_photos + length

            person = database.get_person_from_handle(person_handle)
            name = person.get_primary_name()
            if name.get_first_name() == "" or name.get_surname() == "":
                incomp_names = incomp_names + 1
            if ((not person.get_main_parents_family_handle()) and 
                (not len(person.get_family_handle_list()))):
                disconnected = disconnected + 1
            birth_ref = person.get_birth_ref()
            if birth_ref:
                birth = database.get_event_from_handle(birth_ref.ref)
                if not DateHandler.get_date(birth):
                    missing_bday = missing_bday + 1
            else:
                missing_bday = missing_bday + 1
            if person.get_gender() == gen.lib.Person.FEMALE:
                females = females + 1
            elif person.get_gender() == gen.lib.Person.MALE:
                males = males + 1
            else:
                unknowns += 1
            if name.get_surname() not in namelist:
                namelist.append(name.get_surname())
            if cnt % 200 == 0:
                yield True
            cnt += 1

        text = _("Individuals") + "\n"
        text = text + "----------------------------\n"
        text = text + "%s: %d\n" % (_("Number of individuals"),len(personList))
        text = text + "%s: %d\n" % (_("Males"),males)
        text = text + "%s: %d\n" % (_("Females"),females)
        text = text + "%s: %d\n" % (_("Individuals with unknown gender"),unknowns)
        text = text + "%s: %d\n" % (_("Individuals with incomplete names"),incomp_names)
        text = text + "%s: %d\n" % (_("Individuals missing birth dates"),missing_bday)
        text = text + "%s: %d\n" % (_("Disconnected individuals"),disconnected)
        text = text + "\n%s\n" % _("Family Information")
        text = text + "----------------------------\n"
        text = text + "%s: %d\n" % (_("Number of families"),len(familyList))
        text = text + "%s: %d\n" % (_("Unique surnames"),len(namelist))
        text = text + "\n%s\n" % _("Media Objects")
        text = text + "----------------------------\n"
        text = text + "%s: %d\n" % (_("Individuals with media objects"),with_photos)
        text = text + "%s: %d\n" % (_("Total number of media object references"),total_photos)
        text = text + "%s: %d\n" % (_("Number of unique media objects"),pobjects)
        text = text + "%s: %d %s\n" % (_("Total size of media objects"),bytes,\
                                        _("bytes"))

        if len(notfound) > 0:
            text = text + "\n%s\n" % _("Missing Media Objects")
            text = text + "----------------------------\n"
            for p in notfound:
                text = text + "%s\n" % p
        self.set_text(text)

class PythonGadget(Gadget):
    def init(self):
        self.env = {"dbstate": self.gui.dbstate,
                    "uistate": self.gui.uistate,
                    "self": self,
                    }
        # GUI setup:
        self.gui.textview.set_editable(True)
        self.set_text("Python %s\n> " % sys.version)
        self.gui.textview.connect('key-press-event', self.on_enter)

    def format_exception(self, max_tb_level=10):
        retval = ''
        cla, exc, trbk = sys.exc_info()
        retval += "ERROR: %s %s" %(cla, exc)
        return retval

    def on_enter(self, widget, event):
        if event.keyval == 65293: # enter, where to get this?
            buffer = widget.get_buffer()
            line_cnt = buffer.get_line_count()
            start = buffer.get_iter_at_line(line_cnt - 1)
            end = buffer.get_end_iter()
            line = buffer.get_text(start, end)
            if line.startswith("> "):
                self.append_text("\n")
                line = line[2:]
            # update states, in case of change:
            self.env["dbstate"] = self.gui.dbstate
            self.env["uistate"] = self.gui.uistate
            _retval = None
            if "_retval" in self.env:
                del self.env["_retval"]
            exp1 = """_retval = """ + string.strip(line)
            exp2 = string.strip(line)
            try:
                _retval = eval(exp2, self.env)
            except:
                try:
                    exec exp1 in self.env
                except:
                    try:
                        exec exp2 in self.env
                    except:
                        _retval = self.format_exception()
            if "_retval" in self.env:
                _retval = self.env["_retval"]
            if _retval != None:
                self.append_text("%s\n" % str(_retval))
                self.append_text("> ")
            else:
                self.append_text("> ")
            return True
        return False

class TODOGadget(Gadget):
    def init(self):
        # GUI setup:
        self.gui.textview.set_editable(True)
        self.append_text("Enter your TODO list here.")

    def on_load(self):
        self.load_data_to_text()

    def on_save(self):
        self.gui.data = [] # clear out old data
        self.save_text_to_data()

def make_welcome_content(gui):
    text = """
Welcome to GRAMPS!

GRAMPS is a software package designed for genealogical research. Although similar to other genealogical programs, GRAMPS offers some unique and powerful features.

GRAMPS is an Open Source Software package, which means you are free to make copies and distribute it to anyone you like. It's developed and maintained by a worldwide team of volunteers whose goal is to make GRAMPS powerful, yet easy to use.

Getting Started

The first thing you must do is to create a new Family Tree. To create a new Family Tree (sometimes called a database) select "Family Trees" from the menu.... TODO

You are currently reading from the "My Gramps" page, where you can add your own gadgets.

You can right-click on the background of this page to add additional gadgets and change the number of columns. You can also drag the Properties button to reposition the gadget on this page, and detach the gadget to float above GRAMPS. If you close GRAMPS with a gadget detached, it will re-opened detached the next time you start GRAMPS.

"""
    gui.set_text(text)


register(type="gadget", 
         name="Top Surnames Gadget", 
         height=230,
         content = TopSurnamesGadget,
         title="Top Surnames",
         )

register(type="gadget", 
         name="Stats Gadget", 
         height=230,
         expand=True,
         content = StatsGadget,
         title="Stats",
         )

register(type="gadget", 
         name="Log Gadget", 
         height=230,
         data=['no'],
         content = LogGadget,
         title="Session Log",
         )

register(type="gadget", 
         name="Python Gadget", 
         height=250,
         content = PythonGadget,
         title="Python Shell",
         )

register(type="gadget", 
         name="TODO Gadget", 
         height=300,
         expand=True,
         content = TODOGadget,
         title="TODO List",
         )

register(type="gadget", 
         name="Welcome Gadget", 
         height=300,
         expand=True,
         content = make_welcome_content,
         title="Welcome to GRAMPS!",
         )

register(type="gadget", 
         name="Calendar Gadget", 
         height=200,
         content = CalendarGadget,
         title="Calendar",
         )

