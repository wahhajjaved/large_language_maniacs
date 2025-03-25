from account.models import *
from django.contrib.auth.models import User, Group
from .constants import *
import datetime
from itertools import chain

# import the logging library
import logging

logger = logging.getLogger(__name__)

class BaseRoleAccess(object):
	def __init__(self, user, parentID, parentLevel):
		""" Used to set meta data of mastery
		attributes:
			user(object) = login user
			parentID(int) = Used to maintain hierarchy of claas, school and student data
							i) it could be school_id or class_id if user wants to see the class and student data
							ii) default it should be "-1"
			parentLevel(int) = Used to maintain hierarchy of claas, school and student data
							   i) exculding user as teacher parentLevel is set to 0 to view the visualizer
							   ii) Selction on class, school parent level changed for each user(1=schools, 2=class etc)
		"""
		parentLevelMethods = {1:self.boardMember, 2:self.schoolLeader, 3:self.teacher}
		self.user = user
		self.role = 0

		# Check if user is superuser i.e admin. admin doesn't belongs to any group
		if not user.is_superuser:
			self.role = user.groups.values()[0]['id']

		if self.role == 3: # Set parentLevel = 1 for teacher. He/she dosen't have the permission of institutes. for first we have set it to 1
			parentLevel = 1 if parentLevel <= 0 else parentLevel

		if self.role in parentLevelMethods: # based on the role of user call the respective methods (only for School leader and teacher)
			schools, classes = parentLevelMethods[self.role]()
			level = {0: schools, 1:schools , 2: classes}

			if parentID == -1: # Here set the parent id for teacher. when showing data of teacher we don't have the parent inforamtion for teacher user
				parentID = schools[0]

			if parentLevel in level and classes is not None: # Checked particular user have the access of schools or class
				if not parentID in level[parentLevel] and classes is not None:
					raise Exception("1. Not authorized to access the data")
				else:
					self.institutes = UserInfoSchool.objects.filter(school_id = schools[0])
					self.classes = UserInfoClass.objects.filter(class_id__in = classes)
			#1.Added here to BM who has access the certain set of school data if he/she selected schools while registration so we add funcationality for the BM.
			#2.Default BM has access all the schools data."""
			elif self.role == 1 and classes is None:
				if (len(schools) > 0):
					self.institutes = UserInfoSchool.objects.filter(school_id__in = schools)
				else:
					self.institutes = UserInfoSchool.objects.filter(school_id = schools[0])
				self.classes = None
			else:
				self.institutes = UserInfoSchool.objects.filter(school_id = schools[0])
				# raise Exception("2. Not authorized to access the data")

		# For user admin and board member we have fetched all the institues data
		# Only for admin user view all the schools data as per provide functionality to board Member who can view specific Schools data --Discussed with Harish
		elif self.role == 0:
			userMapping = UserRoleCollectionMapping.objects.filter(user_id= self.user)
			schools = list(userMapping.values_list('institute_id_id', flat=True))
			self.institutes = UserInfoSchool.objects.all()
			self.classes = None
		self.parentLevel = int(parentLevel)
		self.parentId = parentID


	def teacher(self):
		"""
		This function is used to fetch the mapping of classes and schools based on the user role
		"""
		try:
			userMapping = UserRoleCollectionMapping.objects.filter(user_id = self.user)
			schools = list(userMapping.values_list('institute_id_id', flat = True))
			classes = list(userMapping.values_list('class_id_id', flat = True))
			return schools, classes
		except Exception as e:
			logger.error(e)

	def schoolLeader(self):
		"""
		This function is used to fetch the mapping of classes and schools based on the user role
		"""
		try:
			userMapping = UserRoleCollectionMapping.objects.filter(user_id= self.user)
			schools = list(userMapping.values_list('institute_id_id', flat=True))
			classes = list(UserInfoClass.objects.filter(parent = schools[0]).values_list('class_id', flat = True))
			return schools, classes
		except Exception as e:
			logger.error(e)

	def boardMember(self):
		try:
			userMapping = UserRoleCollectionMapping.objects.filter(user_id= self.user)
			schools = list(userMapping.values_list('institute_id_id', flat=True))
			classes = None
			return schools, classes
		except Exception as e:
			logger.error(e)

	# AccessList = [2, 3]
	# def hasAccessSchool(self, parentID):
	# 	if self.role in AccessList:
	# 		userMapping = UserRoleCollectionMapping.objects.filter(user_id = self.user)
	# 		schools = list(userMapping.filter(institute_id_id = parentID).values_list('institute_id_id', flat = True))
	# 	else:
	# 		schools = UserInfoSchool.objects.all()

	# def hasAccessClass(self, parentID):
	# 	if self.role == 3:
	# 		userMapping = UserRoleCollectionMapping.objects.filter(user_id = self.user)
	# 		classes = list(userMapping.filter(class_id_id = parentID).values_list('class_id_id', flat = True))
	# 	else:
	# 		classes = None

