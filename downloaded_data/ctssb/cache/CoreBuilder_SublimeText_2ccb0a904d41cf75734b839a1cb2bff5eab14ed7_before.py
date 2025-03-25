import hashlib

import sublime
import sublime_plugin

from .show_error import show_error
from .cache import (set_cache, get_cache)

class DownloadAuthenticator(object):

    def __init__(self, window=None, on_complete=None):
        self.window = window
        self.on_complete = on_complete
        self.user_auth = {}

    def get_user_auth(self):
        settings = sublime.load_settings('CoreBuilder.sublime-settings')
        cache_ttl = settings.get('cache_length')
        if not settings.get('repository'):
            show_error(u'A valid repository URL should be defined at "repository" setting in "CoreBuilder.sublime-settings" file.')
            self.window.run_command('open_file', {'file': '${packages}/CoreBuilder/CoreBuilder.sublime-settings'})
            return

        cache_key = 'user_authentication'
        self.user_auth = get_cache(cache_key,{})

        def on_user_auth(user_name):
            if not user_name:
                def try_again_empty(self):
                    show_error(u'Username must be informed.')
                    self.window.show_input_panel("CoreBuilder - Username:", '', on_user_auth, None, None)
                    return

                sublime.set_timeout(try_again_empty, 1)
                return

            self.user_auth = {
                'user_name': user_name,
                'user_pass': None
            }

            def on_user_pass(user_pass):
                if not user_pass:
                    def try_again_empty():
                        show_error(u'User password must be informed.')
                        self.window.show_input_panel('CoreBuilder - Password:', '', on_user_pass, None, None)
                        return

                    sublime.set_timeout(try_again_empty, 1)
                    return
                
                self.user_auth['user_pass'] = hashlib.md5(user_pass).hexdigest()

                set_cache(cache_key, self.user_auth, cache_ttl)
                self.on_complete()
                return

            self.window.show_input_panel('CoreBuilder - Password:', '', on_user_pass, None, None)
            return
            
        if 'user_name' not in self.user_auth or not self.user_auth['user_name']:
            self.window.show_input_panel("CoreBuilder - Username:", '', on_user_auth, None, None)
            return
        
        set_cache(cache_key, self.user_auth, cache_ttl)
        self.on_complete()
        return

    def clear_user_auth(self):
        def on_clear():
            cache_ttl = sublime.load_settings('CoreBuilder.sublime-settings').get('cache_length')
            cache_key = 'user_authentication'
            set_cache(cache_key, {}, cache_ttl)
        sublime.set_timeout(on_clear, 1)
