#!/usr/bin/env python3

import re, time, threading, traceback, webbrowser, os, configparser
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
from finitclient import FinitClient

config = configparser.ConfigParser()

# I "stole" this from StackOverflow
def utc2local(utc):
	epoch = time.mktime(utc.timetuple())
	offset = datetime.fromtimestamp(epoch) - datetime.utcfromtimestamp(epoch)
	return utc + offset

# This one is also from StackOverflow
def convert65536(s):
	#Converts a string with out-of-range characters in it into a string with codes in it.
	l=list(s);
	i=0;
	while i<len(l):
		o=ord(l[i]);
		if o>65535:
			l[i]="{"+str(o)+"ū}";
		i+=1;
	return "".join(l);
def parse65536(match):
	#This is a regular expression method used for substitutions in convert65536back()
	text=int(match.group()[1:-2]);
	if text>65535:
		return chr(text);
	else:
		return "ᗍ"+str(text)+"ūᗍ";
def convert65536back(s):
	#Converts a string with codes in it into a string with out-of-range characters in it
	while re.search(r"{\d\d\d\d\d+ū}", s)!=None:
		s=re.sub(r"{\d\d\d\d\d+ū}", parse65536, s);
	s=re.sub(r"ᗍ(\d\d\d\d\d+)ūᗍ", r"{\1ū}", s);
	return s;

def local2utc(local):
	return datetime.utcfromtimestamp(time.mktime(local.timetuple()))

class FinitPyLogin(tk.Frame):
	def __init__(self, master=None, on_login=None):
		tk.Frame.__init__(self, master)
		self.on_login = on_login
		self.grid(sticky=tk.N+tk.S+tk.E+tk.W)
		self.create_widgets()
	def create_widgets(self):
		top = self.winfo_toplevel()
		top.rowconfigure(0, weight=1)
		top.columnconfigure(0, weight=1)
		top.config(borderwidth=10)
		top.config(background=config['COLOR']['bg'])
		
		self.columnconfigure(1, weight=1)
		self.config(background=config['COLOR']['bg'])
		
		self.user_lbl = tk.Label(self, text="Email")
		self.user_lbl.grid(column=0, row=0, sticky=tk.W+tk.E)
		self.user_lbl.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		self.user = tk.Entry(self, width=35)
		self.user_var = tk.StringVar()
		self.user["textvariable"] = self.user_var
		self.user.grid(column=1, row=0, columnspan=2, sticky=tk.W+tk.E)
		self.user.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		self.user_var.set(config['MAIN']['email'])
		
		self.pwd_lbl = tk.Label(self, text="Password")
		self.pwd_lbl.grid(column=0, row=1)
		self.pwd_lbl.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		self.pwd = tk.Entry(self, show="*")
		self.pwd_var = tk.StringVar()
		self.pwd["textvariable"] = self.pwd_var
		self.pwd.grid(column=1, row=1, columnspan=2, sticky=tk.W+tk.E)
		self.pwd.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		self.err_msg = tk.Label(self)
		self.err_msg.grid(column=0, row=2, columnspan=3)
		self.err_msg.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		self.config_btn = tk.Button(self, text="Configure", command=ConfigWindow)
		self.config_btn.grid(column=0, row=3, sticky=tk.W)
		self.config_btn.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		self.login = tk.Button(self, text="Sign in", command=self.sign_in)
		self.login.grid(column=1, row=3, sticky=tk.E)
		self.login.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		self.QUIT = tk.Button(self, text="Quit", command=self.master.destroy)
		self.QUIT.grid(column=2, row=3, sticky=tk.W+tk.E)
		self.QUIT.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
	def sign_in(self):
		global disp
		disp = config['MAIN']['displacement']
		self.set_error("")
		if self.on_login is not None:
			config['MAIN']['email'] = self.user_var.get()
			with open('config.ini', 'w') as configfile:
				config.write(configfile)
			self.on_login(self.user_var.get(), self.pwd_var.get())
	def set_error(self, message):
		self.err_msg["text"] = message