class UserMasteryMeta(BaseRoleAccess):
	"""
	This is used to retrive the user meta information based on the role.

	"""

	def __init__(self, user,parentID, parentLevel):
		super(self.__class__, self).__init__(user, parentID, parentLevel)
		self.parentLevelMethods = [self.getInstituteMeta, self.getClassMeta, self.getStudentMeta]
		self.parentLevels = { 'institutes':0, 'school':1, 'class':2, 'students': 3 }

    # Construct the breadcrumb format
	def construct_breadcrumb(self, parentName, parentLevel, parentId):
		res = {
		"parentName": parentName,
		"parentLevel": parentLevel,
		"parentId": parentId
		}
		return res

	def construct_response(self, code, title, message, data):
		response_object = {}
		response_object["code"] = code
		response_object["info"] = {"title": title,"message": message}
		response_object["data"] = data
		return response_object

	def getClassMeta(self, objBreadcrumb, rows):
		""" Used to fetch the class meta information
		Args:
			parentid(int): Used to retrive respective classes based on school_id(parentid)
			objBreadcrumb(list): used to set metadata(parentId, parentLevel, parentName)of class
			rows(list) = []
			role(int) = Role of the user i.e 1 = board member, 2 = school leader and 3 = teacher
		Returns:
			rows(list) = It returns classes meta information i.e class_id and class_name
			objBreadcrumb(list) = It fetch the hierarchy level of class

		"""
		try:
			if self.role != 3:
				objBreadcrumb.append(self.construct_breadcrumb("Institutes", 0, "-1"))

			school = self.institutes.filter(school_id = self.parentId)
			school_name = ""
			if school:
				school_name = school[0].school_name

			root = self.construct_breadcrumb(school_name, self.parentLevel , self.parentId)
			objBreadcrumb.append(root)

			objClasses = self.classes
			if self.classes == None:
				objClasses = UserInfoClass.objects.filter(parent = school[0].pk)

			for objclass in objClasses:
				class_info = {
					"id": str(objclass.class_id),
					"name": objclass.class_name
				}
				rows.append(class_info)

			return rows, objBreadcrumb
		except Exception as e:
			logger.error("getting error while accessing class meta:", e)

	def getStudentMeta(self, objBreadcrumb, rows):
		""" Used to fetch the stident meta inforamtion
		Args:
			role_id(int) = role of a user_id
			parentId(int) =  used to retrive student information based on class_id(parentId)
			objBreadcrumb(list) = used to set metadata(parentId, parentLevel, parentName) of class and school
			rows(list) = []
		Returns:
			rows(list) = it reurns student inforamtion respective class
			objBreadcrumb(list) = it returns metadata(parentId, parentLevel, parentName) of class and school
		"""
		try:
			if self.classes:
				curr_class = self.classes.filter(class_id = self.parentId)
			else:
				curr_class = UserInfoClass.objects.filter(class_id = self.parentId)
			class_name = curr_class[0].class_name

			school = self.institutes.filter(school_id = curr_class[0].parent).first()

			if self.role != 3:
				objBreadcrumb.append(self.construct_breadcrumb("Institutes", 0, "-1"))

			if school:
				school_id = str(school.school_id)
				school_name = school.school_name
				objBreadcrumb.append(self.construct_breadcrumb(school_name, self.parentLevels['school'], school_id))
				objBreadcrumb.append(self.construct_breadcrumb(class_name, self.parentLevels['class'], self.parentId))

			objStudentData = UserInfoStudent.objects.filter(parent = self.parentId)
			if not objStudentData:
				return rows, objBreadcrumb
			for student in objStudentData:
				studentInfo = {
				'id': str(student.student_id),
				'name': student.student_name
				}
				rows.append(studentInfo)
			return rows, objBreadcrumb
		except Exception as e:
			logger.error(e)

	def getInstituteMeta(self, objBreadcrumb, rows):
		""" Used to fetch the institute meta information
		Args:
			objBreadcrumb(list) = used to set metadata(parentId, parentLevel, parentName) of institutes
			rows(list) = []
		Returns:
			objBreadcrumb(list) = it returns metadata(parentId, parentLevel, parentName) of institutes
			rows(list) = it returns institutes information
		"""
		try:
			objBreadcrumb.append(self.construct_breadcrumb("Institutes", 0, "-1"))
			for institute in self.institutes:
				school_info = {
				    "id": str(institute.school_id),
				    "name": institute.school_name
				}
				rows.append(school_info)
			return rows, objBreadcrumb
		except Exception as e:
			logger.error(e)

	def getPageMeta(self, objMetrics):
		"""" Used to fetch mastery meta inforamtion
		Args:
			None
		Returns:
			response_object(dict) = it returns the code , title , message and meta data
		"""
		try:
			code = 0
			title = ""
			message = ""
			rows = []
			objBreadcrumb = []
			# objMetrics = self.construct_metrics()
			# objMetrics = metricsList
			rows, objBreadcrumb = self.parentLevelMethods[self.parentLevel](objBreadcrumb, rows)

			data = { 'breadcrumb': objBreadcrumb, 'metrics': objMetrics, 'rows': rows }
			response_object = self.construct_response(code, title, message, data)
			return response_object
		except Exception as e:
			logger.error(e)

