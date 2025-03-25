"""
Implementation of all of the individual 'twill' commands.


"""

# export:
__all__ = ['reset_state',
           'extend_with',
           'go',
           'reload',
           'code',
           'follow',
           'find',
           'notfind',
           'back',
           'show',
           'echo',
           'sleep',
           'agent',
           'showforms',
           'submit',
           'formvalue',
           'fv',
           'formclear',
           'getinput',
           'getpassword',
           'save_cookies',
           'load_cookies',
           'clear_cookies',
           'show_cookies',
           ]

import re, getpass, urllib2, time

from mechanize import Browser
from mechanize._mechanize import BrowserStateError, LinkNotFoundError

import ClientCookie, ClientForm
from errors import TwillAssertionError
from utils import trunc, print_form, set_form_control_value, journey

#
# _TwillBrowserState
#

class _TwillBrowserState:
    """
    Wrap mechanize behavior in a simple stateful way.
    """
    def __init__(self):
        self._browser = Browser()
        self._last_result = None
        self._last_submit = None

        # create & set a cookie jar.
        policy = ClientCookie.DefaultCookiePolicy(rfc2965=True)
        cj = ClientCookie.LWPCookieJar(policy=policy)
        self._browser.set_cookiejar(cj)

        self.cj = cj

        # ignore robots.txt
        self._browser.set_handle_robots(None)

    def url(self):
        if self._last_result:
            return self._last_result.get_url()
        return " *empty page* "

    def go(self, url):
        """
        Visit given URL.
        """
        url = url.replace(' ', '%20')
        if url.find('://') == -1:
            url = 'http://%s' % (url,)  # mimic browser behavior
        
        self._last_result = journey(self._browser.open, url)
        print '==> at', self._last_result.get_url()

    def reload(self):
        self._last_result = journey(self._browser.reload)
        print '==> reloaded'

    def back(self):
        """
        Return to previous page, if possible.
        """
        back_url = self._browser.back
        try:
            self._last_result = journey(back_url)
        except AttributeError:
            self._last_result = None
        except BrowserStateError:
            self._last_result = None
        
        if self._last_result:
            print '==> back to', self._last_result.get_url()
        else:
            print '==> no previous URL; ignoring.'
            
    def get_code(self):
        """
        Get the HTTP status code received for the current page.
        """
        return self._last_result.get_http_code()

    def get_html(self):
        """
        Get the HTML for the current page.
        """
        return self._last_result.get_page()

    def get_url(self):
        """
        Get the URL of the current page.
        """
        return journey(self._last_result.get_url)

    def find_link(self, pattern):
        """
        Find the first link with a URL, link text, or name matching the
        given pattern.
        """

        #
        # first, try to find a link matching that regexp.
        #
        
        try:
            l = self._browser.find_link(url_regex=pattern)
        except LinkNotFoundError:

            #
            # then, look for a text match.
            #
            
            try:
                l = self._browser.find_link(text_regex=pattern)
            except LinkNotFoundError:
                
                #
                # finally, look for a name match.
                #
                
                try:
                    l = self._browser.find_link(name_regex=pattern)
                except LinkNotFoundError:
                    l = None

        return l

    def follow_link(self, link):
        """
        Follow the given link.
        """
        try:
            self._last_result = journey(self._browser.follow_link, link)
            print '==> at', self._last_result.get_url()
        except urllib2.HTTPError, e:
            raise

    def set_agent_string(self, agent):
        """
        Set the agent string to the given value.
        """
        # currently doesn't work.
        # self._browser.set_persistent_headers([("User-agent", agent)])

    def showforms(self):
        """
        Pretty-print all of the forms.
        """
        for n, f in enumerate(self._browser.forms()):
            print_form(n, f)

    def get_form(self, formname):
        """
        Return the first form that matches 'formname'.
        """
        # first try regexps
        regexp = re.compile(formname)
        for f in self._browser.forms():
            if f.name and regexp.search(f.name):
                return f

        # ok, try number
        try:
            formnum = int(formname)
            return self._browser.forms()[formnum - 1]
        except ValueError:              # int() failed
            pass
        except IndexError:              # formnum was incorrect
            pass

        return None

    def get_form_field(self, form, fieldname):
        """
        Return the control that matches 'fieldname'.  Must be
        a *unique* regexp/exact string match.
        """
        found = None
        
        regexp = re.compile(fieldname)

        matches = [ ctl for ctl in form.controls \
                    if regexp.search(str(ctl.name)) ]

        if matches:
            if len(matches) == 1:
                found = matches[0]
            else:
                found = None

        if found is None:
            # try num
            clickies = [c for c in form.controls if c.is_of_kind('clickable')]
            try:
                fieldnum = int(fieldname)
                found = clickies[fieldnum]
            except ValueError:          # int() failed
                pass
            except IndexError:          # fieldnum was incorrect
                pass

        if found is None:
            # try value, for readonly controls like submit keys
            clickies = [ c for c in form.controls if c.value == fieldname \
                         and c.readonly ]
            if len(clickies) == 1:
                found = clickies[0]

        return found

    def clicked(self, form, control):

        if self._browser.form != form:
            # construct a function to choose a particular form; select_form
            # can use this to pick out a precise form.

            def choose_this_form(test_form, this_form=form):
                if test_form is this_form:
                    return True

                return False

            self._browser.select_form(predicate=choose_this_form)
            self._last_submit = None

        # record the last submit button clicked.
        if isinstance(control, ClientForm.SubmitControl):
            self._last_submit = control

    def submit(self, fieldname):
        if not self._browser._forms:
            raise Exception("no forms on this page!")
        
        form = self._browser.form
        if form is None:
            if len(self._browser._forms) == 1:
                form = self._browser._forms[0]
            else:
                raise Exception("more than one form; you must select one (use 'fv') before submitting")

        # no fieldname?  see if we can use the last submit button clicked...
        if not fieldname:
            if self._last_submit:
                ctl = self._last_submit
            else:
                # get first submit button in form.
                submits = [ c for c in form.controls \
                            if isinstance(c, ClientForm.SubmitControl) ]
                    
                if not len(submits):
                    raise Exception('no submission buttons!')
                
                ctl = submits[0]
                
        else:
            # fieldname given; find it.
            ctl = self.get_form_field(self._browser.form, fieldname)

        print 'Note: submit is using submit button: name="%s", value="%s"' % \
              (ctl.name, ctl.value)
        
        # got the submit control, now go there.
        control = ctl._click(self._browser.form, True, urllib2.Request)
        self._last_result = journey(self._browser.open, control)

    def save_cookies(self, filename):
        self.cj.save(filename, ignore_discard=True, ignore_expires=True)

    def load_cookies(self, filename):
        self.cj.load(filename, ignore_discard=True, ignore_expires=True)

    def clear_cookies(self):
        self.cj.clear()

    def show_cookies(self):
        print '\nThere are %d cookie(s) in the cookiejar.\n' % (len(self.cj,))
        if len(self.cj):
            for cookie in self.cj:
                print '\t', cookie

            print ''
        