class ConfigWindow(tk.Frame):
	def __init__(self, master=None):
		tk.Frame.__init__(self, master)
		self.create_widgets()
	def create_widgets(self):
		self.wind = tk.Toplevel(self)
		self.wind.wm_title('FinitPy Config')
		top = self.wind.winfo_toplevel()
		top.columnconfigure(0, weight=1)
		top.config(borderwidth=10)
		top.config(background=config['COLOR']['bg'])
		self.config(background=config['COLOR']['bg'])
		
		disp_lbl = tk.Label(self.wind, text="Username Indent")
		disp_lbl.grid(column=1, row=0, sticky=tk.W)
		disp_lbl.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		disp_box = tk.Entry(self.wind)
		self.disp_var = tk.StringVar()
		disp_box["textvariable"] = self.disp_var
		disp_box.config(width=10,)
		disp_box.grid(column=0, row=0, sticky=tk.E+tk.W)
		disp_box.insert(tk.END, config['MAIN']['displacement'])
		disp_box.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])

		user_admin_lbl = tk.Label(self.wind, text="Admin Color")
		user_admin_lbl.grid(column=1, row=1, sticky=tk.W)
		user_admin_lbl.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		disp_box = tk.Entry(self.wind)
		self.admin_color_var = tk.StringVar()
		disp_box["textvariable"] = self.admin_color_var
		disp_box.config(width=10,)
		disp_box.grid(column=0, row=1, sticky=tk.E+tk.W)
		disp_box.insert(tk.END, config['COLOR']['admin'])
		disp_box.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		user_mod_lbl = tk.Label(self.wind, text="Mod Color")
		user_mod_lbl.grid(column=1, row=2, sticky=tk.W)
		user_mod_lbl.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		disp_box = tk.Entry(self.wind)
		self.mod_color_var = tk.StringVar()
		disp_box["textvariable"] = self.mod_color_var
		disp_box.config(width=10,)
		disp_box.grid(column=0, row=2, sticky=tk.E+tk.W)
		disp_box.insert(tk.END, config['COLOR']['mod'])
		disp_box.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		user_op_lbl = tk.Label(self.wind, text="Your Color")
		user_op_lbl.grid(column=1, row=3, sticky=tk.W)
		user_op_lbl.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		disp_box = tk.Entry(self.wind)
		self.op_color_var = tk.StringVar()
		disp_box["textvariable"] = self.op_color_var
		disp_box.config(width=10,)
		disp_box.grid(column=0, row=3, sticky=tk.E+tk.W)
		disp_box.insert(tk.END, config['COLOR']['op'])
		disp_box.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		user_std_lbl = tk.Label(self.wind, text="User Color")
		user_std_lbl.grid(column=1, row=4, sticky=tk.W)
		user_std_lbl.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		disp_box = tk.Entry(self.wind)
		self.std_color_var = tk.StringVar()
		disp_box["textvariable"] = self.std_color_var
		disp_box.config(width=10,)
		disp_box.grid(column=0, row=4, sticky=tk.E+tk.W)
		disp_box.insert(tk.END, config['COLOR']['std'])
		disp_box.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		user_fg_lbl = tk.Label(self.wind, text="Text Color")
		user_fg_lbl.grid(column=1, row=5, sticky=tk.W)
		user_fg_lbl.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		disp_box = tk.Entry(self.wind)
		self.fg_color_var = tk.StringVar()
		disp_box["textvariable"] = self.fg_color_var
		disp_box.config(width=10,)
		disp_box.grid(column=0, row=5, sticky=tk.E+tk.W)
		disp_box.insert(tk.END, config['COLOR']['fg'])
		disp_box.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		user_bg_lbl = tk.Label(self.wind, text="Background Color")
		user_bg_lbl.grid(column=1, row=6, sticky=tk.W)
		user_bg_lbl.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		disp_box = tk.Entry(self.wind)
		self.bg_color_var = tk.StringVar()
		disp_box["textvariable"] = self.bg_color_var
		disp_box.config(width=10,)
		disp_box.grid(column=0, row=6, sticky=tk.E+tk.W)
		disp_box.insert(tk.END, config['COLOR']['bg'])
		disp_box.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		self.user_in_title = tk.IntVar()
		disp_box = tk.Checkbutton(self.wind, text="Display username in title",
			variable=self.user_in_title, foreground=config['COLOR']['fg'],
			background=config['COLOR']['bg'])
		disp_box.grid(column=0, row=7, columnspan=2, sticky=tk.E+tk.W)
		self.user_in_title.set(config['MAIN']['username in title'] == "True")
		
		
		save = tk.Button(self.wind, text="Save", command=self.save)
		save.grid(column=0, row=8, sticky=tk.W)
		save.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
	def save(self):
		config['MAIN']['displacement'] = self.disp_var.get()
		config['MAIN']['username in title'] = str(self.user_in_title.get() == 1)
		config['COLOR']['admin'] = self.admin_color_var.get()
		config['COLOR']['mod'] = self.mod_color_var.get()
		config['COLOR']['op'] = self.op_color_var.get()
		config['COLOR']['fg'] = self.fg_color_var.get()
		config['COLOR']['bg'] = self.bg_color_var.get()
		config['COLOR']['std'] = self.std_color_var.get()
		with open('config.ini', 'w') as configfile:
			config.write(configfile)
		self.wind.destroy()

