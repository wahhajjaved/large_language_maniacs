#!/usr/bin/env python2

"""
PC-BASIC - GW-BASIC/BASICA/Cartridge BASIC compatible interpreter

(c) 2013, 2014, 2015 Rob Hagemans
This file is released under the GNU GPL version 3.
"""

import os
import sys
import shutil
import logging
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
import traceback

import plat
import ansipipe
import printer

# declare to avoid pylint errors
config = None

def main():
    """ Initialise and do requested operations. """
    # make imported modules available in main module
    global config
    try:
        import config
        if plat.system == 'Android':
            # resume from existing directory (or clear it if we're not resuming)
            if not config.get('resume') and os.path.exists(plat.temp_dir):
                shutil.rmtree(plat.temp_dir)
            if not os.path.exists(plat.temp_dir):
                os.mkdir(plat.temp_dir)
        # set up the logging system
        prepare_logging()
        if config.get('version'):
            # in version mode, print version and exit
            sys.stdout.write(plat.version + '\n')
            if config.get('debug'):
                debug_details()
        elif config.get('help'):
            # in help mode, print usage and exit
            with open(os.path.join(plat.info_dir, 'usage.txt')) as f:
                for line in f:
                    sys.stdout.write(line)
        elif config.get('convert'):
            # in converter mode, convert and exit
            convert()
        else:
            # otherwise, go into BASIC
            start_basic()
    finally:
        try:
            printer.wait()
            # clean up our temp dir if we made one
            if plat.temp_dir and plat.system != 'Android':
                shutil.rmtree(plat.temp_dir)
        except NameError:
            pass
        # avoid sys.excepthook errors when piping output
        # http://stackoverflow.com/questions/7955138/addressing-sys-excepthook-error-in-bash-script
        try:
            sys.stdout.close()
        except:
            pass
        try:
            sys.stderr.close()
        except:
            pass

def prepare_logging():
    """ Set up the logging system. """
    logfile = config.get('logfile')
    if config.get('version') or config.get('help'):
        formatstr = '%(message)s'
        loglevel = logging.INFO
    else:
        # logging setup before we import modules and may need to log errors
        formatstr = '%(levelname)s: %(message)s'
        if config.get('debug'):
            loglevel = logging.DEBUG
        else:
            loglevel = logging.INFO
    logging.basicConfig(format=formatstr, level=loglevel, filename=logfile)

def convert():
    """ Perform file format conversion. """
    import program
    import disk
    import error
    # set conversion output
    # first arg, if given, is mode; second arg, if given, is outfile
    mode = config.get('convert')
    infile = (config.get(0) or
              config.get('run') or config.get('load'))
    outfile = config.get(1)
    # keep uppercase first letter
    mode = mode[0].upper() if mode else 'A'
    # load & save in different format
    try:
        prog_infile = None
        if infile:
            prog_infile = open_native_or_dos_filename(infile)
        elif plat.has_stdin:
            # use StringIO buffer for seekability
            in_buffer = StringIO(sys.stdin.read())
            prog_infile = disk.open_diskfile(in_buffer, filetype='ABP', mode='I')
        if prog_infile:
            with prog_infile:
                program.load(prog_infile)
        prog_outfile = None
        if outfile:
            # on save from command-line, use exact file name
            prog_outfile = disk.open_diskfile(open(outfile, 'wb'), filetype=mode, mode='O')
        elif plat.has_stdout:
            prog_outfile = disk.open_diskfile(sys.stdout, filetype=mode, mode='O')
        if prog_outfile:
            with prog_outfile:
                program.save(prog_outfile)
    except error.RunError as e:
        logging.error(error.get_message(e.err))
    except EnvironmentError as e:
        logging.error(str(e))

