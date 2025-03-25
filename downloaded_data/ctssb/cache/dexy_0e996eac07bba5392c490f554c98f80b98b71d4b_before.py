try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict

from dexy.handler import DexyHandler

import os
import pexpect
import time

class ProcessLinewiseInteractiveHandler(DexyHandler):
    """
    Intended for use with interactive processes, such as python interpreter,
    where your goal is to have a session transcript divided into same sections
    as input.
    """
    EXECUTABLE = '/usr/bin/env python'
    PROMPT = '>>>|\.\.\.' # Python uses >>> prompt normally and ... when in multi-line structures like loops
    INPUT_EXTENSIONS = [".txt", ".py"]
    OUTPUT_EXTENSIONS = [".pycon"]
    ALIASES = ['pycon']

    def process_dict(self, input_dict):
        output_dict = OrderedDict()

        proc = pexpect.spawn(self.EXECUTABLE, cwd="artifacts")
        proc.expect(self.PROMPT)
        start = (proc.before + proc.after)

        for k, s in input_dict.items():
            section_transcript = start
            start = ""
            for l in s.rstrip().split("\n"):
                section_transcript += start
                start = ""
                proc.sendline(l)
                proc.expect(self.PROMPT, timeout=30)
                section_transcript += proc.before
                start = proc.after
            output_dict[k] = section_transcript
        return output_dict

class ProcessSectionwiseInteractiveHandler(DexyHandler):
    EXECUTABLE = '/usr/bin/env R --quiet --vanilla'
    PROMPT = '>'
    COMMENT = '#'
    TRAILING_PROMPT = "\r\n> "
    INPUT_EXTENSIONS = ['.txt', '.r', '.R']
    OUTPUT_EXTENSIONS = ['.Rout']
    ALIASES = ['rint']

    def process_dict(self, input_dict):
         output_dict = OrderedDict()
 
         proc = pexpect.spawn(self.EXECUTABLE, cwd=self.artifact.artifacts_dir)
         proc.expect(self.PROMPT)
         start = (proc.before + proc.after)
         
         for k, s in input_dict.items():
             section_transcript = start
             start = ""
             proc.send(s)
             proc.sendline(self.COMMENT * 5)
             proc.expect(self.COMMENT * 5, timeout = self.artifact.doc.args['timeout'])
 
             section_transcript += proc.before.rstrip(self.TRAILING_PROMPT)
             output_dict[k] = section_transcript

         return output_dict

class ProcessStdoutHandler(DexyHandler):
    """
    Intended for use with command line processes where your only interest is in
    the contents of stdout.
    """
    EXECUTABLE = '/usr/bin/env python'
    INPUT_EXTENSIONS = [".txt", ".py"]
    OUTPUT_EXTENSIONS = [".txt"]
    ALIASES = ['py', 'python', 'pyout']
    
    def process(self):
        self.artifact.generate_workfile()
        output, exit_status = pexpect.run("%s %s" % (self.EXECUTABLE, self.artifact.work_filename()), withexitstatus = True)
        self.artifact.data_dict['1'] = output
        if exit_status != 0:
            self.log.warn("an error occurred:\n%s" % output)
            self.artifact.dirty = True

class BashHandler(ProcessStdoutHandler):
    EXECUTABLE = '/usr/bin/env bash'
    INPUT_EXTENSIONS = [".sh", ".bash"]
    OUTPUT_EXTENSIONS = [".txt"]
    ALIASES = ['bash']

class RedclothHandler(ProcessStdoutHandler):
    EXECUTABLE = '/usr/bin/env redcloth'
    INPUT_EXTENSIONS = [".txt", ".textile"]
    OUTPUT_EXTENSIONS = [".html"]
    ALIASES = ['redcloth', 'textile']

class RedclothLatexHandler(ProcessStdoutHandler):
    EXECUTABLE = '/usr/bin/env redcloth -o latex'
    INPUT_EXTENSIONS = [".txt", ".textile"]
    OUTPUT_EXTENSIONS = [".tex"]
    ALIASES = ['redclothl', 'latextile']

class Rst2HtmlHandler(ProcessStdoutHandler):
    EXECUTABLE = '/usr/bin/env rst2html.py'
    INPUT_EXTENSIONS = [".rst", ".txt"]
    OUTPUT_EXTENSIONS = [".html"]
    ALIASES = ['rst2html']

class Rst2LatexHandler(ProcessStdoutHandler):
    EXECUTABLE = '/usr/bin/env rst2latex.py'
    INPUT_EXTENSIONS = [".rst", ".txt"]
    OUTPUT_EXTENSIONS = [".tex"]
    ALIASES = ['rst2latex']

class Rst2BeamerHandler(ProcessStdoutHandler):
    EXECUTABLE = '/usr/bin/env rst2beamer'
    INPUT_EXTENSIONS = [".rst", ".txt"]
    OUTPUT_EXTENSIONS = [".tex"]
    ALIASES = ['rst2beamer']

