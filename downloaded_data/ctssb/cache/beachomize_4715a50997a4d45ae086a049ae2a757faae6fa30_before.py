# -*- coding: utf-8 -*-

try:
    import Tkinter as tk
except:
    import tkinter as tk
try:
    import tkMessageBox
except:
    import tkinter.messagebox as tkMessageBox
try:
    import tkFont
except:
    import tkinter.font as tkFont
from PIL import Image, ImageTk             # PIL.ImageTk officially supports python 2.4-2.7 and 3.2-3.3, but for me it also works on 3.6, on both Windows (anaconda) and Linux.
import time
import numpy as np
import dialog
import turnier2 as turnier
import lang

FILENAME_PLAYERS = "players.txt"
FILENAME_COURTS = "courts.txt"

class StatsWindow(dialog.Dialog):

    def body(self, master):
        sort_indices = np.lexsort((-self.gui.tur.players.points, -self.gui.tur.players.diff, -self.gui.tur.players.score))
        stats_sorted = self.gui.tur.players[sort_indices]
        for u in range(1+int(self.gui.tur.p/self.gui.stats_height)- int(not bool(self.gui.tur.p % self.gui.stats_height))):
            cs = u*(5+int(self.gui.tur.display_mmr))
            tk.Label(master, text=lang.STATS_NAME, font=self.gui.bold_font, bg="#EDEEF3").grid(row=0, column=0+cs, ipadx=int(self.gui.default_size/4))
            tk.Label(master, text=lang.STATS_SCORE, font=self.gui.bold_font, bg="#EDEEF3").grid(row=0, column=1+cs, ipadx=int(self.gui.default_size/4))
            tk.Label(master, text=lang.STATS_DIFF, font=self.gui.bold_font, bg="#EDEEF3").grid(row=0, column=2 + cs, ipadx=int(self.gui.default_size/4))
            tk.Label(master, text=lang.STATS_POINTS, font=self.gui.bold_font, bg="#EDEEF3").grid(row=0, column=3 + cs, ipadx=int(self.gui.default_size/4))
            if self.gui.tur.display_mmr:
                tk.Label(master, text=lang.STATS_MMR, font=self.gui.bold_font, bg="#EDEEF3").grid(row=0, column=4+cs, ipadx=int(self.gui.default_size/4))
            tk.Label(master, text=lang.STATS_APPEARANCES+"    ", font=self.gui.bold_font, bg="#EDEEF3").grid(row=0, column=4+cs+int(self.gui.tur.display_mmr), ipadx=int(self.gui.default_size/4))
            for ip, pl in enumerate(stats_sorted[u*self.gui.stats_height:]):
                if ip == self.gui.stats_height:
                    break
                game_sub = 0
                if pl.index == 0:
                    game_sub += self.gui.tur.rizemode
                if self.gui.tur.state == 1 and pl.index in self.gui.tur.games[-1]:
                    game_sub -= 1
                tk.Label(master, text=pl.name, bg="#EDEEF3").grid(row=ip+1, column=0+cs)
                tk.Label(master, text=pl.score, bg="#EDEEF3").grid(row=ip+1, column=1+cs)
                tk.Label(master, text=pl.diff, bg="#EDEEF3").grid(row=ip + 1, column=2 + cs)
                tk.Label(master, text=pl.points, bg="#EDEEF3").grid(row=ip + 1, column=3 + cs)
                if self.gui.tur.display_mmr:
                    tk.Label(master, text="{:.1f}".format(pl.mmr), bg="#EDEEF3").grid(row=ip+1, column=4+cs)
                tk.Label(master, text=self.gui.tur.i-pl.wait+game_sub, bg="#EDEEF3").grid(row=ip+1, column=4+cs+int(self.gui.tur.display_mmr))

    def buttonbox(self):
        box = tk.Frame(self, bg="#EDEEF3")

        w = tk.Button(box, text=lang.STATS_CLOSE, width=10, command=self.ok, default=tk.ACTIVE, bg="#EDEEF3")
        w.pack(side=tk.LEFT, padx=int(self.gui.default_size/2), pady=int(self.gui.default_size/2))

        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

        box.pack()


