#! Inundation Analysis Scraper 
# scrapes inundation analysis data from noaa
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException
import time
import json
import shelve
from collections import Counter
import os

class InundationQuery:
    """Type to hold user-entered query for the inundation analysis tool."""
    def __init__(self):
        self.ask_date('from')
        self.ask_date('to')
        self.elevation = input("Enter an elevation: ")
        self.dates = {'beginMonth': self.from_month, 'beginDay': self.from_day, 'beginYear': self.from_year, 
                      'endMonth': self.end_month, 'endDay': self.end_day, 'endYear': self.end_year}

    def ask_date(self, to_from):
        if to_from == 'from':
            self.raw_startdate = input("Enter start date(mm/dd/yyyy): ").split("/")
            # dropdown lists are indexed starting at 0.
            self.from_month = str(int(self.raw_startdate[0])-1) # convert back to string
            self.from_day = str(int(self.raw_startdate[1]))
            self.from_year = self.raw_startdate[2]

        elif to_from == 'to':
            self.raw_enddate = input("Enter end date(mm/dd/yyyy): ").split("/")
            # dropdown lists are indexed starting at 0.
            self.end_month = str(int(self.raw_enddate[0])-1) # convert back to string
            self.end_day = str(int(self.raw_enddate[1]))
            self.end_year = self.raw_enddate[2]

    def get_elevation(self):
        return self.elevation

class InundationAnalysis(webdriver.Chrome):
    def __init__(self, base_url ):
        super().__init__() # initialize the webdriver

        self.get(base_url)
        self.query = InundationQuery()
    
    def wait_page(self, css_selector, message, endmessage):
        start_time = time.time()
        print(message)
        while time.time() - start_time < 30:
            time.sleep(0.5)
            if EC.presence_of_element_located((By.CSS_SELECTOR, css_selector)):
                break
        print(endmessage + "\n")
        

    def input_dropdown_date(self, css_selector, mdy):
        try:
            input_element = self.find_element_by_css_selector(css_selector)

        except:
            print("Error")   
        finally:
            options = input_element.find_elements_by_tag_name("option")
            for option in options:
                if option.get_attribute("value") == self.query.dates[mdy]:
                    option.click()
    
    def box_input(self, css_selector, input_value):
        if input_value == 'beginYear' or input_value == 'endYear':
                isYear = True
        else:
            isYear = False

        if input_value in self.query.dates:
            input_value = self.query.dates[input_value]

        try:
            binput = self.find_element_by_css_selector(css_selector)
            binput.click()
            if isYear:
                for i in range(4):
                    binput.send_keys(Keys.BACK_SPACE)
                binput.send_keys(input_value)
                    
            else:
                binput.send_keys(input_value)
        except:
            print("Error inputting to html")
            


    def check_errors(self, css_selector):
        try:
            if EC.presence_of_element_located((By.CSS_SELECTOR, css_selector)):
                errtext = self.find_element_by_css_selector(css_selector).text
                # print the error, if the wrong dates/etc were entered by user.
                print(errtext)
                return True

            else:
                return False
                
        except NoSuchElementException:
            return False
         

    def submit(self, css_selector):
        try:
            submit_btn = self.find_element_by_css_selector(css_selector)
            submit_btn.click()
        except:
            print("Error\n")
    
    def get_table_data(self, css_selector, tag):
        print("Getting data...")
        # check if an error occurred.
        if self.check_errors('body > div.container-fluid.custom-padding > div > div > div.span9 > table > tbody > tr:nth-child(10) > td > span'):
            table_body = self.find_element_by_css_selector('body > div.container-fluid.custom-padding > div > div > div.span9 > table > tbody > tr:nth-child(12) > td > table > tbody')
            
        else: 
            table_body = self.find_element_by_css_selector('body > div.container-fluid.custom-padding > div > div > div.span9 > table > tbody > tr:nth-child(11) > td > table > tbody')

        # proceed to copy over the data
        data_rows = table_body.find_elements_by_tag_name('tr')
        self.data = []
        for i in range(1, len(data_rows)):
            data_row = data_rows[i].find_elements_by_tag_name('td')
            data_set = {'period_start':data_row[0].text.strip(), 
                    'period_end':data_row[1].text.strip(), 
                    'time_high_tide':data_row[2].text.strip(), 
                    'elevation_above_datum':float(data_row[3].text.strip()),
                    'tide_type':data_row[4].text.strip(),
                    'duration':float(data_row[5].text.strip()) }

            self.data.append(data_set)

    def get_data(self):
        return self.data