class SloccountHandler(DexyHandler):
    EXECUTABLE = '/usr/bin/env sloccount'
    OUTPUT_EXTENSIONS = [".txt"]
    ALIASES = ['sloc', 'sloccount']
    
    def process(self):
        self.artifact.generate_workfile()
        self.artifact.data_dict['1'] = pexpect.run("%s %s" % (self.EXECUTABLE, self.artifact.work_filename()))


class ProcessArtifactHandler(DexyHandler):
    """
    Intended for use with command line processes where the process will write
    data directly to the artifact file which is passed as an argument.
    """
    EXECUTABLE = '/usr/bin/env python'
    INPUT_EXTENSIONS = [".txt", ".py"]
    OUTPUT_EXTENSIONS = [".txt"]
    ALIASES = ['pyart']

    def process(self):
        self.artifact.auto_write_artifact = False
        wf = self.artifact.work_filename()
        af = self.artifact.filename()
        self.artifact.stdout = pexpect.run("%s %s %s" % (self.EXECUTABLE, af, wf))

class ProcessTimingHandler(DexyHandler):
    """
    Runs code N times and reports timings.
    """
    EXECUTABLE = '/usr/bin/env python'
    N = 10
    INPUT_EXTENSIONS = [".txt", ".py"]
    OUTPUT_EXTENSIONS = [".times"]
    ALIASES = ['pytime']
    
    def process(self):
        self.artifact.generate_workfile()
        times = []
        for i in xrange(self.N):
            start = time.time()
            pexpect.run("%s %s" % (self.EXECUTABLE, self.artifact.work_filename()))
            times.append("%s" % (time.time() - start))
        self.artifact.data_dict['1'] = "\n".join(times)

# Returns a full transcript, commands and output from each line.
class ROutputHandler(DexyHandler):
    EXECUTABLE = '/usr/bin/env R CMD BATCH --vanilla --quiet --no-timing'
    INPUT_EXTENSIONS = ['.txt', '.r', '.R']
    OUTPUT_EXTENSIONS = [".Rout"]
    ALIASES = ['r', 'R']

    def generate(self):
        self.artifact.write_dj()

    def process(self):
        self.artifact.generate_workfile()
        pexpect.run("%s %s %s" % (self.EXECUTABLE, self.artifact.work_filename(), self.artifact.filename()))
        self.artifact.data_dict['1'] = open(self.artifact.filename(), "r").read()

# Uses the --slave flag so doesn't echo commands, just returns output.
class RArtifactHandler(DexyHandler):
    EXECUTABLE = '/usr/bin/env R CMD BATCH --vanilla --quiet --slave --no-timing'
    INPUT_EXTENSIONS = ['.txt', '.r', '.R']
    OUTPUT_EXTENSIONS = [".txt"]
    ALIASES = ['rart']
    
    def process(self):
        self.artifact.auto_write_artifact = False
        self.artifact.generate_workfile()

        work_file = os.path.basename(self.artifact.work_filename())
        artifact_file = os.path.basename(self.artifact.filename())
        command = "%s %s %s" % (self.EXECUTABLE, work_file, artifact_file)
        self.log.info(command)
        self.artifact.stdout = pexpect.run(command, cwd=self.artifact.artifacts_dir)
        self.artifact.data_dict['1'] = open(self.artifact.filename(), "r").read()

class LatexHandler(DexyHandler):
    INPUT_EXTENSIONS = [".tex", ".txt"]
    OUTPUT_EXTENSIONS = [".pdf", ".png"]
    ALIASES = ['latex']
    
    def generate(self):
        self.artifact.write_dj()

    def process(self):
        latex_filename = self.artifact.filename().replace(".pdf", ".tex")
        latex_basename = os.path.basename(latex_filename)
        
        f = open(latex_filename, "w")
        f.write(self.artifact.input_text())
        f.close()
        
        # Detect which LaTeX compiler we have...
        latex_bin = None
        for e in ["pdflatex", "latex"]:
            latex_bin, s = pexpect.run("/usr/bin/env which %s" % e, withexitstatus = True) 
            if s == 0:
                self.log.info("%s LaTeX command found" % e)
                break
            else:
                self.log.info("%s LaTeX command not found" % e)
                latex_bin = None
        
        if not latex_bin:
            raise Exception("no executable found for latex")

        command = "/usr/bin/env %s %s" % (e, latex_basename)
        self.log.info(command)
        # run LaTeX twice so TOCs, section number references etc. are correct
        self.artifact.stdout = pexpect.run(command, cwd=self.artifact.artifacts_dir, timeout=20)
        self.artifact.stdout += pexpect.run(command, cwd=self.artifact.artifacts_dir, timeout=20)

