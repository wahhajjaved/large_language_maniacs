import datetime
import glob
import logging
import netCDF4
import numpy as np
import os
import re
import sys
import time
import urllib
import urllib2
from multiprocessing import Pool
from ordereddict import OrderedDict

#destinationDir = './'
destinationDir = '/nodc/data/tmp.23555/'

def create_output_dirs():
    logging.basicConfig(level=logging.DEBUG, filename='./errors.log')
    if not os.path.exists(destinationDir + 'netcdf/'):
        os.makedirs(destinationDir + 'netcdf/')


class GHCN:
    """Program to convert GHCN daily files to netCDF; source files and information can be found here ftp://ftp.ncdc.noaa.gov/pub/data/ghcn/daily"""
    """thomas.jaensch@noaa.gov"""

    def __init__(self):
        # Lists and dictionaries with information from
        # ftp://ftp.ncdc.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt to be
        # used in netCDF variables derived with def get_stationInfo
        self.stationIds = []
        self.latDict = {}
        self.lonDict = {}
        self.elevationDict = {}
        self.stationLongNameDict = {}

    def get_station_info(self):
        # Alternatively https://www1.ncdc.noaa.gov/ OR ftp://ftp.ncdc.noaa.gov/
        data = urllib2.urlopen(
            "https://www1.ncdc.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt")
        for line in data:
            if not line:
                break
            # Get station IDs as substrings from each line in source file, etc.
            self.stationIds.append(line[0:11])
            self.latDict[line[0:11]] = line[12:20]
            self.lonDict[line[0:11]] = line[21:30]
            self.elevationDict[line[0:11]] = line[31:37]
            self.stationLongNameDict[line[0:11]] = re.sub(r'[^\x00-\x7f]', r'', line[38:71].strip())

        return self.stationIds

    def download_dly_file(self, fileId):
        try:
            # Alternatively https://www1.ncdc.noaa.gov/ OR
            # ftp://ftp.ncdc.noaa.gov/
            url = 'https://www1.ncdc.noaa.gov/pub/data/ghcn/daily/all/%s.dly' % fileId
            urllib.urlretrieve(url, fileId + '.txt')
        except KeyboardInterrupt:
            print(sys.exc_info()[0])
        except:
            logging.exception(fileId)
        finally:
            pass

    def make_subdir_based_on_file_name(self, fileId):
        dirName = fileId[:7]
        if not os.path.exists(destinationDir + 'netcdf/' + dirName):
            os.makedirs(destinationDir + 'netcdf/' + dirName)
        return dirName

    def dly_file_has_been_updated(self, fileId):
        from datetime import datetime, timedelta
        # Get yesterday's date as e.g. '201605' (Year/Month)
        yesterday = datetime.strftime(datetime.now() - timedelta(1), '%Y%m')
        if yesterday in open('%s.txt' % fileId).read():
            return True
        else:
            return False

    def delete_txt_file(self, fileId):
        os.remove(fileId + '.txt')

    def nc_file_exists(self, fileId):
        dirName = fileId[:7]
        if glob.glob(destinationDir + 'netcdf/' + dirName + '/*' + fileId + '.nc'):
            return True
        else:
            return False

    def rename_old_nc_file(self, fileId):
        dirName = fileId[:7]
        #print(glob.glob(destinationDir + 'netcdf/' + dirName + '/*' + fileId + '.nc')[0])
        os.rename(glob.glob(destinationDir + 'netcdf/' + dirName + '/*' + fileId + '.nc')[0], destinationDir + 'netcdf/' + dirName + '/ghcn-daily_v3.22.' + datetime.datetime.today().strftime('%Y-%m-%d') + '_' + fileId + '.nc')

    # Returns dictionary of unique time values
    def get_unique_time_values(self, fileId):
        uniqueTimeValues = set()
        try:
            with open(fileId + ".txt", "r") as file:
                for line in file:
                    # Loop over days of month in line
                    for i in range(1, 32):
                        try:
                            uniqueTimeValues.add(netCDF4.date2num(datetime.datetime(int(line[11:15]), int(
                                line[15:17]), i, 12, 0, 0), units='days since 1700-01-01 12:00:00', calendar='gregorian'))
                        except:
                            pass
                return dict(enumerate(list(sorted(uniqueTimeValues))))

        except KeyboardInterrupt:
            print(sys.exc_info()[0])
        except:
            logging.exception(fileId)
        finally:
            pass

    def get_time_index_for_day(self, line, dayIndex):
        # Initialize with first value of that line's month
        timeValue = netCDF4.date2num(datetime.datetime(int(line[11:15]), int(
            line[15:17]), 1, 12, 0, 0), units='days since 1700-01-01 12:00:00', calendar='gregorian')
        try:
            timeValue = netCDF4.date2num(datetime.datetime(int(line[11:15]), int(
                line[15:17]), dayIndex, 12, 0, 0), units='days since 1700-01-01 12:00:00', calendar='gregorian')
        except:
            return -1
        return timeValue

    # Find elements like "TMIN", "TMAX", etc.
    def get_unique_elements(self, fileId):
        uniqueElements = set()
        try:
            with open(fileId + ".txt", "r") as file:
                for line in file:
                    uniqueElements.add(line[17:21])
                return dict(enumerate(list(uniqueElements)))

        except KeyboardInterrupt:
            print(sys.exc_info()[0])
        except:
            logging.exception(fileId)
        finally:
            pass

    def initialize_element_lists_with_time_key_and_placeholder_value(self, fileId, dictOfUniqueTimeValues, uniqueElements):
        uniqueElementFlags = []
        for i in uniqueElements.values():
            w = i
            x = i + str('_mflag')
            y = i + str('_qflag')
            z = i + str('_sflag')
            uniqueElementFlags.append(w.lower())
            uniqueElementFlags.append(x.lower())
            uniqueElementFlags.append(y.lower())
            uniqueElementFlags.append(z.lower())
        placeholderElementsFlagsList = {}
        for item in uniqueElementFlags:
            if len(item) == 4:
                dict1 = {}
                for key, value in dictOfUniqueTimeValues.items():
                    dict1[key] = -9999
                placeholderElementsFlagsList[
                    item] = dict1
            else:
                dict2 = {}
                for key, value in dictOfUniqueTimeValues.items():
                    dict2[key] = ' '
                placeholderElementsFlagsList[
                    item] = dict2
        return placeholderElementsFlagsList

    def create_elements_flags_data_lists(self, fileId, uniqueTimeValuesDict, elementAndFlagDicts):
        try:
            with open(fileId + ".txt", "r") as file:
                # Loop over values of month in line according to III. here
                # ftp://ftp.ncdc.noaa.gov/pub/data/ghcn/daily/readme.txt
                for line in file:
                    # Determine the element of that line
                    element = line[17:21].lower()

                    # Add values to the placeholder lists inside of dictionary
                    # initialized at beginning of function

                    # VALUE1
                    timeIndex = self.get_time_index_for_day(
                        line, 1)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[21:26]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[26:27]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[27:28]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[28:29]

                    # VALUE2
                    timeIndex = self.get_time_index_for_day(
                        line, 2)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[29:34]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[34:35]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[35:36]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[36:37]

                    # VALUE3
                    timeIndex = self.get_time_index_for_day(
                        line, 3)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[37:42]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[42:43]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[43:44]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[44:45]

                    # VALUE4
                    timeIndex = self.get_time_index_for_day(
                        line, 4)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[45:50]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[50:51]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[51:52]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[52:53]

                    # VALUE5
                    timeIndex = self.get_time_index_for_day(
                        line, 5)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[53:58]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[58:59]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[59:60]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[60:61]

                    # VALUE6
                    timeIndex = self.get_time_index_for_day(
                        line, 6)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[61:66]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[66:67]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[67:68]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[68:69]

                    # VALUE7
                    timeIndex = self.get_time_index_for_day(
                        line, 7)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[69:74]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[74:75]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[75:76]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[76:77]

                    # VALUE8
                    timeIndex = self.get_time_index_for_day(
                        line, 8)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[77:82]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[82:83]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[83:84]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[84:85]

                    # VALUE9
                    timeIndex = self.get_time_index_for_day(
                        line, 9)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[85:90]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[90:91]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[91:92]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[92:93]

                    # VALUE10
                    timeIndex = self.get_time_index_for_day(
                        line, 10)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[93:98]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[98:99]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[99:100]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[100:101]

                    # VALUE11
                    timeIndex = self.get_time_index_for_day(
                        line, 11)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[101:106]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[106:107]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[107:108]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[108:109]

                    # VALUE12
                    timeIndex = self.get_time_index_for_day(
                        line, 12)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[109:114]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[114:115]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[115:116]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[116:117]

                    # VALUE13
                    timeIndex = self.get_time_index_for_day(
                        line, 13)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[117:122]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[122:123]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[123:124]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[124:125]

                    # VALUE14
                    timeIndex = self.get_time_index_for_day(
                        line, 14)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[125:130]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[130:131]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[131:132]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[132:133]

                    # VALUE15
                    timeIndex = self.get_time_index_for_day(
                        line, 15)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[133:138]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[138:139]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[139:140]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[140:141]

                    # VALUE16
                    timeIndex = self.get_time_index_for_day(
                        line, 16)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[141:146]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[146:147]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[147:148]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[148:149]

                    # VALUE17
                    timeIndex = self.get_time_index_for_day(
                        line, 17)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[149:154]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[154:155]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[155:156]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[156:157]

                    # VALUE18
                    timeIndex = self.get_time_index_for_day(
                        line, 18)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[157:162]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[162:163]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[163:164]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[164:165]

                    # VALUE19
                    timeIndex = self.get_time_index_for_day(
                        line, 19)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[165:170]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[170:171]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[171:172]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[172:173]

                    # VALUE20
                    timeIndex = self.get_time_index_for_day(
                        line, 20)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[173:178]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[178:179]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[179:180]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[180:181]

                    # VALUE21
                    timeIndex = self.get_time_index_for_day(
                        line, 21)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[181:186]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[186:187]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[187:188]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[188:189]

                    # VALUE22
                    timeIndex = self.get_time_index_for_day(
                        line, 22)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[189:194]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[194:195]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[195:196]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[196:197]

                    # VALUE23
                    timeIndex = self.get_time_index_for_day(
                        line, 23)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[197:202]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[202:203]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[203:204]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[204:205]

                    # VALUE24
                    timeIndex = self.get_time_index_for_day(
                        line, 24)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[205:210]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[210:211]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[211:212]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[212:213]

                    # VALUE25
                    timeIndex = self.get_time_index_for_day(
                        line, 25)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[213:218]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[218:219]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[219:220]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[220:221]

                    # VALUE26
                    timeIndex = self.get_time_index_for_day(
                        line, 26)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[221:226]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[226:227]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[227:228]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[228:229]

                    # VALUE27
                    timeIndex = self.get_time_index_for_day(
                        line, 27)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[229:234]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[234:235]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[235:236]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[236:237]

                    # VALUE28
                    timeIndex = self.get_time_index_for_day(
                        line, 28)
                    # Index where the line value needs to be inserted
                    indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                    )[uniqueTimeValuesDict.values().index(timeIndex)]
                    # Insert the actual values
                    elementAndFlagDicts[element][
                        indexInElementAndFlagDicts] = line[237:242]
                    elementAndFlagDicts[
                        element + '_mflag'][indexInElementAndFlagDicts] = line[242:243]
                    elementAndFlagDicts[
                        element + '_qflag'][indexInElementAndFlagDicts] = line[243:244]
                    elementAndFlagDicts[
                        element + '_sflag'][indexInElementAndFlagDicts] = line[244:245]

                    # VALUE29
                    timeIndex = self.get_time_index_for_day(
                        line, 29)
                    if timeIndex != -1:
                        # Index where the line value needs to be inserted
                        indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                        )[uniqueTimeValuesDict.values().index(timeIndex)]
                        # Insert the actual values
                        elementAndFlagDicts[element][
                            indexInElementAndFlagDicts] = line[245:250]
                        elementAndFlagDicts[
                            element + '_mflag'][indexInElementAndFlagDicts] = line[250:251]
                        elementAndFlagDicts[
                            element + '_qflag'][indexInElementAndFlagDicts] = line[251:252]
                        elementAndFlagDicts[
                            element + '_sflag'][indexInElementAndFlagDicts] = line[252:253]
                    else:
                        pass

                    # VALUE30
                    timeIndex = self.get_time_index_for_day(
                        line, 30)
                    if timeIndex != -1:
                        # Index where the line value needs to be inserted
                        indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                        )[uniqueTimeValuesDict.values().index(timeIndex)]
                        # Insert the actual values
                        elementAndFlagDicts[element][
                            indexInElementAndFlagDicts] = line[253:258]
                        elementAndFlagDicts[
                            element + '_mflag'][indexInElementAndFlagDicts] = line[258:259]
                        elementAndFlagDicts[
                            element + '_qflag'][indexInElementAndFlagDicts] = line[259:260]
                        elementAndFlagDicts[
                            element + '_sflag'][indexInElementAndFlagDicts] = line[260:261]
                    else:
                        pass

                    # VALUE31
                    timeIndex = self.get_time_index_for_day(
                        line, 31)
                    if timeIndex != -1:
                        # Index where the line value needs to be inserted
                        indexInElementAndFlagDicts = uniqueTimeValuesDict.keys(
                        )[uniqueTimeValuesDict.values().index(timeIndex)]
                        # Insert the actual values
                        elementAndFlagDicts[element][
                            indexInElementAndFlagDicts] = line[261:266]
                        elementAndFlagDicts[
                            element + '_mflag'][indexInElementAndFlagDicts] = line[266:267]
                        elementAndFlagDicts[
                            element + '_qflag'][indexInElementAndFlagDicts] = line[267:268]
                        elementAndFlagDicts[
                            element + '_sflag'][indexInElementAndFlagDicts] = line[268:269]
                    else:
                        pass
            return elementAndFlagDicts

        except KeyboardInterrupt:
            print(sys.exc_info()[0])
        except:
            logging.exception(fileId)
        finally:
            pass
    # End create_elements_flags_data_lists(self, fileId)

    def parse_to_netCDF(self, fileId, uniqueTimeValues, elementAndFlagDicts):
        # Get unique time values of file for time variable array
        uniqueTimeValues = uniqueTimeValues.values()

        # Get element and flag arrays and their values
        #elementAndFlagDicts = self.create_elements_flags_data_lists(fileId)

        print(fileId)
        try:
            # Empty lists for variables, more information here
            # ftp://ftp.ncdc.noaa.gov/pub/data/ghcn/daily/readme.txt
            ID = []
            YEAR = []
            MONTH = []

            # Fill lists with substring values 0-269 per record per line from
            # .dly file
            with open(fileId + ".txt", "r") as file:
                for line in file:
                    ID.append(line[0:11])
                    YEAR.append(line[11:15])
                    MONTH.append(line[15:17])

            # Create netcdf data object
            with netCDF4.Dataset(destinationDir + 'netcdf/' + self.make_subdir_based_on_file_name(fileId) + '/ghcn-daily_v3.22.' + datetime.datetime.today().strftime('%Y-%m-%d') + '_' + fileId + '.nc', mode="w", format='NETCDF4_CLASSIC') as ds:
                # Define dimensions
                ds.createDimension('time')
                ds.createDimension('station', 1)
                ds.createDimension('station_name_to_char', len(self.stationLongNameDict[fileId].strip()))
                ds.createDimension('station_id_to_char', 11)

                # Define variables
                ds.createVariable('time', 'd', ('time',))[
                    :] = np.array(uniqueTimeValues)[:]
                ds.variables['time'].long_name = 'Center time of day'
                ds.variables['time'].standard_name = 'time'
                ds.variables[
                    'time'].units = 'days since 1700-01-01 12:00:00'
                ds.variables['time'].axis = 'T'
                ds.variables['time'].calendar = 'gregorian'
                ds.variables['time'].coverage_content_type = 'coordinate'

                # The five core elements (ftp://ftp.ncdc.noaa.gov/pub/data/ghcn/daily/readme.txt)
                if 'prcp' in elementAndFlagDicts:
                    prcp = ds.createVariable('prcp', 'short', ('station', 'time',), fill_value=-9999)[
                        :] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['prcp'].values())][:]
                    ds.variables[
                        'prcp'].long_name = 'Precipitation (mm)'
                    ds.variables['prcp'].standard_name = 'precipitation_amount'
                    ds.variables['prcp'].units = 'mm'
                    ds.variables['prcp'].scale_factor = 0.1
                    ds.variables['prcp'].missing_value = -9999
                    ds.variables['prcp'].valid_min = 0
                    ds.variables['prcp'].valid_max = 15000
                    ds.variables[
                        'prcp'].coordinates = 'lat lon alt station_name'
                    ds.variables['prcp'].coverage_content_type = 'physicalMeasurement'
                    ds.variables[
                        'prcp'].ancillary_variables = 'prcp_mflag prcp_qflag prcp_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['prcp']
                except KeyError:
                    pass

                if 'snow' in elementAndFlagDicts:
                    snow = ds.createVariable('snow', 'short', ('station', 'time',), fill_value=-9999)[
                        :] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['snow'].values())][:]
                    ds.variables[
                        'snow'].long_name = 'Snowfall (mm)'
                    ds.variables['snow'].standard_name = 'snowfall_amount'
                    ds.variables['snow'].units = 'mm'
                    ds.variables['snow'].missing_value = -9999
                    ds.variables['snow'].valid_min = 0
                    ds.variables['snow'].valid_max = 20000
                    ds.variables[
                        'snow'].coordinates = 'lat lon alt station_name'
                    ds.variables['snow'].coverage_content_type = 'physicalMeasurement'
                    ds.variables[
                        'snow'].ancillary_variables = 'snow_mflag snow_qflag snow_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['snow']
                except KeyError:
                    pass

                if 'snwd' in elementAndFlagDicts:
                    snwd = ds.createVariable('snwd', 'short', ('station', 'time',), fill_value=-9999)[
                        :] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['snwd'].values())][:]
                    ds.variables[
                        'snwd'].long_name = 'Snow Depth (mm)'
                    ds.variables['snwd'].standard_name = 'snowfall_amount'
                    ds.variables['snwd'].units = 'mm'
                    ds.variables['snwd'].missing_value = -9999
                    ds.variables['snwd'].valid_min = 0
                    ds.variables['snwd'].valid_max = 20000
                    ds.variables[
                        'snwd'].coordinates = 'lat lon alt station_name'
                    ds.variables['snwd'].coverage_content_type = 'physicalMeasurement'
                    ds.variables[
                        'snwd'].ancillary_variables = 'snwd_mflag snwd_qflag snwd_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['snwd']
                except KeyError:
                    pass

                if 'tmax' in elementAndFlagDicts:
                    tmax = ds.createVariable('tmax', 'short', ('station', 'time',), fill_value=-9999)[
                        :] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['tmax'].values())][:]
                    ds.variables[
                        'tmax'].long_name = 'Maximum Temperature (degrees C)'
                    ds.variables['tmax'].standard_name = 'air_temperature'
                    ds.variables['tmax'].units = 'degrees_Celsius'
                    ds.variables['tmax'].scale_factor = 0.1
                    ds.variables['tmax'].missing_value = -9999
                    ds.variables['tmax'].valid_min = -500
                    ds.variables['tmax'].valid_max = 500
                    ds.variables[
                        'tmax'].coordinates = 'lat lon alt station_name'
                    ds.variables['tmax'].coverage_content_type = 'physicalMeasurement'
                    ds.variables[
                        'tmax'].ancillary_variables = 'tmax_mflag tmax_qflag tmax_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['tmax']
                except KeyError:
                    pass

                if 'tmin' in elementAndFlagDicts:
                    tmin = ds.createVariable('tmin', 'short', ('station', 'time',), fill_value=-9999)[
                        :] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['tmin'].values())][:]
                    ds.variables[
                        'tmin'].long_name = 'Minimum Temperature (degrees C)'
                    ds.variables['tmin'].standard_name = 'air_temperature'
                    ds.variables['tmin'].units = 'degrees_Celsius'
                    ds.variables['tmin'].scale_factor = 0.1
                    ds.variables['tmin'].missing_value = -9999
                    ds.variables['tmin'].valid_min = -500
                    ds.variables['tmin'].valid_max = 500
                    ds.variables[
                        'tmin'].coordinates = 'lat lon alt station_name'
                    ds.variables['tmin'].coverage_content_type = 'physicalMeasurement'
                    ds.variables[
                        'tmin'].ancillary_variables = 'tmin_mflag tmin_qflag tmin_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['tmin']
                except KeyError:
                    pass

                # The other elements (ftp://ftp.ncdc.noaa.gov/pub/data/ghcn/daily/readme.txt)
                if 'acmc' in elementAndFlagDicts:
                    acmc = ds.createVariable('acmc', 'short', ('station', 'time',), fill_value=-9999)[
                        :] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['acmc'].values())][:]
                    ds.variables[
                        'acmc'].long_name = 'Average cloudiness midnight to midnight from 30-second ceilometer data (percent)'
                    ds.variables['acmc'].standard_name = 'cloud_area_fraction'
                    ds.variables['acmc'].units = 'percent'
                    ds.variables['acmc'].missing_value = -9999
                    ds.variables['acmc'].valid_min = 0
                    ds.variables['acmc'].valid_max = 100
                    ds.variables[
                        'acmc'].coordinates = 'lat lon alt station_name'
                    ds.variables['acmc'].coverage_content_type = 'physicalMeasurement'
                    ds.variables[
                        'acmc'].ancillary_variables = 'acmc_mflag acmc_qflag acmc_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['acmc']
                except KeyError:
                    pass

                if 'acmh' in elementAndFlagDicts:
                    acmh = ds.createVariable('acmh', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['acmh'].values())][:]
                    ds.variables['acmh'].long_name = 'Average cloudiness midnight to midnight from manual observations (percent)'
                    ds.variables['acmh'].standard_name = 'cloud_area_fraction'
                    ds.variables['acmh'].units = 'percent'
                    ds.variables['acmh'].missing_value = -9999
                    ds.variables['acmh'].valid_min = 0
                    ds.variables['acmh'].valid_max = 100
                    ds.variables['acmh'].coordinates = 'lat lon alt station_name'
                    ds.variables['acmh'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['acmh'].ancillary_variables = 'acmh_mflag acmh_qflag acmh_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['acmh']
                except KeyError:
                    pass

                if 'acsc' in elementAndFlagDicts:
                    acsc = ds.createVariable('acsc', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['acsc'].values())][:]
                    ds.variables['acsc'].long_name = 'Average cloudiness sunrise to sunset from 30-second ceilometer data (percent)'
                    ds.variables['acsc'].standard_name = 'cloud_area_fraction'
                    ds.variables['acsc'].units = 'percent'
                    ds.variables['acsc'].missing_value = -9999
                    ds.variables['acsc'].valid_min = 0
                    ds.variables['acsc'].valid_max = 100
                    ds.variables['acsc'].coordinates = 'lat lon alt station_name'
                    ds.variables['acsc'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['acsc'].ancillary_variables = 'acsc_mflag acsc_qflag acsc_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['acsc']
                except KeyError:
                    pass

                if 'acsh' in elementAndFlagDicts:
                    acsh = ds.createVariable('acsh', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['acsh'].values())][:]
                    ds.variables['acsh'].long_name = 'Average cloudiness sunrise to sunset from manual observations (percent)'
                    ds.variables['acsh'].standard_name = 'cloud_area_fraction'
                    ds.variables['acsh'].units = 'percent'
                    ds.variables['acsh'].missing_value = -9999
                    ds.variables['acsh'].valid_min = 0
                    ds.variables['acsh'].valid_max = 100
                    ds.variables['acsh'].coordinates = 'lat lon alt station_name'
                    ds.variables['acsh'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['acsh'].ancillary_variables = 'acsh_mflag acsh_qflag acsh_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['acsh']
                except KeyError:
                    pass

                if 'awdr' in elementAndFlagDicts:
                    awdr = ds.createVariable('awdr', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['awdr'].values())][:]
                    ds.variables['awdr'].long_name = 'Average daily wind direction (degrees)'
                    ds.variables['awdr'].standard_name = 'wind_from_direction'
                    ds.variables['awdr'].units = 'degree'
                    ds.variables['awdr'].missing_value = -9999
                    ds.variables['awdr'].valid_min = 0
                    ds.variables['awdr'].valid_max = 360
                    ds.variables['awdr'].coordinates = 'lat lon alt station_name'
                    ds.variables['awdr'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['awdr'].ancillary_variables = 'awdr_mflag awdr_qflag awdr_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['awdr']
                except KeyError:
                    pass

                if 'awnd' in elementAndFlagDicts:
                    awnd = ds.createVariable('awnd', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['awnd'].values())][:]
                    ds.variables['awnd'].long_name = 'Average daily wind speed (meters per second)'
                    ds.variables['awnd'].standard_name = 'wind_speed'
                    ds.variables['awnd'].units = 'm s-1'
                    ds.variables['awnd'].scale_factor = 0.1
                    ds.variables['awnd'].missing_value = -9999
                    ds.variables['awnd'].valid_min = 0
                    ds.variables['awnd'].valid_max = 500
                    ds.variables['awnd'].coordinates = 'lat lon alt station_name'
                    ds.variables['awnd'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['awnd'].ancillary_variables = 'awnd_mflag awnd_qflag awnd_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['awnd']
                except KeyError:
                    pass

                if 'daev' in elementAndFlagDicts:
                    daev = ds.createVariable('daev', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['daev'].values())][:]
                    ds.variables['daev'].long_name = 'Number of days included in the multiday evaporation total (MDEV)'
                    ds.variables['daev'].standard_name = 'number_of_observations'
                    ds.variables['daev'].units = 1
                    ds.variables['daev'].missing_value = -9999
                    ds.variables['daev'].valid_min = 0
                    ds.variables['daev'].valid_max = 500
                    ds.variables['daev'].coordinates = 'lat lon alt station_name'
                    ds.variables['daev'].coverage_content_type = 'auxiliaryInformation'
                    ds.variables['daev'].ancillary_variables = 'daev_mflag daev_qflag daev_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['daev']
                except KeyError:
                    pass

                if 'dapr' in elementAndFlagDicts:
                    dapr = ds.createVariable('dapr', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['dapr'].values())][:]
                    ds.variables['dapr'].long_name = 'Number of days included in the multiday precipitation total (MDPR)'
                    ds.variables['dapr'].standard_name = 'number_of_observations'
                    ds.variables['dapr'].units = 1
                    ds.variables['dapr'].missing_value = -9999
                    ds.variables['dapr'].valid_min = 0
                    ds.variables['dapr'].valid_max = 500
                    ds.variables['dapr'].coordinates = 'lat lon alt station_name'
                    ds.variables['dapr'].coverage_content_type = 'auxiliaryInformation'
                    ds.variables['dapr'].ancillary_variables = 'dapr_mflag dapr_qflag dapr_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['dapr']
                except KeyError:
                    pass

                if 'dasf' in elementAndFlagDicts:
                    dasf = ds.createVariable('dasf', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['dasf'].values())][:]
                    ds.variables['dasf'].long_name = 'Number of days included in the multiday snowfall total (MDSF)'
                    ds.variables['dasf'].standard_name = 'number_of_observations'
                    ds.variables['dasf'].units = 1
                    ds.variables['dasf'].missing_value = -9999
                    ds.variables['dasf'].valid_min = 0
                    ds.variables['dasf'].valid_max = 500
                    ds.variables['dasf'].coordinates = 'lat lon alt station_name'
                    ds.variables['dasf'].coverage_content_type = 'auxiliaryInformation'
                    ds.variables['dasf'].ancillary_variables = 'dasf_mflag dasf_qflag dasf_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['dasf']
                except KeyError:
                    pass

                if 'datn' in elementAndFlagDicts:
                    datn = ds.createVariable('datn', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['datn'].values())][:]
                    ds.variables['datn'].long_name = 'Number of days included in the multiday minimum temperature (MDTN)'
                    ds.variables['datn'].standard_name = 'number_of_observations'
                    ds.variables['datn'].units = 1
                    ds.variables['datn'].missing_value = -9999
                    ds.variables['datn'].valid_min = 0
                    ds.variables['datn'].valid_max = 500
                    ds.variables['datn'].coordinates = 'lat lon alt station_name'
                    ds.variables['datn'].coverage_content_type = 'auxiliaryInformation'
                    ds.variables['datn'].ancillary_variables = 'datn_mflag datn_qflag datn_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['datn']
                except KeyError:
                    pass

                if 'datx' in elementAndFlagDicts:
                    datx = ds.createVariable('datx', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['datx'].values())][:]
                    ds.variables['datx'].long_name = 'Number of days included in the multiday maximum temperature (MDTX)'
                    ds.variables['datx'].standard_name = 'number_of_observations'
                    ds.variables['datx'].units = 1
                    ds.variables['datx'].missing_value = -9999
                    ds.variables['datx'].valid_min = 0
                    ds.variables['datx'].valid_max = 500
                    ds.variables['datx'].coordinates = 'lat lon alt station_name'
                    ds.variables['datx'].coverage_content_type = 'auxiliaryInformation'
                    ds.variables['datx'].ancillary_variables = 'datx_mflag datx_qflag datx_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['datx']
                except KeyError:
                    pass

                if 'dawm' in elementAndFlagDicts:
                    dawm = ds.createVariable('dawm', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['dawm'].values())][:]
                    ds.variables['dawm'].long_name = 'Number of days included in the multiday wind movement (MDWM)'
                    ds.variables['dawm'].standard_name = 'number_of_observations'
                    ds.variables['dawm'].units = 1
                    ds.variables['dawm'].missing_value = -9999
                    ds.variables['dawm'].valid_min = 0
                    ds.variables['dawm'].valid_max = 500
                    ds.variables['dawm'].coordinates = 'lat lon alt station_name'
                    ds.variables['dawm'].coverage_content_type = 'auxiliaryInformation'
                    ds.variables['dawm'].ancillary_variables = 'dawm_mflag dawm_qflag dawm_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['dawm']
                except KeyError:
                    pass

                if 'dwpr' in elementAndFlagDicts:
                    dwpr = ds.createVariable('dwpr', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['dwpr'].values())][:]
                    ds.variables['dwpr'].long_name = 'Number of days with non-zero precipitation included in multiday precipitation total (MDPR)'
                    ds.variables['dwpr'].standard_name = 'number_of_observations'
                    ds.variables['dwpr'].units = 1
                    ds.variables['dwpr'].missing_value = -9999
                    ds.variables['dwpr'].valid_min = 0
                    ds.variables['dwpr'].valid_max = 500
                    ds.variables['dwpr'].coordinates = 'lat lon alt station_name'
                    ds.variables['dwpr'].coverage_content_type = 'auxiliaryInformation'
                    ds.variables['dwpr'].ancillary_variables = 'dwpr_mflag dwpr_qflag dwpr_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['dwpr']
                except KeyError:
                    pass

                if 'evap' in elementAndFlagDicts:
                    evap = ds.createVariable('evap', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['evap'].values())][:]
                    ds.variables['evap'].long_name = 'Evaporation of water from evaporation pan (mm)'
                    ds.variables['evap'].standard_name = 'water_evaporation_amount'
                    ds.variables['evap'].units = 'mm'
                    ds.variables['evap'].scale_factor = 0.1
                    ds.variables['evap'].missing_value = -9999
                    ds.variables['evap'].valid_min = 0
                    ds.variables['evap'].valid_max = 3000
                    ds.variables['evap'].coordinates = 'lat lon alt station_name'
                    ds.variables['evap'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['evap'].ancillary_variables = 'evap_mflag evap_qflag evap_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['evap']
                except KeyError:
                    pass

                if 'fmtm' in elementAndFlagDicts:
                    fmtm = ds.createVariable('fmtm', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['fmtm'].values())][:]
                    ds.variables['fmtm'].long_name = 'Time of fastest mile or fastest 1-minute wind (hours and minutes, i.e., HHMM)'
                    ds.variables['fmtm'].missing_value = -9999
                    ds.variables['fmtm'].valid_min = 0
                    ds.variables['fmtm'].valid_max = 2400
                    ds.variables['fmtm'].coordinates = 'lat lon alt station_name'
                    ds.variables['fmtm'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['fmtm'].ancillary_variables = 'fmtm_mflag fmtm_qflag fmtm_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['fmtm']
                except KeyError:
                    pass

                if 'frgb' in elementAndFlagDicts:
                    frgb = ds.createVariable('frgb', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['frgb'].values())][:]
                    ds.variables['frgb'].long_name = 'Base of frozen ground layer (cm)'
                    ds.variables['frgb'].units = 'cm'
                    ds.variables['frgb'].missing_value = -9999
                    ds.variables['frgb'].valid_min = 0
                    ds.variables['frgb'].valid_max = 30000
                    ds.variables['frgb'].coordinates = 'lat lon alt station_name'
                    ds.variables['frgb'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['frgb'].ancillary_variables = 'frgb_mflag frgb_qflag frgb_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['frgb']
                except KeyError:
                    pass

                if 'frgt' in elementAndFlagDicts:
                    frgt = ds.createVariable('frgt', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['frgt'].values())][:]
                    ds.variables['frgt'].long_name = 'Top of frozen ground layer (cm)'
                    ds.variables['frgt'].units = 'cm'
                    ds.variables['frgt'].missing_value = -9999
                    ds.variables['frgt'].valid_min = 0
                    ds.variables['frgt'].valid_max = 20000
                    ds.variables['frgt'].coordinates = 'lat lon alt station_name'
                    ds.variables['frgt'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['frgt'].ancillary_variables = 'frgt_mflag frgt_qflag frgt_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['frgt']
                except KeyError:
                    pass

                if 'frth' in elementAndFlagDicts:
                    frth = ds.createVariable('frth', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['frth'].values())][:]
                    ds.variables['frth'].long_name = 'Thickness of frozen ground layer (cm)'
                    ds.variables['frth'].units = 'cm'
                    ds.variables['frth'].missing_value = -9999
                    ds.variables['frth'].valid_min = 0
                    ds.variables['frth'].valid_max = 30000
                    ds.variables['frth'].coordinates = 'lat lon alt station_name'
                    ds.variables['frth'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['frth'].ancillary_variables = 'frth_mflag frth_qflag frth_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['frth']
                except KeyError:
                    pass

                if 'gaht' in elementAndFlagDicts:
                    gaht = ds.createVariable('gaht', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['gaht'].values())][:]
                    ds.variables['gaht'].long_name = 'Difference between river and gauge height (cm)'
                    ds.variables['gaht'].units = 'cm'
                    ds.variables['gaht'].missing_value = -9999
                    ds.variables['gaht'].valid_min = 0
                    ds.variables['gaht'].valid_max = 30000
                    ds.variables['gaht'].coordinates = 'lat lon alt station_name'
                    ds.variables['gaht'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['gaht'].ancillary_variables = 'gaht_mflag gaht_qflag gaht_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['gaht']
                except KeyError:
                    pass

                if 'mdev' in elementAndFlagDicts:
                    mdev = ds.createVariable('mdev', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['mdev'].values())][:]
                    ds.variables['mdev'].long_name = 'Multiday evaporation total (mm)'
                    ds.variables['mdev'].standard_name = 'water_evaporation_amount'
                    ds.variables['mdev'].units = 'mm'
                    ds.variables['mdev'].scale_factor = 0.1
                    ds.variables['mdev'].missing_value = -9999
                    ds.variables['mdev'].valid_min = 0
                    ds.variables['mdev'].valid_max = 30000
                    ds.variables['mdev'].coordinates = 'lat lon alt station_name'
                    ds.variables['mdev'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['mdev'].ancillary_variables = 'mdev_mflag mdev_qflag mdev_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['mdev']
                except KeyError:
                    pass

                if 'mdpr' in elementAndFlagDicts:
                    mdpr = ds.createVariable('mdpr', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['mdpr'].values())][:]
                    ds.variables['mdpr'].long_name = 'Multiday precipitation total (mm)'
                    ds.variables['mdpr'].standard_name = 'precipitation_amount'
                    ds.variables['mdpr'].units = 'mm'
                    ds.variables['mdpr'].scale_factor = 0.1
                    ds.variables['mdpr'].missing_value = -9999
                    ds.variables['mdpr'].valid_min = 0
                    ds.variables['mdpr'].valid_max = 30000
                    ds.variables['mdpr'].coordinates = 'lat lon alt station_name'
                    ds.variables['mdpr'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['mdpr'].ancillary_variables = 'mdpr_mflag mdpr_qflag mdpr_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['mdpr']
                except KeyError:
                    pass

                if 'mdsf' in elementAndFlagDicts:
                    mdsf = ds.createVariable('mdsf', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['mdsf'].values())][:]
                    ds.variables['mdsf'].long_name = 'Multiday snowfall total (mm)'
                    ds.variables['mdsf'].standard_name = 'snowfall_amount'
                    ds.variables['mdsf'].units = 'mm'
                    ds.variables['mdsf'].missing_value = -9999
                    ds.variables['mdsf'].valid_min = 0
                    ds.variables['mdsf'].valid_max = 30000
                    ds.variables['mdsf'].coordinates = 'lat lon alt station_name'
                    ds.variables['mdsf'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['mdsf'].ancillary_variables = 'mdsf_mflag mdsf_qflag mdsf_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['mdsf']
                except KeyError:
                    pass

                if 'mdtn' in elementAndFlagDicts:
                    mdtn = ds.createVariable('mdtn', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['mdtn'].values())][:]
                    ds.variables['mdtn'].long_name = 'Multiday minimum temperature (degrees C)'
                    ds.variables['mdtn'].standard_name = 'air_temperature'
                    ds.variables['mdtn'].units = 'degrees_Celsius'
                    ds.variables['mdtn'].scale_factor = 0.1
                    ds.variables['mdtn'].missing_value = -9999
                    ds.variables['mdtn'].valid_min = -500
                    ds.variables['mdtn'].valid_max = 500
                    ds.variables['mdtn'].coordinates = 'lat lon alt station_name'
                    ds.variables['mdtn'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['mdtn'].ancillary_variables = 'mdtn_mflag mdtn_qflag mdtn_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['mdtn']
                except KeyError:
                    pass

                if 'mdtx' in elementAndFlagDicts:
                    mdtx = ds.createVariable('mdtx', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['mdtx'].values())][:]
                    ds.variables['mdtx'].long_name = 'Multiday maximum temperature (degrees C)'
                    ds.variables['mdtx'].standard_name = 'air_temperature'
                    ds.variables['mdtx'].units = 'degrees_Celsius'
                    ds.variables['mdtx'].scale_factor = 0.1
                    ds.variables['mdtx'].missing_value = -9999
                    ds.variables['mdtx'].valid_min = -500
                    ds.variables['mdtx'].valid_max = 500
                    ds.variables['mdtx'].coordinates = 'lat lon alt station_name'
                    ds.variables['mdtx'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['mdtx'].ancillary_variables = 'mdtx_mflag mdtx_qflag mdtx_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['mdtx']
                except KeyError:
                    pass

                if 'mdwm' in elementAndFlagDicts:
                    mdwm = ds.createVariable('mdwm', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['mdwm'].values())][:]
                    ds.variables['mdwm'].long_name = 'Multiday wind movement (km)'
                    ds.variables['mdwm'].units = 'km'
                    ds.variables['mdwm'].missing_value = -9999
                    ds.variables['mdwm'].valid_min = 0
                    ds.variables['mdwm'].valid_max = 3000
                    ds.variables['mdwm'].coordinates = 'lat lon alt station_name'
                    ds.variables['mdwm'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['mdwm'].ancillary_variables = 'mdwm_mflag mdwm_qflag mdwm_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['mdwm']
                except KeyError:
                    pass

                if 'mnpn' in elementAndFlagDicts:
                    mnpn = ds.createVariable('mnpn', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['mnpn'].values())][:]
                    ds.variables['mnpn'].long_name = 'Daily minimum temperature of water in an evaporation pan (degrees C)'
                    ds.variables['mnpn'].standard_name = 'air_temperature'
                    ds.variables['mnpn'].units = 'degrees_Celsius'
                    ds.variables['mnpn'].scale_factor = 0.1
                    ds.variables['mnpn'].missing_value = -9999
                    ds.variables['mnpn'].valid_min = -500
                    ds.variables['mnpn'].valid_max = 500
                    ds.variables['mnpn'].coordinates = 'lat lon alt station_name'
                    ds.variables['mnpn'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['mnpn'].ancillary_variables = 'mnpn_mflag mnpn_qflag mnpn_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['mnpn']
                except KeyError:
                    pass

                if 'mxpn' in elementAndFlagDicts:
                    mxpn = ds.createVariable('mxpn', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['mxpn'].values())][:]
                    ds.variables['mxpn'].long_name = 'Daily maximum temperature of water in an evaporation pan (degrees C)'
                    ds.variables['mxpn'].standard_name = 'air_temperature'
                    ds.variables['mxpn'].units = 'degrees_Celsius'
                    ds.variables['mxpn'].scale_factor = 0.1
                    ds.variables['mxpn'].missing_value = -9999
                    ds.variables['mxpn'].valid_min = -500
                    ds.variables['mxpn'].valid_max = 500
                    ds.variables['mxpn'].coordinates = 'lat lon alt station_name'
                    ds.variables['mxpn'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['mxpn'].ancillary_variables = 'mxpn_mflag mxpn_qflag mxpn_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['mxpn']
                except KeyError:
                    pass

                if 'pgtm' in elementAndFlagDicts:
                    pgtm = ds.createVariable('pgtm', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['pgtm'].values())][:]
                    ds.variables['pgtm'].long_name = 'Peak gust time (hours and minutes, i.e., HHMM)'
                    ds.variables['pgtm'].missing_value = -9999
                    ds.variables['pgtm'].valid_min = 0
                    ds.variables['pgtm'].valid_max = 2400
                    ds.variables['pgtm'].coordinates = 'lat lon alt station_name'
                    ds.variables['pgtm'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['pgtm'].ancillary_variables = 'pgtm_mflag pgtm_qflag pgtm_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['pgtm']
                except KeyError:
                    pass

                if 'psun' in elementAndFlagDicts:
                    psun = ds.createVariable('psun', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['psun'].values())][:]
                    ds.variables['psun'].long_name = 'Daily percent of possible sunshine (percent)'
                    ds.variables['psun'].units = 'percent'
                    ds.variables['psun'].missing_value = -9999
                    ds.variables['psun'].valid_min = 0
                    ds.variables['psun'].valid_max = 100
                    ds.variables['psun'].coordinates = 'lat lon alt station_name'
                    ds.variables['psun'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['psun'].ancillary_variables = 'psun_mflag psun_qflag psun_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['psun']
                except KeyError:
                    pass

                if 'tavg' in elementAndFlagDicts:
                    tavg = ds.createVariable('tavg', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['tavg'].values())][:]
                    ds.variables['tavg'].long_name = 'Average temperature (degrees C)'
                    ds.variables['tavg'].standard_name = 'air_temperature'
                    ds.variables['tavg'].units = 'degrees_Celsius'
                    ds.variables['tavg'].scale_factor = 0.1
                    ds.variables['tavg'].valid_min = -500
                    ds.variables['tavg'].valid_max = 500
                    ds.variables['tavg'].missing_value = -9999
                    ds.variables['tavg'].coordinates = 'lat lon alt station_name'
                    ds.variables['tavg'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['tavg'].ancillary_variables = 'tavg_mflag tavg_qflag tavg_sflag'
                    ds.variables['tavg'].comment = 'Note that TAVG from source \'S\' corresponds to an average for the period ending at 2400 UTC rather than local midnight.'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['tavg']
                except KeyError:
                    pass

                if 'thic' in elementAndFlagDicts:
                    thic = ds.createVariable('thic', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['thic'].values())][:]
                    ds.variables['thic'].long_name = 'Thickness of ice on water (mm)'
                    ds.variables['thic'].standard_name = 'floating_ice_thickness'
                    ds.variables['thic'].units = 'mm'
                    ds.variables['thic'].scale_factor = 0.1
                    ds.variables['thic'].valid_min = 0
                    ds.variables['thic'].valid_max = 10000
                    ds.variables['thic'].missing_value = -9999
                    ds.variables['thic'].coordinates = 'lat lon alt station_name'
                    ds.variables['thic'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['thic'].ancillary_variables = 'thic_mflag thic_qflag thic_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['thic']
                except KeyError:
                    pass

                if 'tobs' in elementAndFlagDicts:
                    tobs = ds.createVariable('tobs', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['tobs'].values())][:]
                    ds.variables['tobs'].long_name = 'Temperature at the time of observation (degrees_Celsius)'
                    ds.variables['tobs'].standard_name = 'air_temperature'
                    ds.variables['tobs'].units = 'degrees_Celsius'
                    ds.variables['tobs'].scale_factor = 0.1
                    ds.variables['tobs'].valid_min = -500
                    ds.variables['tobs'].valid_max = 500
                    ds.variables['tobs'].missing_value = -9999
                    ds.variables['tobs'].coordinates = 'lat lon alt station_name'
                    ds.variables['tobs'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['tobs'].ancillary_variables = 'tobs_mflag tobs_qflag tobs_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['tobs']
                except KeyError:
                    pass

                if 'tsun' in elementAndFlagDicts:
                    tsun = ds.createVariable('tsun', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['tsun'].values())][:]
                    ds.variables['tsun'].long_name = 'Daily total sunshine (minutes)'
                    ds.variables['tsun'].units = 'minutes'
                    ds.variables['tsun'].valid_min = '0'
                    ds.variables['tsun'].valid_max = 1440
                    ds.variables['tsun'].missing_value = -9999
                    ds.variables['tsun'].coordinates = 'lat lon alt station_name'
                    ds.variables['tsun'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['tsun'].ancillary_variables = 'tsun_mflag tsun_qflag tsun_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['tsun']
                except KeyError:
                    pass

                if 'wdf1' in elementAndFlagDicts:
                    wdf1 = ds.createVariable('wdf1', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['wdf1'].values())][:]
                    ds.variables['wdf1'].long_name = 'Direction of fastest 1-minute wind (degrees)'
                    ds.variables['wdf1'].standard_name = 'wind_from_direction'
                    ds.variables['wdf1'].units = 'degree'
                    ds.variables['wdf1'].valid_min = 0
                    ds.variables['wdf1'].valid_max = 360
                    ds.variables['wdf1'].missing_value = -9999
                    ds.variables['wdf1'].coordinates = 'lat lon alt station_name'
                    ds.variables['wdf1'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['wdf1'].ancillary_variables = 'wdf1_mflag wdf1_qflag wdf1_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['wdf1']
                except KeyError:
                    pass

                if 'wdf2' in elementAndFlagDicts:
                    wdf2 = ds.createVariable('wdf2', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['wdf2'].values())][:]
                    ds.variables['wdf2'].long_name = 'Direction of fastest 2-minute wind (degrees)'
                    ds.variables['wdf2'].standard_name = 'wind_from_direction'
                    ds.variables['wdf2'].units = 'degree'
                    ds.variables['wdf2'].valid_min = 0
                    ds.variables['wdf2'].valid_max = 360
                    ds.variables['wdf2'].missing_value = -9999
                    ds.variables['wdf2'].coordinates = 'lat lon alt station_name'
                    ds.variables['wdf2'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['wdf2'].ancillary_variables = 'wdf2_mflag wdf2_qflag wdf2_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['wdf2']
                except KeyError:
                    pass

                if 'wdf5' in elementAndFlagDicts:
                    wdf5 = ds.createVariable('wdf5', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['wdf5'].values())][:]
                    ds.variables['wdf5'].long_name = 'Direction of fastest 5-second wind (degrees)'
                    ds.variables['wdf5'].standard_name = 'wind_from_direction'
                    ds.variables['wdf5'].units = 'degree'
                    ds.variables['wdf5'].valid_min = 0
                    ds.variables['wdf5'].valid_max = 360
                    ds.variables['wdf5'].missing_value = -9999
                    ds.variables['wdf5'].coordinates = 'lat lon alt station_name'
                    ds.variables['wdf5'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['wdf5'].ancillary_variables = 'wdf5_mflag wdf5_qflag wdf5_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['wdf5']
                except KeyError:
                    pass

                if 'wdfg' in elementAndFlagDicts:
                    wdfg = ds.createVariable('wdfg', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['wdfg'].values())][:]
                    ds.variables['wdfg'].long_name = 'Direction of peak wind gust (degrees)'
                    ds.variables['wdfg'].standard_name = 'wind_from_direction'
                    ds.variables['wdfg'].units = 'degree'
                    ds.variables['wdfg'].valid_min = 0
                    ds.variables['wdfg'].valid_max = 360
                    ds.variables['wdfg'].missing_value = -9999
                    ds.variables['wdfg'].coordinates = 'lat lon alt station_name'
                    ds.variables['wdfg'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['wdfg'].ancillary_variables = 'wdfg_mflag wdfg_qflag wdfg_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['wdfg']
                except KeyError:
                    pass

                if 'wdfi' in elementAndFlagDicts:
                    wdfi = ds.createVariable('wdfi', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['wdfi'].values())][:]
                    ds.variables['wdfi'].long_name = 'Direction of highest instantaneous wind (degrees)'
                    ds.variables['wdfi'].standard_name = 'wind_from_direction'
                    ds.variables['wdfi'].units = 'degree'
                    ds.variables['wdfi'].valid_min = 0
                    ds.variables['wdfi'].valid_max = 360
                    ds.variables['wdfi'].missing_value = -9999
                    ds.variables['wdfi'].coordinates = 'lat lon alt station_name'
                    ds.variables['wdfi'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['wdfi'].ancillary_variables = 'wdfi_mflag wdfi_qflag wdfi_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['wdfi']
                except KeyError:
                    pass

                if 'wdfm' in elementAndFlagDicts:
                    wdfm = ds.createVariable('wdfm', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['wdfm'].values())][:]
                    ds.variables['wdfm'].long_name = 'Fastest mile wind direction (degrees)'
                    ds.variables['wdfm'].standard_name = 'wind_from_direction'
                    ds.variables['wdfm'].units = 'degree'
                    ds.variables['wdfm'].valid_min = 0
                    ds.variables['wdfm'].valid_max = 360
                    ds.variables['wdfm'].missing_value = -9999
                    ds.variables['wdfm'].coordinates = 'lat lon alt station_name'
                    ds.variables['wdfm'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['wdfm'].ancillary_variables = 'wdfm_mflag wdfm_qflag wdfm_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['wdfm']
                except KeyError:
                    pass

                if 'wdmv' in elementAndFlagDicts:
                    wdmv = ds.createVariable('wdmv', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['wdmv'].values())][:]
                    ds.variables['wdmv'].long_name = '24-hour wind movement (km)'
                    ds.variables['wdmv'].units = 'km'
                    ds.variables['wdmv'].valid_min = 0
                    ds.variables['wdmv'].valid_max = 3000
                    ds.variables['wdmv'].missing_value = -9999
                    ds.variables['wdmv'].coordinates = 'lat lon alt station_name'
                    ds.variables['wdmv'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['wdmv'].ancillary_variables = 'wdmv_mflag wdmv_qflag wdmv_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['wdmv']
                except KeyError:
                    pass

                if 'wesd' in elementAndFlagDicts:
                    wesd = ds.createVariable('wesd', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['wesd'].values())][:]
                    ds.variables['wesd'].long_name = 'Water equivalent of snow on the ground (tenths of mm)'
                    ds.variables['wesd'].standard_name = 'lwe_thickness_of_surface_snow_amount'
                    ds.variables['wesd'].units = 'mm'
                    ds.variables['wesd'].scale_factor = 0.1
                    ds.variables['wesd'].valid_min = 0
                    ds.variables['wesd'].valid_max = 5000
                    ds.variables['wesd'].missing_value = -9999
                    ds.variables['wesd'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['wesd'].coordinates = 'lat lon alt station_name'
                    ds.variables['wesd'].ancillary_variables = 'wesd_mflag wesd_qflag wesd_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['wesd']
                except KeyError:
                    pass

                if 'wesf' in elementAndFlagDicts:
                    wesf = ds.createVariable('wesf', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['wesf'].values())][:]
                    ds.variables['wesf'].long_name = 'Water equivalent of snowfall (tenths of mm)'
                    ds.variables['wesf'].standard_name = 'lwe_thickness_of_snowfall_amount'
                    ds.variables['wesf'].units = 'mm'
                    ds.variables['wesf'].valid_min = 0
                    ds.variables['wesf'].valid_max = 5000
                    ds.variables['wesf'].missing_value = -9999
                    ds.variables['wesf'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['wesf'].coordinates = 'lat lon alt station_name'
                    ds.variables['wesf'].ancillary_variables = 'wesf_mflag wesf_qflag wesf_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['wesf']
                except KeyError:
                    pass

                if 'wsf1' in elementAndFlagDicts:
                    wsf1 = ds.createVariable('wsf1', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['wsf1'].values())][:]
                    ds.variables['wsf1'].long_name = 'Fastest 1-minute wind speed (m s-1)'
                    ds.variables['wsf1'].standard_name = 'wind_speed'
                    ds.variables['wsf1'].units = 'm s-1'
                    ds.variables['wsf1'].scale_factor = 0.1
                    ds.variables['wsf1'].valid_min = 0
                    ds.variables['wsf1'].valid_max = 100
                    ds.variables['wsf1'].missing_value = -9999
                    ds.variables['wsf1'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['wsf1'].coordinates = 'lat lon alt station_name'
                    ds.variables['wsf1'].ancillary_variables = 'wsf1_mflag wsf1_qflag wsf1_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['wsf1']
                except KeyError:
                    pass

                if 'wsf2' in elementAndFlagDicts:
                    wsf2 = ds.createVariable('wsf2', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['wsf2'].values())][:]
                    ds.variables['wsf2'].long_name = 'Fastest 2-minute wind speed (m s-1)'
                    ds.variables['wsf2'].standard_name = 'wind_speed'
                    ds.variables['wsf2'].units = 'm s-1'
                    ds.variables['wsf2'].scale_factor = 0.1
                    ds.variables['wsf2'].valid_min = 0
                    ds.variables['wsf2'].valid_max = 100
                    ds.variables['wsf2'].missing_value = -9999
                    ds.variables['wsf2'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['wsf2'].coordinates = 'lat lon alt station_name'
                    ds.variables['wsf2'].ancillary_variables = 'wsf2_mflag wsf2_qflag wsf2_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['wsf2']
                except KeyError:
                    pass

                if 'wsf5' in elementAndFlagDicts:
                    wsf5 = ds.createVariable('wsf5', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['wsf5'].values())][:]
                    ds.variables['wsf5'].long_name = 'Fastest 5-second wind speed (m s-1)'
                    ds.variables['wsf5'].standard_name = 'wind_speed'
                    ds.variables['wsf5'].units = 'm s-1'
                    ds.variables['wsf5'].scale_factor = 0.1
                    ds.variables['wsf5'].valid_min = 0
                    ds.variables['wsf5'].valid_max = 100
                    ds.variables['wsf5'].missing_value = -9999
                    ds.variables['wsf5'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['wsf5'].coordinates = 'lat lon alt station_name'
                    ds.variables['wsf5'].ancillary_variables = 'wsf5_mflag wsf5_qflag wsf5_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['wsf5']
                except KeyError:
                    pass

                if 'wsfg' in elementAndFlagDicts:
                    wsfg = ds.createVariable('wsfg', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['wsfg'].values())][:]
                    ds.variables['wsfg'].long_name = 'Peak gust wind speed (m s-1)'
                    ds.variables['wsfg'].standard_name = 'wind_speed'
                    ds.variables['wsfg'].units = 'm s-1'
                    ds.variables['wsfg'].scale_factor = 0.1
                    ds.variables['wsfg'].valid_min = 0
                    ds.variables['wsfg'].valid_max = 100
                    ds.variables['wsfg'].missing_value = -9999
                    ds.variables['wsfg'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['wsfg'].coordinates = 'lat lon alt station_name'
                    ds.variables['wsfg'].ancillary_variables = 'wsfg_mflag wsfg_qflag wsfg_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['wsfg']
                except KeyError:
                    pass

                if 'wsfi' in elementAndFlagDicts:
                    wsfi = ds.createVariable('wsfi', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['wsfi'].values())][:]
                    ds.variables['wsfi'].long_name = 'Highest instantaneous wind speed (m s-1)'
                    ds.variables['wsfi'].standard_name = 'wind_speed'
                    ds.variables['wsfi'].units = 'm s-1'
                    ds.variables['wsfi'].scale_factor = 0.1
                    ds.variables['wsfi'].valid_min = 0
                    ds.variables['wsfi'].valid_max = 100
                    ds.variables['wsfi'].missing_value = -9999
                    ds.variables['wsfi'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['wsfi'].coordinates = 'lat lon alt station_name'
                    ds.variables['wsfi'].ancillary_variables = 'wsfi_mflag wsfi_qflag wsfi_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['wsfi']
                except KeyError:
                    pass

                if 'wsfm' in elementAndFlagDicts:
                    wsfm = ds.createVariable('wsfm', 'short', ('station', 'time',), fill_value=-9999)[:] = [np.array(OrderedDict(sorted(elementAndFlagDicts.items()))['wsfm'].values())][:]
                    ds.variables['wsfm'].long_name = 'Fastest mile wind speed (m s-1)'
                    ds.variables['wsfm'].standard_name = 'wind_speed'
                    ds.variables['wsfm'].units = 'm s-1'
                    ds.variables['wsfm'].scale_factor = 0.1
                    ds.variables['wsfm'].valid_min = 0
                    ds.variables['wsfm'].valid_max = 100
                    ds.variables['wsfm'].missing_value = -9999
                    ds.variables['wsfm'].coverage_content_type = 'physicalMeasurement'
                    ds.variables['wsfm'].coordinates = 'lat lon alt station_name'
                    ds.variables['wsfm'].ancillary_variables = 'wsfm_mflag wsfm_qflag wsfm_sflag'
                # Delete key from dictionary after processing to avoid double
                # processing below with dynamically generated value arrays
                try:
                    del elementAndFlagDicts['wsfm']
                except KeyError:
                    pass

                # Other variables
                lat = ds.createVariable('lat', 'f', ('station',))
                lat.long_name = 'Latitude'
                lat.standard_name = 'latitude'
                lat.units = 'degrees_north'
                lat.axis = 'Y'
                lat.coverage_content_type = 'coordinate'
                lat[:] = np.array(self.latDict[fileId])

                lon = ds.createVariable('lon', 'f', ('station',))
                lon.long_name = 'Longitude'
                lon.standard_name = 'longitude'
                lon.units = 'degrees_east'
                lon.axis = 'X'
                lon.coverage_content_type = 'coordinate'
                lon[:] = np.array(self.lonDict[fileId])

                alt = ds.createVariable('alt', 'f', ('station',))
                alt.long_name = 'Station Altitude'
                alt.standard_name = 'surface_altitude'
                alt.units = 'm'
                alt.axis = 'Z'
                alt.coverage_content_type = 'coordinate'
                alt.positive = 'up'
                alt[:] = np.array(self.elevationDict[fileId])

                station_name = ds.createVariable(
                    'station_name', 'S1', ('station', 'station_name_to_char',))[:] = netCDF4.stringtochar(np.array([self.stationLongNameDict[fileId]], 'S'+str(len(self.stationLongNameDict[fileId].strip()))))
                ds.variables['station_name'].long_name = 'Station Name'
                ds.variables['station_name'].standard_name = 'platform_name'
                ds.variables['station_name'].cf_role = 'timeseries_id'
                ds.variables['station_name'].coverage_content_type = 'coordinate'

                station_id = ds.createVariable(
                    'station_id', 'S1', ('station', 'station_id_to_char',))[:] = netCDF4.stringtochar(np.array([fileId], 'S11'))
                ds.variables['station_id'].long_name = 'Station Identification Code'
                ds.variables['station_id'].standard_name = 'platform_id'

                # Dynamically create remaining variables from data arrays that
                # have not been called out and processed previously
                for key, value in OrderedDict(sorted(elementAndFlagDicts.items())).iteritems():
                    if len(key) == 4:
                        ds.createVariable(
                            key, 'i2', ('station', 'time',), fill_value=-9999)[:] = [np.array(value.values())][:]
                        
                        # Add sx.. attributes
                        if 'sx' in key:
                            ds.variables[key].long_name = 'Maximum soil temperature (degrees C)'
                            ds.variables[key].standard_name = 'soil_temperature'
                            ds.variables[key].units = 'degrees_Celsius'
                            ds.variables[key].valid_min = -500
                            ds.variables[key].valid_max = 500
                            ds.variables[key].coordinates = 'lat lon alt station_name'
                            ds.variables[key].coverage_content_type = 'physicalMeasurement'
                            ds.variables[key].missing_value = -9999
                            ds.variables[key].coordinates = 'lat lon alt station_name'
                            ds.variables[key].ancillary_variables = 'sx*#_mflag sx*#_qflag sx*#_sflag'

                            ds.createVariable(key + '_cover', 'byte', ('station', 'time',))
                            ds.variables[key + '_cover'].long_name = 'Ground cover code for maximum soil temperature (SX)'
                            ds.variables[key + '_cover'].standard_name = 'area_type'
                            ds.variables[key + '_cover'].valid_min = 0
                            ds.variables[key + '_cover'].valid_max = 8
                            ds.variables[key + '_cover'].coordinates = 'lat lon alt station_name'
                            ds.variables[key + '_cover'].coverage_content_type = 'auxiliaryInformation'
                            ds.variables[key + '_cover'].flag_values = '0 1 2 3 4 5 6 7 8'
                            ds.variables[key + '_cover'].flag_meanings = 'unknown grass fallow bare_ground brome_grass sod straw_multch grass_muck bare_muck'

                            ds.createVariable(key + '_depth', 'byte', ('station', 'time',))
                            ds.variables[key + '_depth'].long_name = 'Soil depth code for maximum soil temperature (SX)'
                            ds.variables[key + '_depth'].standard_name = 'depth'
                            ds.variables[key + '_depth'].units = 'cm'
                            ds.variables[key + '_depth'].valid_min = 1
                            ds.variables[key + '_depth'].valid_max = 7
                            ds.variables[key + '_depth'].coordinates = 'lat lon alt station_name'
                            ds.variables[key + '_depth'].coverage_content_type = 'auxiliaryInformation'
                            ds.variables[key + '_depth'].flag_values = '1 2 3 4 5 6 7'
                            ds.variables[key + '_depth'].flag_meanings = '5 10 20 50 100 150 180'

                        # Add sn.. attributes
                        if 'sn' in key:
                            ds.variables[key].long_name = 'Minimum soil temperature (degrees C'
                            ds.variables[key].standard_name = 'soil_temperature'
                            ds.variables[key].units = 'degrees_Celsius'
                            ds.variables[key].scale_factor = 0.1
                            ds.variables[key].missing_value = -9999
                            ds.variables[key].valid_min = -500
                            ds.variables[key].valid_max = 500
                            ds.variables[key].coordinates = 'lat lon alt station_name'
                            ds.variables[key].coverage_content_type = 'physicalMeasurement'
                            ds.variables[key].ancillary_variables = 'sn*#_mflag sn*#_qflag sn*#_sflag'

                            ds.createVariable(key + '_cover', 'byte', ('station', 'time',))
                            ds.variables[key + '_cover'].long_name = 'Ground cover code for minimum soil temperature (SN)'
                            ds.variables[key + '_cover'].standard_name = 'area_type'
                            ds.variables[key + '_cover'].valid_min = 0
                            ds.variables[key + '_cover'].valid_max = 8
                            ds.variables[key + '_cover'].coordinates = 'lat lon alt station_name'
                            ds.variables[key + '_cover'].coverage_content_type = 'auxiliaryInformation'
                            ds.variables[key + '_cover'].flag_values = '0 1 2 3 4 5 6 7 8'
                            ds.variables[key + '_cover'].flag_meanings = 'unknown grass fallow bare_ground brome_grass sod straw_multch grass_muck bare_muck'

                            ds.createVariable(key + '_depth', 'byte', ('station', 'time',))
                            ds.variables[key + '_depth'].long_name = 'Soil depth code for minimum soil temperature (SN)'
                            ds.variables[key + '_depth'].standard_name = 'depth'
                            ds.variables[key + '_depth'].units = 'cm'
                            ds.variables[key + '_depth'].valid_min = 1
                            ds.variables[key + '_depth'].valid_max = 7
                            ds.variables[key + '_depth'].coordinates = 'lat lon alt station_name'
                            ds.variables[key + '_depth'].coverage_content_type = 'auxiliaryInformation'
                            ds.variables[key + '_depth'].flag_values = '1 2 3 4 5 6 7'
                            ds.variables[key + '_depth'].flag_meanings = '5 10 20 50 100 150 180'

                        # Add wt.. attributes
                        if 'wt' in key:
                            ds.variables[key].long_name = 'Weather Type'
                            ds.variables[key].valid_min = 1
                            ds.variables[key].valid_max = 22
                            ds.variables[key].missing_value = -9999
                            ds.variables[key].coverage_content_type = 'physicalMeasurement'
                            ds.variables[key].coordinates = 'lat lon alt station_name'
                            ds.variables[key].ancillary_variables = 'wt*#_mflag wt*#_qflag wt*#_sflag'
                            ds.variables[key].flag_values = '1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 21 22'
                            ds.variables[key].flag_meanings = 'Fog_ice_fog_or_freezing_fog_(may_include_heavy_fog) Heavy_fog_or_heaving_freezing_fog_(not_always_distinquished_from_fog) Thunder Ice_pellets_sleet_snow_pellets_or_small_hail Hail_(may_include_small_hail) Glaze_or_rime Dust_volcanic_ash_blowing_dust_blowing_sand_or_blowing_obstruction Smoke_or_haze Blowing_or_drifting_snow Tornado_waterspout_or_funnel_cloud High_or_damaging_winds Blowing_spray Mist Drizzle Freezing_drizzle Rain_(may_include_freezing_rain_drizzle_and_freezing_drizzle) Freezing_rain Snow_snow_pellets_snow_grains_or_ice_crystals Unknown_source_of_precipitation Ground_fog Ice_fog_or_freezing_fog'

                        # Add wv.. attributes
                        if 'wv' in key:
                            ds.variables[key].long_name = 'Weather in the Vicinity'
                            ds.variables[key].valid_min = 1
                            ds.variables[key].valid_max = 20
                            ds.variables[key].missing_value = -9999
                            ds.variables[key].coverage_content_type = 'physicalMeasurement'
                            ds.variables[key].coordinates = 'lat lon alt station_name'
                            ds.variables[key].ancillary_variables = 'wv*#_mflag wv*#_qflag wv*#_sflag'
                            ds.variables[key].flag_values = '1 3 7 18 20'
                            ds.variables[key].flag_meanings = 'Fog_ice_fog_or_freezing_fog_(may_include_heavy_fog) Thunder Ash_dust_sand_or_other_blowing_obstruction Snow_or_ice_crystals Rain_or_snow_shower'
                    
                    if len(key) > 4:
                        ds.createVariable(key, 'c', ('station', 'time',), fill_value=' ')[
                            :] = [np.array(value.values())][:]
                        if 'mflag' in key:
                            ds.variables[
                                key].long_name = 'Measurement flag for the day of the month with ten possible values'
                            ds.variables[key].standard_name = 'status_flag'
                            ds.variables[key].missing_value = ' '
                            ds.variables[
                                key].flag_values = '1 B D H K L O P T W'
                            ds.variables[
                                key].flag_meanings = 'no_measurement_information_applicable precipitation_total_formed_from_two_12-hour_totals precipitation_total_formed_from_four_six-hour_totals represents_highest_or_lowest_hourly_temperature_(TMAX_or_TMIN)_or_the_average_of_hourly_values_(TAVG) converted_from_knots temperature_appears_to_be_lagged_with_respect_to_reported_hour_of_observation converted_from_oktas identified_as_missing_presumed_zero_in_DSI_3200_and_3206 trace_of_precipitation_snowfall_or_snow_depth converted_from_16-point_WBAN_code_(for_wind_direction)'
                            ds.variables[
                                key].coordinates = 'lat lon alt station_name'
                        if 'qflag' in key:
                            ds.variables[
                                key].long_name = 'Quality flag for the day of the month with fifteen possible values'
                            ds.variables[key].standard_name = 'status_flag'
                            ds.variables[key].missing_value = ' '
                            ds.variables[
                                key].flag_values = '1 D G I K L M N O R S T W X Z'
                            ds.variables[key].flag_meanings = 'did_not_fail_any_quality_assurance_check failed_duplicate_check failed_gap_check failed_internal_consistency_check failed_streak_frequent-value_check failed_check_on_length_of_multiday_period failed_megaconsistency_check failed_naught_check failed_climatological_outlier_check failed_lagged_range_check failed_spatial_consistency_check failed_temporal_consistency_check temperature_too_warm_for_snow failed_bounds_check flagged_as_a_result_of_an_official_Datzilla_investigation'
                            ds.variables[
                                key].coordinates = 'lat lon alt station_name'
                        if 'sflag' in key:
                            ds.variables[
                                key].long_name = 'Source flag for the day of the month with twenty nine possible values'
                            ds.variables[key].standard_name = 'status_flag'
                            ds.variables[key].missing_value = ' '
                            ds.variables[
                                key].flag_values = '1 0 6 7 A a B b C E F G H I K M N Q R r S s T U u W X Z z'
                            ds.variables[key].flag_meanings = 'No_source_(data_value_missing) US_Cooperative_Summary_of_the_Day_(NCDC_DSI-3200) CDMP_Cooperative_Summary_of_the_Day_(NCDC_DSI-3206) US_Cooperative_Summary_of_the_Day_--_Transmitted_via_WxCoder3_(NCDC_DSI-3207) US_Automated_Surface_Observing_System_(ASOS)_real-time_data_(since_01_January_2006) Australian_data_from_the_Australian_Bureau_of_Meteorology US_ASOS_data_for_October_2000_to_December_2005_(NCDC_DSI-3211) Belarus_update Environment_Canada European_Climate_Assessment_and_Dataset_(Klein_Tank_et_al_2002) US_Fort_data Official_Global_Climate_Observing_System_(GCOS)_or_other_government-supplied_data High_Plains_Regional_Climate_Center_real-time_data International_collection_(non_US_data_received_through_personal_contacts US_Cooperative_Summary_of_the_Day_data_digitized_from_paper_observer_forms_(from_2011_to_present) Monthly_METAR_Extract_(additional_ASOS_data) Community_Collaborative_Rain_Hail_and_Snow_(CoCoRaHS) Data_from_several_African_countries_that_had_been_quarantined_withheld_from_public_release_until_permission_was_granted_from_the_respective_meteorological_services NCEI_Reference_Network_Database_(Climate_Reference_Network_and_Regional_Climate_Reference_Network) All-Russian_Research_Institute_of_Hydrometeorological_Information-World_Data_Center Global_Summary_of_the_Day_(NCDC_DSI-9618) China_Meteorological_Administration_National_Meteorological_Information_Center_Climatic_Data_Center SNOwpack_TELemtry_(SNOTEL)_data_obtained_from_the_US_Department_of_Agriculture_s_Natural_Resources_Conservation_Service Remote_Automatic_Weather_Station_(RAWS)_data_obtained_from_the_Western_Regional_Climate_Center Ukraine_update WBAN_ASOS_Summary_of_the_Day_from_NCDC_s_Integrated_Surface_Data_(ISD) US_First-Order_Summary_of_the_Day_(NCDC_DSI-3210) Datzilla_official_additions_or_replacements Uzbekistan_update'
                            ds.variables[
                                key].coordinates = 'lat lon alt station_name'
                            ds.variables[
                                key].comment = 'When data are available for the same time from more than one source, the highest priority source is chosen according to the following priority order (from highest to lowest): Z,R,0,6,C,X,W,K,7,F,B,M,r,E,z,u,b,s,a,G,Q,I,A,N,T,U,H,S. NOTE for Global Summary of the Day: S values are derived from hourly synoptic reports exchanged on the Global Telecommunications System (GTS). Daily values derived in this fashion may differ significantly from true daily data, particularly for precipitation (i.e., use with caution).'

                # Global metadata attributes
                ds.Conventions = "CF-1.6, ACDD-1.3"
                ds.ncei_template_version = "NCEI_NetCDF_Grid_Template_v2.0"
                ds.title = 'GHCN-Daily Surface Observations from ' + fileId
                ds.source = 'Surface Observations: 1) the U.S. Collection; 2) the International Collection; 3) Government Exchange Data; and 4) the Global Summary of the Day'
                ds.id = 'ghcn-daily_v3.22.' + datetime.datetime.today().strftime('%Y-%m-%d') + \
                    '_' + fileId + '.nc'
                ds.naming_authority = 'gov.noaa.ncei'
                ds.summary = 'Global Historical Climatology Network - Daily (GHCN-Daily) is an integrated database of daily climate summaries from land surface stations across the globe. GHCN-Daily is comprised of daily climate records from numerous sources that have been integrated and subjected to a common suite of quality assurance reviews. GHCN-Daily contains records from over 100,000 stations in 180 countries and territories. NCEI provides numerous daily variables, including maximum and minimum temperature, total daily precipitation, snowfall, and snow depth; however, about one half of the stations report precipitation only. Both the record length and period of record vary by station and cover intervals ranging from less than a year to more than 175 years.'
                ds.featureType = 'timeSeries'
                ds.cdm_data_type = 'Point'
                ds.history = 'File updated on ' + \
                    datetime.datetime.today().strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
                ds.date_modified = datetime.datetime.today().strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
                ds.date_created = datetime.datetime.today().strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
                ds.product_version = 'Version 3.22'
                ds.processing_level = 'NOAA Level 2'
                ds.institution = 'NOAA National Centers for Environmental Information'
                ds.creator_url = 'https://www.ncei.noaa.gov/'
                ds.creator_email = 'matthew.menne@noaa.gov'
                ds.publisher_institution = 'NOAA National Centers for Environmental Information'
                ds.publisher_url = 'http://www.ncei.noaa.gov/'
                ds.publisher_email = 'ncei.orders@noaa.gov'
                ds.geospatial_lat_min = float(self.latDict[fileId].strip())
                ds.geospatial_lat_max = float(self.latDict[fileId].strip())
                ds.geospatial_lon_min = float(self.lonDict[fileId].strip())
                ds.geospatial_lon_max = float(self.lonDict[fileId].strip())
                ds.time_coverage_start = YEAR[0] + '-' + MONTH[0] + '-01'
                ds.time_coverage_end = YEAR[-1] + '-' + MONTH[-1] + '-31'
                ds.keywords = 'Earth Science > Atmosphere > Precipitation > Precipitation Amount > 24 Hour Precipitation Amount, Earth Science > Terrestrial Hydrosphere > Snow/Ice > Snow Depth, Earth Science > Atmosphere > Atmospheric Temperature > Surface Temperature > Maximum/Minimum Temperature > 24 Hour Maximum Temperature, Earth Science > Atmosphere > Atmospheric Temperature > Surface Temperature > Maximum/Minimum Temperature > 24 Hour Minimum Temperature'
                ds.keywords_vocabulary = 'Global Change Master Directory (GCMD) Earth Science Keywords'
                ds.standard_name_vocabulary = 'CF Standard Name Table (v46, 25 July 2017)'
                ds.metadata_link = 'https://doi.org/10.7289/V5D21VHZ'
                ds.references = 'https://doi.org/10.1175/JTECH-D-11-00103.1, https://doi.org/10.1175/2010JAMC2375.1, https://doi.org/10.1175/2007JAMC1706.1'
                ds.comment = 'Data was converted from native fixed-length text (DLY) format to NetCDF-4 format following metadata conventions.'

        except KeyboardInterrupt:
            print(sys.exc_info()[0])
        except:
            logging.exception(fileId + ": ")
        finally:
            pass

        # End def parse_to_netCDF(self, fileId)

    def run_combined_defs(self, fileId):
        if self.nc_file_exists(fileId) == False:
            self.download_dly_file(fileId)
            dictOfUniqueTimeValues = self.get_unique_time_values(fileId)
            uniqueElements = self.get_unique_elements(fileId)
            placeholderElementsFlagsList = self.initialize_element_lists_with_time_key_and_placeholder_value(fileId, dictOfUniqueTimeValues, uniqueElements)
            elementsAndFlagsDataLists = self.create_elements_flags_data_lists(fileId, dictOfUniqueTimeValues, placeholderElementsFlagsList)
            self.parse_to_netCDF(fileId, dictOfUniqueTimeValues, elementsAndFlagsDataLists)
            self.delete_txt_file(fileId)
        
        elif self.nc_file_exists(fileId) == True:
            self.download_dly_file(fileId)
            if self.dly_file_has_been_updated(fileId) == True:
                self.rename_old_nc_file(fileId)
                dictOfUniqueTimeValues = self.get_unique_time_values(fileId)
                uniqueElements = self.get_unique_elements(fileId)
                placeholderElementsFlagsList = self.initialize_element_lists_with_time_key_and_placeholder_value(fileId, dictOfUniqueTimeValues, uniqueElements)
                elementsAndFlagsDataLists = self.create_elements_flags_data_lists(fileId, dictOfUniqueTimeValues, placeholderElementsFlagsList)
                self.parse_to_netCDF(fileId, dictOfUniqueTimeValues, elementsAndFlagsDataLists)
                self.delete_txt_file(fileId)
            else:
                self.delete_txt_file(fileId)
        else:
            pass

    def go(self, stationIds):
        p = Pool(10)
        p.map(self, stationIds)

    def __call__(self, fileId):
        return self.run_combined_defs(fileId)


# __main__
if __name__ == '__main__':
    start = time.time()

    create_output_dirs()

    ghcn = GHCN()
    stationIds = ghcn.get_station_info()
    ghcn.go(stationIds)

    print('The program took ', (time.time() - start) / 60 / 60 / 24, 'days to complete.')

# End __main__
