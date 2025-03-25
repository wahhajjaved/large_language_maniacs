#import schedule
import shlex
import copy
from datetime import datetime
from scheduler.schedule import *
from scheduler.course import *
from scheduler.choicestats import *
from scheduler.models import *
from scheduler.datetimeconverter import *

# Main function
#takes number of courses that the student wants,
# and a list of coursese the student is interested in and outputs a list of courses 
#that will be in an optimal schedule
#def createOptimalSchedule(numberOfCourses, listofCourses):
	
def createOptimalSchedule(numberOfCourses, listofCourses, filterDistanceCourses = True):
	schedule = Schedule()
	#schedule.poolOfLockedCourses = []
   	newListOfCourses = []
    	poolOfCutCourses = []
    	for i in range (0, len(listofCourses)):
		newCourse = convertCourseModelToCourseObject(listofCourses[i], filterDistanceCourses)
		if (newCourse != False):
	    		#print "Course is acceptable"
	    		#newListOfCourses.append(newCourse)
			#This handles labs and appends the course
			
			handleLabsForCourse(newCourse, newListOfCourses)
   			#print "size of newListOfCourses =" + str(len(newListOfCourses))
    			#print "new newlistcourse = " + str(newListOfCourses[0])
			#handle additional labs
    			
			#newCourse = newListOfCourses[0]
    			#newMeetingTimes = newCourse.meetingTimes
    	for i in range (0, numberOfCourses):
        	iterateBEHEMOTH(schedule, newListOfCourses, numberOfCourses)
    	outPutListOfLockedCourses = []
    	
	#Locked meeting times
	listMeetingTimes = []
	for i in range (0, len(schedule.poolOfLockedCourses)):
		meetingTimes = schedule.poolOfLockedCourses[i].meetingTimes
		for j in range (0, len(meetingTimes)):
			meetingTime = meetingTimes[j]
			listMeetingTimes.append(meetingTime)
	#Locked Courses
    	outPutListOfCutCourses = []
	for i in range (0, len(schedule.poolOfCutCourses)):
		cutCourse = schedule.poolOfCutCourses[i]
		outputCourse = cutCourse.dataBaseCourse
		outPutListOfCutCourses.append(outputCourse)
	
	#Cut MeetingTimes
	listCutMeetingTimes = []
	for i in range (0, len(schedule.poolOfCutCourses)):
		meetingTimes = schedule.poolOfCutCourses[i].meetingTimes
		for j in range (0, len(meetingTimes)):
			meetingTime = meetingTimes[j]
			listCutMeetingTimes.append(meetingTime)

	#Cut Courses
    	for i in range (0, len(schedule.poolOfLockedCourses)):
		lockedCourse = schedule.poolOfLockedCourses[i]
		outputCourse = lockedCourse.dataBaseCourse		
       		outPutListOfLockedCourses.append(outputCourse)
	
	
	
	
	#largerOutputArray.append(listCutMeetingTimes)
	
	#listActualMeetingTimes = []
	#wooo dev speed > efficiency!	
	#for i in range (0, len(listMeetingTimes)):
	#	currentScheduleMeetingTime = listMeetingTimes[i]
	#	actualMeetingTime = MeetingTime.objects.get(id = currentScheduleMeetingTime.meetingTimeID)		
	#	listActualMeetingTimes.append(actualMeetingTime)
	

	largerOutputArray = []
	largerOutputArray.append(listMeetingTimes)
	largerOutputArray.append(outPutListOfLockedCourses)
	largerOutputArray.append(listCutMeetingTimes)
	largerOutputArray.append(outPutListOfCutCourses)
    	#Schedule Stats
	TotalDays = schedule.getTotalDays()
    	TotalTimeGap = schedule.getTotalTimeGap()
    	crossCampusTravels = schedule.getTotalCrossCampusTravels()
    	currentChoiceStats = ChoiceStats(TotalDays, TotalTimeGap, crossCampusTravels)
    	largerOutputArray.append(currentChoiceStats)
    	largerOutputArray.append(schedule)
	#list of meeting times
	
	#largerOutputArray.append(meetingTime)
    	return largerOutputArray


