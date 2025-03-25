import arcpy
import sys
import os
import operator
import csv
from os.path import split, join
from string import replace
from datetime import datetime
arcpy.env.overwriteOutput = True

#..............................................................................................................................
# Creator - Seth Docherty
#
#   Helper functions for the Budding GDB toolset.  Make sure this script is called
#   to import all functions.
#
#..............................................................................................................................

def Add_Records_to_Table(input_list, table_path):
    '''
    Add data from a list to a blank ArcGIS Table.

    Required input:
        Python list
        Path to ArcGIS table

    *Note*
    Table should be empty before adding data to it.
    '''
    input_fields = Extract_Field_Name(table_path)
    if "GLOBALID" in input_fields:
        input_fields.remove('GLOBALID')
    with arcpy.da.InsertCursor(table_path, input_fields) as iCursor:
        for id, row in enumerate(input_list):
            row.insert(0,id)
            try:
                row = [x if x else None for x in row] #TODO Look into adding a continue statement for the else statement.
            except:
                print "Ran in to a Problem adding the following row to the table... {}: Likely an issues with text format i.e. unicode encoding problem. Try fixing the items and run the script again.".format(row)
            iCursor.insertRow(row)

                
def buildWhereClause(table, field, value):
    """Constructs a SQL WHERE clause to select rows having the specified value
    within a given field and table (or Feature Class)."""

    # Add DBMS-specific field delimiters
    fieldDelimited = arcpy.AddFieldDelimiters(table, field)

    # Determine field type
    fieldType = arcpy.ListFields(table, field)[0].type

    ## Add single-quotes for string field values
    invalid_vals = ['NULL',"''"]
    value = value.strip("'")
    if str(fieldType) == 'String' and value not in invalid_vals:
        value = "'{}'".format(value)

    # Format WHERE clause
    if value == "NULL":
        whereClause = "{} IS {}".format(fieldDelimited, value)
    else:
        whereClause = "{} = {}".format(fieldDelimited, value)
    return whereClause


def Create_Empty_Table(input_field_info, table_name, path):
    '''
    Create an empty table with from a list of input fields.

    Required input:
        List of field information - [Field Name, Field Type, Field Length] *Must be in this order
        Name of table to be created
        Path of workspace where table will be saved to.
    '''
    tmp_table = os.path.join('in_memory', 'table_template')
    arcpy.management.CreateTable(*os.path.split(tmp_table))
    for field in input_field_info:
        arcpy.AddField_management(tmp_table,field[0], field_type=field[1], field_length=field[2])
    # Create the actual output table.
    try:
        arcpy.CreateTable_management(path, table_name, template=tmp_table)
    except:
        print ("Unable to create table since it already exists at '{}'. "
                "Please close out of the ArcMap and/or ArcCatalog session that may be accessing the table, '{}' "
                "and re-run the script").format(path, table_name)
        arcpy.AddWarning(("Unable to create table since it already exists at '{}'. "
                "Please close out of the ArcMap and/or ArcCatalog session that may be accessing the table, '{}' "
                "and re-run the script").format(path, table_name))
        sys.exit()
    arcpy.Delete_management(tmp_table)


def Create_FL(LayerName, FCPath, expression = ''):
    '''
    Create a Feature layer from a feature class. Optionally, an expression clause can be passed in to
    filter out a subset of data.
    '''
    if arcpy.Exists(LayerName):
        arcpy.Delete_management(LayerName)
    try:
        if expression:
            return arcpy.MakeFeatureLayer_management(FCPath, LayerName, expression, "")
        else:
            return arcpy.MakeFeatureLayer_management(FCPath, LayerName, "", "")
    except:
        return arcpy.AddError(arcpy.GetMessages(2))


def Compare_Fields(fc1_path,fc2_path):
    fc1_fields = [field.name for field in arcpy.ListFields(fc1_path)]
    fc2_fields = [field.name for field in arcpy.ListFields(fc2_path)]
    if fc1_fields == fc2_fields:
        return True
    else:
        return False


def convert_invalid_values(input_list):
    '''
    Due to python script validation, <Null> values can not be populated in a value list since <Null> is a None type in python.
    In order to show <Null values in the value list, None type must be converted to a string so it can show up in the list
    and must be convereted back to a None type when the values are passed on. The same issue comes up with values = ''.  These values
    must be converted to ' ' and then back to ''.

    The dictionary below can be populated with additional invalid values.  These invalid values may need to be accounted for in the BuildWhereClause function.
    '''
    invalid_vals = {'NULL':'NULL', "' '":''}
    for val in invalid_vals.keys():
        if val in input_list:    
            input_list.remove(val)
            input_list.append(invalid_vals[val])
    return input_list