class FiniyPyMain(tk.Frame):
	def __init__(self, master=None, conn=None):
		tk.Frame.__init__(self, master)
		self.conn = conn
		self.conn.on_message = self.on_message
		self.rooms = {}
		self.active_channel = ""
		self.new_msg_count = 0
		self.new_pm = False
		self.master.protocol("WM_DELETE_WINDOW", self.before_close)
		self.grid(sticky=tk.N+tk.S+tk.E+tk.W)
		self.create_widgets()
		self.get_notifications()
		self.links = {}
	def create_widgets(self):
		top = self.winfo_toplevel()
		top.rowconfigure(0, weight=1)
		top.columnconfigure(0, weight=1)
		top.config(borderwidth=10)
		top.config(background=config['COLOR']['bg'])
		
		self.rowconfigure(3, weight=1)
		self.columnconfigure(0, weight=1)
		self.columnconfigure(1, weight=2)
		self.columnconfigure(2, weight=1)
		self.columnconfigure(3, weight=1)
		self.config(background=config['COLOR']['bg'])
		
		# user information
		self.user_info = tk.Label(self)
		self.user_info_var = tk.StringVar()
		self.user_info["textvariable"] = self.user_info_var
		self.user_info_var.set("@"+self.conn.user_data["user"]["username"])
		self.user_info.grid(column=0, row=1, columnspan=4)
		self.user_info.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		# channel list
		self.join_lbl = tk.Label(self, text="Join a Chat")
		self.join_lbl.grid(column=0, row=1)
		self.join_lbl.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		self.join = tk.Entry(self)
		self.join_var = tk.StringVar()
		self.join["textvariable"] = self.join_var
		self.join.bind("<Key-Return>", self.join_room)
		self.join.grid(column=0, row=2, sticky=tk.E+tk.W)
		self.join.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		self.channel_list = tk.Listbox(self)
		self.channel_list.grid(column=0, row=3, rowspan=2, sticky=tk.N+tk.S+tk.E+tk.W)
		self.channel_list.configure(exportselection=False)
		self.channel_list.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		self.leave = tk.Button(self, text="Leave", command=self.leave_room)
		self.leave.grid(column=0, row=5, sticky=tk.E+tk.W)
		self.leave.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		# chat area
		self.message_area = tk.Text(self, wrap='word', height=28, width=80)
		self.message_area.grid(column=1, row=3, rowspan=2, columnspan=2, sticky=tk.N+tk.S+tk.E+tk.W)
		self.message_area.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		self.message_area.tag_configure('normal', font=('Courier', 10,))
		self.message_area.tag_configure('italics', font=('Courier', 10, 'italic',))
		self.message_area.tag_configure('bold', font=('Courier', 10, 'bold',))
		self.message_area.tag_configure('bold-italics', font=('Courier', 10, 'bold italic',))
		self.message_area.tag_configure('user', foreground=config['COLOR']['std'])
		self.message_area.tag_configure('admin', foreground=config['COLOR']['admin'])
		self.message_area.tag_configure('mod', foreground=config['COLOR']['mod'])
		self.message_area.tag_configure('op', foreground=config['COLOR']['op'])
		for i in ["admin","mod","op", "user"]:
			self.message_area.tag_bind(i, "<Button-1>", self._click_user)
			self.message_area.tag_bind(i, "<Enter>", self._enter_link)
			self.message_area.tag_bind(i, "<Leave>", self._leave_link)
		self.message_area.tag_config("hyper", underline=1)
		self.message_area.tag_bind("hyper", "<Enter>", self._enter_link)
		self.message_area.tag_bind("hyper", "<Leave>", self._leave_link)
		self.message_area.tag_bind("hyper", "<Button-1>", self._click_link)
		self.message_area.tag_config("spoiler", font=('Courier', 10,), foreground=config['COLOR']['fg'], background=config['COLOR']['fg'])
		self.message_area.tag_config("spoiler-visible", font=('Courier', 10,), foreground=config['COLOR']['bg'], background=config['COLOR']['fg'])
		self.message_area.tag_bind("spoiler", "<Enter>", self._enter_spoiler)
		self.message_area.tag_bind("spoiler-visible", "<Leave>", self._leave_spoiler)
		self.message_area.config(state=tk.DISABLED)
		
		# user list
		self.users_lbl = tk.Label(self, text="Users")
		self.users_lbl.grid(column=3, row=1)
		self.users_lbl.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		self.user_list = tk.Listbox(self)
		self.user_list.grid(column=3, row=3, sticky=tk.N+tk.S+tk.E+tk.W)
		self.user_list.configure(exportselection=False)
		self.user_list.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		# message sending
		self.message = tk.Entry(self)
		self.message_var = tk.StringVar()
		self.message["textvariable"] = self.message_var
		self.message.bind("<Key-Return>", self.send_message)
		self.message.grid(column=1, row=5, sticky=tk.N+tk.S+tk.E+tk.W)
		self.message.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		self.send = tk.Button(self, text="Send", command=self.send_message)
		self.send.grid(column=2, row=5, sticky=tk.E+tk.W)
		self.send.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		# user options
		self.whois = tk.Button(self, text="Info", command=self.get_whois)
		self.whois.grid(column=3, row=4, sticky=tk.E+tk.W+tk.S)
		self.whois.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		self.mention = tk.Button(self, text="Mention", command=self.mention_user)
		self.mention.grid(column=3, row=5, sticky=tk.E+tk.W)
		self.mention.config(foreground=config['COLOR']['fg'], background=config['COLOR']['bg'])
		
		self.after(0, self.poll)
	
	def get_notifications(self):
		notif = self.conn.get_all_notifications()
		for n in notif:
			if n["event"] == 10: # PM
				name = "@" + n["source"]["username"]
				self.conn.read_notification(n["id"])
				if name in self.rooms:
					self.rooms[name]["unread"] += 1
					self.update_channel_list(name)
					continue
				id1, id2 = int(n["source_id"]), int(n["user_id"])
				if id2 < id1:
					id1, id2 = id2, id1
				uid = self.conn.get_user_id(n["source"]["username"])
				self.channel_list.insert(tk.END, name + " (1)")
				self.rooms[name] = {"channel_name":"prv_{}_{}".format(id1,id2), "id":uid,
					"messages":[], "members":[], "list_name":name+" (1)", "loaded":False,
					"unread": 1}
				self.new_pm = True
		self.update_title()
	def _enter_link(self, event):
		self.message_area.config(cursor="hand2")
	def _leave_link(self, event):
		self.message_area.config(cursor="xterm")
	def _click_user(self, event):
		tags = event.widget.tag_names("current")
		for t in tags:
			if t.startswith("user-"):
				self.message.insert(tk.INSERT, t[5:]+" ")
				self.message.focus_set()
				return
	def _click_link(self, event):
		w = event.widget
		x, y = event.x, event.y
		tags = w.tag_names("@%d,%d" % (x, y))
		for t in tags:
			if t.startswith("link-"):
				webbrowser.open(t[5:])
				return
			elif t.startswith("channel-"):
				chn = t[8:].lower()
				if chn not in self.rooms:
					self.finit_join(chn)
				else:
					idx = -1
					for i in range(self.channel_list.size()):
						if self.channel_list.get(i) == chn:
							idx = i
							break
					if idx < 0: return
					self.channel_list.selection_clear(0, tk.END)
					self.channel_list.selection_set(idx)
					self.channel_list.activate(idx)
				return
	def _enter_spoiler(self, event):
		w = event.widget
		x, y = event.x, event.y
		line = w.index("current").split(".")[0]
		text = w.get(line+".0", line+".end")
		start = str(re.search("\[spoiler\]", text).end()+1)
		self.message_area.tag_add("spoiler-visible", line+"."+start, line+".end")
		self.message_area.tag_remove("spoiler", line+"."+start, line+".end")
	def _leave_spoiler(self, event):
		w = event.widget
		x, y = event.x, event.y
		line = w.index("current").split(".")[0]
		text = w.get(line+".0", line+".end")
		start = str(re.search("\[spoiler\]", text).end()+1)
		self.message_area.tag_add("spoiler", line+"."+start, line+".end")
		self.message_area.tag_remove("spoiler-visible", line+"."+start, line+".end")
	def poll(self):
		if self.channel_list.size() == 0:
			self.active_channel = ""
			self.message_area.config(state=tk.NORMAL)
			self.message_area.delete('1.0', tk.END)
			self.message_area.config(state=tk.DISABLED)
			self.user_list.delete(0, tk.END)
			self.refresh_lists()
		else:
			sel = self.get_channel_from_list_name(self.channel_list.get(tk.ACTIVE))
			if sel != self.active_channel:
				self.active_channel = sel
				self.rooms[sel]["unread"] = 0
				self.update_channel_list(sel)
				if len(sel) and not self.rooms[sel]["loaded"]:
					self.finit_join(sel)
				else:
					self.refresh_lists()
		try:
			if self.focus_displayof() is not None and (self.new_msg_count > 0 or self.new_pm):
				self.new_msg_count = 0
				self.new_pm = False
				self.update_title()
		except:
			pass
		self.after(250, self.poll)
	def mention_user(self):
		if self.user_list.size() == 0: return
		self.message.insert(tk.INSERT, "@{} ".format(
			re.sub("^\\[\\w+\\]\\s+", "", self.user_list.get(tk.ACTIVE))
		))
		self.message.focus_set()
	def get_whois(self):
		if self.user_list.size() == 0: return
		try:
			data = self.conn.get_user_info(self.user_list.get(tk.ACTIVE))
			uid = data["data"]["id"]
			username = data["data"]["username"]
			account_type = "a guest" if data["data"]["is_temp"] == 1 else "registered"
			#name = data["data"]["full_name"]
			#birthday = data["data"]["dob"]
			#gender = data["data"]["gender"]
			site = data["data"]["website"]
			bio = data["data"]["bio"]
			if data["data"]["id"] == 1:
				mod = "everything, he's the admin"
			elif len(data["data"]["mod_powers"]) == 0:
				mod = "nothing"
			else:
				mod = ", ".join(["#"+re.match("^pub_(.*)",i).group(1) for i in data["data"]["mod_powers"]])
			#messagebox.showinfo("Info - {}".format(username), "Name: {}\nBirthday: {}\nGender: {}\nWebsite: {}\nBio: {}\nModerates: {}".format(name, birthday, gender, site, bio, mod))
			messagebox.showinfo("Info - {}".format(username), "User ID: {}\nThe account is {}\nWebsite: {}\nBio: {}\nModerates: {}".format(uid, account_type, site, bio, mod))
		except Exception:
			traceback.print_exc()
	def join_room(self, event):
		self.finit_join(self.conn.get_normalized_channel_name(self.join_var.get()))
	def leave_room(self):
		if len(self.active_channel):
			self.conn.leave(self.active_channel)
	def send_message(self, event=None):
		sel = self.active_channel
		msg = self.message_var.get().strip()[:255]
		self.message_var.set("")
		if len(sel) and len(msg):
			r = self.channel_list.get(tk.ACTIVE)
			self.conn.message(r, msg)
			time = datetime.now()
			self.chatlog_add_message(r, local2utc(time).isoformat(),
				self.conn.get_current_user()[1], msg)
			time = ("00"+str(time.hour))[-2:] + ":" + ("00"+str(time.minute))[-2:]
			self.rooms[r]["messages"].append({
				"created_at": time,
				"sender": {"id": self.conn.user_data["user"]["id"],
					"username": self.conn.user_data["user"]["username"]},
				"body": msg
			})
			self.message_area.see(tk.END)
			if len(self.rooms[r]["messages"]) > 100:
				self.refresh_messages(True)
			else:
				self.refresh_messages()
	def before_close(self):
		for r in self.rooms:
			self.conn.leave(r)
		self.conn.wait_for_logout()
		self.master.destroy()
	def finit_join(self, room):
		name = self.conn.get_normalized_channel_name(room)
		if name in self.rooms and self.rooms[name]["loaded"]:
			idx = -1
			for i in range(self.channel_list.size()):
				if self.channel_list.get(i) == self.rooms[name]["list_name"]:
					idx = i
					break
			if idx < 0: return
			self.join_var.set("")
			self.channel_list.selection_clear(0, tk.END)
			self.channel_list.selection_set(idx)
			self.channel_list.activate(idx)
			self.refresh_lists()
			return
		uid = self.conn.get_user_id(name)
		if name[0] == "@":
			if uid is None: return
			name = "@"+self.conn.user_name_cache[uid]
		messages = self.conn.get_messages(name)
		if messages is not None and "data" in messages:
			messages = messages["data"]
		else:
			messages = []
		messages.reverse()
		if name in self.rooms:
			self.rooms[name]["messages"] = messages
		else:
			self.rooms[name] = {"channel_name":name, "id":uid,
				"messages":messages, "list_name":name, "loaded":True,
				"unread": 0}
		self.conn.join(name)
	def on_message(self, conn, data):
		# looks for API events
		try:
			if data["event"] == "subscribed":
				name = self.conn.get_channel_name(data["channel"])
				time = local2utc(datetime.now()).isoformat()
				self.chatlog_add_message(name, time, self.conn.user_data["user"]["username"], None, "subscribed")
				if name in self.rooms and not self.rooms[name]["loaded"]:
					idx = -1
					for i in range(self.channel_list.size()):
						if self.channel_list.get(i) == self.rooms[name]["list_name"]:
							idx = i
							break
					if idx < 0: return
					self.rooms[name]["list_name"] = name
					self.channel_list.delete(idx)
					self.channel_list.insert(idx, name)
					self.channel_list.selection_clear(0, tk.END)
					self.channel_list.selection_set(idx)
					self.channel_list.activate(idx)
					self.refresh_lists()
				else:
					self.join_var.set("")
					self.channel_list.insert(tk.END, name)
					self.channel_list.selection_clear(0, tk.END)
					self.channel_list.selection_set(tk.END)
					self.channel_list.activate(self.channel_list.size()-1)
				self.rooms[name]["channel_name"] = data["channel"]
				self.rooms[name]["members"] = data["members"]
				self.rooms[name]["loaded"] = True
			elif data["event"] == "subscription-failure":
				name = self.conn.get_channel_name(data["channel"])
				if name in self.rooms:
					del self.rooms[name]
				if data["reason"] == "invalid-input":
					self.join_var.set("Invalid name")
				elif data["reason"] == "banned":
					self.join_var.set("You are banned from "+self.conn.get_channel_name(data["channel"]))
				else:
					self.join_var.set("Failed to subscribe")
			elif data["event"] == "kicked-from-channel":
				time = local2utc(datetime.now()).isoformat()
				self.chatlog_add_message(data["channel"], time, None, None, "kicked")
				self.conn.leave(self.conn.get_channel_name(data["channel"]))
			elif data["event"] == "banned-from-channel":
				time = local2utc(datetime.now()).isoformat()
				self.chatlog_add_message(data["channel"], time, None, None, "banned")
				self.conn.leave(self.conn.get_channel_name(data["channel"]))
			elif data["event"] == "unsubscribed":
				f = None
				for k in self.rooms:
					if self.rooms[k]["channel_name"] == data["channel"]:
						f = k
						break
				time = local2utc(datetime.now()).isoformat()
				self.chatlog_add_message(data["channel"], time, self.conn.user_data["user"]["username"], None, "unsubscribed")
				if f is None: return
				for i in range(self.channel_list.size()):
					if self.get_channel_from_list_name(self.channel_list.get(i)) == k:
						self.channel_list.delete(i)
						break
				del self.rooms[k]
				if self.channel_list.size() > 0:
					self.channel_list.selection_clear(0, tk.END)
					self.channel_list.selection_set(0)
			elif data["event"] == "client-message":
				channel = None
				for c in self.rooms:
					if self.rooms[c]["channel_name"] == data["channel"]:
						channel = c
						break
				if channel is None: return
				self.new_msg_count += 1
				self.update_title()
				data = data["data"].copy()
				time = datetime.now()
				self.chatlog_add_message(channel, local2utc(time).isoformat(),
					data["sender"]["username"], data["body"])
				data["created_at"] = ("00"+str(time.hour))[-2:] + ":" + ("00"+str(time.minute))[-2:]
				self.rooms[channel]["messages"].append(data)
				if len(self.rooms[channel]["messages"]) > 100:
					if channel == self.active_channel:
						self.rooms[channel]["unread"] = 0
						self.update_channel_list(channel)
						self.refresh_messages(True)
					else:
						self.rooms[channel]["messages"] = self.rooms[channel]["messages"][-100:]
						self.rooms[channel]["unread"] += 1
						self.update_channel_list(channel)
				elif channel == self.active_channel:
					self.rooms[channel]["unread"] = 0
					self.update_channel_list(channel)
					self.refresh_messages(True, less_than_100=True)
				else:
					self.rooms[channel]["unread"] += 1
					self.update_channel_list(channel)
			elif data["event"] == 10: # This is a PM
				self.conn.read_notification(data["id"])
				name = "@" + data["source"]["username"]
				if name in self.rooms:
					self.rooms[name]["unread"] += 1
					self.update_channel_list(name)
					self.new_pm = True
					self.update_title()
					return
				id1, id2 = int(data["source_id"]), int(data["user_id"])
				if id2 < id1:
					id1, id2 = id2, id1
				uid = self.conn.get_user_id(data["source"]["username"])
				self.channel_list.insert(tk.END, name + " (1)")
				self.rooms[name] = {"channel_name":"prv_{}_{}".format(id1,id2), "id":uid,
					"messages":[], "members":[], "list_name":name+" (1)", "loaded":False,
					"unread": 1}
				self.new_pm = True
				self.update_title()
			elif data["event"] == "member-added":
				time = local2utc(datetime.now()).isoformat()
				self.chatlog_add_message(data["channel"], time, data["data"]["sender"]["username"], None, "connected")
				channel = self.conn.get_channel_name(data["channel"])
				self.rooms[channel]["members"].append(data["data"])
				if channel == self.active_channel:
					self.refresh_members()
			elif data["event"] == "member-removed":
				time = local2utc(datetime.now()).isoformat()
				self.chatlog_add_message(data["channel"], time, data["data"]["sender"]["username"], None, "disconnected")
				channel = self.conn.get_channel_name(data["channel"])
				u = None
				for m in self.rooms[channel]["members"]:
					if int(m["id"]) == int(data["data"]["id"]):
						u = m
						break
				if u is None: return
				self.rooms[channel]["members"].remove(u)
				if channel == self.active_channel:
					self.refresh_members()
			elif data["event"] not in ["connected", "client-connected", "client-disconnected"]:
				print(data)
		except Exception:
			traceback.print_exc()
	def update_channel_list(self, name):
		idx = -1
		for i in range(self.channel_list.size()):
			if self.channel_list.get(i) == self.rooms[name]["list_name"]:
				idx = i
				break
		if idx < 0: return
		if self.active_channel == name or self.rooms[name]["unread"] == 0:
			self.rooms[name]["list_name"] = name
		elif self.rooms[name]["unread"] > 0:
			self.rooms[name]["list_name"] = "{} ({})".format(name,
				self.rooms[name]["unread"])
		self.channel_list.delete(idx)
		self.channel_list.insert(idx, self.rooms[name]["list_name"])
		if self.active_channel == name:
			self.channel_list.selection_clear(0, tk.END)
			self.channel_list.selection_set(idx)
			self.channel_list.activate(idx)
	def update_title(self):
		try:
			if self.focus_displayof() is None:
				pm = "* " if self.new_pm else ""
				if config["MAIN"]["username in title"] == "True":
					user = self.conn.user_data["user"]["username"]
					if self.new_msg_count > 0:
						self.master.title("{}FinitPy - @{} ({})".format(pm, user, self.new_msg_count))
					else:
						self.master.title("{}FinitPy - @{}".format(pm, user))
				else:
					if self.new_msg_count > 0:
						self.master.title("{}FinitPy - ({})".format(pm, self.new_msg_count))
					else:
						self.master.title("{}FinitPy".format(pm))
			elif config["MAIN"]["username in title"] == "True":
				self.master.title("FinitPy - {}".format(self.conn.user_data["user"]["username"]))
			else:
				self.master.title("FinitPy")
		except:
			pass
	def refresh_lists(self):
		if len(self.active_channel) > 0:
			self.user_info_var.set("@"+self.conn.user_data["user"]["username"]+" - "+self.active_channel)
		else:
			self.user_info_var.set("@"+self.conn.user_data["user"]["username"])
		self.refresh_members()
		self.refresh_messages()
	def get_channel_from_list_name(self, lname):
		if len(lname) == 0: return ""
		for c in self.rooms:
			if self.rooms[c]["list_name"] == lname:
				return c
		return ""
	def refresh_members(self):
		r = self.active_channel
		if len(r) == 0: return
		self.rooms[r]["members"].sort(key=lambda u:(
			int(u["id"])!=1,
			not any([r.upper() == self.conn.get_channel_name(s).upper() for s in u["mod_powers"]]),
			u["username"] != self.conn.user_data["user"]["username"],
			u["username"].upper()
		))
		prev_active_user = self.user_list.get(tk.ACTIVE)
		active_index = -1
		self.user_list.delete(0, tk.END)
		prev_name = ""
		for i,u in enumerate(self.rooms[r]["members"]):
			username = u["username"]
			color = None
			if int(u["id"]) == 1:
				color = config['COLOR']['admin']
			else:
				for m in u["mod_powers"]:
					if self.conn.get_channel_name(m).upper() == r.upper():
						color = config['COLOR']['mod']
						break
			if color is None and username == self.conn.user_data["user"]["username"]:
				color = config['COLOR']['op']
			if prev_name != username:
				self.user_list.insert(tk.END, username)
				if color: self.user_list.itemconfig(tk.END, foreground=color)
			if username == prev_active_user:
				active_index = i
			prev_name = username
		if active_index >= 0:
			self.user_list.activate(active_index)
	def _generate_links(self, body):
		ps = (
			("(?<!\w)#[a-z0-9]+", "CHANNEL", re.I),
			("(?<![\w/])/?([rv]/[a-z0-9]+|c/\\d+|vp/\\d+)", "SHORT", re.I),
			("(?<!\w)(https?):((//)|(\\\\))+([\w\d:#@%/;$()~_?\+-=\\\.&](#!)?)*", "LINK", re.I),
			("(?<!\w)([\w][\w\d-]*\.)+[a-z]{2,}(/([\w\d:#@%/;$()~_?\+-=\\\.&](#!)?)*)?", "NPLINK", re.I),
			("(?<!\w)hunter2(\W|$)", "HUNTER2", 0)
		)
		while len(body):
			l = (float("inf"), None, None)
			for p in ps:
				s = re.search(p[0], body, p[2])
				if s and s.start() < l[0]:
					l = (s.start(), s.end(), p[1])
			if l[0] == float("inf"):
				self.message_area.insert(tk.END, body)
				break
			if l[0] > 0:
				self.message_area.insert(tk.END, body[:l[0]])
			link = body[l[0]:l[1]]
			if l[2] == "LINK":
				self.message_area.insert(tk.END, link, ("hyper", "link-"+link))
			elif l[2] == "CHANNEL":
				self.message_area.insert(tk.END, link, ("hyper", "channel-"+link))
			elif l[2] == "SHORT":
				text = link
				ll = link.lower()
				if link[0] != "/": link = "/" + link
				if ll[:2] == "/r": link = "https://www.reddit.com" + link
				elif ll[:2] == "/c" or ll[:3] == "/vp":
					link = "https://diluted.hoppy.haus" + link
				elif ll[:2] == "/v": link = "https://voat.co" + link
				self.message_area.insert(tk.END, text, ("hyper", "link-"+link))
			elif l[2] == "NPLINK":
				self.message_area.insert(tk.END, link, ("hyper", "link-http://"+link))
			elif l[2] == "HUNTER2":
				l = (l[0], l[0]+7)
				self.message_area.insert(tk.END, "*******")
			body = body[l[1]:]
	def _add_message(self, m):
		if m["sender"] is None:
			m["sender"] = {
				"id": 0,
				"username": "Guest",
				"mod_powers": []
			}
		if len(m["created_at"]) <= 5:
			d = m["created_at"]
		else:
			d = utc2local(datetime.strptime(m["created_at"], "%Y-%m-%d %H:%M:%S"))
			d = ("00"+str(d.hour))[-2:] + ":" + ("00"+str(d.minute))[-2:]
		user_type = "user"
		if m["sender"]["id"] == 1:
			user_type = "admin"
		elif m["sender"]["username"] == self.conn.user_data["user"]["username"]:
			user_type = "op"
		else:
			for p in m["sender"]["mod_powers"]:
				if self.conn.get_channel_name(p).upper() == self.active_channel.upper():
					user_type = "mod"
					break
		displacement = int(disp) - len(m["sender"]["username"])
		displaced = ' ' * displacement
		body = convert65536(m["body"])
		if re.match("^/me\s", body, re.I):
			user_style = (user_type, "bold-italics", "user-@"+m["sender"]["username"])
			line = str(int(self.message_area.index("end").split(".")[0])-1)
			self.message_area.insert(tk.END, displaced+"{} * ".format(d))
			self.message_area.insert(tk.END, "@"+m["sender"]["username"], user_style)
			self.message_area.insert(tk.END, " ", "bold-italics")
			me_start = line+"."+str(len(displaced+"{} * @"+m["sender"]["username"]+" "))
			self._generate_links(body[3:].lstrip())
			self.message_area.insert(tk.END, "\n")
			self.message_area.tag_add("italics", me_start, line+".end")
			self.message_area.tag_add("normal", line+".0", line+".end")
		elif re.match("^/spoiler\s", body, re.I):
			user_style = (user_type, "bold", "user-@"+m["sender"]["username"])
			line = str(int(self.message_area.index("end").split(".")[0])-1)
			self.message_area.insert(tk.END, d+" "+displaced)
			self.message_area.insert(tk.END, "@"+m["sender"]["username"]+":", user_style)
			self.message_area.insert(tk.END, " ", "bold")
			self.message_area.insert(tk.END, "[spoiler] ")
			spoiler_start = line+"."+str(len(d+" "+displaced+"@"+m["sender"]["username"]+": [spoiler] "))
			self._generate_links(body[9:].lstrip())
			self.message_area.insert(tk.END, "\n")
			self.message_area.tag_add("spoiler", spoiler_start, line+".end")
			self.message_area.tag_add("normal", line+".0", line+".end")
		else:
			user_style = (user_type, "bold", "user-@"+m["sender"]["username"])
			line = str(int(self.message_area.index("end").split(".")[0])-1)
			self.message_area.insert(tk.END, d+" "+displaced)
			self.message_area.insert(tk.END, "@"+m["sender"]["username"]+":", user_style)
			self.message_area.insert(tk.END, " ", "bold")
			self._generate_links(body)
			self.message_area.insert(tk.END, "\n")
			self.message_area.tag_add("normal", line+".0", line+".end")
	def refresh_messages(self, refresh=False, less_than_100=False):
		r = self.active_channel
		if len(r) == 0: return
		if refresh == True:
			scroll = False
			self.message_area.update_idletasks()
			if self.message_area.bbox(str(int(self.message_area.index("end").split(".")[0])-1)+".0"):
				scroll = True
			if less_than_100 == True:
				self.message_area.config(state=tk.NORMAL)
				self._add_message(self.rooms[r]["messages"][-1])
			else:
				discarded = []
				if len(self.rooms[r]["messages"]) > 100:
					discarded = self.rooms[r]["messages"][:-100]
					self.rooms[r]["messages"] = self.rooms[r]["messages"][-100:]
				lines_to_remove = 0
				for d in discarded:
					lines_to_remove += 1 + len(list(filter(lambda x:x=='\n', d["body"])))
				self.message_area.config(state=tk.NORMAL)
				if lines_to_remove > 0:
					self.message_area.delete('1.0', str(lines_to_remove+1)+'.0')
				for i in range(100-len(discarded),100):
					self._add_message(self.rooms[r]["messages"][i])
			if scroll:
				self.message_area.see(tk.END)
			self.message_area.config(state=tk.DISABLED)
		else:
			self.message_area.config(state=tk.NORMAL)
			self.message_area.delete('1.0', tk.END)
			for m in self.rooms[r]["messages"]:
				self._add_message(m)
			self.message_area.see(tk.END)
			self.message_area.config(state=tk.DISABLED)
	def chatlog_add_message(self, channel, timestamp, user, msg_text, event=None):
		try:
			channel = channel.replace("@","prv_{}_".format(self.conn.get_current_user()[1])).replace("#","pub_")
			path = os.path.join('logs', channel+'.txt')
			if os.path.isdir('logs') is False:
				os.mkdir('logs')
			if event in ("disconnected", "connected", "unsubscribed", "subscribed"):
				log = "{} @{} has {}\n".format(timestamp, user, event)
			elif event in ("kicked", "banned"):
				log = "{} You have been {}".format(timestamp, user, event)
			else:
				log = "{} @{}: {}\n".format(timestamp, user, msg_text)
			with open(path, 'a+') as logfile:
				logfile.write(log)
		except Exception:
			traceback.print_exc()
			