def start_basic():
    """ Load & run programs and commands and hand over to interactive mode. """
    import program
    import run
    import error
    import state
    import devices
    import disk
    import cassette
    import reset
    import sound
    import audio
    do_reset = False
    backend, console = None, None
    exit_error = ''
    try:
        # resume from saved emulator state if requested and available
        resume = config.get('resume') and state.load()
        # choose the video and sound backends
        backend, console = prepare_console()
        # greet, load and run only if not resuming
        if resume:
            # override selected settings from command line
            cassette.override()
            disk.override()
            # suppress double prompt
            if not state.basic_state.execute_mode:
                state.basic_state.prompt = False
            run.start('', False, config.get('quit'))
        else:
            # load/run program
            config.options['run'] = config.get(0) or config.get('run')
            prog = config.get('run') or config.get('load')
            if prog:
                # on load, accept capitalised versions and default extension
                with open_native_or_dos_filename(prog) as progfile:
                    program.load(progfile)
                reset.clear()
            print_greeting(console)
            # start the interpreter (and get out if we ran with -q)
            run.start(config.get('exec'), config.get('run'), config.get('quit'))
    except error.RunError as e:
        exit_error = error.get_message(e.err)
    except error.Exit:
        # pause before exit if requested
        if config.get('wait'):
            backend.video_queue.put(backend.Event(backend.VIDEO_SET_CAPTION, 'Press a key to close window'))
            backend.video_queue.put(backend.Event(backend.VIDEO_SHOW_CURSOR, False))
            state.console_state.keyb.pause = True
            # this performs a blocking keystroke read if in pause state
            backend.check_events()
    except error.Reset:
        do_reset = True
    except KeyboardInterrupt:
        if config.get('debug'):
            raise
    except Exception as e:
        exit_error = "Unhandled exception\n%s" % traceback.format_exc()
    finally:
        try:
            audio.close()
        except (NameError, AttributeError) as e:
            logging.debug('Error on closing audio: %s', e)
        try:
            # fix the terminal on exit (important for ANSI terminals)
            # and save display interface state into screen state
            state.console_state.screen.close()
        except (NameError, AttributeError) as e:
            logging.debug('Error on closing screen: %s', e)
        # delete state if resetting
        if do_reset:
            state.delete()
            if plat.system == 'Android':
                shutil.rmtree(plat.temp_dir)
        else:
            state.save()
        try:
            # close files if we opened any
            devices.close_files()
        except (NameError, AttributeError) as e:
            logging.debug('Error on closing files: %s', e)
        try:
            devices.close_devices()
        except (NameError, AttributeError) as e:
            logging.debug('Error on closing devices: %s', e)
        if exit_error:
            logging.error(exit_error)

def prepare_console():
    """ Initialise backend and console. """
    import state
    import backend
    import display
    import sound
    import console
    import error
    import fp
    # we need this prepared for input to work,
    # even if we don't use any function from it
    import inputs
    interface = config.get('interface') or 'graphical'
    display.init(interface)
    sound.init('none' if config.get('nosound') else interface)
    if not state.loaded:
        console.init_mode()
    # set the output for maths error messages
    fp.init(error_stream=console)
    return backend, console

def print_greeting(console):
    """ Print the greeting and the KEY row if we're not running a program. """
    import var
    greeting = (
        'PC-BASIC {version} {note}\r'
        '(C) Copyright 2013--2015 Rob Hagemans.\r'
        '{free} Bytes free')
    # following GW, don't write greeting for redirected input
    # or command-line filter run
    if (not config.get('run') and not config.get('exec') and
             not config.get('input') and not config.get(0) and
             not config.get('interface') == 'none'):
        debugstr = ' [DEBUG mode]' if config.get('debug') else ''
        params = { 'version': plat.version, 'note': debugstr, 'free': var.fre()}
        console.clear()
        console.write_line(greeting.format(**params))
        console.show_keys(True)

def open_native_or_dos_filename(infile):
    """ If the specified file exists, open it; if not, try as DOS file name. """
    import devices
    import disk
    import cassette
    import error
    try:
        # first try exact file name
        return disk.open_diskfile(open(os.path.expandvars(os.path.expanduser(infile)), 'r'), filetype='BPA', mode='I')
    except EnvironmentError as e:
        # otherwise, accept capitalised versions and default extension
        return devices.open_file(0, infile, filetype='BPA', mode='I')

def debug_details():
    logging.info('os: %s', plat.system)
    # try numpy before pygame to avoid strange ImportError on FreeBSD
    modules = ('numpy', 'pygame', 'curses', 'pexpect', 'serial')
    for module in modules:
        try:
            __import__(module)
            sys.stdout.write("%s: available\n" % module)
        except ImportError:
            sys.stdout.write("%s: not available\n" % module)

if __name__ == "__main__":
    main()