def csv_to_table(input_csv, input_fc, selection_fields, ParentField,scratch_gdb):
    # Getting Filepath/name of input csv/fc
    csv_path, csv_name = InputCheck(input_csv)
    fc_path, fc_name = InputCheck(input_fc)
    
    #Extracting CSV stuff
    csv_list = Extract_File_Records(csv_path,"No")
    header = Space2Underscore(csv_list.pop(0))
    fields = Extract_input_fields_from_csv(selection_fields, ParentField, header)
    field_index = get_column_index(header,fields)
    csv_list = extract_list_columns(csv_list, field_index, "No")

    #Creating blank table and appending csv list
    name = "csv2table_temp"
    header_fieldInfo = get_Data_Type_FromGIS(fields, fc_path)
    Create_Empty_Table(header_fieldInfo, name, scratch_gdb)
    Add_Records_to_Table(csv_list, os.path.join(scratch_gdb, name))
    return os.path.join(scratch_gdb, name)
   

def Delete_Values_From_FC(values_to_delete, key_field, FC, FC_Path):
    FC = str(FC) + "_Layer"
    Create_FL(FC,FC_Path,"")
    What_to_Delete = []

    if not values_to_delete:
        print "No features were selected to be deleted"
        arcpy.AddMessage("No features were selected to be deleted")
    else:
        values_to_delete = values_to_delete.split(";")
        values_to_delete = convert_invalid_values(values_to_delete)
        for value in values_to_delete:
            arcpy.AddMessage("Deleting the following from {}...........................{}".format(FC,value))
            print "Deleting the following from {}...........................{}".format(FC,value)
            clause = buildWhereClause(FC_Path, key_field, value)
            arcpy.SelectLayerByAttribute_management(FC, "NEW_SELECTION", clause)
            arcpy.DeleteRows_management(FC)
    arcpy.Delete_management(FC)


def Extract_Field_Name(fc):
    '''
    Return a list of fields name from a FC.
    '''
    fields = [f.name for f in arcpy.ListFields(fc)]
    return fields


#Extract field name and type
def Extract_Field_NameType(fc):
    field_info=[]
    for field in arcpy.ListFields(fc):
        if field.name == 'Shape' or field.name == 'Shape_Length' or field.name == 'OBJECTID' or field.name == 'RID':
            pass
        else:
            item=[]
            item.append(field.name)
            item.append(field.type)
            field_info.append(item)
    return field_info


#Load a .csv file and that is convereted into a list of tuples
def Extract_File_Records(filename, tuple_list=''):
    fp = open(filename, 'Ur')
    data_list = []
    for line in fp:#reader:
        if not tuple_list:
            data_list.append(tuple(line.strip().split(',')))
        else:
            data_list.append(line.strip().split(','))
    fp.close()
    return data_list


def extract_list_columns(input_list,index_list, tuple_list=''):
    my_items = operator.itemgetter(*index_list)
    new_list = [my_items(x) for x in input_list]
    if not tuple_list:
        return new_list
    else:
        new_list = [list(item) for item in new_list]
        return new_list
    

#Load a ArcMap table and that is convereted into a list of tuples
def Extract_Table_Records(fc, fields=''):
    if fields: # User has provided a list of fields for extraction
        records=[]
        with arcpy.da.SearchCursor(fc, fields) as cursor:
            for row in cursor:
                records.append(row)
        return records
    else: #User has not provided a list. Will default to all fields.
        fields = Remove_DBMS_Specific_Fields(fc)
        records=[]
        with arcpy.da.SearchCursor(fc, fields) as cursor:
            for row in cursor:
                records.append(row)
        return records


def Extract_input_fields_from_csv(selection_fields, ParentField, header):
    input_fields = list()
    field_selection = selection_fields.split(";")
    for field in field_selection:
        if field in header:
            input_fields.append(field)
    if not input_fields:
        arcpy.AddError("None of the user selected fields to update are in the csv document")
        sys.exit()
    input_fields.append(ParentField)
    #if FigureExtentField:
    #    input_fields.append(FigureExtentField)
    return input_fields


