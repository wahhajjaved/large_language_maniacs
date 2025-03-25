# -*- coding:utf-8 -*-

import sublime
import sublime_plugin
import os, datetime, subprocess

default_settings = {
    'memolist_template_dir_path': '$HOME/memo',
    'memolist_memo_suffix': 'md',
    'memolist_memo_date': '%Y-%m-%d'
}

insert_text = [
    'title: ',
    '==========',
    'date: ',
    'tags: []',
    'categories: []',
    '- - -'
]

def update_settings():
    global default_settings
    settings = sublime.load_settings('Sublime-memolist.sublime-settings')
    user_settings = {
        'memolist_template_dir_path': settings.get('memolist_template_dir_path'),
        'memolist_memo_suffix': settings.get('memolist_memo_suffix'),
        'memolist_memo_date': settings.get('memolist_memo_date')
    }
    default_settings.update(user_settings)

class MemolistInsertCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        global insert_text
        self.view.insert(edit, 0, '\n'.join(insert_text))

class MemolistOpenCommand(sublime_plugin.WindowCommand):
    def run(self):
        update_settings()
        self.window.show_input_panel(
            'Memo title:',
            self.get_filename(),
            self.open_memo_file,
            None, None)

    def open_memo_file(self, file_title):
        global insert_text, default_settings

        if file_title == '':
            return None

        dir_path = self.set_memolist_dir()
        insert_text[0] += file_title
        date_prefix = default_settings['memolist_memo_date'] + '-'
        file_name = datetime.datetime.today().strftime(date_prefix) + file_title

        self.window.open_file(dir_path + '/' + file_name + '.md')
        sublime.set_timeout(lambda:
                self.window.run_command('memolist_insert'), 0)

    def set_memolist_dir(self):
        global default_settings
        memo_dir = os.path.expandvars(default_settings['memolist_template_dir_path'])

        self.makedir(memo_dir)

        return memo_dir + '/'

    def makedir(self, path):
        if not os.path.isdir(path):
            os.mkdir(path)

    def get_filename(self):
        global insert_text
        insert_text[2] += datetime.datetime.today().strftime('%Y-%m-%d %H:%M')
        return ''

class MemolistShowCommand(sublime_plugin.WindowCommand):
    def run(self):
        global default_settings
        update_settings()
        self.memo_dir = os.path.expandvars(default_settings['memolist_template_dir_path'])

        try:
            self.files = os.listdir(self.memo_dir)
        except os.error:
            print('Memolist - open: No such file or directory')
            return None

        if '.DS_Store' in self.files:
            self.files.remove('.DS_Store')
 
        self.window.show_quick_panel(self.files, self.on_chosen)

    def on_chosen(self, index):
        if index == -1:
          return

        self.window.open_file(self.memo_dir + '/' + self.files[index])

class MemolistSearchCommand(sublime_plugin.WindowCommand):
    def run(self):
        update_settings()
        self.window.show_input_panel(
            'MemoGrep word:',
            '',
            self.search_memo_file,
            None, None)

    def search_memo_file(self, query):
        global default_settings
        self.results = []
        self.memo_dir = os.path.expandvars(default_settings['memolist_template_dir_path'])

        cmd = ['grep', '-nrl', query, self.memo_dir]

        if int(sublime.version()) >= 3000:
            try:
                output = subprocess.check_output(cmd, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError:
                print('Memolist - search: No such file or directory')
                return None
        else:
            try:
                output = subprocess.Popen(cmd, stdout=subprocess.PIPE, startupinfo=startupinfo).communicate()[0]
            except subprocess.CalledProcessError:
                print('Memolist - search: No such file or directory')
                return None

        for line in output.decode().splitlines():
            try:
                self.results.append(line.replace(self.memo_dir + '/', ''))
            except:
                pass

        if '.DS_Store' in self.results:
            self.results.remove('.DS_Store')

        self.window.show_quick_panel(self.results, self.on_chosen)

    def on_chosen(self, index):
        if index == -1:
          return

        self.window.open_file(self.memo_dir + '/' + self.results[index])

class MemolistListener(sublime_plugin.EventListener):
    def on_post_save(self, view):
        update_settings();

    def on_load(self, view):
        update_settings();