#handles courses we need to take
#Potential issue!
#Say hte user wants to take cmpt 300, and we are passed all sections of cmpt 300
#This means I should group up all the sections of cmpt 300 together into one list
#NOT DONE
def handleCoursesWeNeed(coursesWeNeedListOfLists, schedule, numberOfCourses):
	#go through the courses we need to take and attempt to add them one by one	
	#poolOfLockedCourses = []
	#for each course name (e.g. cmpt300
	#note each course name has multiple sections
	#for every course name
	for i in range (0, len(coursesWeNeedListOfLists)):
		listOfCopiesOfNeededCourse = []
		courseListWithCertainName = coursesWeNeedListOfLists[i]
		#for every entry with that course name (different sections)
		#get the copies of the course
		for j in range (0, len(courseListWithCertainName)):
			currentCourseSection = courseListWithCertainName[j]
			handleLabsForCourse(currentCourseWeNeed, listOfCopiesOfNeededCourse)
		iterateBEHEMOTH(schedule, listOfCopiesOfNeededCourse, schedule.poolOfCutCourses, numberOfCourses)

	

#Handles multiple labs for a course
def handleLabsForCourse(inputCourse, listofCourses):
	if len(inputCourse.labs) != 0:
		#create a clone course for each lab
		for i in range (0, len(inputCourse.labs)):
			testcourse = copy.deepcopy(inputCourse)
			testcourse.addMeetingTime(inputCourse.labs[i])
			listofCourses.append(testcourse)
	else:
		listofCourses.append(inputCourse)
		

#Turns a course model object into a course object that we can use in the scheduler
#Converts : course from database --> course usable by scheduler
#def convertCourseModelToCourseObject(inputCourse):
def convertCourseModelToCourseObject(inputCourse, filterDistanceCourses):
    	id = inputCourse.id		
    	listofmeetingTimes = MeetingTime.objects.filter(course = id)
	#Filters out distance courses	
	if "C" in inputCourse.section:
		return False    	
	if (len (listofmeetingTimes) == 0):
		return False
    	if inputCourse.component == "PRA":
		return False
    	courseInfo = inputCourse.subject
    	courseInfo += inputCourse.number
  	courseMeetingTimes = []
  	courseCampus = inputCourse.campus
  	courseCampusNumber = convertCampusModelToInt(courseCampus)
  	courseExam = []
  	courseLabs = []
  	for i in range (0, len(listofmeetingTimes)):
		meetingTime = listofmeetingTimes[i]
		if (meetingTime.type == "EXAM"):
	    		courseExam.append(meetingTime)
		elif (meetingTime.type == "LAB"):
	    		courseLabs.append(meetingTime)
		else:
	    		courseMeetingTimes.append(meetingTime)
    	if (filterDistanceCourses == True) and len(courseMeetingTimes) == 0:
    		return False
    	else:
		outputCourse = SchedulingCourse(courseInfo, id, courseMeetingTimes, courseExam, courseLabs, courseCampusNumber, inputCourse)
		return outputCourse
    

def convertCampusModelToInt(campus):
	if campus == "BRNBY":
		return 1
    	elif campus == "SURRY":
		return 2
   	elif campus == "VANCR" or campus == "GNWC":
		return 3
 	else :
		return 0






#Converts an input string into a date
def convertStringToDate(inputString):
	outputdate = datetime.strptime(inputString, '%Y-%m-%d')
   	return outputdate
#Converts an imput string into a time object
def convertStringToTime(inputString):
   	outputdate = datetime.strptime(inputString, '%H:%M:%S')
	return outputdate

#Convert Particular time to Timeslots
#See scheduler
def convertTimeToTimeSlot(intputTime):
	timeslot = intputTime.hour * 6
 	timeslot += intputTime.minute /10
   	return timeslot

def checkCourseConflict(course, schedule):
	#if (course.title =="Cmpt165 "):
	#		print "exam conflict Cmpt 165"
	if courseExamConflict(course, schedule.poolOfLockedCourses) == True:
		#print "Course exam conflict" +	course.title
		#if (course.title =="Cmpt165 "):
		#	print "exam conflict Cmpt 165"
		return True
	else:
    		if checkCourseTimeConflict(course, schedule) == True:
			#print "Course checkCourseTimeConflict conflict" +	course.title
			#if (course.title =="Cmpt165"):
			#	print "checkCourseTimeConflict conflict Cmpt 165"
	    		return True
	return False