#Find out if a Feature Class exists
def FC_Exist(FCname, DatasetPath, Template):
    FCpath = os.path.join(DatasetPath,FCname)
    FCtype = arcpy.Describe(Template).shapeType
    if arcpy.Exists(FCpath):
        if Compare_Fields(FCpath,Template):
            arcpy.AddMessage("Feature class, {}, already exists. Clearing records.......".format(FCname))
            try:
                arcpy.TruncateTable_management(FCpath)
            except:
                arcpy.DeleteRows_management(FCpath)
        else:
            arcpy.AddMessage("Additional fields have been added since the Feature class, {}, was created. Recreating Feature class.......".format(FCname))
            arcpy.Delete_management(FCpath)
            return arcpy.CreateFeatureclass_management(DatasetPath, FCname, FCtype, Template, "SAME_AS_TEMPLATE", "SAME_AS_TEMPLATE", Template)
    else:
        arcpy.AddMessage("Feature class, {}, does not exist. Creating now.......".format(FCname))
        return arcpy.CreateFeatureclass_management(DatasetPath, FCname, FCtype, Template, "SAME_AS_TEMPLATE", "SAME_AS_TEMPLATE", Template)


def FieldExist(FC,field_to_check):
    fields = [field.name for field in arcpy.ListFields(FC)]
    if field_to_check in fields:
      return True
    else:
      return False

def Find_New_Features(Layer_To_Checkp, Initial_Checkp, Intermediate_Checkp, Final_Check, clause, in_count):
    #Make Feature Layer output names for all FC of interest and then run make feature layer tool
    Layer_To_Check = arcpy.Describe(Layer_To_Checkp).name+"_layer"
    Initial_Check = arcpy.Describe(Initial_Checkp).name +"_layer"
    Intermediate_Check = arcpy.Describe(Intermediate_Checkp).name +"_layer"

    Create_FL(Layer_To_Check, Layer_To_Checkp, clause)
    Create_FL(Initial_Check, Initial_Checkp, clause)
    Create_FL(Intermediate_Check, Intermediate_Checkp, clause)

    #Select all features in the in bucket layer and append to temporary point check FC
    arcpy.SelectLayerByLocation_management(Initial_Check, "INTERSECT", Initial_Check, "", "NEW_SELECTION")
    arcpy.Append_management(Initial_Check, Intermediate_Check,"NO_TEST","","")
    #Select all samples in the Report Sample FC
    arcpy.SelectLayerByLocation_management(Layer_To_Check, "INTERSECT", Layer_To_Check, "", "NEW_SELECTION")
    #Select Features from Bucket FC that intersect the Report Sample FC and invert
    arcpy.SelectLayerByLocation_management(Intermediate_Check, "INTERSECT", Layer_To_Check, "", "NEW_SELECTION")
    arcpy.SelectLayerByLocation_management(Intermediate_Check, "INTERSECT", Intermediate_Check, "", "SWITCH_SELECTION")
    arcpy.AddMessage("Selecting the new features that fall inside the figure")
    print "Selecting the new features that fall inside the figure"
    #Append selected features to Report Sample Location FC
    arcpy.Append_management(Intermediate_Check, Final_Check,"NO_TEST","","")
    out_count = int(arcpy.GetCount_management(Final_Check).getOutput(0))
    print "Number of new features found in the figure: " + str(out_count - in_count)
    arcpy.AddMessage("Number of new features found in the figure: " + str(out_count - in_count))
    arcpy.AddMessage("Added the new features to " + Final_Check)
    print "Added the new features to " + Final_Check
    return out_count

##    #Search for locations that are intersect existing points.
##    FigureGeometryCheck(Layer_To_Checkp, Initial_Checkp, Final_Checkp,clause)

    #Delete Feature Layers
    arcpy.Delete_management(Intermediate_Check)
    arcpy.Delete_management(Initial_Check)
    arcpy.Delete_management(Layer_To_Check)


def make_unicode(input):
    if type(input) != unicode:
        input = unicode(input, "utf-8")
        #input =  input.decode('utf-8')
        return input
    else:
        return input

def fix_unicode(data):
    if isinstance(data, unicode):
        return data.encode('utf-8')
    elif isinstance(data, dict):
        data = dict((fix_unicode(k), fix_unicode(data[k])) for k in data)
    elif isinstance(data, list):
        for i in xrange(0, len(data)):
            data[i] = fix_unicode(data[i])
    return data


def get_column_index(row_header,fields):
    '''
    Return a dictionary of field names as keys and the mapped column index for the field as the dictionary value.
    '''
    index_list = list()
    for field in fields:
        try:
            index_list.append(row_header.index(field))
        except ValueError:
            arcpy.AddMessage(("{} does not exist in the header field list. Please make sure field is spelled correctly and in the header row.\n "
                            "Exiting script.  Please correct errors and try again.").format(field))
            print ("{} does not exist in the header field list. Please make sure field is spelled correctly and in the header row.\n "
                            "Exiting script.  Please correct errors and try again.").format(field)
            sys.exit()
    return index_list