class ResultsWindow(dialog.Dialog):

    def body(self, master):
        res_list = self.gui.tur.results[self.gui.tur.i - 1]
        self.is_correction = False
        if not len(res_list[0]) == 0:
            self.is_correction = True
        self.master = master
        if self.gui.sets > 3:
            self.gui.sets = 3
        elif self.gui.sets < 1:
            self.gui.sets = 1
        self.game_labels = []
        team_indices = self.gui.tur.games[-1]
        names_sorted = self.gui.tur.players.name[team_indices]
        self.spinboxes = []
        self.placeholders = []
        for ci in range(self.gui.tur.c):
            tk.Label(master, text=self.gui.court_names[ci], font=self.gui.bold_font, bg="#EDEEF3").grid(row=2*ci, column=0)
            lbl1 = ""
            lbl2 = ""
            for pi in range(self.gui.tur.teamsize):
                lbl1 += (names_sorted[2 * ci][pi] + "/") if pi < self.gui.tur.teamsize-1 else names_sorted[2 * ci][pi]
                lbl2 += (names_sorted[2 * ci + 1][pi] + "/") if pi < self.gui.tur.teamsize - 1 else names_sorted[2 * ci + 1][pi]
            self.game_labels.append(tk.Label(master, text=lbl1 + " - " + lbl2, bg="#EDEEF3"))
            self.game_labels[ci].grid(row=2*ci+1, column=0, padx=self.gui.default_size)
            self.spinboxes.append([])
            self.placeholders.append([])
            for si in range(3):
                self.spinboxes[-1].append([])
                self.placeholders[-1].append([])
                self.placeholders[-1][-1].append(tk.Label(master, text="        ", bg="#EDEEF3"))
                self.placeholders[-1][-1][-1].grid(row=2 * ci + 1, column=4 * si+1)
                self.spinboxes[-1][-1].append(tk.Spinbox(master, width=5, from_=0, to=30, bg="#EDEEF3"))
                self.spinboxes[-1][-1][-1].grid(row=2*ci+1,column=4*si+2)
                self.placeholders[-1][-1].append(tk.Label(master,text="-", bg="#EDEEF3"))
                self.placeholders[-1][-1][-1].grid(row=2*ci+1, column=4*si+3)
                self.spinboxes[-1][-1].append(tk.Spinbox(master, width=5, from_=0, to=30, bg="#EDEEF3"))
                self.spinboxes[-1][-1][-1].grid(row=2 * ci+1, column=4*si+4)
                #if result already known, fill spinbox
                if len(res_list[ci]) > si:
                    self.spinboxes[-1][-1][0].delete(0, "end")
                    self.spinboxes[-1][-1][0].insert(0, res_list[ci][si][0])
                    self.spinboxes[-1][-1][1].delete(0, "end")
                    self.spinboxes[-1][-1][1].insert(0, res_list[ci][si][1])

        self.spinboxes[0][0][0].selection_adjust("end")
        return self.spinboxes[0][0][0]

    def buttonbox(self):
        box = tk.Frame(self, bg="#EDEEF3")

        w = tk.Button(box, text=lang.DIALOG_OK, width=10, command=self.ok, default=tk.ACTIVE, bg="#EDEEF3")
        w.pack(side=tk.LEFT, padx=int(self.gui.default_size/2), pady=int(self.gui.default_size/2))
        stateval = tk.NORMAL if self.gui.sets > 1 else tk.DISABLED
        self.reduce_but = tk.Button(box, text=lang.RESULTS_SET_DECREASE, width=5, command=self.reduce_set_number, state=stateval, bg="#EDEEF3")
        self.reduce_but.pack(side=tk.LEFT, padx=int(self.gui.default_size/2), pady=int(self.gui.default_size/2))
        stateval = tk.NORMAL if self.gui.sets < 3 else tk.DISABLED
        self.increase_but = tk.Button(box, text=lang.RESULTS_SET_INCREASE, width=5, command=self.increase_set_number, state=stateval, bg="#EDEEF3")
        self.increase_but.pack(side=tk.LEFT, padx=int(self.gui.default_size/2), pady=int(self.gui.default_size/2))

        #self.bind("<Return>", self.ok_bind)
        #self.bind("<Escape>", self.cancel)

        box.pack()

        goal_sets = self.gui.sets
        self.gui.sets = 3
        while self.gui.sets > goal_sets:
            self.reduce_set_number()

    def reduce_set_number(self):
        self.gui.sets -= 1
        for ci in range(self.gui.tur.c):
            self.placeholders[ci][self.gui.sets][1].grid_forget()
            self.spinboxes[ci][self.gui.sets][1].delete(0, "end")
            self.spinboxes[ci][self.gui.sets][1].insert(0, 0)
            self.spinboxes[ci][self.gui.sets][1].grid_forget()
            self.placeholders[ci][self.gui.sets][0].grid_forget()
            self.spinboxes[ci][self.gui.sets][0].delete(0, "end")
            self.spinboxes[ci][self.gui.sets][0].insert(0, 0)
            self.spinboxes[ci][self.gui.sets][0].grid_forget()
        if self.increase_but["state"] == tk.DISABLED:
            self.increase_but["state"] = tk.NORMAL
        if self.gui.sets == 1:
            self.reduce_but["state"] = tk.DISABLED

    def increase_set_number(self):
        for ci in range(self.gui.tur.c):
            self.placeholders[ci][self.gui.sets][0].grid(row=2 * ci + 1, column=4 * self.gui.sets + 1)
            self.spinboxes[ci][self.gui.sets][0].grid(row=2 * ci + 1, column=4 * self.gui.sets + 2)
            self.placeholders[ci][self.gui.sets][1].grid(row=2 * ci + 1, column=4 * self.gui.sets + 3)
            self.spinboxes[ci][self.gui.sets][1].grid(row=2 * ci + 1, column=4 * self.gui.sets + 4)
        self.gui.sets += 1
        if self.reduce_but["state"] == tk.DISABLED:
            self.reduce_but["state"] = tk.NORMAL
        if self.gui.sets == 3:
            self.increase_but["state"] = tk.DISABLED

    def validate(self):
        self.res_list = []
        for ci in range(self.gui.tur.c):
            self.res_list.append([])
            for si in range(self.gui.sets):
                set_res = []
                for ii in range(2):
                    try:
                        set_res.append(int(self.spinboxes[ci][si][ii].get()))
                    except Exception:
                        tkMessageBox.showwarning(lang.ERROR_TITLE, lang.ERROR_INVALID_INPUT, parent=self)
                        self.spinboxes[ci][si][ii].selection_adjust("end")
                        self.initial_focus = self.spinboxes[ci][si][ii]
                        return 0
                self.res_list[-1].append([set_res[0], set_res[1]])
        return 1

    def apply(self):

        if self.is_correction:
            self.gui.tur.cor_res(self.res_list)
        else:
            self.gui.tur.res(self.res_list)

