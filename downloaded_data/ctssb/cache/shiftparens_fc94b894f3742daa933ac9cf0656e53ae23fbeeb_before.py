__all__ = ['VimEmitter']

import subprocess

class VimEmitter:
    def __init__(self, options):
        self.quiet = options.quiet
        self.server = options.server or self.discover_server()
        self.prepare_server()

    @classmethod
    def setup_argparse(cls, parser):
        parser.add_argument('--server', metavar='ID', dest='server', help='Vim server name to use. Use `vim --serverlist` to discover them. Default is to use the first one found', default=None)

    def discover_server(self):
        servers = subprocess.check_output(['vim', '--serverlist']).split("\n")
        return servers[0]

    def prepare_server(self):
        # set a flag when vim has focus
        subprocess.call(['vim', '--servername', self.server,
            '--remote-send', '<C-\><C-N>:au FocusGained * let g:vim_has_focus=1 | au FocusLost,TabLeave * let g:vim_has_focus=0<CR>'])
        # define a function for typing text ONLY if vim has focus and is in insert mode
        # doubles for sending key symbols, with mode='m'
        subprocess.call(['vim', '--servername', self.server,
            '--remote-send', ':function! Feedinsert(text, mode)<CR>if g:vim_has_focus == 1 && mode() =~ "^[ir]$"<CR>call feedkeys(a:text, a:mode)<CR>endif<CR>endfunction<CR><CR><CR>'])

    def feed(self, text, remap=False):
        # see :help feedkeys
        remap_flag = 'm' if remap else 'n'
        return """Feedinsert("%s", '%s')""" % (text, remap_flag)

    def send_to_vim(self, input, remap=False):
        self.log("sending %s" % self.feed(input, remap))
        subprocess.call(['vim', '--servername', self.server, '--remote-expr', self.feed(input)])

    VIM_SYMBOL = {
            'Escape': '<Esc>'
    }

    def key(self, symbol):
        if symbol in self.VIM_SYMBOL:
            self.send_to_vim("\\" + self.VIM_SYMBOL[symbol], True)

    def type(self, keys):
        self.send_to_vim(keys)

    def log(self, text):
        if not self.quiet:
            print text
