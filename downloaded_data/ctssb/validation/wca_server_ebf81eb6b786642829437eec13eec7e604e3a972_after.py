from tables.base_table_class import Base_Table

class HOUSEHOLD_TYPE_SIZE_Table(Base_Table):

	table_name = "HOUSEHOLD_TYPE_SIZE"

	def __init__(self) :
		self.table_name = HOUSEHOLD_TYPE_SIZE_Table.table_name
		self.columns = Base_Table.columns + ["Family households","2-person 1","3-person 1","4-person 1","5-person 1","6-person 1","7-or-more person 1","Nonfamily households","1-person 2","2-person 2","3-person 2","4-person 2","5-person 2","6-person 2","7-or-more person 2","Total households","1-person 3","2-person 3","3-person 3","4-person 3","5-person 3","6-person 3","7-or-more person 3"]
		self.table_extra_meta_data = Base_Table.table_extra_meta_data
		self.initalize()

	def getInsertQueryForCSV(self, csvFile, fromYear, toYear) :
		skipCount = 0
		insertDataQuery = """INSERT INTO `{0}` VALUES """.format(self.table_name)
		for line in csvFile:
			row = line.split(",")
			if (skipCount < Base_Table.num_of_rows_to_leave) :
				skipCount += 1
				continue

			defaultQuery = self.getIDAndYearQueryForRow(row, fromYear, toYear)
			dataQuery = "%d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, \
                       %d, %d, %d, %d, %d, %d, %d" %(int(row[4]), #B
										int(row[5]), #C
										int(row[6]), #D
                                                         int(row[7]), #E
										int(row[8]), #F
                                                         int(row[9]), #G
										int(row[10]), #H
                                                         int(row[11]), #I
										int(row[12]), #J
                                                         int(row[13]), #K
										int(row[14]), #L
                                                         int(row[15]), #M
										int(row[16]), #N
                                                         int(row[17]), #O
										int(row[18]), #P
                                                         int(row[3]), #Q
										int(row[12]), #R
                                                         int(row[5])+int(row[13]), #S
										int(row[6])+int(row[14]), #T
                                                         int(row[7])+int(row[15]), #U
										int(row[8])+int(row[16]), #V
                                                         int(row[9])+int(row[17]), #W
										int(row[10])+int(row[18])) #X
			insertDataQuery += "(" + defaultQuery + dataQuery + "),"

		insertDataQuery = insertDataQuery[:-1]
		insertDataQuery += ";"
		return insertDataQuery