class VoiceHandler(DexyHandler):
    INPUT_EXTENSIONS = [".*"]
    OUTPUT_EXTENSIONS = [".mp3"]
    ALIASES = ['voice', 'say']
     
    def process(self):
        self.artifact.auto_write_artifact = False
        self.artifact.generate_workfile()
        work_file = os.path.basename(self.artifact.work_filename())
        artifact_file = os.path.basename(self.artifact.filename())

        for e, ext in {"say" : "aiff", "espeak" : "wav"}.items():
            sound_file = artifact_file.replace('mp3', ext)
            tts_bin, s = pexpect.run("/usr/bin/env which %s" % e, withexitstatus = True)
            if s == 0:
                self.log.info("%s text-to-speech found at %s" % (e, tts_bin))
                break
            else:
                self.log.info("%s text-to-speech not found" % e)
                e = None
        
        if e == "say":
            command = "/usr/bin/env say -f %s -o %s" % (work_file, sound_file)
        elif e == "espeak":
            command = "/usr/bin/env espeak -f %s -w %s" % (work_file, sound_file)
        else:
            raise Exception("unknown tts command %s" % e)

        self.log.info(command)
        self.artifact.stdout = pexpect.run(command, cwd=self.artifact.artifacts_dir)

        # Converting to mp3
        command = "/usr/bin/env lame %s %s" % (sound_file, artifact_file)
        self.log.info(command)
        self.artifact.stdout = pexpect.run(command, cwd=self.artifact.artifacts_dir)


class RagelRubyHandler(DexyHandler):
    INPUT_EXTENSIONS = [".rl"]
    OUTPUT_EXTENSIONS = [".rb"]
    ALIASES = ['rlrb', 'ragelruby']
    
    def process(self):
        self.artifact.auto_write_artifact = False
        self.artifact.generate_workfile()
        artifact_file = self.artifact.filename(False)
        work_file = self.artifact.work_filename(False)
        command = "/usr/bin/env ragel -R -o %s %s" % (artifact_file, work_file)
        self.log.info(command)
        self.artifact.stdout = pexpect.run(command, cwd=self.artifact.artifacts_dir)
        self.artifact.data_dict['1'] = open(self.artifact.filename(), "r").read()

class RagelRubyDotHandler(DexyHandler):
    INPUT_EXTENSIONS = [".rl"]
    OUTPUT_EXTENSIONS = [".dot"]
    ALIASES = ['rlrbd', 'ragelrubydot']
    
    def process(self):
        self.artifact.generate_workfile()
        work_file = os.path.basename(self.artifact.work_filename())
        command = "/usr/bin/env ragel -R -V %s" % (work_file)
        self.log.info(command)
        self.artifact.data_dict['1'] = pexpect.run(command, cwd=self.artifact.artifacts_dir)


class DotHandler(DexyHandler):
    INPUT_EXTENSIONS = [".dot"]
    OUTPUT_EXTENSIONS = [".png", ".pdf"]
    ALIASES = ['dot', 'graphviz']
    
    def process(self):
        self.artifact.auto_write_artifact = False
        self.artifact.generate_workfile()
        wf = self.artifact.work_filename(False)
        af = self.artifact.filename(False)
        command = "/usr/bin/env dot -T%s -o%s %s" % (self.artifact.ext.replace(".", ""), af, wf)
        self.log.info(command)
        self.artifact.stdout = pexpect.run(command, cwd=self.artifact.artifacts_dir)


class RubyStdoutHandler(ProcessStdoutHandler):
    EXECUTABLE = '/usr/bin/env ruby'
    INPUT_EXTENSIONS = [".txt", ".rb"]
    OUTPUT_EXTENSIONS = [".txt"]
    ALIASES = ['rb']


class RubyInteractiveHandler(DexyHandler):
    EXECUTABLE = '/usr/bin/env ruby'
    INPUT_EXTENSIONS = [".txt", ".rb"]
    OUTPUT_EXTENSIONS = [".txt"]
    ALIASES = ['rbint']

    def process(self):
        self.artifact.generate_workfile()
        command = "/usr/bin/env ruby %s" % self.artifact.work_filename(False)
        self.log.info(command)

        self.artifact.load_input_artifacts()
        for k, v in self.artifact.input_artifacts_dict.items():
            self.log.info(k)
            for s, t in v['data_dict'].items():
                self.log.info("spawning process for section %s" % s)
                self.log.info(t)
                proc = pexpect.spawn(command, cwd=self.artifact.artifacts_dir)
                proc.send(t)
                proc.sendcontrol('d') # eof
                self.artifact.data_dict[s] = proc.read()[:-4] # strip off ^D^H^H

class RspecHandler(ProcessStdoutHandler):
    EXECUTABLE = '/usr/bin/env spec -f s'
    INPUT_EXTENSIONS = [".txt", ".rb"]
    OUTPUT_EXTENSIONS = [".txt"]
    ALIASES = ['spec', 'rspec']

    def process(self):
        self.artifact.auto_write_artifact = False
        self.artifact.generate_workfile()
        self.artifact.data_dict['1'] = pexpect.run("%s %s" % (self.EXECUTABLE, self.artifact.work_filename(False)), cwd=self.artifact.artifacts_dir)
