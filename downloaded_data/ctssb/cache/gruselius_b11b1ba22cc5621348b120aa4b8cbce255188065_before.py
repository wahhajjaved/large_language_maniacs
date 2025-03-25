
import os

class CourseRepo:
	def __init__(self, name):
		self.lastname = name
		self.updateRequired()

	def updateRequired(self):
		self.required = [".git", "setup.py", "README.md",
			"scripts/getting_data.py", "scripts/check_repo.py",
			self.lastname+"/__init__.py", self.lastname+"/session3.py"]

	@property
	def surename(self):
		return self.name

	@surename.setter
	def surename(self, name):
		self.lastname = name
		self.updateRequired()

	def check(self):
		status = [os.path.exists(file) for file in self.required]
		return all(status)

class TemporarilyChangeDir:
	def __init__(self, path):
		self.originalPath = os.getcwd()
		self.tempPath = path

	def __enter__(self):
		os.chdir(self.tempPath)

	def __exit__(self, type, value, traceback):
		os.chdir(self.originalPath)
