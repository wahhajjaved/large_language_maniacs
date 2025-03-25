#
# This file is part of kaldi-active-grammar.
# (c) Copyright 2019 by David Zurow
# Licensed under the AGPL-3.0, with exceptions; see LICENSE.txt file.
#

import collections, copy, logging, multiprocessing, os, re, shlex, shutil, subprocess
import concurrent.futures
from contextlib import contextmanager
from io import open

from six.moves import range, zip

from . import _log, KaldiError
from .utils import ExternalProcess, debug_timer, load_symbol_table, platform, show_donation_message, symbol_table_lookup, touch_file
from .wfst import WFST, NativeWFST, SymbolTable
from .model import Model
from .wrapper import KaldiAgfCompiler, KaldiAgfNNet3Decoder, KaldiLafNNet3Decoder
import kaldi_active_grammar.alternative_dictation as alternative_dictation
import kaldi_active_grammar.defaults as defaults

_log = _log.getChild('compiler')


########################################################################################################################

class KaldiRule(object):

    def __init__(self, compiler, name, nonterm=True, has_dictation=None, is_complex=None):
        """
        :param nonterm: bool whether rule represents a nonterminal in the active-grammar-fst (only False for the top FST?)
        """
        self.compiler = compiler
        self.name = name
        self.nonterm = nonterm
        self.has_dictation = has_dictation
        self.is_complex = is_complex

        # id: matches "nonterm:rule__"; 0-based; can/will change due to rule unloading!
        self.id = int(self.compiler.alloc_rule_id() if nonterm else -1)
        if self.id > self.compiler._max_rule_id: raise KaldiError("KaldiRule id > compiler._max_rule_id")
        if self.id in self.compiler.kaldi_rule_by_id_dict: raise KaldiError("KaldiRule id already in use")
        if self.id >= 0:
            self.compiler.kaldi_rule_by_id_dict[self.id] = self

        # Private/protected
        self._fst_text = None
        self.compiled = False
        self.loaded = False
        self.reloading = False  # KaldiRule is in the process of the reload contextmanager
        self.has_been_loaded = False  # KaldiRule was loaded, then reload() was called & completed, and now it is not currently loaded, and load() we need to call the decoder's reload
        self.destroyed = False  # KaldiRule must not be used/referenced anymore

        # Public
        self.fst = WFST() if not self.compiler.native_fst else NativeWFST()
        self.filename = None
        self.matcher = None
        self.active = True

    def __repr__(self):
        return "%s(%s, %s)" % (self.__class__.__name__, self.id, self.name)

    fst_cache = property(lambda self: self.compiler.fst_cache)
    decoder = property(lambda self: self.compiler.decoder)
    pending_compile = property(lambda self: (self in self.compiler.compile_queue) or (self in self.compiler.compile_duplicate_filename_queue))
    pending_load = property(lambda self: self in self.compiler.load_queue)

    @property
    def filepath(self):
        if isinstance(self.fst, WFST):
            assert self.filename
            assert self.compiler.tmp_dir
            return os.path.join(self.compiler.tmp_dir, self.filename)
        raise KaldiError("Invalid KaldiRule.fst")

    def compile(self, lazy=False, duplicate=None):
        if self.destroyed: raise KaldiError("Cannot use a KaldiRule after calling destroy()")

        if self.fst.native:
            if self.compiler.decoding_framework == 'agf':
                self.fst_hclg_cp = self.compiler._compile_agf_graph(compile=True, nonterm=self.nonterm, input_fst=self.fst, return_output_fst=True)
            self.compiled = True
            return self

        if not self._fst_text:
            # self.fst.normalize_weights()
            self._fst_text = self.fst.get_fst_text()
            self.filename = self.fst_cache.get_fst_filename(self._fst_text)
        # if 'dictation' in self._fst_text: _log.log(50, '\n    '.join(["%s: FST text:" % self] + self._fst_text.splitlines()))  # log _fst_text

        if self.fst_cache.fst_is_current(self.filepath):
            _log.debug("%s: Skipped full compilation thanks to FileCache" % self)
            touch_file(self.filepath)
            self.compiled = True
            return self
        else:
            # _log.debug("%s: FileCache useless; has %s not %s" % (self, self.fst_cache.cache.get(self.filepath), self.fst_cache.hash_data(self._fst_text)))
            if duplicate:
                _log.warning("%s was supposed to be a duplicate compile, but was not found in FileCache")

        if lazy:
            if not self.pending_compile:
                if not any(self.filename == kaldi_rule.filename for kaldi_rule in self.compiler.compile_queue if self != kaldi_rule):
                    self.compiler.compile_queue.add(self)
                else:
                    self.compiler.compile_duplicate_filename_queue.add(self)
            return self

        return self.finish_compile()

    def finish_compile(self):
        # Must be thread-safe!
        assert self._fst_text
        _log.debug("%s: Compiling %sstate/%sarc/%sbyte fst.txt file to %s" % (self, self.fst.num_states, self.fst.num_arcs, len(self._fst_text), self.filename))
        if _log.isEnabledFor(2): _log.log(2, '\n    '.join(["%s: FST text:" % self] + self._fst_text.splitlines()))  # log _fst_text

        if self.compiler.decoding_framework == 'agf':
            self.compiler._compile_agf_graph(compile=True, nonterm=self.nonterm, input_text=self._fst_text, output_filename=self.filepath)
            self._fst_text = None
        elif self.compiler.decoding_framework == 'laf':
            # self.compiler._compile_laf_graph(compile=True, nonterm=self.nonterm, input_text=self._fst_text, output_filename=self.filepath)
            # self._fst_text_backup = self._fst_text  # FIXME: hack!
            # Keep self._fst_text, for adding directly later
            pass
        else: raise KaldiError("unknown compiler.decoding_framework")

        self.compiled = True
        with self.fst_cache.lock:
            self.fst_cache.add_fst(self.filepath)
            self.fst_cache.save()
        return self

    def load(self, lazy=False):
        if self.destroyed: raise KaldiError("Cannot use a KaldiRule after calling destroy()")
        if lazy or self.pending_compile:
            self.compiler.load_queue.add(self)
            return self
        assert self.compiled

        if self.has_been_loaded:
            self._do_reloading()
        else:
            if self.compiler.decoding_framework == 'agf':
                grammar_fst_index = self.decoder.add_grammar_fst(self.fst_hclg_cp) if self.fst.native else self.decoder.add_grammar_fst_file(self.filepath)
            elif self.compiler.decoding_framework == 'laf':
                grammar_fst_index = self.decoder.add_grammar_fst(self.fst) if self.fst.native else self.decoder.add_grammar_fst_text(self._fst_text)
            else: raise KaldiError("unknown compiler decoding_framework")
            assert self.id == grammar_fst_index, "add_grammar_fst allocated invalid grammar_fst_index %d for %s" % (grammar_fst_index, self)

        self.loaded = True
        self.has_been_loaded = True
        return self

    def _do_reloading(self):
        if self.compiler.decoding_framework == 'agf':
            return self.decoder.reload_grammar_fst(self.id, self.fst_hclg_cp) if self.fst.native else self.decoder.reload_grammar_fst_file(self.id, self.filepath)
        elif self.compiler.decoding_framework == 'laf':
            return self.decoder.reload_grammar_fst(self.id, self.fst) if self.fst.native else self.decoder.reload_grammar_fst_text(self.id, self._fst_text)  # FIXME: not implemented?
        else: raise KaldiError("unknown compiler decoding_framework")

    @contextmanager
    def reload(self):
        """ Used for modifying a rule in place, e.g. ListRef. """
        if self.destroyed: raise KaldiError("Cannot use a KaldiRule after calling destroy()")

        was_loaded = self.loaded
        self.reloading = True
        self.fst.clear()
        self._fst_text = None
        self.compiled = False
        self.loaded = False

        yield

        if self.compiled and was_loaded:
            if not self.loaded:
                # FIXME: how is this different from the branch of the if above in load()?
                self._do_reloading()
                self.loaded = True
        elif was_loaded:  # must be not self.compiled (i.e. the compile during reloading was lazy)
            self.compiler.load_queue.add(self)
        self.reloading = False

    def destroy(self):
        """ Destructor. Unloads rule. The rule should not be used/referenced anymore after calling! """
        if self.destroyed:
            return

        if self.loaded:
            self.decoder.remove_grammar_fst(self.id)
            assert self not in self.compiler.compile_queue
            assert self not in self.compiler.compile_duplicate_filename_queue
            assert self not in self.compiler.load_queue
        else:
            if self in self.compiler.compile_queue: self.compiler.compile_queue.remove(self)
            if self in self.compiler.compile_duplicate_filename_queue: self.compiler.compile_duplicate_filename_queue.remove(self)
            if self in self.compiler.load_queue: self.compiler.load_queue.remove(self)

        # Adjust other kaldi_rules ids down, if above self.id, then rebuild dict
        other_kaldi_rules = list(self.compiler.kaldi_rule_by_id_dict.values())
        other_kaldi_rules.remove(self)
        for kaldi_rule in other_kaldi_rules:
            if kaldi_rule.id > self.id:
                kaldi_rule.id -= 1
        self.compiler.kaldi_rule_by_id_dict = { kaldi_rule.id: kaldi_rule for kaldi_rule in other_kaldi_rules }

        self.compiler.free_rule_id()
        self.destroyed = True