class FinitApp:
	def __init__(self):
		self.initconfig()
		self.client = FinitClient()
		self.root = tk.Tk()
		self.root.title("FinitPy - Sign in")
		self.app = FinitPyLogin(master=self.root, on_login=self.on_login)
		self.app.mainloop()
	def initconfig(self):
		def extend(a, b):
			for k in b:
				if k not in a:
					a[k] = b[k]
		default_options = {'displacement': 0, 'username in title': 'True', 'email': ''}
		default_colors = {'admin': 'red', 'mod': 'blue', 'op': 'lime green',
			'std': 'black', 'fg': 'black', 'bg': 'white'}
		if os.path.isfile('config.ini') is False:
			config['MAIN'] = default_options
			config['COLOR'] = default_colors
			with open('config.ini', 'w') as configfile:
				config.write(configfile)
		config.read('config.ini')
		if not 'MAIN' in config: config['MAIN'] = {}
		extend(config['MAIN'], default_options)
		if not 'COLOR' in config: config['COLOR'] = {}
		extend(config['COLOR'], default_colors)
		with open('config.ini', 'w') as configfile:
			config.write(configfile)
	def on_login(self, email, pwd):
		if self.client.login(email, pwd):
			self.root.destroy()
			self.root = tk.Tk()
			self.root.title("FinitPy")
			self.app = FiniyPyMain(master=self.root, conn=self.client)
			self.app.mainloop()
		else:
			self.app.set_error("Wrong credentials or network error")

if __name__ == "__main__":
	FinitApp()
