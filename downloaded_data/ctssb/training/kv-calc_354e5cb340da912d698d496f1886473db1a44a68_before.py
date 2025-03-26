import operator
from kivy.app import App
from kivy.properties import *
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button


class Calc(BoxLayout):
	current_num = StringProperty('0')
	current_operator = StringProperty(None, allownone=True)
	last_pressed = StringProperty(None, allownone=True)
	previous = StringProperty(None, allownone=True)
	operator_dict = DictProperty({'+': operator.add,
								  '-': operator.sub,
								  '*': operator.mul,
								  '/': operator.truediv,
								  '=': None})
	def backspace_callback(self):
		if self.last_pressed in self.operator_dict.keys():
			return
		if len(self.current_num) == 1:
			self.current_num = 0
		else:
			self.current_num = self.current_num[:-1]

	def clear_callback(self):
		self.current_num = '0'
		if self.last_pressed == 'c':
			self.current_operator = None
			self.last_pressed = None
			self.previous = None
		self.last_pressed = 'c'


	def equals_callback(self):
		if self.previous != None and self.last_pressed != '=':
			self.current_num = str(self.evaluate())
			self.previous = None
			self.current_operator = None
		self.last_pressed = '='


	def operand_callback(self,input_number):
		if self.current_num == '0' or self.last_pressed in self.operator_dict.keys():
			self.current_num = input_number
		else:
			self.current_num += input_number
		self.last_pressed = input_number


	def operator_callback(self,operator_type):
		if self.last_pressed == '.':
			self.current_num = self.current_num[:-1]

		if self.previous == None:
			self.previous = self.current_num
		elif self.last_pressed in self.operator_dict.keys():
			pass
		else:
			self.current_num = self.evaluate()
			self.previous = self.current_num

		self.last_pressed = operator_type
		self.current_operator = operator_type
		

	def evaluate(self):
		if self.last_pressed == '.':
			self.current_num = self.current_num[:-1]

		prev = float(self.previous)
		curr = float(self.current_num)
		return self.operator_dict[self.current_operator](prev, curr)

	def sign_change_callback(self):
		if self.current_num[0] == '-':
			self.current_num = self.current_num[1:]

			if self.last_pressed in self.operator_dict.keys():
				self.previous = self.previous[1:]

		else:
			self.current_num = '-' + self.current_num

			if self.last_pressed in self.operator_dict.keys():
				self.previous = '-' + self.previous


class CalculatorApp(App):
	def build(self):
		return Calc()

if __name__ == '__main__':
	CalculatorApp().run()
