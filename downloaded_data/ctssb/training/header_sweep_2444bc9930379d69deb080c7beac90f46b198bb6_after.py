import requests
import colorama
import getopt
import datetime
from sys import argv, exit


def sweep_and_get_results(target):

    header_list = {}
    is_https = False
    request_list = ["GET|"+target, "POST|"+target, "GET|"+target+"/asdf", "POST|"+target+"/asdf"]

    for sample_req in request_list:
        method, req_url = sample_req.split("|")
        r = requests.request(method, req_url)
        header_list.update(r.headers.lower_items())
        if "https" in r.url:
            is_https = True

    return header_list, is_https


def assess_security_headers(header_list, is_https=False):

    must_have_headers = ["X-XSS-Protection", "X-Frame-Options", "Strict-Transport-Security", "Content-Security-Policy"]
    must_not_have_headers = ["Server", "x-powered-by", "x-aspnet-version", "Access-Control-Allow-Origin"]
    must_have_values = {"Content-Type": "charset", "Cache-Control": "no-cache", "X-Permitted-Cross-Domain-Policies": "none",
                        "X-Content-Type-Options": "nosniff"}

    missing_headers = {}
    found_headers = {}
    bad_headers = {}
    bad_cookies = {}

    for sec_header in must_have_headers:
        if sec_header.lower() not in header_list.keys() and sec_header != "Strict-Transport-Security":
            missing_headers[sec_header] = "Header Not Present."

        if sec_header == "Strict-Transport-Security" and is_https is True and sec_header.lower() not in header_list.keys():
            missing_headers[sec_header] = "HTTPS used and Header Not Present."

        if sec_header.lower() in header_list.keys() and sec_header not in missing_headers.keys():
            found_headers[sec_header] = header_list[sec_header.lower()]

    for sec_header, sec_value in must_have_values.iteritems():
        if sec_header.lower() not in header_list.keys():
            missing_headers[sec_header] = "Header Not Present"
        elif sec_value.lower() not in (header_list[sec_header.lower()]).lower():
            missing_headers[sec_header] = "Missing security value : " + sec_value
            if sec_header == "Cache-Control":
                missing_headers[sec_header] += " (Note: value should be present only if sensitive data transmitted)"

        else:
            found_headers[sec_header] = header_list[sec_header.lower()]

    for bad_header in must_not_have_headers:
        if bad_header.lower() in header_list.keys():
            bad_headers[bad_header] = header_list[bad_header.lower()]
            if "access-control-allow-origin" in bad_header.lower():
                bad_headers[bad_header] += " + (CORS) Check the actual header value to infer severity. ((*) is the highest severity) +"

    try:
        cookies = header_list["set-cookie"].split("\n")

    except KeyError:
        cookies = {}
    for cookie in cookies:

        if "httponly" not in cookie.lower():
            try:
                bad_cookies[cookie] += "+ Missing `HTTPOnly` flag +"
            except KeyError:
                bad_cookies[cookie] = "+ Missing `HTTPOnly` flag +"

        if "secure" not in cookie.lower() and is_https is True:
            try:
                bad_cookies[cookie] += "+ Missing `Secure` flag +"
            except KeyError:
                bad_cookies[cookie] = "+ Missing `Secure` flag +"

    return [found_headers, missing_headers, bad_headers, bad_cookies]