# -----Functions-----

def get_s_name(station_id, maindriver):
    text = maindriver.find_element_by_xpath('/html/body/div[2]/div/div/div[2]/form').text.split()
    name = ""
    for it in range(4, len(text)):
        if text[it] == 'Data':
            break
        name += text[it] + " "

    return name.strip()

def save_data(data, station_name, startdate, enddate):
    savdir = input("Data will be saved at {0} Change?(y/n)".format(os.getcwd()))
    if savdir.lower() == 'y':
        savdir = input("Enter a directory to save data: ")
        if os.path.exists(savdir):
            os.chdir(savdir)
        else:
            os.mkdir(savdir)
            os.chdir(savdir)
    # format start/end dates in filename
    s_mon, s_d, s_yr = startdate
    e_mon, e_d, e_yr = enddate
    name = station_name.split(',')
    startdate = "{0}-{1}-{2}".format(s_yr, s_mon, s_d)
    enddate = "{0}-{1}-{2}".format(e_yr, e_mon, e_d)
    fname = "{0} Inundation Data{1} - {2}".format(name, startdate, enddate)
    # write to txt file
    try:
        with open(fname + ".txt", 'w') as datfile:
            
            for dataset in data:
                datfile.write(json.dumps(dataset))
                datfile.write('\n')
            datfile.close()
        print("Saved to txt file.")
    except:
        print("Error writing to txt file.")

    # save as a python-shelve object.
    try:
        with shelve.open(fname) as db:
            cnt = 0
            for dataset in data:
                db['data{0}'.format(cnt)] = dataset
                cnt += 1
        db.close()
        print("Saved as a python shelve file.")
    except:
        print("Error saving as persistent object.")
    
        

def main():
    # -----Main program-----
    # ex. wrightsville beach station id = 8658163
    while True:
        station_id = input("Enter station ID: ")
        base_url = "https://tidesandcurrents.noaa.gov/inundation/AnalysisParams?id={0}".format(station_id)
        
        # -----startup selenium webdriver-----
        maindriver = InundationAnalysis(base_url)

        # wait for page to load
        maindriver.wait_page('#paramform > table.table > tbody > tr:nth-child(9) > td > input[type=text]', "Loading page", "Success")
    
    
        # get name of station      
        station_name = get_s_name(station_id, maindriver)
        print("Inputting html-forms for {0}...".format(station_name))
        # -----find and input the elevation, dates----- 
        maindriver.box_input('#paramform > table.table > tbody > tr:nth-child(9) > td > input[type=text]', maindriver.query.get_elevation())
        # begin-date input 
        maindriver.input_dropdown_date('#beginDate_Month_ID', 'beginMonth')      
        maindriver.input_dropdown_date('#beginDate_Day_ID', 'beginDay')  
        maindriver.box_input('#beginDate_Year_ID', 'beginYear')
        
        # end-date input
        maindriver.input_dropdown_date('#endDate_Month_ID', 'endMonth')
        maindriver.input_dropdown_date('#endDate_Day_ID', 'endDay')
        maindriver.box_input('#endDate_Year_ID', 'endYear')
        
        # submit the form
        print("Submitting...")
        maindriver.submit('#paramform > input[type=submit]:nth-child(31)')
            

        # wait for page to load
        maindriver.wait_page('body > div.container-fluid.custom-padding > div > div > div.span9 > table > tbody > tr:nth-child(11) > td > table > tbody', "Loading Results", "Page Loaded")
        # check if forms are correct.
        if maindriver.check_errors('#paramform > span'):
            continue # to top of loop     
    
        # save the table into memory as a lsit of dicts
        # check if there are 'gaps' in data, if so, advance the tr:nth-child from 11-12
        maindriver.get_table_data('body > div.container-fluid.custom-padding > div > div > div.span9 > table > tbody > tr:nth-child(11) > td > table > tbody', 'tr')
        data = maindriver.get_data()
        maindriver.close()
        save_data(data, station_name, maindriver.query.raw_startdate, maindriver.query.raw_enddate)
        
        
main()