#check to see if the coures conflicts with the schedule
def checkCourseTimeConflict(course, schedule):
	campus = course.campus

    	for i in range (0, len(course.meetingTimes)):
        	meetingTime = course.meetingTimes[i]
		#print "checkcourseconflict course title = " + str(course.title)
		#print "checkcourseconflict course id = " + str(course.courseID)
		#print "checkcourseconflict meetingtimes = " + str(course.meetingTimes)
       		#if (schedule.checkTimeWeekConflict(meetingTime.startTime, meetingTime.endTime, meetingTime.weekday) == True):
        	#if (schedule.checkTimeWeekConflictCampus(meetingTime.startTime, meetingTime.endTime, meetingTime.weekday, campus) == True):
		startTime = convertTimeToTimeSlot(meetingTime.start_time)
		endTime = convertTimeToTimeSlot(meetingTime.end_time)
		if (schedule.checkTimeWeekConflictCampus(startTime, endTime, meetingTime.weekday, campus) == True):
        	#print "I found a course conflict"
            		return True
    	return False

def courseExamConflict(course, listOfLockedCourses):
	#print "exam conflict for " + course.title
	#print "len of list of locked courses" + str(len(listOfLockedCourses))	
	for i in range (0, len(listOfLockedCourses)):
	    	lockedCourse = listOfLockedCourses[i]
	    	for j in range (0, len(course.exams)):
	    		courseExam = course.exams[j]
			for k in range (0, len(lockedCourse.exams)):
		    		lockedCourseExam = lockedCourse.exams[k]
		    		if examConflict(courseExam, lockedCourseExam) == True:
					return True
	return False

#Checks if there is a conflict between two lists of meeting times
def meetingTimesListConflict(firstListOfMeetingTimes, secondListOfMeetingTimes):
	for i in range (0, len(firstListOfMeetingTimes)):
	    	meetingTimeOne = firstListOfMeetingTimes[i]
	    	for j in range (0, len(firstListOfMeetingTimes)):
	    		meetingTimeTwo = secondListOfMeetingTimes[j]
			#This function works for all courses
	    		if meetingTimesConflict(meetingTimeOne, meetingTimeTwo) == True:
				return True
	return False

#meeting Times conflict checker that also tells which meetingTimse conflict with which meeting Times
def meetingTimesNewTimesOldTimesFilter(newTimesList, oldTimesList):
	listOfNonConflictingNewTimes = []
	#For each new time 
	for i in range (0, len(newTimesList)):
	    	newTime = newTimesList[i]
		if meetingTimeConflictWithList(newTime, oldTimesList) == False:
			listOfNonConflictingNewTimes.append(newTime)
	return listOfNonConflictingNewTimes

#Checks if a meeting time conflicts with a list of meeting time
def meetingTimeConflictWithList(meetingTimeOne, meetingTimeList):
	for i in range (0, len(meetingTimeList)):
		meetingTimeTwo = meetingTimeList[i]
		if meetingTimesConflict(meetingTimeOne, meetingTimeTwo) == True:
			return True
	return False

#checks if two meeting times conflict
def meetingTimesConflict(firstMeetingTime, secondMeetingTime):
	if (firstMeetingTime.weekday == secondMeetingTime.weekday):
		if examConflict(firstMeetingTime, secondMeetingTime) == True:
			return True
		else:
			return False
	return False
		


#check if two courses have the same name
#also works for ... two lists of 
def examConflict(examOne, examTwo):
    	if datetimeconflict(examOne.start_day, examOne.end_day, examTwo.start_day, examTwo.end_day) == True:
		exam1StartTime = convertTimeToTimeSlot(examOne.start_time)
		exam1EndTime = convertTimeToTimeSlot(examOne.end_time)
		exam2StartTime = convertTimeToTimeSlot(examTwo.start_time)
		exam2EndTime = convertTimeToTimeSlot(examTwo.end_time)
		#if timeConflict(examOne.startTime, examOne.endTime, examTwo.startTime, examTwo.endTime) == True:
		if timeConflict(exam1StartTime, exam1EndTime, exam2StartTime, exam2EndTime) == True:
			#print "examConflict()..."
	    		return True
		else:
	    		return False
    	else:
		return False   