class WelcomeWindow(dialog.Dialog):

    def body(self, master):
        tk.Label(master, text=lang.WELCOME_HEADING, bg="#EDEEF3").pack()
        return None

    def buttonbox(self):
        box = tk.Frame(self, bg="#EDEEF3")

        w = tk.Button(box, text=lang.NEW_BUTTON, width=10, command=self.new, default=tk.ACTIVE, bg="#EDEEF3")
        w.grid(row=0, column=0, padx=int(self.gui.default_size/2), pady=int(self.gui.default_size/2))
        w = tk.Button(box, text=lang.LOAD_BUTTON, width=10, command=self.ok, bg="#EDEEF3")
        w.grid(row=0, column=1, padx=int(self.gui.default_size/2), pady=int(self.gui.default_size/2))

        self.cvar = tk.IntVar()
        self.cvar.set(3)
        self.cvar_outer = tk.IntVar()
        self.cvar_outer.set(3)
        tk.Label(box, text=lang.WELCOME_COURT_NUMBER, bg="#EDEEF3").grid(row=1, column=0, pady=int(self.gui.default_size/2))
        self.cmenu = tk.OptionMenu(box, self.cvar, 1, 2, 3, 4, 5)
        self.cmenu.config(bg="#EDEEF3")
        self.cmenu["menu"].config(bg="#EDEEF3")
        self.cmenu.grid(row=2, column=0)
        self.clabel_outer = tk.Label(box, text=lang.WELCOME_COURT_NUMBER_OUTER, bg="#EDEEF3")
        self.cmenu_outer = tk.OptionMenu(box, self.cvar_outer, 1, 2, 3, 4, 5)
        self.cmenu_outer.config(bg="#EDEEF3")
        self.cmenu_outer["menu"].config(bg="#EDEEF3")
        self.out_show = False

        self.tvar = tk.IntVar()
        self.tvar.set(2)
        tk.Label(box, text=lang.WELCOME_TEAMSIZE, bg="#EDEEF3").grid(row=1, column=1, pady=int(self.gui.default_size / 2))
        self.tmenu = tk.OptionMenu(box, self.tvar, 2, 3, 4, 5, 6)
        self.tmenu.config(bg="#EDEEF3")
        self.tmenu.grid(row=2, column=1)

        tk.Label(box, text=lang.WELCOME_TIME_DURATION, bg="#EDEEF3").grid(row=3, column=0, pady=int(self.gui.default_size / 2))
        self.time_scale = tk.Scale(box, from_=0, to=23.5, resolution=0.5, orient=tk.HORIZONTAL, showvalue=0, label=lang.TIME_FORMAT.format(21, 0), length=self.gui.default_size * 10,
                                   command=self.time_update, bg="#EDEEF3")
        self.time_scale.set(21.0)
        self.time_scale.grid(row=4, column=0)
        self.duration_scale = tk.Scale(box, from_=1, to=6, resolution=0.5, orient=tk.HORIZONTAL, showvalue=0, label=lang.DURATION_FORMAT.format(3, 0), length=self.gui.default_size * 10,
                                       command=self.duration_update, bg="#EDEEF3")
        self.duration_scale.set(3.0)
        self.duration_scale.grid(row=5, column=0)
        tk.Label(box, text=lang.WELCOME_INTERVALS, bg="#EDEEF3").grid(row=3, column=1, pady=int(self.gui.default_size / 2))
        self.interval1_scale = tk.Scale(box, from_=21, to=23, resolution=0.5, orient=tk.HORIZONTAL, showvalue=0, label=lang.TIME_FORMAT.format(21, 0), length=self.gui.default_size * 10,
                                   command=self.interval1_update, bg="#EDEEF3")
        self.interval1_scale.set(21.0)
        self.interval1_scale.grid(row=4, column=1)
        self.interval2_scale = tk.Scale(box, from_=22, to=24, resolution=0.5, orient=tk.HORIZONTAL, showvalue=0, label=lang.TIME_FORMAT.format(24, 0), length=self.gui.default_size * 10,
                                       command=self.interval2_update, bg="#EDEEF3")
        self.interval2_scale.set(24.0)
        self.interval2_scale.grid(row=5, column=1)

        tk.Label(box, text=lang.WELCOME_MMR_METHOD, bg="#EDEEF3").grid(row=6, column=0, pady=int(self.gui.default_size / 2))
        self.mmrtagvar = tk.StringVar()
        self.mmrtagvar.set(turnier.MMR_TAGS[0])
        self.taglabel = tk.Label(box, text=lang.WELCOME_MMR_TAGS, bg="#EDEEF3")
        self.taglabel.grid(row=10, column=0, pady=int(self.gui.default_size / 2))
        self.tagmenu = tk.OptionMenu(box, self.mmrtagvar, *turnier.MMR_TAGS)
        self.tagmenu.config(bg="#EDEEF3")
        self.tagmenu["menu"].config(bg="#EDEEF3")
        self.tagmenu.grid(row=11, column=0)
        self.tag_rendered = True

        self.mmr_score_diff_var = tk.IntVar()
        self.mmr_score_diff_var.set(1)
        tk.Checkbutton(box, text=lang.WELCOME_MMR_SCORE_DIFFERENCE, variable=self.mmr_score_diff_var, command=None, bg="#EDEEF3").grid(row=7, column=0)
        self.mmr_mmr_diff_var = tk.IntVar()
        self.mmr_mmr_diff_var.set(1)
        tk.Checkbutton(box, text=lang.WELCOME_MMR_MMR_DIFFERENCE, variable=self.mmr_mmr_diff_var, command=None, bg="#EDEEF3").grid(row=8, column=0)
        self.mmr_streak_var = tk.IntVar()
        self.mmr_streak_var.set(1)
        tk.Checkbutton(box, text=lang.WELCOME_MMR_STREAK, variable=self.mmr_streak_var, command=self.update_mmr, bg="#EDEEF3").grid(row=9, column=0)

        self.bind('<Return>', self.new)

        box.pack()

    def show_outer(self):
        if not self.out_show:
            self.out_show = True
            self.clabel_outer.grid(row=6, column=1, pady=int(self.gui.default_size / 2))
            self.cmenu_outer.grid(row=7, column=1)

    def hide_outer(self):
        if self.out_show:
            self.out_show = False
            self.clabel_outer.grid_forget()
            self.cmenu_outer.grid_forget()

    def timdur(self, tim, dur):
        self.interval1_scale["from"] = tim
        self.interval1_scale["to"] = tim + dur - 1
        self.interval1_scale.set(tim)
        self.interval1_update()
        self.interval2_scale["from"] = tim + 1
        self.interval2_scale["to"] = tim + dur
        self.interval2_scale.set(tim + dur)
        self.interval2_update()
        self.hide_outer()

    def time_update(self, event=None):
        tim = self.time_scale.get()
        dur = self.duration_scale.get()
        self.timdur(tim, dur)
        hour = int(tim)
        minute = int(60*(tim-hour))
        self.time_scale["label"] = lang.TIME_FORMAT.format(hour,minute)

    def duration_update(self, event=None):
        dur = self.duration_scale.get()
        tim = self.time_scale.get()
        self.timdur(tim,dur)
        hour = int(dur)
        minute = int(60*(dur-hour))
        self.duration_scale["label"] = lang.DURATION_FORMAT.format(hour,minute)

    def interval1_update(self, event=None):
        int1 = self.interval1_scale.get()
        if int1 == self.interval1_scale["from"]:
            self.hide_outer()
        else:
            self.show_outer()
        self.interval2_scale["from"] = int1+1
        hour = int(int1)
        minute = int(60*(int1-hour))
        self.interval1_scale["label"] = lang.TIME_FORMAT.format(hour%24, minute)

    def interval2_update(self, event=None):
        int2 = self.interval2_scale.get()
        if int2 == self.interval2_scale["to"]:
            self.hide_outer()
        else:
            self.show_outer()
        self.interval1_scale["to"] = int2-1
        hour = int(int2)
        minute = int(60*(int2-hour))
        self.interval2_scale["label"] = lang.TIME_FORMAT.format(hour%24, minute)

    def update_mmr(self, event=None):
        if self.mmr_streak_var.get():
        # if "streak" in self.mmrvar.get():
            if not self.tag_rendered:
                self.taglabel.grid(row=10, column=0, pady=int(self.gui.default_size / 2))
                self.tagmenu.grid(row=11, column=0)
                self.tag_rendered = True
        else:
            if self.tag_rendered:
                self.taglabel.grid_forget()
                self.tagmenu.grid_forget()
                self.tag_rendered = False

    def validate(self):
        try:
            self.gui.tur = turnier.load(self.gui)
        except IOError:
            tkMessageBox.showwarning(lang.ERROR_TITLE, lang.WELCOME_NO_SAVED_FILE, parent=self)
            return 0
        return 1

    def apply(self):
        if self.gui.tur.state == 1:
            pass
        pass

    def new(self, event=None):   #parameter event for call by event binding from enter
        start = self.time_scale.get()
        starttime = int(start) * 100 + int(60 * (int(start) - start))
        dur = self.duration_scale.get()
        duration = int(dur) * 100 + int(60 * (int(dur) - dur))
        end = start + dur
        int1 = self.interval1_scale.get()
        int2 = self.interval2_scale.get()
        t1 = (int1-start) / dur
        t2 = (int2-int1) / dur
        t3 = (end-int2) /dur

        self.withdraw()
        self.update_idletasks()

        names, mmr, female_count = self.gui.in_players()
        self.gui.tur = turnier.Turnier(names, mmr, courts=self.cvar.get(), courts13=self.cvar_outer.get(), start_time=starttime, duration=duration, t1=t1, t2=t2, t3=t3,
                                       matchmaking=[self.mmr_score_diff_var.get(), self.mmr_mmr_diff_var.get(), self.mmr_streak_var.get()],
                                       matchmaking_tag=turnier.MMR_TAGS.index(self.mmrtagvar.get()), females=female_count, teamsize=self.tvar.get())

        self.cancel()

