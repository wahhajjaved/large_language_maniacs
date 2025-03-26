from django.core.management.base import BaseCommand, CommandError
from webinterface.models import *
import random


class Command(BaseCommand):
    help = 'Populates an empty database with a rich demonstration ' \
           'featuring all types of objects and functionalities.' \
           'By default, the total timeframe of the demo spans 32 weeks (from <this week minus 7 weeks> up to ' \
           '<this week plus 24 weeks>).'

    def add_arguments(self, parser):
        parser.add_argument('-timeframe', nargs='*', type=int, help="Length of the demo time frame in weeks (integer). "
                                                                    "Must be >= 4.")
        parser.add_argument('--clear-db', nargs='*', help="Add this flag if you would like to delete all existing "
                                                          "objects (to have an empty database) before running.")

    def handle(self, *args, **options):
        if options['timeframe'] is not None and options['timeframe'] and options['timeframe'] >= 4:
            demo_length = options['timeframe'][0]
        else:
            demo_length = 32
        start_before = demo_length // 4 - 1

        if options['clear_db'] is not None:
            clear_db = True
        else:
            clear_db = False

        def eval_model(model, delete: bool):
            obj = model.objects.all()
            if obj.exists():
                if delete:
                    self.stdout.write("Deleting {} objects...".format(model.__name__))
                    obj.delete()
                else:
                    raise CommandError("Found {} object! The database needs to be empty of objects "
                                       "in order to create the demo database! Add flag '--clear-db' to clear "
                                       "the database first (this is irreversible!).".format(model.__name__))

        eval_model(DutySwitch, clear_db)
        eval_model(Task, clear_db)
        eval_model(Assignment, clear_db)
        eval_model(TaskTemplate, clear_db)
        eval_model(CleaningWeek, clear_db)
        eval_model(Affiliation, clear_db)
        eval_model(Cleaner, clear_db)
        if clear_db:
            User.objects.filter(is_superuser=False).delete()
        eval_model(ScheduleGroup, clear_db)
        eval_model(Schedule, clear_db)

        self.stdout.write("Creating schedules...")
        sch1 = Schedule.objects.create(name="Bad EG", cleaners_per_date=1, weekday=6, frequency=1)
        sch2 = Schedule.objects.create(name="Bad 1. OG", cleaners_per_date=1, weekday=6, frequency=1)
        sch3 = Schedule.objects.create(name="Bad 2. OG", cleaners_per_date=1, weekday=6, frequency=1)
        sch4 = Schedule.objects.create(name="Küche EG & 1. OG", cleaners_per_date=2, weekday=5, frequency=1)
        sch5 = Schedule.objects.create(name="Küche 2. OG", cleaners_per_date=2, weekday=5, frequency=1)
        sch6 = Schedule.objects.create(name="Treppenhaus", cleaners_per_date=2, weekday=3, frequency=1)
        sch7 = Schedule.objects.create(name="Um Katze kümmern", cleaners_per_date=2, weekday=3, frequency=1)
        sch8 = Schedule.objects.create(name="Garten", cleaners_per_date=2, weekday=4, frequency=2)
        sch9 = Schedule.objects.create(name="Keller", cleaners_per_date=2, weekday=4, frequency=3)
        schd = Schedule.objects.create(name="Alter Plan", cleaners_per_date=2, weekday=4, frequency=3, disabled=True)


        self.stdout.write("Creating ScheduleGroups...")
        eg = ScheduleGroup.objects.create(name="Erdgeschoss")
        eg.schedules.add(sch1, sch4, sch6, sch7, sch8, sch9)
        og1 = ScheduleGroup.objects.create(name="1. Obergeschoss")
        og1.schedules.add(sch2, sch4, sch6, sch7, sch8, sch9)
        og2 = ScheduleGroup.objects.create(name="2. Obergeschoss")
        og2.schedules.add(sch3, sch5, sch6, sch7, sch8, sch9, schd)

        self.stdout.write("Creating Cleaners...")
        cl_a = Cleaner.objects.create(name="Anne")
        cl_b = Cleaner.objects.create(name="Bernd")
        cl_c = Cleaner.objects.create(name="Clara")
        cl_d = Cleaner.objects.create(name="Daniel")
        cl_e = Cleaner.objects.create(name="Eric")
        cl_f = Cleaner.objects.create(name="Franziska")
        cl_g = Cleaner.objects.create(name="Gero")
        cl_h = Cleaner.objects.create(name="Hannah")
        cl_i = Cleaner.objects.create(name="Ina")
        cl_j = Cleaner.objects.create(name="Justin")
        cl_k = Cleaner.objects.create(name="Kim")
        cl_l = Cleaner.objects.create(name="Luisa")
        cl_m = Cleaner.objects.create(name="Marlene")
        cl_n = Cleaner.objects.create(name="Nina")
        cl_o = Cleaner.objects.create(name="Olaf")
        cl_moved_out = Cleaner.objects.create(name="Ehemaliger")

        self.stdout.write("Creating TaskTemplates...")

        def create_task_templates(schedule: Schedule, template_tuples: list):
            for name, help_text, start, end in template_tuples:
                TaskTemplate.objects.create(name=name, help_text=help_text, schedule=schedule,
                                            start_days_before=start, end_days_after=end)

        common_bathroom_kitchen_tasks = \
            [('Boden wischen', 'Wische den Boden. Verwende Allzweckreiniger im Putzwasser', 2, 2),
             ('Müll rausbringen', 'Bringe den Müll raus', 2, 2),
             ('Oberflächen', 'Wische die Oberflächen ab, damit sie Staub- und Schmutzfrei sind', 2, 2),
             ('Handtücher wechseln', 'Gib dem Bad frische Handtücher', 1, 4),
             ('Putzmittel auffüllen', 'Putzmittel leer? Neues her!', 1, 4),
             ('Putzlappen wecheln', 'Lasse die Putzlappen waschen', 1, 4),
             ('Dusche putzen', 'Schrubbe die Duschwände und hole die Haare aus dem Abfluss', 1, 4)]

        bathroom_tasks = \
            [('Waschbecken putzen', 'Wische das Waschbecken', 2, 2),
             ('Spiegel putzen', 'Putze den Spiegel mit Glasreiniger', 2, 2),
             ('Toilette putzen', 'Putze die Toilettenschüssel mit Reiniger und der Klobürste', 2, 2),
             ('Dusche putzen', 'Schrubbe die Duschwände und hole die Haare aus dem Abfluss', 1, 4)] + \
            common_bathroom_kitchen_tasks

        for sch in [sch1, sch2, sch3]:
            create_task_templates(schedule=sch, template_tuples=bathroom_tasks)

        kitchen_tasks = \
            [('Herd putzen', 'Schrubbe den Herd blitzeblank', 2, 2),
             ('Spülbecken putzen', 'Schrubbe die Spülbecken', 2, 2),
             ('Esstisch abwischen', 'Wische den Esstisch ab', 2, 2),
             ('Biomülleimer putzen', 'Putze den siffigen Biomüll-Eimer', 2, 2)] + \
            common_bathroom_kitchen_tasks

        for sch in [sch4, sch5]:
            create_task_templates(schedule=sch, template_tuples=kitchen_tasks)

        stairway_tasks = \
            [('Treppe fegen', 'Fege die Treppe, bevor du sie wischst', 2, 2),
             ('Treppe wischen', 'Wische die Treppe mit normalem Wasser (kein Reiniger!)', 2, 2),
             ('Handtücher waschen', 'Zum Treppenputzdienst gehört auch das Waschen aller Handtücher', 2, 2)]
        create_task_templates(schedule=sch6, template_tuples=stairway_tasks)

        meowmeow_tasks = \
            [('Futter auffüllen', 'Mietz will schließlich was zu essen haben', 2, 2),
             ('Katzenklo', 'Fisch die Brocken aus dem Streu', 2, 2),
             ('Wasser auffüllen', 'Und nochmal für alle: KEIN BIER', 2, 2)]
        create_task_templates(schedule=sch7, template_tuples=meowmeow_tasks)

        garden_tasks = \
            [('Rasen mähen', 'Fülle bitte Benzin nach wenn es fast leer ist!', 4, 2),
             ('Unkraut yeeten', 'Sonst wächst das Gemüse nicht gut', 4, 2),
             ('Kompost umgraben', 'Die unteren Schichten nach oben und umgekehrt', 2, 4)]
        create_task_templates(schedule=sch8, template_tuples=garden_tasks)

        basement_tasks = \
            [('Inventar machen', 'Schreibe bitte auf wie viel von jedem Getränk da ist', 2, 4),
             ('Boden fegen', 'Am besten Staubmaske tragen', 2, 4),
             ('Gaszähler lesen', 'Schreibe bitte den Stand in unser Buch', 4, 2)]
        create_task_templates(schedule=sch9, template_tuples=basement_tasks)

        # Create time-dependent objects, using current week number as reference so that you can see the difference
        # between cleaning week in past and in future
        now = current_epoch_week()

        self.stdout.write("Creating Affiliations...")

        def affiliate_cleaner(cleaner: Cleaner, groups: list):
            weeks_in_each_group = demo_length // len(groups)
            for j, group in enumerate(groups):
                if group is None:
                    continue
                beginning = now + j * weeks_in_each_group - start_before
                end =       now + ((j + 1) * weeks_in_each_group - 1) - start_before
                self.stdout.write("    Creating Affiliation for {} in {} from {} to {} (current week is {})".format(
                    cleaner, group, beginning, end, current_epoch_week()
                ))
                Affiliation.objects.create(cleaner=cleaner, group=group, beginning=beginning, end=end)

        affiliate_cleaner(cl_a, groups=[eg])
        affiliate_cleaner(cl_b, groups=[eg])
        affiliate_cleaner(cl_c, groups=[eg])

        affiliate_cleaner(cl_d, groups=[og1])
        affiliate_cleaner(cl_e, groups=[og1])
        affiliate_cleaner(cl_f, groups=[og1])

        affiliate_cleaner(cl_g, groups=[og2])
        affiliate_cleaner(cl_h, groups=[og2])
        affiliate_cleaner(cl_i, groups=[og2])

        affiliate_cleaner(cl_j, groups=[eg, og1])
        affiliate_cleaner(cl_k, groups=[og1, eg])

        affiliate_cleaner(cl_l, groups=[eg, og2])
        affiliate_cleaner(cl_m, groups=[og2, eg])

        affiliate_cleaner(cl_n, groups=[og1, og2])
        affiliate_cleaner(cl_o, groups=[og2, og1])

        Affiliation.objects.create(cleaner=cl_moved_out, group=eg, beginning=now-10, end=now-1)

        self.stdout.write("Creating Assignments (this can take some time)...")
        for sch in Schedule.objects.enabled():
            sch.create_assignments_over_timespan(start_week=now - start_before,
                                                 end_week=now - start_before + demo_length)

        self.stdout.write("Creating Tasks...")
        for cleaning_week in CleaningWeek.objects.all():
            cleaning_week.create_missing_tasks()

        self.stdout.write("Creating DutySwitch objects...")
        # Sprinkle some dutyswitch requests over the cleaning_weeks
        assignments = Assignment.objects.filter(cleaning_week__week__range=(now, now+demo_length-start_before-4))
        if assignments:
            for i in range(0, 5):
                choice = random.choice(assignments)
                DutySwitch.objects.create(requester_assignment=choice)
                assignments = assignments.exclude(pk=choice.pk)

        self.stdout.write("Last tweaks...")
        # Of course the Cleaners were diligent and did all tasks until now
        for task in Task.objects.filter(cleaning_week__week__range=(now - start_before, now)):
            possible_cl = task.possible_cleaners()
            if len(possible_cl) != 0:
                selected_cleaner = random.choice(possible_cl)
                if task.my_time_has_come():
                    if random.random() > 0.5:
                        task.set_cleaned_by(selected_cleaner)
                elif task.has_passed():
                    task.set_cleaned_by(selected_cleaner)

        # Except a couple of tasks which are chosen by random
        cleaned_tasks = Task.objects.exclude(cleaned_by__isnull=True)
        if len(cleaned_tasks) != 0:
            for i in range(0, 10):
                uncleaned_task = random.choice(cleaned_tasks)
                uncleaned_task.set_cleaned_by(None)
                cleaned_tasks = cleaned_tasks.exclude(pk=uncleaned_task.pk)




