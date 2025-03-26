from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.options import Options
from time import sleep
import json

# given a dict when called by user
# dict is used as the root
# allows interactive browsing of dict and its values
def dict_crawler(dictionary, depth=0, parent_list=["root"], parent_values_list=[], done=False):
    parent_values_list.append(dictionary)
    #print(
    #    "Entering Dict\ne/q:exit\nt:type\nk:keys\nl:list items\nn:len of keys or list\np:go to parent\n1-9:go to index/key at that num\nv:enter get value at index\nh:print this message")
    exit_dict = False
    if done:
        return False

    print("\ndepth", depth)
    print("parent_list", parent_list)
    # print("parent values list",parent_values_list)
    while not exit_dict:
        inpt = input("input>")
        # try for 1-9
        try:
            index = int(inpt)
            #print("got value", index)

            if type(dictionary) == type(dict()):
                c = 0
                for i in dictionary.keys():
                    if c == index - 1:
                        dest = i
                    c += 1
            else:
                dest = index - 1
            print("dest", dest)
            try:
                parent_list.append(dest)
                depth += 1

                exit_dict = dict_crawler(dictionary[dest], depth, parent_list, parent_values_list, done)
            except:
                pass
        except:
            print()
        if inpt == "e" or inpt == "q":
            exit_dict = True
        if inpt == "t":
            print("type is", type(dictionary))
        if inpt == "k":
            print(dictionary.keys())
            counter = 1
            for key in dictionary.keys():
                print(str(counter) + ":" + str(key))
                counter += 1
        if inpt == "l":
            counter = 1
            for item in dictionary:
                print(str(counter) + ":" + str(item))
                counter += 1

        if inpt == "n":
            try:
                print("Num of keys is", len(dictionary.keys()))
            except:
                try:
                    print("Num of items in list is", len(dictionary))
                except:
                    pass
        if inpt == "p":
            try:
                print("parent is", parent_list[depth - 1])
                if parent_list[depth - 1] == "root":

                    dest = parent_values_list[0]
                    print("dest", dest)
                    depth = 0
                    parent_list.pop(len(parent_list) - 1)
                    parent_values_list.pop(len(parent_values_list) - 1)
                    exit_dict = dict_crawler(dest, depth, parent_list, parent_values_list, done)

                else:

                    dest = parent_values_list[depth - 2][parent_list[depth - 1]]
                    print("dest", dest)
                    depth -= 1
                    parent_list.pop(len(parent_list) - 1)
                    parent_values_list.pop(len(parent_values_list) - 1)
                    exit_dict = dict_crawler(dest, depth, parent_list, parent_values_list, done)

            except:
                print("at root")

        if inpt == "v":
            value_target = input("Enter index of value wanted")

            if value_target == "*":
                print("all values")
                try:
                    for i in dictionary.keys():
                        print(str(i) + ":" + str(dictionary[i]))
                except:
                    for i in dictionary:
                        print(str(dictionary.index(i)) + ":" + str(i))
            else:
                index = int(value_target)

                if type(dictionary) == type(dict()):
                    c = 0
                    for i in dictionary.keys():
                        if c == index - 1:
                            dest = i
                        c += 1
                else:
                    dest = index - 1
                print("dest", dest)
                print(type(dictionary[dest]))
                print(dictionary[dest])
        if inpt == "h":
            print(
                "e/q:exit\nt:type\nk:keys\nl:list items\nn:len of keys or list\np:go to parent\n1-9:go to index/key at that num\nv:enter get value at index\nh:print this message")
            print("parent list / path")
            print(parent_list)
    return True