class GameNumberWindow(dialog.Dialog):
    def __init__(self, parent, gui, goodlist, waitlist, playlist, waitlist2, playlist2, waitlist3, playlist3, title=lang.GAME_NUMBER_TITLE):
        self.goodlist = goodlist
        self.waitlist = waitlist
        self.playlist = playlist
        self.waitlist2 = waitlist2
        self.playlist2 = playlist2
        self.waitlist3 = waitlist3
        self.playlist3 = playlist3
        dialog.Dialog.__init__(self, parent, gui, title)

    def body(self, master):
        tk.Label(master, text=lang.GAME_NUMBER_HEADING, bg="#EDEEF3").pack()
        gridframe = tk.Frame(master, bg="#EDEEF3")
        buttonlist = []
        tk.Label(gridframe, text=lang.RIZEMODE_NORMAL.format(self.gui.tur.players.name[0]), bg="#EDEEF3").grid(row=0)
        for gg, good in enumerate(self.goodlist):
            buttonlist.append(tk.Radiobutton(gridframe, text=str(good), variable=self.gui.game_count, value=good, bg="#EDEEF3"))
            buttonlist[-1].grid(row=0, column=1+gg)
        tk.Label(gridframe, text=lang.RIZEMODE_WAIT.format(self.gui.tur.players.name[0]), bg="#EDEEF3").grid(row=1)
        for ww, wait in enumerate(self.waitlist):
            buttonlist.append(tk.Radiobutton(gridframe, text=str(wait), variable=self.gui.game_count, value=wait, bg="#EDEEF3"))
            buttonlist[-1].grid(row=1, column=1+ww)
        tk.Label(gridframe, text=lang.RIZEMODE_PLAY.format(self.gui.tur.players.name[0]), bg="#EDEEF3").grid(row=2)
        for pp, play in enumerate(self.playlist):
            buttonlist.append(tk.Radiobutton(gridframe, text=str(play), variable=self.gui.game_count, value=play, bg="#EDEEF3"))
            buttonlist[-1].grid(row=2, column=1+pp)
        tk.Label(gridframe, text=lang.RIZEMODE_WAIT2.format(self.gui.tur.players.name[0]), bg="#EDEEF3").grid(row=3)
        for ww2, wait2 in enumerate(self.waitlist2):
            buttonlist.append(tk.Radiobutton(gridframe, text=str(wait2), variable=self.gui.game_count, value=wait2, bg="#EDEEF3"))
            buttonlist[-1].grid(row=3, column=1+ww2)
        tk.Label(gridframe, text=lang.RIZEMODE_PLAY2.format(self.gui.tur.players.name[0]), bg="#EDEEF3").grid(row=4)
        for pp2, play2 in enumerate(self.playlist2):
            buttonlist.append(tk.Radiobutton(gridframe, text=str(play2), variable=self.gui.game_count, value=play2, bg="#EDEEF3"))
            buttonlist[-1].grid(row=4, column=1+pp2)
        tk.Label(gridframe, text=lang.RIZEMODE_WAIT3.format(self.gui.tur.players.name[0]), bg="#EDEEF3").grid(row=5)
        for ww3, wait3 in enumerate(self.waitlist3):
            buttonlist.append(tk.Radiobutton(gridframe, text=str(wait3), variable=self.gui.game_count, value=wait3, bg="#EDEEF3"))
            buttonlist[-1].grid(row=5, column=1 + ww3)
        tk.Label(gridframe, text=lang.RIZEMODE_PLAY3.format(self.gui.tur.players.name[0]), bg="#EDEEF3").grid(row=6)
        for pp3, play3 in enumerate(self.playlist3):
            buttonlist.append(tk.Radiobutton(gridframe, text=str(play3), variable=self.gui.game_count, value=play3, bg="#EDEEF3"))
            buttonlist[-1].grid(row=6, column=1 + pp3)
        gridframe.pack()
        return buttonlist[0]

    def buttonbox(self):
        box = tk.Frame(self, bg="#EDEEF3")

        w = tk.Button(box, text=lang.DIALOG_OK, width=10, command=self.ok, default=tk.ACTIVE, bg="#EDEEF3")
        w.pack(side=tk.LEFT, padx=int(self.gui.default_size/2), pady=int(self.gui.default_size/2))

        self.bind("<Return>", self.ok)

        box.pack()