class UserMasteryData(BaseRoleAccess):
	"""
	This function is used to fetch the mastery data of the user
	"""
	def __init__(self, user, parentID, parentLevel, topicID, channelID, startTimestamp, endTimestamp, channelContetID):
		super(self.__class__, self).__init__(user, parentID, parentLevel)
		self.topicID = topicID if topicID[0] != '-1' else ['']
		self.channelID = channelID if channelID[0] != '-1' else ['']
		endTimestamp = str(int(endTimestamp) + 86400)
		self.startTimestamp = datetime.date.fromtimestamp(int(startTimestamp)).strftime('%Y-%m-%d')
		self.endTimestamp = datetime.date.fromtimestamp(int(endTimestamp)).strftime('%Y-%m-%d')
		self.parentLevelMethods = [self.getInstitutesData, self.getClassData, self.getStudentData]
		self.parentLevels = { 'institutes':0, 'school':1, 'class':2, 'students': 3 }
		self.channelContetID = channelContetID
	def getTopicsData(self):
		""" Used to calculate the total_questions based on the selected topicID and channelID
		Args:
			None
		Returns:
			total_questions(int) : Count of total_questions
		"""
		try:
			total_questions = 0
			topic_id = self.topicID
			filterTopics = {'topic_id__in':self.topicID}
			if self.topicID:
				filterTopics['channel_id__in']=self.channelID
			topic = Content.objects.filter(**filterTopics)
			for t in topic:
			# topic = Content.objects.filter(topic_id__in=topic_ids).filter(channel_id__in=channel_ids).first()
				total_questions += t.total_questions
			return total_questions
		except Exception as e:
			logger.error(e)

	def getSubTopicsData(self):
		""" Used to calculate the total_subtopics based on the selected topicID and channelID
		Args:
			None
		Returns:
			total_questions(int) : Count of total_subtopics
		"""
		try:
			total_subtopics = 0
			topic_id= self.topicID
			filterTopics = {'topic_id__in':self.topicID}
			if self.topicID:
				filterTopics['channel_id__in']=self.channelID
			topic = Content.objects.filter(**filterTopics)
			# topic = Content.objects.filter(topic_id__in=topic_ids).filter(channel_id__in=channel_ids).first()
			for st in topic:
				total_subtopics += st.sub_topics_total
			return total_subtopics
		except Exception as e:
			logger.error(e)

	def getLogData(self, masteryElement):
		""" Used to fetch the log data of each masteryElement(class, school, student)
		Args:
			masteryElement(obj): It could be class, school and student
		Returns:
			masteryData(Queryset): It contains mastry logs of each masteryElement
		"""
		try:
			if not (self.channelContetID):
				filterTopics = {'content_id__in':self.topicID}
				filterTopics['date__range'] = (self.startTimestamp, self.endTimestamp)

				if self.topicID:
					filterTopics['channel_id__in']=self.channelID

				if self.parentLevel == 0:
					filterTopics['school_id'] = masteryElement
					masteryData = MasteryLevelSchool.objects.filter(**filterTopics)
				elif self.parentLevel == 1:
					filterTopics['class_id'] = masteryElement
					masteryData = MasteryLevelClass.objects.filter(**filterTopics)
				elif self.parentLevel == 2:
					filterTopics['student_id'] = masteryElement
					masteryData = MasteryLevelStudent.objects.filter(**filterTopics)
				return masteryData
			else:
				result_list = []
				for (k,v) in  self.channelContetID.items():
					filterTopics = {'content_id__in':v}
					filterTopics['date__range'] = (self.startTimestamp, self.endTimestamp)

					# if self.topicID:
					filterTopics['channel_id']=k

					if self.parentLevel == 0:
						filterTopics['school_id'] = masteryElement
						masteryData = MasteryLevelSchool.objects.filter(**filterTopics)
						if masteryData:
							result_list.extend(list(chain(masteryData)))
					elif self.parentLevel == 1:
						filterTopics['class_id'] = masteryElement
						masteryData = MasteryLevelClass.objects.filter(**filterTopics)
						if masteryData:
							result_list.extend(list(chain(masteryData)))
					elif self.parentLevel == 2:
						filterTopics['student_id'] = masteryElement
						masteryData = MasteryLevelStudent.objects.filter(**filterTopics)
						if masteryData:
							result_list.extend(list(chain(masteryData)))
				return result_list
		except Exception as e:
			logger.error(e)

	def getInstitutesData(self):
		""" Used to fetch the institutes mastery details
		Args:
			None
		Returns:
			data(dict): It contains rows of mastry data and it's aggregation
		"""
		res = list(map(self.getMastryLogDetails, self.institutes))
		aggregationResult = [res['aggregation'] for res in res]
		data = self.getMasteryAggregationData(aggregationResult, res)
		return data

	def getMasteryAggregationData(self, aggregationResult, masteryData):
		""" Used to Calculate the aggregation of each masteryElements
		Args:
			aggregationResult(list) : list of percentage vaue of four metrics
			masteryData(dict) = mastry data of masteryElements
		Returns:
			data(dict) = it contains aggregation result and mastery data of class, school
		"""
		try:
			data = {}
			percent_complete_array = []
			percent_correct_array = []
			number_of_attempts_array = []
			percent_student_completed_array = []
			sample_metrix = []
			mastered_topics = []
			percent_mastered_topics = []
			correct_questionsList = []
			completed_questionsList =[]
			number_of_exercise_attempts_list = []
			for row in aggregationResult:
				mastered_topics.append(row[0])
				number_of_exercise_attempts_list.append(row[1])
				percent_mastered_topics.append(row[2])
				correct_questionsList.append(row[3])
				number_of_attempts_array.append(row[4])
				percent_correct_array.append(row[5])
				# completed_questionsList.append(row[5])
				# percent_complete_array.append(row[5])

			# Removed unwanted data of aggregation
			for row in masteryData:
				row.pop('aggregation', None)

			aggregation = self.getAggrigation(mastered_topics, number_of_exercise_attempts_list,percent_mastered_topics, number_of_attempts_array,correct_questionsList,percent_correct_array)
			data['rows'] = masteryData
			data['aggregation'] = aggregation
			return data
		except Exception as e:
			logger.error(e)

	def getClassData(self):
		""" Used to fetch mastery class data
		Args:
			None
		Returns:
			data(dict): It contains rows of mastry data and it's aggregation
		"""
		try:
			school = self.institutes.filter(school_id = self.parentId)
			objClasses = self.classes
			if self.classes == None:
				objClasses = UserInfoClass.objects.filter(parent = school[0].pk)

			res = list(map(self.getMastryLogDetails, objClasses))
			aggregationResult = [res['aggregation'] for res in res]

			data = self.getMasteryAggregationData(aggregationResult, res)
			return data
		except Exception as e:
			logger.error(e)

	def getStudentData(self):
		""" Used to fetch mastery student data
		Args:
			None
		Returns:
			data(dict): It contains rows of mastry data and it's aggregation
		"""
		try:
			students = UserInfoStudent.objects.filter(parent = self.parentId)
			if not students:
				return None
			res = list(map(self.getStudentDetails, students))

			#res = [i for i in res if i is not None]
			aggregationResult = [res['aggregation'] for res in res]
			data = self.getMasteryAggregationData(aggregationResult, res)
			return data
		except Exception as e:
			logger.error(e)


	def getStudentDetails(self, student):
		""" Used to fetch the stduent mastery details
		Args:
			studnt(obj): passed each student as args
			row(dict) : list of mastery data
		"""
		try:

			completed_questions = 0
			correct_questions = 0
			number_of_attempts = 0
			number_of_content = 0
			mastered_topics = 0
			percent_mastered_topics = 0
			number_of_exercise_attempts = 0
			total_questions = self.getTopicsData()
			total_subtopics = self.getSubTopicsData()
			mastery_students = self.getLogData(student)
			for mastery_student in mastery_students:
				mastered_topics += mastery_student.mastered
				completed_questions += mastery_student.completed_questions
				correct_questions += mastery_student.correct_questions
				number_of_attempts += mastery_student.attempt_questions
				number_of_exercise_attempts += mastery_student.attempt_exercise

			if len(mastery_students) == 0 or number_of_exercise_attempts == 0 or number_of_attempts == 0:
				completed = "0.00%"
				values = [0,0,"0.00%", 0, 0, "0.00%"]
				aggregation = [0,0,0.00, 0, 0, 0.00]

				row = {'id': str(student.student_id), 'name': student.student_name, 'total_questions': total_questions, 'total_subtopics': total_subtopics, 'values': values, 'aggregation': aggregation}
			else:
				# percent_complete_float = float(completed_questions) / total_questions # Hide the %questions_completed as per enhancment and defeat sheet changes
				# percent_complete = "{0:.2%}".format(percent_complete_float)

				# Calculate the percentage of correct questions
				percent_correct_float = float(correct_questions) / number_of_attempts # changed the formula to calculate the % correct based on total_attempts instead of total_questions of respective content. As discussed with Harish
				percent_correct = "{0:.2%}".format(percent_correct_float)

				percent_mastered_topics_float = float(mastered_topics) / number_of_exercise_attempts
				percent_mastered_topics = "{0:.2%}".format(percent_mastered_topics_float)

				values = [mastered_topics, number_of_exercise_attempts, percent_mastered_topics, correct_questions, number_of_attempts, percent_correct]
				#aggregation = [percent_complete_float, percent_correct_float, completed, number_of_attempts] # Added for Testing
				aggregation = [mastered_topics, number_of_exercise_attempts, percent_mastered_topics_float, correct_questions, number_of_attempts,percent_correct_float]

				row = {'id': str(student.student_id), 'name': student.student_name, 'total_questions': total_questions, 'total_subtopics': total_subtopics, 'values': values, 'aggregation': aggregation}
			return row
		except Exception as e:
			logger.error(e)

	def getMastryLogDetails(self, masteryElement):
		""" Used to fetch mastery details of any masteryElement(i.e class, school and student)
		Args:
			masteryElement(obj): fetched the school and class mastery
		Returns:
			row(dict) : It contains the mastery data of school or class
		"""
		try:
			aggregation = []
			rows = []
			values = []
			completed_questions = 0
			correct_questions = 0
			number_of_attempts = 0
			students_completed = 0
			total_students = 0
			mastered_topics = 0
			number_of_exercise_attempts = 0
			percent_mastered_topics = 0
			total_questions = self.getTopicsData()
			total_subtopics = self.getSubTopicsData()
			objMasteryData = self.getLogData(masteryElement)

			for objMastery in objMasteryData:
				mastered_topics += objMastery.mastered
				completed_questions += objMastery.completed_questions
				correct_questions += objMastery.correct_questions
				number_of_attempts += objMastery.attempt_questions
				number_of_exercise_attempts += objMastery.attempt_exercise

			# Filter mastery level belongs to a certain class with certain topic id, and within certain time range
			total_students = masteryElement.total_students
			if total_questions == 0 or total_students == 0 or correct_questions == 0 or number_of_exercise_attempts == 0:
				values = [0,0,"0.00%",0,0,"0.00%"]
				aggregation = [0,0,0.00, 0, 0,0.00]
				if self.parentLevel == 0:
					row = {'id': str(masteryElement.school_id), 'name': masteryElement.school_name, 'total_questions': total_questions, 'total_subtopics': total_subtopics, 'values': values, 'aggregation': aggregation}
				else:
					row = {'id': str(masteryElement.class_id), 'name': masteryElement.class_name, 'total_questions': total_questions, 'total_subtopics': total_subtopics, 'values': values, 'aggregation': aggregation}
			else:
				# Calculate the percentage of completed questions
				# percent_complete_float = float(completed_questions) / (total_questions * total_students)
				# percent_complete = "{0:.2%}".format(percent_complete_float)

				# Calculate the percentage of correct questions
				percent_correct_float = float(correct_questions) / (number_of_attempts) # changed the formula to calculate the % correct based on total_attempts instead of total_questions of respective content. As discussed with Harish
				percent_correct = "{0:.2%}".format(percent_correct_float)

				# Calculate the percentage of exercise mastered
				percent_mastered_topics_float = float(mastered_topics) / (number_of_exercise_attempts) # changed formula to calculate the % exrecise mastered based on total_exercise_attempts instead of total_subtopics of respective content.
				percent_mastered_topics = "{0:.2%}".format(percent_mastered_topics_float)

				values = [mastered_topics, number_of_exercise_attempts,percent_mastered_topics, correct_questions,number_of_attempts,percent_correct]
				aggregation = [mastered_topics, number_of_exercise_attempts,percent_mastered_topics_float, correct_questions, number_of_attempts,percent_correct_float]
				if self.parentLevel == 0:
					row = {'id': str(masteryElement.school_id), 'name': masteryElement.school_name, 'total_questions': total_questions, 'total_subtopics': total_subtopics, 'values': values, 'aggregation':aggregation}
				else:
					row = {'id': str(masteryElement.class_id), 'name': masteryElement.class_name, 'total_questions': total_questions, 'total_subtopics': total_subtopics, 'values': values, 'aggregation': aggregation}
			return row
		except Exception as e:
			logger.error(e)


	def getAggrigation(self, mastered_topics, percent_of_exercise_attempts_list, percent_mastered_topics, correctQuestionsList, numberOfAttemptsList,percentCorrectList):
		""" Used to calculate the aggregation for each masteryElement based on metrics data
		Args:
			percentCompleteList(list) :  List of completed questions(percentage)
			percentCorrectList(list) : List of correct questions(percentage)
			percentStudentCompletedList(list) : List of students completed the topic(percentage)
			numberOfAttemptsList(int) : List of number of attempts

		Returns:
			aggregation[list] = returns average of metrics data in list
		"""
		try:
			aggregation = []
			avg_complete = 0
			avg_percent_complete = 0
			avg_correct = 0
			avg_percent_correct = 0
			avg_number_of_attempts = 0
			avg_percent_student_completed = 0
			avg_mastered_topics = 0
			avg_percent_mastered_topics = 0
			avg_number_of_exercise_attempts = 0
			# Calculate the average for these four metrics
			length = len(percentCorrectList)
			if length != 0:
			    for i in range(length):
			    	avg_mastered_topics += mastered_topics[i]
			    	avg_number_of_exercise_attempts += percent_of_exercise_attempts_list[i]
			    	avg_percent_mastered_topics += percent_mastered_topics[i]
			    	avg_correct += correctQuestionsList[i]
			    	avg_number_of_attempts += numberOfAttemptsList[i]
			    	avg_percent_correct += percentCorrectList[i]
			    	# avg_complete += completedQuestionsList[i]
			    	# avg_percent_complete +=  percentCompleteList[i]

			    avg_mastered_topics /= length
			    avg_number_of_exercise_attempts /= length
			    avg_percent_mastered_topics /= length
			    avg_correct /= length
			    avg_number_of_attempts /= length
			    avg_percent_correct /= length
			    # avg_complete /= length
			    # avg_percent_complete /= length


			    # if self.parentLevel == 2: # Added for Testing
			    #     avg_percent_student_completed = "" # Added for Testing
			    # else: # Added for Testing
			    #      avg_percent_student_completed /= length # Added for Testing
			    #      avg_percent_student_completed = "{0:.2%}".format(avg_percent_student_completed) # Added for Testing
			    values = [str(int(avg_mastered_topics)), int(avg_number_of_exercise_attempts) ,"{0:.2%}".format(avg_percent_mastered_topics), str(int(avg_correct)), str(int(avg_number_of_attempts)),"{0:.2%}".format(avg_percent_correct)] #, avg_percent_student_completed, 15] # Added for testing last parameter

			    average = {'name': 'Average', 'values': values}
			    aggregation.append(average)
			return aggregation
		except Exception as e:
			logger.error(e)

	def getPageData(self):
		result = self.parentLevelMethods[self.parentLevel]()
		return result