def run_main():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(chrome_options=chrome_options)

    print("Getting list of classes")
    #sign into lconnect
    driver.get("http://lconnect.wit.edu")
    #driver.delete_all_cookies()
    username = "username"
    password = "password"
    with open("creds","r") as creds:
        lines = creds.readlines()
        username = lines[0][:-1]
        password = lines[1]


    #print(driver.title)

    user_name_field = driver.find_element_by_id("username")
    password_field = driver.find_element_by_id("password")
    sign_in_button = driver.find_elements_by_xpath("/html/body/div/div[3]/form/table/tbody/tr[4]/td[1]/div/input")[0]

    user_name_field.send_keys(username)
    password_field.send_keys(password)
    sign_in_button.send_keys(Keys.RETURN)
    #print(driver.title)
    leopardweb_button = driver.find_elements_by_xpath("/html/body/div[8]/div/div[2]/div[2]/div[1]/div/div[1]/section/div/div/div/div[1]/p[1]/a/img")[0]

    leopardweb_button.click()
    handles = list(driver.window_handles)
    old_window = driver.current_window_handle

    handles.remove(driver.current_window_handle)
    driver.switch_to_window(handles[0])

    #open leopardweb in mroe permnetn instanece
    driver.get("https://prodweb2.wit.edu/SSBPROD/twbkwbis.P_GenMenu?name=bmenu.P_StuMainMnu")
    #print(driver.title)
    student_tab = driver.find_elements_by_xpath("/html/body/div[1]/div[2]/span/map/table/tbody/tr[1]/td/table/tbody/tr/td[3]/a")[0]
    #student tab
    #print(driver.title)

    registration_button = driver.find_elements_by_xpath("/html/body/div[3]/table[1]/tbody/tr[1]/td[2]/a")[0]
    registration_button.click()
    #print(driver.title)
    #registration button page
    search_button = driver.find_elements_by_xpath("/html/body/div[3]/table[1]/tbody/tr[3]/td[2]/a")[0]
    search_button.click()
    #print(driver.title)
    #select a search term for classes
    dropdown = driver.find_element_by_id("term_input_id")
    selecting = Select(dropdown)
    selecting.select_by_visible_text("Summer 2018")

    submit = driver.find_elements_by_xpath("/html/body/div[3]/form/input[2]")[0]
    submit.click()
    #print(driver.title)
    #do advanced search to get all
    advanced_search_button  =driver.find_elements_by_xpath("/html/body/div[3]/form/input[18]")[0]
    advanced_search_button.click()
    #print(driver.title)
    subjects = ["ARCT","ARCH","BIOL","BMED","BLDG","CHEM","TCNA","CIVE","COMM","COMP","TCON","TCLI","CONM","TCMC","COOP","DSGN","TDRW","ECON","ELEC","TEIT","ENGR","ENGL","FMGT","CMFM","TFMC","HIST","HUMN","HUSS","INDS","INTD","TJEC","LITR","TMTO","MGMT","MANF","MATH","MECH","TCAD","PHIL","PHYS","POLS","PSYC","SOCL","SURV","TWEL"]
    subject_select = driver.find_element_by_id("subj_id")
    subject_selecting = Select(subject_select)
    for sub in subjects:
        subject_selecting.select_by_value(sub)

    #go to big list
    section_search_button = driver.find_elements_by_xpath("/html/body/div[3]/form/span/input[1]")[0]
    section_search_button.click()
    #print(driver.title)

    source = str(driver.page_source)
    source = source[source.find("Sections Found"):source.find("Skip to top")]

    source_lines = source.split("\n")
    #print(len(source_lines))
    data_lines = []
    adding = False
    for line in source_lines:
        should_add = (line.find("<td class=")>-1)
        #print("line: ",line,"\nadding: ",adding,"\nshould add",should_add)

        if should_add:
            data_lines.append(line)
    #print(len(data_lines))

    table_stuff_string = "\n".join(data_lines)
    split_on_classes = table_stuff_string.split("<td class=\"dddefault\"><a href=\"")
    #print(len(split_on_classes))
    #now make dict with crn being key and other values as values per class
    classes_dict = dict()
    for course in split_on_classes:
        crn = course[course.find("return true\">")+13:course.find("return true\">")+18]
        is_valid_crn = False
        try:
            int(crn)
            is_valid_crn = True
        except:
            #print("bad CRN")
            #print(course)
            pass
        if is_valid_crn:
            temp_couse = course.replace("<td class=\"dddefault\">","").replace("</td>","").replace("(<abbr title=\"Primary\">P</abbr>)","").replace("<abbr title=\"To Be Announced\">TBA</abbr>","TBA")
            #print(temp_couse,"\n\n\n")
            course_list = temp_couse.split("\n")
            course_list = course_list[1:]
            #print(course_list)
            classes_dict[crn] = dict()
            classes_dict[crn]["Subject"] = course_list[0]
            classes_dict[crn]["Course"] = course_list[1]
            classes_dict[crn]["Section"] = course_list[2]
            classes_dict[crn]["Campus"] = course_list[3]
            classes_dict[crn]["Credit hrs"] = course_list[4]
            classes_dict[crn]["Name"] = course_list[5]
            classes_dict[crn]["Days"] = course_list[6]
            classes_dict[crn]["Time"] = course_list[7]
            classes_dict[crn]["Capacity"] = course_list[8]
            classes_dict[crn]["Filled"] = course_list[9]
            classes_dict[crn]["Remaining"] = course_list[10]
            classes_dict[crn]["Instructor"] = course_list[11]
            classes_dict[crn]["Location"] = course_list[13]
            classes_dict[crn]["Full"] = bool(int(course_list[10])<=1)

    #now have dict of csvs and such
    #print(classes_dict.keys())

    print("Checking for open slots")
    for crn in crns_to_watch:
        if not classes_dict[crn]["Full"]:
            print("CRN:",crn," isn't full\nAttempting to register")
            print(classes_dict[crn])

            #now check if in classes are full
            student_tab = driver.find_elements_by_xpath("/html/body/div[1]/div[2]/span/map/table/tbody/tr[1]/td/table/tbody/tr/td[3]/a")[0]
            student_tab.click()
            #print(driver.title)

            registration_button = driver.find_elements_by_xpath("/html/body/div[3]/table[1]/tbody/tr[1]/td[2]/a")[0]
            registration_button.click()
            #print(driver.title)

            add_or_drop_button = driver.find_elements_by_xpath("/html/body/div[3]/table[1]/tbody/tr[2]/td[2]/a")[0]
            add_or_drop_button.click()
            #print(driver.title)
            crn_input = driver.find_element_by_id("crn_id1")
            crn_input.send_keys(crn)
            submit_button = driver.find_elements_by_xpath("/html/body/div[3]/form/input[19]")[0]
            submit_button.click()

            status = driver.find_elements_by_xpath("/html/body/div[3]/form/table[4]/tbody/tr[2]/td[1]")[0]
            print("Registration result for CRN:",crn," is ",status.text)

    #close chrome that was used
    driver.close()
    driver.switch_to_window(old_window)
    driver.close()


crns_to_watch = []

with open("crns","r") as crms_file:
    crns_lines = crms_file.readlines()
    for crn in crns_lines:
        crns_to_watch.append(crn.replace("\n",""))



cycles = int(json.load(open('config.json'))["cycles"])
wait_time = int(json.load(open('config.json'))["wait_time"])

if cycles == -1:
    while(True):
        run_main()
        sleep(wait_time)
else:

    for i in range(1,cycles):
        run_main()
        sleep(wait_time)