state = _TwillBrowserState()

def reset_state():
    """
    >> reset_state

    Reset the browser completely.
    """
    global state
    state = _TwillBrowserState()

###

def go(url):
    """
    >> go <url>
    
    Visit the URL given.
    """
    state.go(url)

def reload():
    """
    >> reload
    
    Reload the current URL.
    """
    state.reload()

def code(should_be):
    """
    >> code <int>
    
    Check to make sure the response code for the last page is as given.
    """
    should_be = int(should_be)
    if state.get_code() != int(should_be):
        raise TwillAssertionError("code is %d, != %d" % (state.get_code(),
                                                         should_be))

def follow(what):
    """
    >> follow <regexp>
    
    Find the first matching link on the page & visit it.
    """
    regexp = re.compile(what)
    links = state.find_link(regexp)

    if links:
        state.follow_link(links)
        return

    raise TwillAssertionError("no links match to '%s'" % (what,))

def find(what):
    """
    >> find <regexp>
    
    Succeed if the regular expression is on the page.
    """
    regexp = re.compile(what)
    page = state.get_html()

    if not regexp.search(page):
        raise TwillAssertionError("no match to '%s'" % (what,))

def notfind(what):
    """
    >> notfind <regexp>
    
    Fail if the regular expression is on the page.
    """
    regexp = re.compile(what)
    page = state.get_html()

    if regexp.search(page):
        raise TwillAssertionError("match to '%s'" % (what,))