def get_csv_headers(input_path):
    with open(input_path, "rb") as f:
        reader = csv.reader(f)
        header_fields = reader.next()
    return header_fields
 

def get_Data_Type_FromGIS(input_fields, path):
    '''
    Return a list of pertinent field information for a list of fields from a user specfied Feature Class or Table.
    The return list contains:
        - Field Name
        - Field Type
        - Field Length

    Requried Inputs:
        List of input fields.
        Path to Feature class or Table

    *NOTE*
    The fields in the list must be present in the feature class or table.
    '''
    allFields = arcpy.ListFields(path)
    # List Formt: [Field Name (0), Field Type (1), Field Length (2)]
    field_info = []
    for in_field in input_fields:
        for field in allFields:
            if field.name == in_field:
                temp = []
                temp.append(field.name)
                temp.append(field.type)
                temp.append(field.length)
                field_info.append(temp)
    return field_info


def Get_Field_Type(fc,field_to_check):
    fields = [[field.name,field.type] for field in arcpy.ListFields(fc)]
    type = [type for field,type in fields if field_to_check == field][0]
    return type


def Get_Figure_List(FCpath, Keyfield, User_Selected_Figures):
    '''Get_Figure_List(FCpath, Keyfield, User_Selected_Figures)
    Return a list that contains that names of figures that user has selected to edit.  If user did not specify
    any figures in the tool parameters, a list of all figures will be returned.  The function will also return
    '''
    FigureList=[]
    if not User_Selected_Figures:
        FigureList = ListRecords(FCpath,Keyfield)
        arcpy.AddMessage(str(len(FigureList)) + " Figures are going to be updated")
    else:
        FigureList = [item.strip() for item in User_Selected_Figures.split(";")] #List Comprehension which splits delimited string and removes any qoutes that may be present in string.
        FigureList = [item.strip("'") for item in FigureList]
        arcpy.AddMessage(str(len(FigureList)) + " Figure(s) are going to be updated")
    return FigureList


def get_geodatabase_path(input_table):
  '''Return the Geodatabase path from the input table or feature class.
  :param input_table: path to the input table or feature class
  '''
  workspace = os.path.dirname(input_table)
  if [any(ext) for ext in ('.gdb', '.mdb', '.sde') if ext in os.path.splitext(workspace)]:
    return workspace
  else:
    return os.path.dirname(workspace)


#Check if there is a filepath from the input layers. If not, pre-pend the path. Also extract the FC names.
def InputCheck(Input_Layer):
    if arcpy.Exists(Input_Layer):
        InputPath = arcpy.Describe(Input_Layer).catalogPath #join(arcpy.Describe(Input_Layer).catalogPath,arcpy.Describe(Input_Layer).name)
        InputName = arcpy.Describe(Input_Layer).name
    else:
        arcpy.AddError("{} Does not exist".format(Input_Layer))
        sys.exit()
    return InputPath, InputName


#Pull out records and make lists. Final List that is returned to variable
def ListRecords(fc,fields):
    records=[]
    with arcpy.da.SearchCursor(fc,fields) as cursor:
        for row in cursor:
            records.append(row)
        FigureHolder=[]
        for FigureHolder in zip(*records):
            FigureHolder
    return FigureHolder


# Replace a layer/table view name with a path to a dataset (which can be a layer file) or create the layer/table view within the script
# The following inputs are layers or table views: "Report1_Sample_Locations"
def RecordCount(fc):
    count = int((arcpy.GetCount_management(fc)).getOutput(0))
    return count


#Remove default fields
def Remove_DBMS_Specific_Fields(fc):
    fields = [f.name for f in arcpy.ListFields(fc)]
    fields_to_remove = ['SHAPE_Area', 'SHAPE_Length', 'OBJECTID', 'GLOBALID', 'SHAPE', "RID"]
    for i,f in enumerate(fields):
        if f in fields_to_remove:
            del fields[i]
    return fields

def remove_space(fields):
    field_update=[]
    for field in fields:
        if field.find(" ") > 0:
            x=field.replace(' ','_')
            field_update.append(x)
        else:
            field_update.append(field)
    return field_update

def remove_underscore(fields):
    field_update=[]
    for field in fields:
        if field.find("_") > 0:
            x=field.replace('_',' ')
            field_update.append(x)
        else:
            field_update.append(field)
    return field_update

