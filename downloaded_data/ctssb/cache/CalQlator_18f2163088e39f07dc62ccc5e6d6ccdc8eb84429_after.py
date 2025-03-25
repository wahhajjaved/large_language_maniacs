from __future__ import division
from gi.repository import Gtk
from gi.repository import Gdk
import sys
import math
import re

class pr2(object):
	
	# Quit the Calculator when window is closed 
	def on_window1_delete_event(self, *args):
		Gtk.main_quit(*args)
	
	# Helper function, called when any number is pressed
	def add_num(self, num):
		if self.res==1:
			self.add_fun(num)
		else:
			enditer = self.textbuffer.get_end_iter()
			self.textbuffer.insert(enditer, num)
			self.arr.append(num)
	
	# Helper function, called when any sign '+, -, *, -, ^' is pressed
	def add_sign(self, sign):
		tt = self.textbuffer
		if self.res==1:
			tt.set_text(''.join(self.arr).replace(' ','')+sign)
			self.arr.append(sign)
			self.res=0
			self.dot_flag=1
		else:
			enditer = self.textbuffer.get_end_iter()
			if len(self.arr)!=0:
				last_text = self.arr[-1]
				self.res=0
				self.dot_flag=1
				if sign=='-':
					if last_text=='-' or last_text=='+':
						tt.set_text(tt.get_text(tt.get_start_iter(), tt.get_end_iter(), True)[:-1] + sign)
						self.arr.pop()
						self.arr.append(sign)
					elif last_text=='*' or last_text=='/':
						text = self.arr.pop()
						self.arr.append(text+sign)
						tt.insert(enditer, sign)
					else:
						tt.insert(enditer, sign)
						self.arr.append(sign)
				else:
					if last_text=='-' or last_text=='+' or last_text=='*' or last_text=='/':
						tt.set_text(tt.get_text(tt.get_start_iter(), tt.get_end_iter(), True)[:-1] + sign)
						self.arr.pop()
						self.arr.append(sign)
					elif last_text=='/-' or last_text=='*-':
						tt.set_text(tt.get_text(tt.get_start_iter(), tt.get_end_iter(), True)[:-2] + sign)
						self.arr.pop()
						self.arr.append(sign)
					else:
						tt.insert(enditer, sign)
						self.arr.append(sign)
	
	# Helper function, called on pressing button after previous result has just been evaluated
	def add_fun(self, n):
		tt = self.textbuffer
		tt.set_text(n)
		del self.arr[:]
		self.arr.append(n)
		self.res=0
		self.dot_flag=1
	
	# Helper function, called on pressing 'PI' or 'e'
	def add_extra(self, n):
		if self.res==1:
			self.add_fun(n)
		else:
			enditer = self.textbuffer.get_end_iter()
			self.textbuffer.insert(enditer, n)
			try:
				if self.arr[-1].isdigit()==True:
					self.arr.append('*'+n)
				else:
					self.arr.append(n)
			except:
				self.arr.append(n)
	
	# Function called on pressing number 7
	def on_button1_clicked(self, bt):
		self.add_num('7')
	
	# Function called on pressing number 8
	def on_button5_clicked(self, bt):
		self.add_num('8')
	
	# Function called on pressing number 9
	def on_button9_clicked(self, bt):
		self.add_num('9')
	
	# Function called on pressing number 4
	def on_button2_clicked(self, bt):
		self.add_num('4')
	
	# Function called on pressing number 5
	def on_button6_clicked(self, bt):
		self.add_num('5')
	
	# Function called on pressing number 6
	def on_button14_clicked(self, bt):
		self.add_num('6')
		
	# Function called on pressing number 1
	def on_button3_clicked(self, bt):
		self.add_num('1')
	
	# Function called on pressing number 2
	def on_button7_clicked(self, bt):
		self.add_num('2')
	
	# Function called on pressing number 3
	def on_button12_clicked(self, bt):
		self.add_num('3')
	
	# Function called on pressing number 0
	def on_button4_clicked(self, bt):
		self.add_num('0')
	
	# Function called on pressing /
	def on_button18_clicked(self, bt):
		self.add_sign('/')
	
	# Function called on pressing *
	def on_button11_clicked(self, bt):
		self.add_sign('*')
	
	# Function called on pressing -
	def on_button21_clicked(self, bt):
		self.add_sign('-')
	
	# Function called on pressing +
	def on_button15_clicked(self, bt):
		self.add_sign('+')
	
	# Function called on pressing ^
	def on_button13_clicked(self, bt):
		self.add_sign('^')
	
	# Function called on pressing PI
	def on_button23_clicked(self, bt):
		self.add_extra('pi')
	
	# Function called on pressing e
	def on_button24_clicked(self, bt):
		self.add_extra('e')
	
	# Function called on pressing .
	def on_button8_clicked(self, bt):
		if self.res==1:
			if self.dot_flag==1:
				tt = self.textbuffer
				tt.set_text(''.join(self.arr)+'.')
				self.arr.append('.')
				self.dot_flag=0
				self.res=0
		else:
			if self.dot_flag==1:
				enditer = self.textbuffer.get_end_iter()
				self.textbuffer.insert(enditer, '.')
				self.arr.append('.')
			self.dot_flag=0
	
	# Function called on pressing (
	def on_button20_clicked(self, bt):
		tt = self.textbuffer
		self.dot_flag=1
		self.op+=1
		if self.res==1:
			self.add_fun('(')
		else:
			enditer = self.textbuffer.get_end_iter()
			try:
				last_text = tt.get_text(tt.get_start_iter(), tt.get_end_iter(), True)[-1]
				tt.insert(enditer, '(')
				if last_text.isdigit()==True or last_text=='.':
					self.arr.append('*(')
				else:
					self.arr.append('(')
			except:
				tt.insert(enditer, '(')
				self.arr.append('(')
	
	# Function called on pressing )
	def on_button22_clicked(self, bt):
		self.dot_flag=1
		self.cl+=1
		if self.res==1:
			self.add_fun(')')
		else:
			enditer = self.textbuffer.get_end_iter()
			self.textbuffer.insert(enditer, ')')
			self.arr.append(')')
	
	# Function called on pressing log
	def on_button10_clicked(self, bt):
		self.dot_flag=1
		self.op+=1
		tt = self.textbuffer
		if self.res==1:
			self.add_fun('ln(')
		else:
			enditer = self.textbuffer.get_end_iter()	
			try:
				last_text = tt.get_text(tt.get_start_iter(), tt.get_end_iter(), True)[-1]
				tt.insert(enditer, 'ln(')
				if last_text.isdigit()==True:
					self.arr.append('*ln(')
				else:
					self.arr.append('ln(')
			except:
				tt.insert(enditer, 'ln(')
				self.arr.append('ln(')
	
	# Function called on pressing C
	def on_button17_clicked(self, bt):
		self.dot_flag=1
		self.res=1
		self.textbuffer.set_text('')
		del self.arr[:]
	
	# Function called on pressing Del
	def on_button19_clicked(self, bt):
		tt = self.textbuffer
		if self.res==1:
			tt.set_text('')
			del self.arr[:]
			self.res=0
			self.dot_flag = 1
			self.op=0
			self.cl=0
		else:
			text = tt.get_text(tt.get_start_iter(), tt.get_end_iter(), True)
			if len(self.arr)!=0:
				tt.set_text(tt.get_text(tt.get_start_iter(), tt.get_end_iter(), True)[:-self.dc[self.arr[-1]]])
				dot = self.arr.pop()
				if dot=='*-' or dot=='/-':
					self.arr.append(dot[0])
				if dot.find('(')!=-1:
					self.op-=1
				if dot.find(')')!=-1:
					self.cl-=1
				if dot=='.':
					self.dot_flag=1
				if len(self.arr)!=0:
					if self.arr[-1]==' ':
						self.arr.pop()
						self.dot_flag=0
	
	# Function called on pressing =
	def on_button16_clicked(self, bt):
		if self.res==0 and len(self.arr)!=0:
			text = ''.join(self.arr)
			text = text.replace('^', '**')
			text = text.replace('ln', 'math.log')
			text = text.replace('pi', 'math.pi')
			text = text.replace('e', 'math.e')
			text = text.replace(' ','')
			if self.op>self.cl:
				text+=(self.op-self.cl)*')'
			if self.cl>self.op:
				text = '('*(self.cl-self.op)+text
			tt = self.textbuffer
			self.res=1
			self.op=0
			self.cl=0
			del self.arr[:]
			text = re.sub(r'(?<!\.)\b0+(?!\b)', '', text)
			try:
				ans = eval(text)
				fl=False
				if ans%1==0:
					ans = int(ans)
				else:
					fl=True
				if ans>10000000000 or ans<1000000:
					ans = '%E' %ans
					fl=True
				text = tt.get_text(tt.get_start_iter(), tt.get_end_iter(), True)
				self.textbuffer.set_text(text + ' = \n' + str(ans))
				self.arr = [j for j in str(ans)]
				if fl==True:
					self.arr.append(' ')
			except:
				self.textbuffer.set_text('Error')

	def __init__(self):
		try:
			builder = Gtk.Builder()
			builder.add_from_file("calc.glade")
		except:
			print "Unable to load file: calc.glade"
			sys.exit(1)
		builder.connect_signals(self)
		self.arr = []
		self.dc = { '1':1, '2':1, '3':1, '4':1, '5':1, '6':1, '7':1, '8':1, '9':1, '0':1, '+': 1, '-':1, '*':1, '/':1, 'e':1, '(':1, ')':1, '.':1, '^':1, 'ln(':3, '*ln(':3, '*e':1, 'E':1, '*(':1, 'pi':2, ' ':1, '/-':1, '*-':1 }
		self.op = 0
		self.cl = 0
		self.dot_flag=1
		self.res = 0
		self.w = builder.get_object("window1")
		self.textview = builder.get_object("textview1")
		self.textview.override_background_color(Gtk.StateType.NORMAL, Gdk.RGBA(.5,.5,.5,.5))
		self.textbuffer = self.textview.get_buffer()
		self.textview.set_editable(False)
		self.textview.set_cursor_visible(False)
		self.w.show_all()
		Gtk.main()

if __name__ == '__main__':
	app = pr2()