#locks a course into the schedule
#(time is locked and the course is added to locked courses)
def lockCourse(course, schedule, poolOfPotentialCourses):
    	#print "Locking Course"
	if (checkCourseConflict(course, schedule) == False):
        	#print "There is no course Conflict for lock"
        	# lock the course
		campus = course.campus
		#print "lockCourse - course campus = " + str(campus)
        	for i in range (0, len(course.meetingTimes)):
            		meetingTime = course.meetingTimes[i]
            		#print "Locking MeetingTime"
            		#schedule.lockMeetingTime(meetingTime.startTime, meetingTime.endTime, meetingTime.weekday)
			startTime = convertTimeToTimeSlot(meetingTime.start_time)
			endTime = convertTimeToTimeSlot(meetingTime.end_time)
	    		#schedule.lockMeetingTimeCampus(meetingTime.startTime, meetingTime.endTime, meetingTime.weekday, campus)
			schedule.lockMeetingTimeCampus(startTime, endTime, meetingTime.weekday, campus)
        	schedule.poolOfLockedCourses.append(course)
        	poolOfPotentialCourses.remove(course)
    	else:
		print "failed to lock course"

#unlocks the coures from the schedule (time is freed and the course is removed from locked courses)
def unlockCourse(course, schedule, poolOfPotentialCourses):
    #print "unlockingCourse"
    	if (checkCourseConflict(course, schedule) == True):
        	#print "There is a conflict for unlock"
        	# unlock/free the course
		campus = course.campus
        	for i in range (0, len(course.meetingTimes)):
            		meetingTime = course.meetingTimes[i]
			startTime = convertTimeToTimeSlot(meetingTime.start_time)
			endTime = convertTimeToTimeSlot(meetingTime.end_time)
	    		#schedule.unlockMeetingTimeCampus(meetingTime.startTime, meetingTime.endTime, meetingTime.weekday, campus)
			schedule.unlockMeetingTimeCampus(startTime, endTime, meetingTime.weekday, campus)
        	poolOfPotentialCourses.append(course)
        	schedule.poolOfLockedCourses.remove(course)

#sets the course without any additional overhead
def setCourse(course, schedule):
    	#print "Setting Course"
    	if (checkCourseConflict(course, schedule) == False):
        	#print "There is no conflict for set"
        	# Set the course
		campus = course.campus
        	for i in range (0, len(course.meetingTimes)):
            		meetingTime = course.meetingTimes[i]
            		#schedule.setMeetingTime(meetingTime.startTime, meetingTime.endTime, meetingTime.weekday)
			startTime = convertTimeToTimeSlot(meetingTime.start_time)
			endTime = convertTimeToTimeSlot(meetingTime.end_time)
			schedule.setMeetingTimeCampus(startTime, endTime, meetingTime.weekday, campus)
	    		#schedule.setMeetingTimeCampus(meetingTime.startTime, meetingTime.endTime, meetingTime.weekday, campus)

#frees the course with updating the respective list of courses
def freeCourse(course, schedule):
    	#print "freeingupcourse"
	#print "There is a conflict for unlock"    	
	#print "There is no conflict"
        # unlock/free the course
	campus = course.campus
        for i in range (0, len(course.meetingTimes)):
		meetingTime = course.meetingTimes[i]
            	#schedule.unlockMeetingTime(meetingTime.startTime, meetingTime.endTime, meetingTime.weekday)
		startTime = convertTimeToTimeSlot(meetingTime.start_time)
		endTime = convertTimeToTimeSlot(meetingTime.end_time)
            	#schedule.unlockMeetingTimeCampus(meetingTime.startTime, meetingTime.endTime, meetingTime.weekday, campus)
		schedule.unlockMeetingTimeCampus(startTime, endTime, meetingTime.weekday, campus)