def back():
    """
    >> back
    
    Return to the previous page.
    """
    state.back()

def show():
    """
    >> show
    
    Show the HTML for the current page.
    """
    print state.get_html()

def echo(*strs):
    """
    >> echo <list> <of> <strings>
    
    Echo the arguments to the screen.
    """
    strs = map(str, strs)
    s = " ".join(strs)
    print s

def sleep(interval="1"):
    """
    >> sleep [<interval>]

    Sleep for the specified amount of time.
    If no interval is given, sleep for 1 second.
    """
    time.sleep(float(interval))

def agent(what):
    """
    >> agent <agent>
    
    Set the agent string -- does nothing, currently.
    """
    what = what.strip()
    agent = agent_map.get(what, what)
    state.set_agent_string(agent)

def submit(submit_button=None):
    """
    >> submit [<buttonspec>]
    
    Submit the current form (the one last clicked on) by clicking on the
    n'th submission button.  If no "buttonspec" is given, submit the current
    form by using the last clicked submit button.
    """
    state.submit(submit_button)

def showforms():
    """
    >> showforms
    
    Show all of the forms on the current page.
    """
    state.showforms()

def formclear(formname):
    """
    >> formclear <formname>
    
    Run 'clear' on all of the controls in this form.
    """
    form = state.get_form(formname)
    for control in form.controls:
        if control.readonly:
            continue

        control.clear()

def formvalue(formname, fieldname, value):
    """
    >> formvalue <formname> <field> <value>

    Set value of a form field.

    There are some ambiguities in the way formvalue deals with lists:
    'set' will *add* the given value to a multilist.

    Formvalue ignores read-only fields completely; if they're readonly,
    nothing is done.

    Available as 'fv' as well.
    """
    form = state.get_form(formname)
    control = state.get_form_field(form, fieldname)

    if control:
        state.clicked(form, control)
        if control.readonly:
            return

        set_form_control_value(control, value)
    else:
        print 'NO SUCH FIELD FOUND'
        # @CTB

fv = formvalue

def extend_with(module_name):
    """
    >> extend_with <module>
    
    Import contents of given module.
    """
    from twill.parse import get_twill_glocals
    global_dict, local_dict = get_twill_glocals()
    
    exec "from %s import *" % (module_name,) in global_dict, local_dict

def getinput(prompt):
    """
    >> getinput <prompt>
    Get input, store it in '__input__'.
    """
    from twill.parse import get_twill_glocals
    global_dict, local_dict = get_twill_glocals()

    inp = raw_input(prompt)

    local_dict['__input__'] = inp

def getpassword(prompt):
    """
    >> getpassword <prompt>
    
    Get a password ("invisible input"), store it in '__password__'.
    """
    from twill.parse import get_twill_glocals
    global_dict, local_dict = get_twill_glocals()

    inp = getpass.getpass(prompt)

    local_dict['__password__'] = inp

def save_cookies(filename):
    """
    >> save_cookies <filename>

    Save all of the current cookies to the given file.
    """
    state.save_cookies(filename)

def load_cookies(filename):
    """
    >> load_cookies <filename>

    Clear the cookie jar and load cookies from the given file.
    """
    state.load_cookies(filename)

def clear_cookies():
    """
    >> clear_cookies

    Clear the cookie jar.
    """
    state.clear_cookies()

def show_cookies():
    """
    >> show_cookies

    Show all of the cookies in the cookie jar.
    """
    state.show_cookies()

#### doesn't really work just yet.

agent_map = dict(
    ie5='Mozilla/4.0 (compatible; MSIE 5.0; Windows NT 5.1)',
    ie55='Mozilla/4.0 (compatible; MSIE 5.5; Windows NT 5.1)',
    ie6='Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1)',
    moz17='Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US; rv:1.7) Gecko/20040616',
    opera7='Opera/7.0 (Windows NT 5.1; U) [en]',
    konq32='Mozilla/5.0 (compatible; Konqueror/3.2.3; Linux 2.4.14; X11; i686)',
    saf11='Mozilla/5.0 (Macintosh; U; PPC Mac OS X; en-us) AppleWebKit/100 (KHTML, like Gecko) Safari/100',
    aol9='Mozilla/4.0 (compatible; MSIE 5.5; AOL 9.0; Windows NT 5.1)',)