########################################################################################################################

class Compiler(object):

    def __init__(self, model_dir=None, tmp_dir=None, alternative_dictation=None, cloud_dictation_lang='en-US', framework='agf-direct', native_fst=False):
        # Supported parameter combinations:
        #   framework='agf-indirect' native_fst=False (original method)
        #   framework='agf-direct' native_fst=False (no external CLI programs needed)
        #   framework='agf-direct' native_fst=True (no external CLI programs needed; no cache/temp files used)
        #   framework='laf' native_fst=False (no reloading supported)
        #   framework='laf' native_fst=True (no reloading supported)

        show_donation_message()
        self._log = _log

        AGF_INTERNAL_COMPILATION = True
        if framework == 'agf-direct':
            framework = 'agf'
            AGF_INTERNAL_COMPILATION = True
        if framework == 'agf-indirect':
            framework = 'agf'
            AGF_INTERNAL_COMPILATION = False
            assert not native_fst, "AGF with NativeWFST not supported"
        self.decoding_framework = framework
        assert self.decoding_framework in ('agf', 'laf')
        self.parsing_framework = 'token'
        assert self.parsing_framework in ('token', 'text')
        self.native_fst = bool(native_fst)

        tmp_dir_needed = bool(not self.native_fst)
        self.model = Model(model_dir, tmp_dir, tmp_dir_needed=tmp_dir_needed)
        self.alternative_dictation = alternative_dictation
        self.cloud_dictation_lang = cloud_dictation_lang
        self.decoder = None

        self._num_kaldi_rules = 0
        self._max_rule_id = load_symbol_table(self.files_dict['phones.txt'])[-1][1] - symbol_table_lookup(self.files_dict['phones.txt'], '#nonterm:rule0')  # FIXME: inaccuracy
        self._max_rule_id = 999
        self.nonterminals = tuple(['#nonterm:dictation'] + ['#nonterm:rule%i' % i for i in range(self._max_rule_id + 1)])

        self.kaldi_rule_by_id_dict = collections.OrderedDict()  # maps KaldiRule.id -> KaldiRule
        self.compile_queue = set()  # KaldiRule
        self.compile_duplicate_filename_queue = set()  # KaldiRule; queued KaldiRules with a duplicate filename (and thus contents), so can skip compilation
        self.load_queue = set()  # KaldiRule; must maintain same order as order of instantiation!

        if self.native_fst:
            NativeWFST.init(isymbol_table=SymbolTable(self.files_dict['words.relabeled.txt' if self.decoding_framework == 'laf' else 'words.txt']),
                osymbol_table=SymbolTable(self.files_dict['words.txt']),
                wildcard_nonterms=self.wildcard_nonterms)
        self._agf_compiler = self._init_agf_compiler() if AGF_INTERNAL_COMPILATION else None

    def init_decoder(self, config=None, dictation_fst_file=None):
        if self.decoder: raise KaldiError("Decoder already initialized")
        if dictation_fst_file is None: dictation_fst_file = self.dictation_fst_filepath
        decoder_kwargs = dict(model_dir=self.model_dir, tmp_dir=self.tmp_dir, dictation_fst_file=dictation_fst_file, max_num_rules=self._max_rule_id+1, config=config)
        if self.decoding_framework == 'agf':
            top_fst_rule = self.compile_top_fst()
            if top_fst_rule.fst.native: decoder_kwargs.update(top_fst_cp=top_fst_rule.fst_hclg_cp)
            else: decoder_kwargs.update(top_fst_file=top_fst_rule.filepath)
            self.decoder = KaldiAgfNNet3Decoder(**decoder_kwargs)
        elif self.decoding_framework == 'laf':
            self.decoder = KaldiLafNNet3Decoder(**decoder_kwargs)
        else:
            raise KaldiError("Invalid Compiler.decoding_framework: %r" % self.decoding_framework)
        return self.decoder

    exec_dir = property(lambda self: self.model.exec_dir)
    model_dir = property(lambda self: self.model.model_dir)
    tmp_dir = property(lambda self: self.model.tmp_dir)
    files_dict = property(lambda self: self.model.files_dict)
    fst_cache = property(lambda self: self.model.fst_cache)

    num_kaldi_rules = property(lambda self: self._num_kaldi_rules)
    lexicon_words = property(lambda self: self.model.lexicon_words)
    _longest_word = property(lambda self: self.model.longest_word)

    _default_dictation_g_filepath = property(lambda self: os.path.join(self.model_dir, defaults.DEFAULT_DICTATION_G_FILENAME))
    _dictation_fst_filepath = property(lambda self: os.path.join(self.model_dir,
        (defaults.DEFAULT_DICTATION_FST_FILENAME if self.decoding_framework == 'agf' else 'Gr.fst')))  # FIXME: generalize
    _plain_dictation_hclg_fst_filepath = property(lambda self: os.path.join(self.model_dir, defaults.DEFAULT_PLAIN_DICTATION_HCLG_FST_FILENAME))

    def alloc_rule_id(self):
        id = self._num_kaldi_rules
        self._num_kaldi_rules += 1
        return id

    def free_rule_id(self):
        id = self._num_kaldi_rules
        self._num_kaldi_rules -= 1
        return id

    ####################################################################################################################
    # Methods for compiling graphs.

    def _compile_laf_graph(self, input_text=None, input_filename=None, output_filename=None, **kwargs):
        # FIXME: documentation
        with debug_timer(self._log.debug, "laf graph compilation"):
            format_kwargs = dict(self.files_dict, **kwargs)

            if input_text and input_filename: raise KaldiError("_compile_laf_graph passed both input_text and input_filename")
            elif input_text: input = ExternalProcess.shell.echo(input_text.encode('utf-8'))
            elif input_filename: input = input_filename
            else: raise KaldiError("_compile_laf_graph passed neither input_text nor input_filename")
            compile_command = input
            format = ExternalProcess.get_list_formatter(format_kwargs)

            compile_command |= ExternalProcess.fstcompile(*format('--isymbols={words_txt}', '--osymbols={words_txt}'))
            # g_filename = output_filename.replace('.fst', '.G.fst')
            compile_command |= output_filename
            compile_command()
            # fstrelabel --relabel_ipairs=relabel G.fst | fstarcsort --sort_type=ilabel | fstconvert --fst_type=const > Gr.fst

    def _init_agf_compiler(self):
        format_kwargs = dict(self.files_dict)
        config = dict(
            tree_rxfilename = '{tree}',
            model_rxfilename = '{final_mdl}',
            lex_rxfilename = '{L_disambig_fst}',
            disambig_rxfilename = '{disambig_int}',
            word_syms_filename = '{words_txt}',
            )
        config = { key: value.format(**format_kwargs) for (key, value) in config.items() }
        return KaldiAgfCompiler(config)

    def _compile_agf_graph(self, compile=False, nonterm=False, input_text=None, input_filename=None, input_fst=None, output_filename=None, return_output_fst=False, simplify_lg=True, **kwargs):
        """
        :param compile: bool whether to compile FST (False if it has already been compiled, like importing dictation FST)
        :param nonterm: bool whether rule represents a nonterminal in the active-grammar-fst (only False for the top FST?)
        :param simplify_lg: bool whether to simplify LG (disambiguate, and more) (do for command grammars, but not for dictation graph!)
        """
        # Must be thread-safe!
        # Possible combinations of (compile,nonterm): (True,True) (True,False) (False,True)
        # FIXME: documentation
        with debug_timer(self._log.debug, "agf graph compilation") as get_time_spent:
            verbose_level = 5 if self._log.isEnabledFor(5) else 0
            format_kwargs = dict(self.files_dict, input_filename=input_filename, output_filename=output_filename, verbose=verbose_level, **kwargs)
            format_kwargs.update(nonterm_phones_offset=self.model.nonterm_phones_offset)
            format_kwargs.update(words_nonterm_begin=self.model.nonterm_words_offset, words_nonterm_end=self.model.nonterm_words_offset+1)
            format_kwargs.update(simplify_lg=str(bool(simplify_lg)).lower())

            if self._agf_compiler:
                # Internal-style (no external CLI programs)
                config = dict(
                    nonterm_phones_offset = self.model.nonterm_phones_offset,
                    disambig_rxfilename = '{disambig_int}',
                    simplify_lg = simplify_lg,
                    verbose = verbose_level,
                    tree_rxfilename = '{tree}',
                    model_rxfilename = '{final_mdl}',
                    lex_rxfilename = '{L_disambig_fst}',
                    word_syms_filename = '{words_txt}',
                    )
                if output_filename:
                    config.update(hclg_wxfilename=output_filename)
                elif self._log.isEnabledFor(3):
                    import datetime
                    config.update(hclg_wxfilename=os.path.join(self.tmp_dir, datetime.datetime.now().isoformat().replace(':', '') + '.fst'))
                if nonterm:
                    config.update(grammar_prepend_nonterm=self.model.nonterm_words_offset, grammar_append_nonterm=self.model.nonterm_words_offset+1)
                config = { key: value.format(**format_kwargs) if isinstance(value, str) else value for (key, value) in config.items() }

                if 1 != sum(int(i is not None) for i in [input_text, input_filename, input_fst]):
                    raise KaldiError("must pass exactly one input")
                if input_text:
                    return self._agf_compiler.compile_graph(config, grammar_fst_text=input_text, return_graph=return_output_fst)
                if input_filename:
                    return self._agf_compiler.compile_graph(config, grammar_fst_file=input_filename, return_graph=return_output_fst)
                if input_fst:
                    return self._agf_compiler.compile_graph(config, grammar_fst=input_fst, return_graph=return_output_fst)

            elif True:
                # Pipeline-style
                assert not input_fst
                if input_text and input_filename: raise KaldiError("_compile_agf_graph passed both input_text and input_filename")
                elif input_text: input = ExternalProcess.shell.echo(input_text.encode('utf-8'))
                elif input_filename: input = input_filename
                else: raise KaldiError("_compile_agf_graph passed neither input_text nor input_filename")
                compile_command = input
                format = ExternalProcess.get_list_formatter(format_kwargs)
                args = []

                # if True: (input | ExternalProcess.fstcompile(*format('--isymbols={words_txt}', '--osymbols={words_txt}')) | ExternalProcess.fstinfo | 'stats.log+')()
                # if True: (ExternalProcess.shell.echo(input_text) | ExternalProcess.fstcompile(*format('--isymbols={words_txt}', '--osymbols={words_txt}')) | (output_filename+'-G'))()

                if compile:
                    compile_command |= ExternalProcess.fstcompile(*format('--isymbols={words_txt}', '--osymbols={words_txt}'))
                    if self._log.isEnabledFor(5):
                        g_txt_filename = output_filename.replace('.fst', '.G.fst.txt')
                        self._log.log(5, "Saving text grammar FST to %s", g_txt_filename)
                        with open(g_txt_filename, 'wb') as f: shutil.copyfileobj(copy.deepcopy(compile_command.commands[0].get_opt('stdin')), f)
                        g_filename = output_filename.replace('.fst', '.G.fst')
                        self._log.log(5, "Saving compiled grammar FST to %s", g_filename)
                        (copy.deepcopy(compile_command) | g_filename)()
                    args.extend(['--arcsort-grammar'])
                if nonterm:
                    args.extend(format('--grammar-prepend-nonterm={words_nonterm_begin}', '--grammar-append-nonterm={words_nonterm_end}'))
                args.extend(format(
                    '--nonterm-phones-offset={nonterm_phones_offset}',
                    '--read-disambig-syms={disambig_int}',
                    '--simplify-lg={simplify_lg}',
                    '--verbose={verbose}',
                    '{tree}', '{final_mdl}', '{L_disambig_fst}', '-', '{output_filename}'))
                compile_command |= ExternalProcess.compile_graph_agf(*args, **ExternalProcess.get_debug_stderr_kwargs(self._log))
                compile_command()

                # if True: (ExternalProcess.shell.echo('%s -> %s\n' % (len(input_text), get_time_spent())) | ExternalProcess.shell('cat') | 'stats.log+')()

            else:
                # CLI-style (deprecated!)
                assert not input_fst
                run = lambda cmd, **kwargs: run_subprocess(cmd, format_kwargs, "agf graph compilation step", format_kwargs_update=dict(input_filename=output_filename), **kwargs)
                if compile: run("{exec_dir}fstcompile --isymbols={words_txt} --osymbols={words_txt} {input_filename}.txt {output_filename}")
                # run("cp {input_filename} {output_filename}-G")
                if compile: run("{exec_dir}fstarcsort --sort_type=ilabel {input_filename} {output_filename}")
                if nonterm: run("{exec_dir}fstconcat {tmp_dir}nonterm_begin.fst {input_filename} {output_filename}")
                if nonterm: run("{exec_dir}fstconcat {input_filename} {tmp_dir}nonterm_end.fst {output_filename}")
                # run("cp {input_filename} {output_filename}-G")
                run("{exec_dir}compile-graph --nonterm-phones-offset={nonterm_phones_offset} --read-disambig-syms={disambig_int} --verbose={verbose}"
                    + " {tree} {final_mdl} {L_disambig_fst} {input_filename} {output_filename}")

    def compile_plain_dictation_fst(self, g_filename=None, output_filename=None):
        if g_filename is None: g_filename = self._default_dictation_g_filepath
        if output_filename is None: output_filename = self._plain_dictation_hclg_fst_filepath
        verbose_level = 5 if self._log.isEnabledFor(5) else 0
        format_kwargs = dict(self.files_dict, g_filename=g_filename, output_filename=output_filename, verbose=verbose_level)
        format = ExternalProcess.get_list_formatter(format_kwargs)
        args = format('--read-disambig-syms={disambig_int}', '--simplify-lg=false', '--verbose={verbose}',
            '{tree}', '{final_mdl}', '{L_disambig_fst}', '{g_filename}', '{output_filename}')
        compile_command = ExternalProcess.compile_graph_agf(*args, **ExternalProcess.get_debug_stderr_kwargs(self._log))
        compile_command()

    def compile_agf_dictation_fst(self, g_filename=None):
        if g_filename is None: g_filename = self._default_dictation_g_filepath
        self._compile_agf_graph(input_filename=g_filename, output_filename=self._dictation_fst_filepath, nonterm=True, simplify_lg=False)

    # def _compile_base_fsts(self):
    #     filepaths = [self.tmp_dir + filename for filename in ['nonterm_begin.fst', 'nonterm_end.fst']]
    #     if all(self.fst_cache.is_current(filepath) for filepath in filepaths):
    #         return
    #     format_kwargs = dict(self.files_dict)
    #     def run(cmd): subprocess.check_call(cmd.format(**format_kwargs), shell=True)  # FIXME: unsafe shell?
    #     if platform == 'windows':
    #     else:
    #         run("(echo 0 1 #nonterm_begin 0^& echo 1) | {exec_dir}fstcompile.exe --isymbols={words_txt} > {tmp_dir}nonterm_begin.fst")
    #         run("(echo 0 1 #nonterm_end 0^& echo 1) | {exec_dir}fstcompile.exe --isymbols={words_txt} > {tmp_dir}nonterm_end.fst")
    #         run("(echo 0 1 \\#nonterm_begin 0; echo 1) | {exec_dir}fstcompile --isymbols={words_txt} > {tmp_dir}nonterm_begin.fst")
    #         run("(echo 0 1 \\#nonterm_end 0; echo 1) | {exec_dir}fstcompile --isymbols={words_txt} > {tmp_dir}nonterm_end.fst")
    #     for filepath in filepaths:
    #         self.fst_cache.add(filepath)

    def compile_top_fst(self):
        kaldi_rule = KaldiRule(self, 'top', nonterm=False)
        fst = kaldi_rule.fst
        state_initial = fst.add_state(initial=True)
        state_return = fst.add_state()
        state_final = fst.add_state(final=True)
        for i in range(self._max_rule_id + 1):
            # fst.add_arc(state_initial, state_final, '#nonterm:rule'+str(i), olabel=WFST.eps)
            # fst.add_arc(state_initial, state_final, '#nonterm:rule'+str(i))
            fst.add_arc(state_initial, state_return, '#nonterm:rule'+str(i))
        fst.add_arc(state_return, state_final, None, '#nonterm:end')
        kaldi_rule.compile()
        return kaldi_rule

    def compile_top_fst_dictation_only(self):
        kaldi_rule = KaldiRule(self, 'top', nonterm=False)
        fst = kaldi_rule.fst
        state_initial = fst.add_state(initial=True)
        state_return = fst.add_state()
        state_final = fst.add_state(final=True)
        fst.add_arc(state_initial, state_return, '#nonterm:dictation')
        fst.add_arc(state_return, state_final, None, '#nonterm:end')
        kaldi_rule.compile()
        return kaldi_rule

    def _get_dictation_fst_filepath(self):
        if os.path.exists(self._dictation_fst_filepath):
            return self._dictation_fst_filepath
        self._log.error("cannot find dictation fst: %s", self._dictation_fst_filepath)
        # FIXME: Fall back to universal dictation?
    dictation_fst_filepath = property(_get_dictation_fst_filepath)

    # def _construct_dictation_states(self, fst, src_state, dst_state, number=(1,None), words=None, start_weight=None):
    #     """
    #     Matches `number` words.
    #     :param number: (0,None) or (1,None) or (1,1), where None is infinity.
    #     """
    #     # unweighted=0.01
    #     if words is None: words = self._lexicon_words
    #     word_probs = self._lexicon_word_probs
    #     backoff_state = fst.add_state()
    #     fst.add_arc(src_state, backoff_state, None, weight=start_weight)
    #     if number[0] == 0:
    #         fst.add_arc(backoff_state, dst_state, None)
    #     for word, prob in word_probs.items():
    #         state = fst.add_state()
    #         fst.add_arc(backoff_state, state, word, weight=prob)
    #         if number[1] == None:
    #             fst.add_arc(state, backoff_state, None)
    #         fst.add_arc(state, dst_state, None)

    def compile_universal_grammar(self, words=None):
        """recognizes any sequence of words"""
        kaldi_rule = KaldiRule(self, 'universal', nonterm=False)
        if words is None: words = self._lexicon_words
        fst = kaldi_rule.fst
        backoff_state = fst.add_state(initial=True, final=True)
        for word in words:
            # state = fst.add_state()
            # fst.add_arc(backoff_state, state, word)
            # fst.add_arc(state, backoff_state, None)
            fst.add_arc(backoff_state, backoff_state, word)
        kaldi_rule.compile()
        return kaldi_rule

    def process_compile_and_load_queues(self):
        # Allowing this gives us leeway elsewhere
        # for kaldi_rule in self.compile_queue:
        #     if kaldi_rule.compiled:
        #         self._log.warning("compile_queue has %s but it is already compiled", kaldi_rule)
        # for kaldi_rule in self.compile_duplicate_filename_queue:
        #     if kaldi_rule.compiled:
        #         self._log.warning("compile_duplicate_filename_queue has %s but it is already compiled", kaldi_rule)
        # for kaldi_rule in self.load_queue:
        #     if kaldi_rule.loaded:
        #         self._log.warning("load_queue has %s but it is already loaded", kaldi_rule)

        # Clean out obsolete entries
        self.compile_queue.difference_update([kaldi_rule for kaldi_rule in self.compile_queue if kaldi_rule.compiled])
        self.compile_duplicate_filename_queue.difference_update([kaldi_rule for kaldi_rule in self.compile_duplicate_filename_queue if kaldi_rule.compiled])
        self.load_queue.difference_update([kaldi_rule for kaldi_rule in self.load_queue if kaldi_rule.loaded])

        if self.compile_queue or self.compile_duplicate_filename_queue or self.load_queue:
            with concurrent.futures.ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
                results = executor.map(lambda kaldi_rule: kaldi_rule.finish_compile(), self.compile_queue)
                # Load pending rules that have already been compiled
                # for kaldi_rule in (self.load_queue - self.compile_queue - self.compile_duplicate_filename_queue):
                #     kaldi_rule.load()
                #     self.load_queue.remove(kaldi_rule)
                # Handle rules as they are completed (have been compiled)
                for kaldi_rule in results:
                    assert kaldi_rule.compiled
                    self.compile_queue.remove(kaldi_rule)
                    # if kaldi_rule in self.load_queue:
                    #     kaldi_rule.load()
                    #     self.load_queue.remove(kaldi_rule)
                # Handle rules that were pending compile but were duplicate and so compiled by/for another rule
                for kaldi_rule in list(self.compile_duplicate_filename_queue):
                    kaldi_rule.compile(duplicate=True)
                    assert kaldi_rule.compiled
                    self.compile_duplicate_filename_queue.remove(kaldi_rule)
                    # if kaldi_rule in self.load_queue:
                    #     kaldi_rule.load()
                    #     self.load_queue.remove(kaldi_rule)
                # Load rules in correct order
                for kaldi_rule in sorted(self.load_queue, key=lambda kr: kr.id):
                    kaldi_rule.load()
                    assert kaldi_rule.loaded
                    self.load_queue.remove(kaldi_rule)

    ####################################################################################################################
    # Methods for recognition.

    def prepare_for_recognition(self):
        if self.compile_queue or self.compile_duplicate_filename_queue or self.load_queue:
            self.process_compile_and_load_queues()
        if self.fst_cache.dirty:
            self.fst_cache.save()

    wildcard_nonterms = ('#nonterm:dictation', '#nonterm:dictation_cloud')

    def parse_output_for_rule(self, kaldi_rule, output):
        """Can be used even when self.parsing_framework == 'token', only for mimic (which contains no nonterms)."""
        labels = kaldi_rule.fst.does_match(output.split(), wildcard_nonterms=self.wildcard_nonterms)
        self._log.log(5, "parse_output_for_rule(%s, %r) got %r", kaldi_rule, output, labels)
        if labels is False:
            return None
        words = [label for label in labels if not label.startswith('#nonterm:')]
        parsed_output = ' '.join(words)
        if parsed_output.lower() != output:
            self._log.error("parsed_output(%r).lower() != output(%r)" % (parsed_output, output))
        return words

    alternative_dictation_regex = re.compile(r'(?<=#nonterm:dictation_cloud )(.*?)(?= #nonterm:end)')  # lookbehind & lookahead assertions

    def parse_output(self, output, dictation_info_func=None):
        assert self.parsing_framework == 'token'
        self._log.debug("parse_output(%r)" % output)
        if output == '':
            return None, [], []

        nonterm_token, _, parsed_output = output.partition(' ')
        assert nonterm_token.startswith('#nonterm:rule')
        kaldi_rule_id = int(nonterm_token[len('#nonterm:rule'):])
        kaldi_rule = self.kaldi_rule_by_id_dict[kaldi_rule_id]

        if self.alternative_dictation and dictation_info_func and kaldi_rule.has_dictation and '#nonterm:dictation_cloud' in parsed_output:
            try:
                if callable(self.alternative_dictation):
                    alternative_text_func = self.alternative_dictation
                elif self.alternative_dictation == 'gcloud':
                    alternative_text_func = alternative_dictation.GCloud.transcribe_data_sync
                else:
                    raise KaldiError("Invalid alternative_dictation value: %r" % self.alternative_dictation)

                audio_data, word_align = dictation_info_func()
                self._log.log(5, "alternative_dictation word_align: %s", word_align)
                words, times, lengths = list(zip(*word_align))
                # Find start & end word-index & byte-offset of each alternative dictation span
                dictation_spans = [{
                        'index_start': index,
                        'offset_start': time,
                        'index_end': words.index('#nonterm:end', index),
                        'offset_end': times[words.index('#nonterm:end', index)],
                    }
                    for index, (word, time, length) in enumerate(word_align)
                    if word.startswith('#nonterm:dictation_cloud')]

                # If last dictation is at end of utterance, include rest of audio_data; else, include half of audio_data between dictation end and start of next word
                dictation_span = dictation_spans[-1]
                if dictation_span['index_end'] == len(word_align) - 1:
                    dictation_span['offset_end'] = len(audio_data)
                else:
                    next_word_time = times[dictation_span['index_end'] + 1]
                    dictation_span['offset_end'] = (dictation_span['offset_end'] + next_word_time) // 2

                def replace_dictation(matchobj):
                    orig_text = matchobj.group(1)
                    dictation_span = dictation_spans.pop(0)
                    dictation_audio = audio_data[dictation_span['offset_start'] : dictation_span['offset_end']]
                    kwargs = dict(language_code=self.cloud_dictation_lang)
                    with debug_timer(self._log.debug, 'alternative_dictation call'):
                        alternative_text = alternative_text_func(dictation_audio, **kwargs)
                        self._log.debug("alternative_dictation: %.2fs audio -> %r", (0.5 * len(dictation_audio) / 16000), alternative_text)  # FIXME: hardcoded sample_rate!
                    # alternative_dictation.write_wav('test.wav', dictation_audio)
                    return (alternative_text or orig_text)

                parsed_output = self.alternative_dictation_regex.sub(replace_dictation, parsed_output)
            except Exception as e:
                self._log.exception("Exception performing alternative dictation")

        words = []
        words_are_dictation_mask = []
        in_dictation = False
        for word in parsed_output.split():
            if word.startswith('#nonterm:'):
                if word.startswith('#nonterm:dictation'):
                    in_dictation = True
                elif in_dictation and word == '#nonterm:end':
                    in_dictation = False
            else:
                words.append(word)
                words_are_dictation_mask.append(in_dictation)

        return kaldi_rule, words, words_are_dictation_mask

    def parse_partial_output(self, output):
        assert self.parsing_framework == 'token'
        # self._log.debug("parse_partial_output(%r)" % output)
        if output == '':
            return None, [], [], False

        nonterm_token, _, parsed_output = output.partition(' ')
        assert nonterm_token.startswith('#nonterm:rule')
        kaldi_rule_id = int(nonterm_token[len('#nonterm:rule'):])
        kaldi_rule = self.kaldi_rule_by_id_dict[kaldi_rule_id]

        words = []
        words_are_dictation_mask = []
        in_dictation = False
        for word in parsed_output.split():
            if word.startswith('#nonterm:'):
                if word.startswith('#nonterm:dictation'):
                    in_dictation = True
                elif in_dictation and word == '#nonterm:end':
                    in_dictation = False
            else:
                words.append(word)
                words_are_dictation_mask.append(in_dictation)

        return kaldi_rule, words, words_are_dictation_mask, in_dictation

########################################################################################################################
# Utility functions.

def remove_nonterms_in_words(words):
    return [word for word in words if not word.startswith('#nonterm:')]

def remove_nonterms_in_text(text):
    return ' '.join(word for word in text.split() if not word.startswith('#nonterm:'))

def run_subprocess(cmd, format_kwargs, description=None, format_kwargs_update=None, **kwargs):
    with debug_timer(_log.debug, description or "description", False), open(os.devnull, 'wb') as devnull:
        output = None if _log.isEnabledFor(logging.DEBUG) else devnull
        args = shlex.split(cmd.format(**format_kwargs), posix=(platform != 'windows'))
        _log.log(5, "subprocess.check_call(%r)", args)
        subprocess.check_call(args, stdout=output, stderr=output, **kwargs)
        if format_kwargs_update:
            format_kwargs.update(format_kwargs_update)
