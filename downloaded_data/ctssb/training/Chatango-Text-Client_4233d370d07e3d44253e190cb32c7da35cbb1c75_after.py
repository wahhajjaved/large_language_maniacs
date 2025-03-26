import ch
import threading
import tkinter
import time
import webbrowser
from tkinter import *

class TestBot(ch.RoomManager):
  def onConnect(self, room):
    self.setNameColor("333333")
    self.setFontColor("FFFFFF")
    self.setFontFace("Latha")
    self.setFontSize(11)
    self.ListNum = 0
    listbox.insert(END, 'Connected to '+room.name+'\n')
    self.Ignored = []
    try: #Ignored file not 'mandatory' anymore.
      with open ('ignored.txt', 'r') as f: self.Ignored = f.read()
    except IOError:
      print ("Missing 'Ignored.txt' file")

  def onMessage(self, room, user, message):
    if user.name not in self.Ignored:
      self.ListNum += 1
      listbox.insert(END, user.name+'-'+time.strftime('%X')+'   '+message.body+'\n')
      listbox.itemconfig(self.ListNum,fg='#'+user.fontColor)
      listbox.yview_scroll(self.ListNum, 'p')
NICK = input("Your Account name: ")
PASS = input("Your Password: ")
ROOM = input("Room name: ")
TestBot = TestBot(NICK,PASS)
TestBot.joinRoom(ROOM)
TestBot_thread = threading.Thread(target=TestBot.main,)
TestBot_thread.setDaemon(True)
TestBot_thread.start()

class BotGUI(tkinter.Tk):

  def Select(event):
    if 'http' in '\n'.join([listbox.get(x) for x in listbox.curselection()]):
      for i in '\n'.join([listbox.get(x) for x in listbox.curselection()]).split():
        if 'http' in i:
          webbrowser.open(i)
          return #Return added so only uses one link in message

  def get(event):
    try:
      if '!bg' in text.get():  #Client background colour
        if text.get().split()[1].isdigit():
          listbox.config(bg='#'+str(text.get().split()[1]))
        else:
          listbox.config(bg=str(text.get().split()[1]))
      elif '!nc' in text.get():#Name colour
        TestBot.setNameColor(text.get().split()[1])
      elif '!bc' in text.get():#Body colour
        TestBot.setFontColor(text.get().split()[1])
      elif '!bs' in text.get(): #Body size
        TestBot.setFontSize(int(text.get().split()[1]))
      elif '!font' in text.get():#Font name
        TestBot.setFontFace(text.get().split()[1])
      elif '!ignore' in text.get():#(Possibly) not working.
        if text.get().split()[1] in TestBot.Ignored:
          TestBot.Ignored += text.get().split()[1]
        else:
          TestBot.Ignored = TestBot.Ignored.replace(text.get().split()[1],"")
      else:
        room = TestBot.getRoom(ROOM)
        room.message(text.get(), False)  
    except Exception as error: print (error)
    text.delete(0,20000) #Clears Textfield
  
  GUI = tkinter.Tk()
  GUI.title('Chat Client')
  GUI.geometry("360x660")
  GUI.minsize(100,100)
  global listbox,text
  text = Entry(GUI)
  text.bind('<Return>', get)
  listbox = Listbox(GUI)
  listbox.bind('<<ListboxSelect>>',Select)
  text.pack(fill=BOTH, side='bottom')
  listbox.config(bg='#484848', borderwidth=0, selectborderwidth=0)
  listbox.pack(side='right',fill=BOTH, expand=1)

gui_thread = threading.Thread(target=tkinter.mainloop(),)
gui_thread.setDaemon(True)
gui_thread.start()