class SettingsWindow(dialog.Dialog):
    def body(self, master):
        tk.Button(master, text=lang.SETTINGS_COMMAND_LINE_BUTTON, command=self.cmd, bg="#EDEEF3").grid(row=0, columnspan=2, pady = self.gui.default_size)
        tk.Label(master, text=lang.SETTINGS_FONT_SIZE, bg="#EDEEF3").grid(row=1, column=0, padx=int(self.gui.default_size/2), pady=int(self.gui.default_size/2))
        self.default_size_spin = tk.Spinbox(master, width=5, from_=5, to=30, bg="#EDEEF3")
        self.default_size_spin.delete(0, "end")
        self.default_size_spin.insert(0, int(np.round(self.gui.default_size/self.gui.hdfactor)))
        self.default_size_spin.grid(row=1, column=1)
        tk.Label(master, text=lang.SETTINGS_TABLE_HEIGHT, bg="#EDEEF3").grid(row=2, column=0, padx=int(self.gui.default_size / 2), pady=int(self.gui.default_size / 2))
        self.table_height_spin = tk.Spinbox(master, width=5, from_=5, to=20, bg="#EDEEF3")
        self.table_height_spin.delete(0, "end")
        self.table_height_spin.insert(0, self.gui.table_height)
        self.table_height_spin.grid(row=2, column=1)
        tk.Label(master, text=lang.SETTINGS_STATS_HEIGHT, bg="#EDEEF3").grid(row=3, column=0, padx=int(self.gui.default_size / 2), pady=int(self.gui.default_size / 2))
        self.stats_height_spin = tk.Spinbox(master, width=5, from_=5, to=20, bg="#EDEEF3")
        self.stats_height_spin.delete(0, "end")
        self.stats_height_spin.insert(0, self.gui.stats_height)
        self.stats_height_spin.grid(row=3, column=1)
        tk.Label(master, text=lang.SETTINGS_HEIGHT_INFO, bg="#EDEEF3", fg="red").grid(row=4, columnspan=2, padx=int(self.gui.default_size / 2), pady=int(self.gui.default_size / 2))
        return self.default_size_spin

    def cmd(self, event=None):
        _ = CommandWindow(self, self.gui, title=lang.COMMAND_LINE_TITLE)

    def check_value(self):
        try:
            self.fontval = int(self.default_size_spin.get())
        except:
            self.fontval = self.gui.default_size
        if not self.fontval > 4 and self.fontval < 31:
            self.fontval = self.gui.default_size
        self.default_size_spin.delete(0, "end")
        self.default_size_spin.insert(0, self.fontval)
        try:
            self.tableval = int(self.table_height_spin.get())
        except:
            self.tableval = self.gui.table_height
        if not self.tableval > 4 and self.tableval < 21:
            self.tableval = self.gui.table_height
        self.table_height_spin.delete(0, "end")
        self.table_height_spin.insert(0, self.tableval)
        try:
            self.statsval = int(self.stats_height_spin.get())
        except:
            self.statsval = self.gui.stats_height
        if not self.statsval > 4 and self.statsval < 21:
            self.statsval = self.gui.stats_height
        self.stats_height_spin.delete(0, "end")
        self.stats_height_spin.insert(0, self.statsval)

    def update_gui(self, val, main=True, this=True):
        if val > 4 and val < 31:
            #fonts
            self.gui.default_font.configure(size=val)
            self.gui.text_font.configure(size=val)
            self.gui.bold_font.configure(size=val)
            self.gui.big_bold_font.configure(size=int(1.33 * val))
            self.gui.clock_font.configure(size=int(2.22 * val))
            #self header
            if this:
                dim = self.gui.dims_by_scale(0.015 * val)[1]
                imobj = self.imorg.resize((dim, dim), Image.ANTIALIAS)
                self.gui.logo = ImageTk.PhotoImage(imobj)
                self.header_image_label["image"] = self.gui.logo
            #gui banner
            if main:
                dim = self.gui.dims_by_scale(0.045 * val)[1]
                fac = float(dim) / self.gui.imorg.size[0]
                dim2 = int(self.gui.imorg.size[1] * fac)
                imobj = self.gui.imorg.resize((dim, dim2), Image.ANTIALIAS)
                self.gui.banner = ImageTk.PhotoImage(imobj)
                self.gui.banner_label["image"]=self.gui.banner
                self.gui.banner_label.grid(columnspan=3)
                #gui settings button
                dim = self.gui.dims_by_scale(0.002 * val)[1]
                imobj = self.gui.cogorg.resize((dim, dim), Image.ANTIALIAS)
                self.gui.cog = ImageTk.PhotoImage(imobj)
                self.gui.settings_but["image"] =self.gui.cog

    def buttonbox(self):
        box = tk.Frame(self, bg="#EDEEF3")

        w = tk.Button(box, text=lang.DIALOG_OK, width=10, command=self.ok, default=tk.ACTIVE, bg="#EDEEF3")
        w.pack(side=tk.LEFT, padx=int(self.gui.default_size/2), pady=int(self.gui.default_size/2))
        w = tk.Button(box, text=lang.SETTINGS_PREVIEW, width=10, command=self.preview, bg="#EDEEF3")
        w.pack(side=tk.LEFT, padx=int(self.gui.default_size / 2), pady=int(self.gui.default_size / 2))
        w = tk.Button(box, text=lang.SETTINGS_REVERT, width=10, command=self.cancel, bg="#EDEEF3")
        w.pack(side=tk.LEFT, padx=int(self.gui.default_size/2), pady=int(self.gui.default_size/2))

        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

        box.pack()

    def preview(self):
        self.check_value()
        self.update_gui(int(np.round(self.fontval * self.gui.hdfactor)))

    def apply(self):
        self.check_value()
        self.gui.default_size = int(np.round(self.fontval * self.gui.hdfactor))
        self.gui.table_height = self.tableval
        self.gui.stats_height = self.statsval
        np.save(".font.npy", self.gui.default_size)
        np.save(".table.npy", self.gui.table_height)
        np.save(".stats.npy", self.gui.stats_height)

    def cancel(self, event=None):
        self.update_gui(self.gui.default_size, this=False)

        self.parent.focus_set()
        self.destroy()