#find all courses that currently conflict with our schedule and remove them from the list of potential courses
def updateCleanPotentialCourses(poolOfPotentialCourses, schedule):
    	listOfCoursesToDelete = []
    #build a list of courses for us to remove
    	for i in range (0, len(poolOfPotentialCourses)):
        	courseWeCheckOut = poolOfPotentialCourses[i]
        	if checkCourseConflict(courseWeCheckOut, schedule) == True:
            		listOfCoursesToDelete.append(courseWeCheckOut)
    #and remove them
    	for i in range (0, len(listOfCoursesToDelete)):
       		courseToDelete = listOfCoursesToDelete[i]
        	poolOfPotentialCourses.remove(courseToDelete)
		schedule.poolOfCutCourses.append(courseToDelete)
		#print "removing course from update"
		#print "Coruse name == " + courseToDelete.title
		#print "courseOne.title == " + courseOne.title
		#print "courseTwo.title == " + courseTwo.title

#check if two courses have the same name
def courseNameConflict(courseOne, courseTwo):
	if courseOne.title == courseTwo.title:
		#print "course Name conflict"
		#print "courseOne.title == " + courseOne.title
		#print "courseTwo.title == " + courseTwo.title
		return True
	else:
		return False
    
#Eliminates all duplicate courses 
def eliminateDuplicateCourses(poolOfPotentialCourses, schedule):
    	listOfCoursesToDelete = []
   	#build a list of courses for us to remove
    	for i in range (0, len(poolOfPotentialCourses)):	
		for j in range (0, len(schedule.poolOfLockedCourses)):
	    		if courseNameConflict(poolOfPotentialCourses[i], schedule.poolOfLockedCourses[j]) == True:
				listOfCoursesToDelete.append(poolOfPotentialCourses[i])
	
    	#and remove them
    	for i in range (0, len(listOfCoursesToDelete)):
        	courseToDelete = listOfCoursesToDelete[i]
        	poolOfPotentialCourses.remove(courseToDelete)
		#poolOfCutCourses.append(courseToDelete)



#This is the central algorithm
# it requires:
	#pool of courses the user is interested in
	#pool of locked courses for a schedule
	#a "schedule" object to handle the time grid
	#the number of courses a student wants to take
def iterateBEHEMOTH(schedule, poolOfPotentialCourses, maxSize):
	print "Iterate Behemoth"    	
	if len(schedule.poolOfLockedCourses) < maxSize:
		#print "interBehe We have the right size"
		#print "len len(poolOfPotentialCourses) = " + str(len(poolOfPotentialCourses))
        	orignialTimeGap = schedule.getTotalTimeGap()
        	originalNumberDays =  schedule.getTotalDays()
		eliminateDuplicateCourses(poolOfPotentialCourses, schedule)
		#print "Post eliminateDuplicateCourses len(poolOfPotentialCourses) = " + str(len(poolOfPotentialCourses))
        	updateCleanPotentialCourses(poolOfPotentialCourses, schedule)
		#print "Post updateCleanPotentialCourses len(poolOfPotentialCourses) = " + str(len(poolOfPotentialCourses))
		#i.e. if are taking cmpt 300 already... it will delete any other mentions of cmpt 300 from the potential list
        	
        	choiceStatsList = []
		#print "new len(poolOfPotentialCourses) = " + str(len(poolOfPotentialCourses))
        	if len(poolOfPotentialCourses) >= 2:
			#print "Behemoth PotentialCourses >=2"
            		#Gather information on all possible choices:
	    		#First temporarily add the course to the schedule and gather stats about the new schedule
            		for i in range (0, len(poolOfPotentialCourses)):
                	#schedule.clearSchedule()
                		courseWeTryToAdd = poolOfPotentialCourses[i]
                		setCourse(courseWeTryToAdd, schedule)
            
                		newTotalDays = schedule.getTotalDays()
                		newTotalTimeGap = schedule.getTotalTimeGap()
				newCrossCampusTravels = schedule.getTotalCrossCampusTravels()
                		currentChoiceStats = ChoiceStats(newTotalDays, newTotalTimeGap, newCrossCampusTravels)
               			choiceStatsList.append(currentChoiceStats)
                		#free certain course
                		freeCourse(courseWeTryToAdd, schedule)
                		#schedule.clearSchedule()

            		#try to make the best decision as to which course we should lock
            		currentPositionOfChoice = 0
            		currentBestChoiceStats = choiceStatsList[currentPositionOfChoice]

            		#evaluate the stats of all potential courses we can add, and add the course that has the best stats
            		for i in range (1, len(poolOfPotentialCourses)):
                		currentChoiceStats = choiceStatsList[i]
                		# find the best course
                		if currentChoiceStats.numberOfDays <= currentBestChoiceStats.numberOfDays:
                    			if currentChoiceStats.numberOfDays < currentBestChoiceStats.numberOfDays:
                        			currentBestChoiceStats = currentChoiceStats;
                        			currentPositionOfChoice = i;
                    			elif (currentChoiceStats.crossCampusTravels <= currentBestChoiceStats.crossCampusTravels):
						if (currentChoiceStats.crossCampusTravels < currentBestChoiceStats.crossCampusTravels):
                            				currentBestChoiceStats = currentChoiceStats
                            				currentPositionOfChoice = i
		    				elif (currentChoiceStats.totalGap < currentBestChoiceStats.totalGap):
                            				currentBestChoiceStats = currentChoiceStats
                            				currentPositionOfChoice = i
            		#get the Course that has risen above all others and solidify its position in the schedule
            		courseThatHasRisenAboveAllOthers = poolOfPotentialCourses[currentPositionOfChoice]
            		#also make sure to update here....
			#print "Locking course from len(potcourse) >=2"
            		lockCourse(courseThatHasRisenAboveAllOthers, schedule, poolOfPotentialCourses)

        	elif len(poolOfPotentialCourses) == 1:
            		onlyCourseOption = poolOfPotentialCourses[0]
			#print "Locking course from len(potcourse) ==1"
	    		lockCourse(onlyCourseOption, schedule, poolOfPotentialCourses)

	else:
		print "Maxed out on behe interation numbers"


