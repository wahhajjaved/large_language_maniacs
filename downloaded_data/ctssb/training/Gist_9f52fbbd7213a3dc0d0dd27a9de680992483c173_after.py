import functools
import json
import os
import shutil
import tempfile
import threading
import traceback
import webbrowser

import sublime
import sublime_plugin

from .request import api_request
from .exceptions import MissingCredentialsException
from . import helpers

settings = None


def plugin_loaded():
    global settings
    settings = sublime.load_settings('Gist.sublime-settings')

    if settings.get('max_gists') > 100:
        settings.set('max_gists', 100)  # the URLs are not updated.
        sublime.status_message("Gist: GitHub API does not support a value of higher than 100")

    MAX_GISTS = '?per_page=%d' % settings.get('max_gists')

    api_url = settings.get('api_url')  # Should add validation?
    settings.set('GISTS_URL', api_url + '/gists' + MAX_GISTS)
    settings.set('USER_GISTS_URL', api_url + '/users/%s/gists' + MAX_GISTS)
    settings.set('STARRED_GISTS_URL', api_url + '/gists/starred' + MAX_GISTS)
    settings.set('ORGS_URL', api_url + '/user/orgs')
    settings.set('ORG_MEMBERS_URL', api_url + '/orgs/%s/members')


def catch_errors(fn):
    @functools.wraps(fn)
    def _fn(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except MissingCredentialsException:
            sublime.error_message("Gist: GitHub token isn't provided in Gist.sublime-settings file. "
                                  "All other authorization methods are deprecated.")
            user_settings_path = os.path.join(sublime.packages_path(), 'User', 'Gist.sublime-settings')
            if not os.path.exists(user_settings_path):
                default_settings_path = os.path.join(sublime.packages_path(), 'Gist', 'Gist.sublime-settings')
                shutil.copy(default_settings_path, user_settings_path)
            sublime.active_window().open_file(user_settings_path)
        except:
            traceback.print_exc()
            sublime.error_message("Gist: unknown error (please, report a bug!)")

    return _fn


def create_gist(public, description, files):
    for filename, text in list(files.items()):
        if not text:
            sublime.error_message("Gist: Unable to create a Gist with empty content")
            return

    file_data = dict((filename, {'content': text}) for filename, text in list(files.items()))
    data = json.dumps({'description': description, 'public': public, 'files': file_data})
    gist = api_request(settings.get('GISTS_URL'), data)
    return gist


def update_gist(gist_url, file_changes, auth_token=None, https_proxy=None, new_description=None):
    request = {'files': file_changes}
    # print('Request:', request)
    if new_description is not None:
        request['description'] = new_description
    data = json.dumps(request)
    # print('Data:', data)
    result = api_request(gist_url, data, token=auth_token, https_proxy=https_proxy, method="PATCH")

    sublime.status_message("Gist updated")

    # print('Result:', result)
    return result


def open_gist(gist_url):
    gist = api_request(gist_url)
    # print('Gist:', gist)
    files = sorted(gist['files'].keys())

    for gist_filename in files:
        allowedTypes = ['text', 'application']
        type = gist['files'][gist_filename]['type'].split('/')[0]
        if type not in allowedTypes:
            continue

        view = sublime.active_window().new_file()

        helpers.gistify_view(view, gist, gist_filename)

        view.run_command('append', {
            'characters': gist['files'][gist_filename]['content'],
        })

        if settings.get('supress_save_dialog'):
            view.set_scratch(True)

        if settings.get('save-update-hook'):
            view.retarget(tempfile.gettempdir() + '/' + gist_filename)
            # Save over it (to stop us reloading from that file in case it exists)
            # But don't actually do a gist update
            view.settings().set('do-update', False)
            view.run_command('save')

        helpers.set_syntax(view, gist['files'][gist_filename])


def insert_gist(gist_url):
    gist = api_request(gist_url)
    files = sorted(gist['files'].keys())

    for gist_filename in files:
        view = sublime.active_window().active_view()

        is_auto_indent = view.settings().get('auto_indent')

        if is_auto_indent:
            view.settings().set('auto_indent', False)
            view.run_command('insert', {
                'characters': gist['files'][gist_filename]['content'],
            })
            view.settings().set('auto_indent', True)
        else:
            view.run_command('insert', {
                'characters': gist['files'][gist_filename]['content'],
            })



def insert_gist_embed(gist_url):
    gist = api_request(gist_url)
    files = sorted(gist['files'].keys())

    for gist_filename in files:
        view = sublime.active_window().active_view()

        template = '<script src="{0}"></script>'.format(gist['files'][gist_filename]['raw_url'])

        view.run_command('insert', {
            'characters': template,
        })


class GistCommand(sublime_plugin.TextCommand):
    public = True

    def mode(self):
        return "Public" if self.public else "Private"

    @catch_errors
    def run(self, edit):
        regions = [region for region in self.view.sel() if not region.empty()]

        if len(regions) == 0:
            regions = [sublime.Region(0, self.view.size())]
            gistify = True
        else:
            gistify = False

        region_data = [self.view.substr(region) for region in regions]

        window = self.view.window()

        def on_gist_description(description):
            filename = os.path.basename(self.view.file_name() if self.view.file_name() else '')

            @catch_errors
            def on_gist_filename(filename):
                # We need to figure out the filenames. Right now, the following logic is used:
                #   If there's only 1 selection, just pass whatever the user typed to Github.
                #       It'll rename empty files for us.
                #   If there are multiple selections and user entered a filename, rename the files from foo.js to
                #       foo (1).js, foo (2).js, etc.
                #   If there are multiple selections and user didn't enter anything, post the files as
                #       $SyntaxName 1, $SyntaxName 2, etc.
                if len(region_data) == 1:
                    gist_data = {filename: region_data[0]}
                else:
                    if filename:
                        (namepart, extpart) = os.path.splitext(filename)
                        make_filename = lambda num: "%s (%d)%s" % (namepart, num, extpart)
                    else:
                        syntax_name, _ = os.path.splitext(os.path.basename(self.view.settings().get('syntax')))
                        make_filename = lambda num: "%s %d" % (syntax_name, num)
                    gist_data = dict((make_filename(idx), data) for idx, data in enumerate(region_data, 1))

                gist = create_gist(self.public, description, gist_data)

                if not gist:
                    return

                gist_html_url = gist['html_url']
                sublime.set_clipboard(gist_html_url)
                sublime.status_message("%s Gist: %s" % (self.mode(), gist_html_url))

                if gistify:
                    helpers.gistify_view(self.view, gist, list(gist['files'].keys())[0])
                    # else:
                    # open_gist(gist['url'])

            window.show_input_panel('Gist File Name: (optional):', filename, on_gist_filename, None, None)

        window.show_input_panel("Gist Description (optional):", '', on_gist_description, None, None)


class GistViewCommand(object):
    """A base class for commands operating on a gistified view"""

    def is_enabled(self):
        return self.gist_url() is not None

    def gist_url(self):
        return self.view.settings().get("gist_url")

    def gist_html_url(self):
        return self.view.settings().get("gist_html_url")

    def gist_filename(self):
        return self.view.settings().get("gist_filename")

    def gist_description(self):
        return self.view.settings().get("gist_description")


class GistCopyUrl(GistViewCommand, sublime_plugin.TextCommand):
    def run(self, edit):
        sublime.set_clipboard(self.gist_html_url())


class GistOpenBrowser(GistViewCommand, sublime_plugin.TextCommand):
    def run(self, edit):
        webbrowser.open(self.gist_html_url())


class GistRenameFileCommand(GistViewCommand, sublime_plugin.TextCommand):
    def run(self, edit):
        old_filename = self.gist_filename()

        @catch_errors
        def on_filename(filename):
            if filename and filename != old_filename:
                text = self.view.substr(sublime.Region(0, self.view.size()))
                file_changes = {old_filename: {'filename': filename, 'content': text}}
                new_gist = update_gist(self.gist_url(), file_changes)
                helpers.gistify_view(self.view, new_gist, filename)
                sublime.status_message('Gist file renamed')

        self.view.window().show_input_panel('New File Name:', old_filename, on_filename, None, None)


class GistChangeDescriptionCommand(GistViewCommand, sublime_plugin.TextCommand):
    def run(self, edit):
        @catch_errors
        def on_gist_description(description):
            if description and description != self.gist_description():
                gist_url = self.gist_url()
                new_gist = update_gist(gist_url, {}, new_description=description)
                for window in sublime.windows():
                    for view in window.views():
                        if view.settings().get('gist_url') == gist_url:
                            helpers.gistify_view(view, new_gist, view.settings().get('gist_filename'))
                sublime.status_message('Gist description changed')

        self.view.window().show_input_panel('New Description:', self.gist_description() or '',
                                            on_gist_description, None, None)


class GistUpdateFileCommand(GistViewCommand, sublime_plugin.TextCommand):
    @catch_errors
    def run(self, edit):
        text = self.view.substr(sublime.Region(0, self.view.size()))
        changes = {self.gist_filename(): {'content': text}}
        update_gist(self.gist_url(), changes)
        sublime.status_message("Gist updated")


class GistDeleteFileCommand(GistViewCommand, sublime_plugin.TextCommand):
    @catch_errors
    def run(self, edit):
        changes = {self.gist_filename(): None}
        update_gist(self.gist_url(), changes)
        helpers.ungistify_view(self.view)
        sublime.status_message("Gist file deleted")


class GistDeleteCommand(GistViewCommand, sublime_plugin.TextCommand):
    @catch_errors
    def run(self, edit):
        gist_url = self.gist_url()
        api_request(gist_url, method='DELETE')
        for window in sublime.windows():
            for view in window.views():
                if view.settings().get("gist_url") == gist_url:
                    helpers.ungistify_view(view)
        sublime.status_message("Gist deleted")


class GistPrivateCommand(GistCommand):
    public = False


class GistListCommandBase(object):
    gists = orgs = users = []

    @catch_errors
    def run(self, *args):
        filtered = helpers.gists_filter(api_request(settings.get('GISTS_URL')))
        filtered_stars = helpers.gists_filter(api_request(settings.get('STARRED_GISTS_URL')))

        self.gists = filtered[0] + filtered_stars[0]
        gist_names = filtered[1] + list(map(lambda x: [u"★ " + x[0]], filtered_stars[1]))

        if settings.get('include_users'):
            self.users = list(settings.get('include_users'))
            gist_names = [["> " + user] for user in self.users] + gist_names

        if settings.get('include_orgs'):
            if settings.get('include_orgs'):
                self.orgs = [org.get("login") for org in api_request(settings.get('ORGS_URL'))]
            else:
                self.orgs = settings.get('include_orgs')

            gist_names = [["> " + org] for org in self.orgs] + gist_names

        # print(gist_names)

        def on_gist_num(num):
            offOrgs = len(self.orgs)
            offUsers = offOrgs + len(self.users)

            if num < 0:
                pass
            elif num < offOrgs:
                self.gists = []

                members = [member.get("login") for member in
                           api_request(settings.get('ORG_MEMBERS_URL') % self.orgs[num])]
                for member in members:
                    self.gists += api_request(settings.get('USER_GISTS_URL') % member)

                filtered = helpers.gists_filter(self.gists)
                self.gists = filtered[0]
                gist_names = filtered[1]
                # print(gist_names)

                self.orgs = self.users = []
                self.get_window().show_quick_panel(gist_names, on_gist_num)
            elif num < offUsers:
                filtered = helpers.gists_filter(api_request(settings.get('USER_GISTS_URL') % self.users[num - offOrgs]))
                self.gists = filtered[0]
                gist_names = filtered[1]
                # print(gist_names)

                self.orgs = self.users = []
                self.get_window().show_quick_panel(gist_names, on_gist_num)
            else:
                self.handle_gist(self.gists[num - offUsers])

        self.get_window().show_quick_panel(gist_names, on_gist_num)


class GistListCommand(GistListCommandBase, sublime_plugin.WindowCommand):
    @catch_errors
    def handle_gist(self, gist):
        open_gist(gist['url'])

    def get_window(self):
        return self.window


class GistListener(GistViewCommand, sublime_plugin.EventListener):
    @catch_errors
    def on_pre_save(self, view):
        if view.settings().get('gist_filename') is not None:
            if settings.get('save-update-hook'):
                # we ignore the first update, it happens upon loading a gist
                if not view.settings().get('do-update'):
                    view.settings().set('do-update', True)
                    return
                text = view.substr(sublime.Region(0, view.size()))
                changes = {view.settings().get('gist_filename'): {'content': text}}
                gist_url = view.settings().get('gist_url')
                # Start update_gist in a thread so we don't stall the save
                threading.Thread(target=update_gist,
                                 args=(gist_url, changes, settings.get('token'), settings.get('https_proxy'))
                                 ).start()


class InsertGistListCommand(GistListCommandBase, sublime_plugin.WindowCommand):
    @catch_errors
    def handle_gist(self, gist):
        insert_gist(gist['url'])

    def get_window(self):
        return self.window


class InsertGistEmbedListCommand(GistListCommandBase, sublime_plugin.WindowCommand):
    @catch_errors
    def handle_gist(self, gist):
        insert_gist_embed(gist['url'])

    def get_window(self):
        return self.window


class GistAddFileCommand(GistListCommandBase, sublime_plugin.TextCommand):
    def is_enabled(self):
        return self.view.settings().get('gist_url') is None

    def handle_gist(self, gist):
        @catch_errors
        def on_filename(filename):
            if filename:
                text = self.view.substr(sublime.Region(0, self.view.size()))
                changes = {filename: {'content': text}}
                new_gist = update_gist(gist['url'], changes)
                helpers.gistify_view(self.view, new_gist, filename)
                sublime.status_message("File added to Gist")

        filename = os.path.basename(self.view.file_name() if self.view.file_name() else '')
        self.view.window().show_input_panel('File Name:', filename, on_filename, None, None)

    def get_window(self):
        return self.view.window()