class CommandWindow(dialog.Dialog):
    def header(self, master):
        pass

    def body(self, master):
        self.cm = tk.StringVar()
        self.ent = tk.Entry(master, textvariable=self.cm, bg="#EDEEF3")
        self.ent.pack()
        return self.ent

    def validate(self):
        try:
            print(eval(self.cm.get()))
        except Exception as e:
            try:
                exec(self.cm.get())
            except:
                print(e)
                tkMessageBox.showwarning(lang.ERROR_TITLE, lang.COMMAND_LINE_ERROR, parent=self)
                self.ent.selection_adjust("end")
                return 0
        return 1


class GUI:
    def __init__(self):
        self.root = tk.Tk()
        self.screenwidth = self.root.winfo_screenwidth()
        self.screenheight = self.root.winfo_screenheight()
        self.screen_resolution = [self.screenwidth, self.screenheight]
        self.hdfactor = self.screenheight/1080.
        try:
            self.default_size = np.load(".font.npy")
        except:
            self.default_size = int(np.round(15*self.hdfactor))
        try:
            self.table_height = np.load(".table.npy")
        except:
            self.table_height = 10
        try:
            self.stats_height = np.load(".stats.npy")
        except:
            self.stats_height = 10
        self.default_font = tkFont.nametofont("TkDefaultFont")
        self.default_font.configure(size=self.default_size)
        self.text_font = tkFont.nametofont("TkTextFont")
        self.text_font.configure(size=self.default_size)
        self.bold_font = self.default_font.copy()
        self.bold_font.configure(weight="bold")
        self.big_bold_font = self.bold_font.copy()
        self.big_bold_font.configure(size=int(1.33*self.default_size))
        self.clock_font = self.bold_font.copy()
        self.clock_font.configure(size=int(2.22*self.default_size))
        try:
            self.root.iconbitmap("favicon.ico")
        except:
            pass

        self.root.title(lang.MAIN_TITLE)
        self.root.configure(bg="#EDEEF3")
        self.tur = None

        # self.root.withdraw()
        self.welcome = WelcomeWindow(self.root, self, title=lang.WELCOME_TITLE)
        if self.tur is None:
            self.root.destroy()
        else:
            # self.root.deiconify()
            if self.tur.state == -1:
                self.tur.set_game_count(self.in_game_count())

            #create main window elements here
            #banner
            self.imorg = Image.open("ims/banner2.jpg")
            dim = self.dims_by_scale(0.045*self.default_size)[1]
            fac = float(dim) / self.imorg.size[0]
            dim2 = int(self.imorg.size[1] * fac)
            imobj = self.imorg.resize((dim, dim2), Image.ANTIALIAS)
            self.banner = ImageTk.PhotoImage(imobj)
            self.banner_label = tk.Label(self.root, image=self.banner, bg="#EDEEF3")
            self.banner_label.grid(columnspan=3)

            #clock
            clock = tk.Label(self.root, font=self.clock_font, bg="#EDEEF3")
            clock.grid(row=1, columnspan=3, padx=self.default_size, pady=self.default_size)
            def tick():
                s = time.strftime(lang.CLOCK_FORMAT)
                if s != clock["text"]:
                    clock["text"] = s
                clock.after(200, tick)
            tick()

            #player list
            tk.Label(self.root, text=lang.PLAYER_LIST_TITLE, font=self.big_bold_font, bg="#EDEEF3").grid(row=2,column=0, pady=self.default_size)
            self.pl_table=tk.Frame(self.root, bg="#EDEEF3")
            self.pl_labels = []
            for id, nam in enumerate(self.tur.players.name):
                self.pl_labels.append(tk.Label(self.pl_table, text=nam, bg="#EDEEF3"))
                self.pl_labels[id].bind("<Button-1>", lambda event, pid = id: self.toggle_wait(pid))
                self.pl_labels[id].grid(row=id%self.table_height, column=int(id/self.table_height), ipadx = int(self.default_size/2))
            self.pl_table.grid(row=3,column=0)

            #schedule
            tk.Label(self.root, text=lang.SCHEDULE_TITLE, font=self.big_bold_font, bg="#EDEEF3").grid(row=2,column=1, pady=self.default_size)
            self.schedule_table = tk.Frame(self.root, bg="#EDEEF3")
            self.schedule_labels = []
            g_cum_nonzero = []
            for i, gel in enumerate(self.tur.g_list):
                if gel == 0:
                    continue
                g_cum_nonzero.append(gel+sum(self.tur.g_list[0:i]))
            offs = 0
            for id, tim in enumerate(self.tur.schedule):
                if id == g_cum_nonzero[offs]:
                    tk.Label(self.schedule_table, text="", bg="#EDEEF3").grid(row=(id+offs)%self.table_height, column=int((id+offs)/self.table_height), ipadx = int(self.default_size/2))
                    offs += 1
                hour = int(tim/100)
                minute = int(tim-hour*100)
                self.schedule_labels.append(tk.Label(self.schedule_table, text=("{:02d} - " + lang.TIME_FORMAT).format(id+1, hour, minute), bg="#EDEEF3"))
                self.schedule_labels[id].grid(row=(id+offs)%self.table_height, column=int((id+offs)/self.table_height), ipadx = int(self.default_size/2))
            self.schedule_labels[0]["fg"] = "dark green"
            self.schedule_table.grid(row=3,column=1)

            #game announcement
            tk.Label(self.root, text=lang.GAME_ANNOUNCE_TITLE, font=self.big_bold_font, bg="#EDEEF3").grid(row=2,column=2, pady=self.default_size)
            self.game_table = tk.Frame(self.root, bg="#EDEEF3")
            self.game_labels = []
            self.mmr_labels = []
            self.court_names = self.in_court_names()
            cmax = max(self.tur.c13, self.tur.c2)
            h1 = max(int(cmax/2),1)
            #h2 = cmax-h1
            col = 0
            for ci in range(max(self.tur.c13, self.tur.c2)):
                if ci == h1 and not cmax < int(self.table_height/3)+1:   #if court list would be higher than table to the left, split in two columns
                    col = 1
                tk.Label(self.game_table, text=self.court_names[ci], font=self.bold_font, bg="#EDEEF3").grid(row=3*(ci-h1*col), column=col, ipadx = int(self.default_size/2))
                self.game_labels.append(tk.Label(self.game_table, text="", bg="#EDEEF3"))
                self.game_labels[ci].grid(row=3*(ci-h1*col)+1, column=col, ipadx = int(self.default_size/2))
                self.mmr_labels.append(tk.Label(self.game_table, text="", bg="#EDEEF3"))
                self.mmr_labels[ci].grid(row=3*(ci-h1*col)+2, column=col, ipadx = int(self.default_size/2))
            self.game_table.grid(row=3,column=2)

            #buttons
            buttonbox = tk.Frame(self.root, bg="#EDEEF3")
            self.wait_list = [False]*self.tur.p
            self.game_but = tk.Button(buttonbox, text=lang.NEXT_GAME_BUTTON, default=tk.ACTIVE, command=self.new_game, bg="#EDEEF3")
            self.game_but.pack(side=tk.LEFT, padx=int(self.default_size/2), pady=self.default_size)
            self.result_but = tk.Button(buttonbox, text=lang.ENTER_RESULT_BUTTON, command=self.enter_results, state=tk.DISABLED, bg="#EDEEF3")
            self.result_but.pack(side=tk.LEFT, padx=int(self.default_size/2), pady=self.default_size)
            self.sets = 2
            self.stats_but = tk.Button(buttonbox, text=lang.STATS_BUTTON, command=self.show_stats, bg="#EDEEF3")
            self.stats_but.pack(side=tk.LEFT, padx=int(self.default_size/2), pady=self.default_size)
            self.disp_mmr_var = tk.IntVar()
            self.disp_mmr_var.set(0)
            self.tur.display_mmr = 0
            minibox = tk.Frame(buttonbox, bg="#EDEEF3")
            tk.Checkbutton(minibox, text=lang.MMR_CHECKBUTTON, variable=self.disp_mmr_var, command=self.toggle_mmr_display, bg="#EDEEF3").pack(side=tk.LEFT, padx=int(self.default_size/2), pady=int(self.default_size/2))
            self.cogorg = Image.open("ims/cog.png")
            dim = self.dims_by_scale(0.002 * self.default_size)[1]
            imobj = self.cogorg.resize((dim, dim), Image.ANTIALIAS)
            self.cog = ImageTk.PhotoImage(imobj)
            self.settings_but = tk.Button(minibox, text="", image=self.cog, command=self.settings, bg="#EDEEF3")
            self.settings_but.pack(side=tk.LEFT, padx=int(self.default_size / 2), pady=int(self.default_size / 2))
            minibox.pack(side=tk.LEFT, padx=int(self.default_size/2), pady=int(self.default_size/2))
            buttonbox.grid(row=4, columnspan=3, padx=int(self.default_size/2), pady=self.default_size)

            #properties
            c_text = ""
            w_text = ""
            out = False   #false in the beginning because negating is the first we do in loop
            for i, gel in enumerate(self.tur.g_list):
                out = not out
                if gel == 0:
                    continue
                if not c_text == "":
                    c_text += ", "
                    w_text += ", "
                c_text += str(self.tur.c13) if out else str(self.tur.c2)
                w_text += str(self.tur.w13) if out else str(self.tur.w2)
            propbox = tk.Frame(self.root, bg="#EDEEF3")
            tk.Label(propbox, text=lang.PROP_PLAYERS.format(self.tur.p), bg="#EDEEF3").grid(row=0, column=0)
            tk.Label(propbox, text=lang.PROP_COURTS.format(c_text), bg="#EDEEF3").grid(row=0, column=1)
            tk.Label(propbox, text=lang.PROP_WAIT.format(w_text), bg="#EDEEF3").grid(row=0, column=2)
            tk.Label(propbox, text=lang.PROP_APPEARANCES.format(self.tur.appearances), bg="#EDEEF3").grid(row=0, column=3)
            tk.Label(propbox, text=lang.PROP_RIZEMODE.format(self.tur.players.name[0], self.tur.rizemode), bg="#EDEEF3").grid(row=0, column=4)
            self.message_label = tk.Label(propbox, text="", fg="red", font=self.bold_font, bg="#EDEEF3")
            self.message_label.grid(row=1, columnspan=5)
            propbox.grid(row=5, columnspan=3)

            if self.tur.state > 0:
                self.new_game(after_load=True)
            if self.tur.state > 1:
                self.enter_results(after_load=True)

            self.root.mainloop()


    def dims_by_scale(self, scale):
        if hasattr(scale, '__iter__'):
            return [int(el * sc) for el, sc in zip(self.screen_resolution,scale)]
        return [int(el * scale) for el in self.screen_resolution]

    def center_coords(self, window_dims):
        posX = int((self.screen_resolution[0] - window_dims[0]) / 2)
        posY = int((self.screen_resolution[1] - window_dims[1]) / 2)
        return [posX, posY]

    def in_game_count(self):
        self.game_count = tk.IntVar()
        self.game_count.set(0)
        while self.game_count.get() == 0:
            # self.root.withdraw()
            self.selector = GameNumberWindow(self.root, self, self.tur.goodlist, self.tur.waitlist, self.tur.playlist, self.tur.waitlist2, self.tur.playlist2, self.tur.waitlist3, self.tur.playlist3)
            # self.root.deiconify()
        return self.game_count.get()

    def in_players(self):
        def isfloat(x):
            try:
                a = float(x)
            except ValueError:
                return False
            else:
                return True

        filename = FILENAME_PLAYERS
        with open(filename) as f:
            filecontent = f.readlines()
        names = []
        init_mmr = []
        male_count = 1000
        for st in filecontent:
            spl = st.split()
            if len(spl) > 1 and isfloat(spl[-1]):
                init_mmr.append(float(spl[-1]))
                names.append(" ".join(spl[:-1]))
            elif '=' in spl[0]:  # Separator that contains '='. Female players follow after separator.
                male_count = len(names)
            else:
                init_mmr.append(0)
                names.append(" ".join(spl))
        female_count = max(0, len(names)-male_count)

        return names, init_mmr, female_count

    def in_court_names(self):
        filename = FILENAME_COURTS
        max_c = max(self.tur.c13, self.tur.c2)
        try:
            with open(filename) as f:
                filecontent = f.readlines()
            if len(filecontent) < max_c:
                raise Exception()
            cnames = []
            for nam in filecontent:    #remove newline and add colon if necessary
                nams = nam.rstrip()
                if not nams[-1] == ":":
                    nams += ":"
                cnames.append(nams)
        except:
            cnames = [lang.CENTER_COURT_NAME]
            for i in range(1, max_c):
                cnames.append(lang.COURT_NAMES.format(i))
        return cnames

    def toggle_wait(self, pl_id):
        if self.game_but["state"] == tk.DISABLED or self.tur.i == self.tur.g:
            return
        if self.pl_labels[pl_id]["fg"] == "red":
            self.pl_labels[pl_id]["fg"] = "black"
            self.wait_list[pl_id] = False
        else:
            self.pl_labels[pl_id]["fg"] = "red"
            self.wait_list[pl_id] = True
        wait_req = self.make_wait_request()
        changed, wait_request = self.tur.canwait(wait_req, return_changed=True)
        if changed:
            for pi in range(self.tur.p):
                if pi in wait_request:
                    self.pl_labels[pi]["fg"] = "red"
                    self.wait_list[pi] = True
                else:
                    self.pl_labels[pi]["fg"] = "black"
                    self.wait_list[pi] = False

    def make_wait_request(self):
        return [pi for pi in range(self.tur.p) if self.wait_list[pi]]

    def new_game(self, after_load=False):
        def mes_reset():
            self.message_label["text"] = ""
        game_return = 0
        if not after_load:
            game_return = self.tur.game(self.make_wait_request())
        if game_return == 1:
            self.message_label["text"] = lang.MESSAGE_PARTNER_MATRIX_REGULAR
            self.message_label.after(2000, mes_reset)
        elif game_return == 2:
            self.message_label["text"] = lang.MESSAGE_PARTNER_MATRIX_IRREGULAR
            self.message_label.after(2000, mes_reset)
        team_indices = self.tur.games[-1]
        names_sorted = self.tur.players.name[team_indices]
        if self.tur.display_mmr:
            mmr_sorted = self.tur.players.mmr[team_indices]
            mmr_mean = np.mean(mmr_sorted.astype(float), axis=1)
        for i in range(int(len(team_indices)/2)):
            for pi in range(self.tur.teamsize):
                self.pl_labels[team_indices[2*i][pi]]["fg"] = "dark green"
                self.pl_labels[team_indices[2 * i+1][pi]]["fg"] = "dark green"
            lbl1 = ""
            lbl2 = ""
            for pi in range(self.tur.teamsize):
                lbl1 += (names_sorted[2 * i][pi] + "/") if pi < self.tur.teamsize-1 else names_sorted[2 * i][pi]
                lbl2 += (names_sorted[2 * i + 1][pi] + "/") if pi < self.tur.teamsize - 1 else names_sorted[2 * i + 1][pi]
            self.game_labels[i]["text"] = lbl1 + " - " + lbl2
            if self.tur.display_mmr:
                self.mmr_labels[i]["text"] = "{:.1f}/{:.1f} (ø{:.2f}) - {:.1f}/{:.1f} (ø{:.2f})".format(mmr_sorted[2 * i][0], mmr_sorted[2 * i][1], mmr_mean[2 * i], mmr_sorted[2 * i + 1][0], mmr_sorted[2 * i + 1][1], mmr_mean[2 * i + 1])
            else:
                self.mmr_labels[i]["text"] = ""
        for ii in range(i+1,max(self.tur.c13,self.tur.c2)):   #continue loop here one existing labels for a court that is not used / not available at the moment, and delete text
            self.game_labels[ii]["text"] = ""
            self.mmr_labels[ii]["text"] = ""
        self.game_but["state"] = tk.DISABLED
        self.result_but["state"] = tk.NORMAL
        self.result_but["text"] = lang.ENTER_RESULT_BUTTON
        self.result_but.focus_set()
        for ii in range(self.tur.i-1):
            self.schedule_labels[ii]["fg"] = "red"
            self.schedule_labels[ii]["font"] = self.default_font
        self.schedule_labels[self.tur.i-1]["fg"] = "dark green"
        self.schedule_labels[self.tur.i - 1]["font"] = self.bold_font

    def enter_results(self, after_load=False):
        if not after_load:
            self.res_window = ResultsWindow(self.root, self, title=lang.RESULTS_TITLE.format(self.tur.i))
        res_list = self.tur.results[self.tur.i-1]
        if not len(res_list[0]) == 0:

            for ci in range(self.tur.c):
                score_text = ""
                for si in range(self.sets):
                    score_text += "   {} - {}   ".format(res_list[ci][si][0], res_list[ci][si][1])
                self.mmr_labels[ci]["text"] = score_text

            self.wait_list = self.wait_list = [False] * self.tur.p
            if self.tur.i < self.tur.g:
                for lab in self.pl_labels:
                    lab["fg"] = "black"
                    self.game_but["state"] = tk.NORMAL
                    self.game_but.focus_set()
            else:
                self.stats_but.focus_set()
                self.stats_but["text"] = lang.STATS_BUTTON_END
            self.result_but["state"] = tk.NORMAL
            self.result_but["text"] = lang.CORRECT_RESULT_BUTTON

    def show_stats(self):
        game_number = self.tur.i
        if self.tur.state < 2:
            #results not entered yet
            game_number -= 1
        if game_number < 1:
            tit = lang.STATS_TITLE_0
        else:
            tit = lang.STATS_TITLE.format(game_number)
        if game_number == self.tur.g:
            tit = lang.STATS_TITLE_END
        self.stats_window = StatsWindow(self.root, self, title=tit)
        pass

    def toggle_mmr_display(self):
        self.tur.display_mmr = self.disp_mmr_var.get()
        if self.tur.state < 2 and self.tur.i > 0:
            #results not entered yet AND at least one game was announced already
            team_indices = self.tur.games[-1]
            if self.tur.display_mmr:
                mmr_sorted = self.tur.players.mmr[team_indices]
                mmr_mean = np.mean(mmr_sorted.astype(float), axis=1)
                for i in range(len(team_indices) // 2):
                    self.mmr_labels[i]["text"] = "{:.1f}/{:.1f} (ø{:.2f}) - {:.1f}/{:.1f} (ø{:.2f})".format(mmr_sorted[2 * i][0], mmr_sorted[2 * i][1], mmr_mean[2 * i], mmr_sorted[2 * i + 1][0], mmr_sorted[2 * i + 1][1], mmr_mean[2 * i + 1])
            else:
                for i in range(len(team_indices) // 2):
                    self.mmr_labels[i]["text"] = ""
        pass

    def settings(self):
        self.settings_window = SettingsWindow(self.root, self, title=lang.SETTINGS_TITLE)

if __name__ == '__main__':
    GUI()