def start_edit_session(fc_to_edit):
    # Start an edit session. Must provide the worksapce.
    workspace = get_geodatabase_path(fc_to_edit)
    edit = arcpy.da.Editor(workspace)
    # Edit session is started without an undo/redo stack for versioned data and starting edit operation
    #  (for second argument, use False for unversioned data)
    edit.startEditing(False, False)
    edit.startOperation()
    return edit

def stop_edit_session(edit):
    # Stop the edit session and save the changes
    edit.stopOperation()
    edit.stopEditing(True)
    

def Select_and_Append(feature_selection_path, select_from_path, append_path, clause=''):
    Create_FL("Feature_Selection", feature_selection_path, clause)
    Create_FL("Select_From", select_from_path, clause)
    arcpy.SelectLayerByLocation_management("Feature_Selection", "INTERSECT", "Feature_Selection", "", "NEW_SELECTION")
    arcpy.SelectLayerByLocation_management("Select_From", "INTERSECT", "Feature_Selection", "", "NEW_SELECTION")
    arcpy.Append_management("Select_From", append_path, "NO_TEST", "", "")

    print "Selecting features from {} that intersect {} \nSelected features were appened to {}".format(os.path.basename(feature_selection_path),os.path.basename(select_from_path),os.path.basename(append_path))
    arcpy.AddMessage("Selecting features from {} that intersect {} \nSelected features were appened to {}".format(os.path.basename(feature_selection_path),os.path.basename(select_from_path),os.path.basename(append_path)))

    arcpy.Delete_management("Feature_Selection")
    arcpy.Delete_management("Select_From")


def Space2Underscore(fields):
    '''
    Replace spaces in strings with an underscore.
    This is intended for header fields from that need to be compared against fields in ArcGIS.
    '''
    field_update=[]
    for field in fields:
        if field.find(" ") > 0:
            x=field.replace(' ','_')
            field_update.append(x)
        else:
            field_update.append(field)
    return field_update


def unique_values(fc,field):
    with arcpy.da.SearchCursor(fc,[field])as cur:
        return sorted({row[0] for row in cur})

# TODO

#def FigureGeometryCheck(fc1,fc2,fc3,expression):
#	fc1_lyr1 = "lyr1"
#	fcl_lyr2 = "lyr2"
#	fcl_lyr3 = "lyr3"
#	Create_FL(fc1_lyr1,fc1,expression)
#	Create_FL(fcl_lyr2,fc2,expression)
#	Create_FL(fcl_lyr3,fc3,expression)
#	fc1_count = RecordCount(fc1_lyr1)
#	fc2_count = RecordCount(fcl_lyr2)
#	field = "Location_ID"
#	if fc1_count == fc2_count:
#		pass
#	else:
#		fc1_list = unique_values(fc1_lyr1,field)
#		fc2_list = unique_values(fcl_lyr2,field)
#		fc3_list = unique_values(fcl_lyr3,field)
#		difference = list(set(fc2_list) - set(fc1_list)- set(fc3_list))
#		if len(difference) != 0:
#			print str(len(difference)) + " additional locations have been found that intersect previous locations that are in the figure. They are:\n"
#			arcpy.AddMessage(str(len(difference)) + " additional locations have been found that intersect previous locations that are in the figure. They are:\n")
#			for record in difference:
#				clause =  '"' + field + '"' + " = '" + record + "'"
#				arcpy.SelectLayerByAttribute_management(fcl_lyr2,"ADD_TO_SELECTION",clause)
#				arcpy.AddMessage(str(record))
#				print str(record)
#			arcpy.Append_management(fcl_lyr2, fcl_lyr3,"NO_TEST","","")


#FigureGeometryCheck(Layer_To_Checkp, Initial_Checkp, Final_Checkp,clause)
#def Check_Coincident_Features(Layer_To_Check, Initial_Check, Final_Check):
       
#    #Get field names:
#    field1 = Remove_DBMS_Specific_Fields(Layer_To_Check) #[f.name for f in arcpy.ListFields(Layer_To_Checkp)]
#    field2 = Remove_DBMS_Specific_Fields(Final_Check) #[f.name for f in arcpy.ListFields(Final_Checkp)]
#    fields = list(set(field1)&set(field2))
#    fields.remove("SHAPE")

#    table1 = Extract_Table_Records(Layer_To_Checkp, fields)
#    table2 = Extract_Table_Records(Initial_Checkp, fields)
#    table3 = Extract_Table_Records(Final_Checkp, fields)
#    difference = list(set(table1) - set(table3) - set(table2))
    
#    if len(difference) != 0:
#        arcpy.AddMessage("{} features have been found which were coincident".format(len(difference)))
#        #arcpy.Append_management()

    #append difference to final check