#def handleUnavailableMeetingTimes(MeetingTimesListFromWebsite, schedule):
		
#	for i in range(0, len(MeetingTimes):
#		meetingTimeFromWebSite = MeetingTimesListFromWebsite[i]
		#day = convertTimeToTimeSlot(meetingTimeFromWebSite[0])
		#day = convertTimeToTimeSlot(meetingTimeFromWebSite[0])
		#def lockMeetingTime(self, startTime, endTime, weekday):
		#schedule.lockMeetingTime(startTime, endTime, weekday
	#convertTimeToTimeSlot
	#convertDayStringToDayInt

#Potentially obsolete code
#<MeetingTime: Monday - 10:30:00 to 12:20:00>
#parse string and turn it into a meetingtime
# same funcitonality of convertModelMeetingTimeToScheduleMeetingTime but ... instead uses a string instead of a 
def convertStringToMeetingTime(inputString):
    stringArray = shlex.split(inputString)
    #['<MeetingTime:', 'Monday', '-', '10:30:00', 'to', '12:20:00>']
    dayInteger = convertDayStringToDayInt(stringArray[1])
    #startTime = convertStringToTime(stringArray[3])
    startSlot = convertTimeToTimeSlot(startTime)
    endString = stringArray[5][:-1]
    endTime = convertStringToTime(endString)
    endSlot = convertTimeToTimeSlot(endTime)
    meetingTime = SchedulingMeetingTime(startSlot, endSlot, dayInteger)
    return meetingTime

def convertDayStringToDayInt(inputString):
    if inputString == "Monday":
        return 0
    elif inputString == "Tuesday":
        return 1
    elif inputString == "Wednesday":
        return 2
    elif inputString == "Thursday":
        return 3
    elif inputString == "Friday":
        return 4
    elif inputString == "Saturday":
        return 5
    elif inputString == "Sunday":
        return 6

#converts a meeting time from the table into a meeting time object that we can use it in the scheduling algorithm
#Converts : meeting time from database --> meetingtime usable by scheduler
def convertModelMeetingTimeToScheduleMeetingTime(inputMeetingTime):   
	dayInteger = int(inputMeetingTime.weekday)
	startTime = inputMeetingTime.start_time
	startSlot = convertTimeToTimeSlot(startTime)
  	endTime = inputMeetingTime.end_time
  	endSlot = convertTimeToTimeSlot(endTime)
  	startDate = inputMeetingTime.start_day
  	endDate = inputMeetingTime.end_day
  	meetingType = inputMeetingTime.type
	meetingID = inputMeetingTime.id
  	outputMeetingTime = SchedulingMeetingTime(startSlot, endSlot, dayInteger, startDate, endDate, meetingType, meetingID)
  	return outputMeetingTime