def header_sweep(argv):
    target_url = ""
    output_file = ""
    try:
        opts, args = getopt.getopt(argv, "ht:o:")
    except getopt.GetoptError:
        print(colorama.Fore.BLUE + "usage : header_sweep.py -t <target_url> -o <output_file>")
        exit(2)

    if len(argv) == 0:
        print(colorama.Fore.BLUE + "usage : header_sweep.py -t <target_url> -o <output_file>")
        exit(2)

    for opt, arg in opts:
        if opt == "-h":
            print(colorama.Fore.BLUE + "usage : header_sweep.py -t <target_url> -o <output_file>")
            exit()
        elif opt == "-t":
            target_url = arg
        elif opt == "-o":
            output_file = arg

    if output_file != "":
        with open(output_file, "w+") as fp:
            fp.write(colorama.Fore.BLUE + "+++ Welcome to header sweeper tool written by Dante +++\n")
            fp.write(colorama.Fore.BLUE + "+++ Target is : " + target_url + " +++\n")
            fp.write(colorama.Fore.BLUE + "+++ Initializing Sweep at : " + str(datetime.datetime.now()) + " +++\n\n\n")

    print(colorama.Fore.BLUE + "+++ Welcome to header sweeper tool written by Dante +++")
    print(colorama.Fore.BLUE + "+++ Target is : " + target_url + " +++")
    print(colorama.Fore.BLUE + "+++ Initializing Sweep at : " + str(datetime.datetime.now()) + " +++")
    print(colorama.Fore.BLUE + "\r---------------------------------------------------------------------")

    header_list, is_https = sweep_and_get_results(target_url)
    print(colorama.Fore.BLUE+ "\n Headers collected, evaluating...\n\n---------------------------------------------------------------------")
    results = assess_security_headers(header_list, is_https)

    strengths = results[0]
    issues = results[1]
    bads = results[2]
    cookies = results[3]

    print(colorama.Fore.BLUE + "\n\n+++ Headers assessment results : +++")
    if output_file != "":
            with open(output_file, "a+") as fp:
                fp.write(colorama.Fore.BLUE + "\n\n+++ Headers assessment results : +++\n")

    for issue, issue_reason in issues.iteritems():
        if output_file != "":
            with open(output_file, "a+") as fp:
                fp.write(colorama.Fore.RED + "*** " + issue + " : " + issue_reason + " ***\n")
        print(colorama.Fore.RED + "*** " + issue + " : " + issue_reason + " ***")

    for strength, value in strengths.iteritems():
        if output_file != "":
            with open(output_file, "a+") as fp:
                fp.write(colorama.Fore.GREEN + "*** " + strength + " : " + value + " ***\n")
        print(colorama.Fore.GREEN + "*** " + strength + " : " + value + " ***")

    if len(bads) > 0:
        print(colorama.Fore.BLUE + "\n\n+++ Headers detected with possible insecure values or sensitive information contained : +++")
        if output_file != "":
                with open(output_file, "a+") as fp:
                    fp.write(colorama.Fore.BLUE + "\n\n+++ Headers detected with possible insecure values or sensitive information contained : +++\n")
        for bad, value in bads.iteritems():
            if output_file != "":
                with open(output_file, "a+") as fp:
                    fp.write(colorama.Fore.RED + "*** " + bad + " : " + value + " ***\n")
            print(colorama.Fore.RED + "*** " + bad + " : " + value + " ***")

    if len(cookies) > 0:
        print(colorama.Fore.BLUE + "\n\n+++ Cookies detected with security flags not set : +++ \n")
        if output_file != "":
                with open(output_file, "a+") as fp:
                    fp.write(colorama.Fore.BLUE + "\n\n+++ Cookies detected with security flags not set : +++ \n")
        for cookie, value in cookies.iteritems():
            if output_file != "":
                with open(output_file, "a+") as fp:
                    fp.write(colorama.Fore.RED + "*** " + cookie + "  " + value + " ***\n")
            print(colorama.Fore.RED + "*** " + cookie + "  " + value + " ***")

    print(colorama.Fore.BLUE + "\n\n+++ Sweep Finished at : " + str(datetime.datetime.now()) + " +++")
    if output_file != "":
            with open(output_file, "a+") as fp:
                fp.write(colorama.Fore.BLUE + "\n\n+++ Sweep Finished at : " + str(datetime.datetime.now()) + " +++\n")


if __name__ == '__main__':
    colorama.init()
    header_sweep(argv[1:])
