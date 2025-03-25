# Sublime Text plugin for Tern

import sublime, sublime_plugin
import os, sys, platform, subprocess, webbrowser, json, re, time, atexit

windows = platform.system() == "Windows"
python3 = sys.version_info[0] > 2
is_st2 = int(sublime.version()) < 3000

def is_js_file(view):
  return view.score_selector(view.sel()[0].b, "source.js") > 0

files = {}
arghints_enabled = False
tern_command = None
tern_arguments = []

class Listeners(sublime_plugin.EventListener):
  def on_close(self, view):
    files.pop(view.file_name(), None)

  def on_deactivated(self, view):
    pfile = files.get(view.file_name(), None)
    if pfile and pfile.dirty:
      send_buffer(pfile, view)

  def on_modified(self, view):
    pfile = files.get(view.file_name(), None)
    if pfile: pfile_modified(pfile, view)

  def on_selection_modified(self, view):
    if not arghints_enabled: return
    pfile = get_pfile(view)
    if pfile is not None: show_argument_hints(pfile, view)

  def on_query_completions(self, view, prefix, _locations):
    pfile = get_pfile(view)
    if pfile is None: return None

    completions, fresh = ensure_completions_cached(pfile, view)
    if completions is None: return None

    if not fresh:
      completions = [c for c in completions if c[1].startswith(prefix)]
    return completions


class ProjectFile(object):
  def __init__(self, name, view, project):
    self.project = project
    self.name = name
    self.dirty = view.is_dirty()
    self.cached_completions = None
    self.cached_arguments = None
    self.showing_arguments = False
    self.last_modified = 0

class Project(object):
  def __init__(self, dir):
    self.dir = dir
    self.port = None
    self.proc = None
    self.last_failed = 0

  def __del__(self):
    kill_server(self)


def get_pfile(view):
  if not is_js_file(view): return None
  fname = view.file_name()
  if fname is None: return None
  if fname in files: return files[fname]

  pdir = project_dir(fname)
  if pdir is None: return None

  project = None
  for f in files.values():
    if f.project.dir == pdir:
      project = f.project
      break
  pfile = files[fname] = ProjectFile(fname, view, project or Project(pdir))
  return pfile

def project_dir(fname):
  dir = os.path.dirname(fname)
  if not os.path.isdir(dir): return None

  cur = dir
  while True:
    parent = os.path.dirname(cur[:-1])
    if not parent:
      break
    if os.path.isfile(os.path.join(cur, ".tern-project")):
      return cur
    cur = parent
  return dir

def pfile_modified(pfile, view):
  pfile.dirty = True
  now = time.time()
  if now - pfile.last_modified > .5:
    pfile.last_modified = now
    sublime.set_timeout(lambda: maybe_save_pfile(pfile, view, now), 5000)
  if pfile.cached_completions and view.sel()[0].a < pfile.cached_completions[0]:
    pfile.cached_completions = None
  if pfile.cached_arguments and view.sel()[0].a < pfile.cached_arguments[0]:
    pfile.cached_arguments = None

def maybe_save_pfile(pfile, view, timestamp):
  if pfile.last_modified == timestamp and pfile.dirty:
    send_buffer(pfile, view)

def server_port(project, ignored=None):
  if project.port is not None and project.port != ignored:
    return (project.port, True)
  if project.port == ignored:
    kill_server(project)

  port_file = os.path.join(project.dir, ".tern-port")
  if os.path.isfile(port_file):
    port = int(open(port_file, "r").read())
    if port != ignored:
      project.port = port
      return (port, True)

  started = start_server(project)
  if started is not None:
    project.port = started
  return (started, False)

def start_server(project):
  if not tern_command: return None
  if time.time() - project.last_failed < 30: return None
  env = None
  if platform.system() == "Darwin":
    env = os.environ.copy()
    env["PATH"] += ":/usr/local/bin"
  proc = subprocess.Popen(tern_command + tern_arguments, cwd=project.dir, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=windows)
  output = ""

  while True:
    line = proc.stdout.readline().decode("utf-8")
    if not line:
      sublime.error_message("Failed to start server" + (output and ":\n" + output))
      project.last_failed = time.time()
      return None
    match = re.match("Listening on port (\\d+)", line)
    if match:
      project.proc = proc
      return int(match.group(1))
    else:
      output += line

def kill_server(project):
  if project.proc is None: return
  try:
    if windows:
      subprocess.call("taskkill /t /f /pid " + str(project.proc.pid), shell=True)
    else:
      project.proc.terminate()
      project.proc.wait()
  except:
    pass
  project.proc = None

def relative_file(pfile):
  return pfile.name[len(pfile.project.dir) + 1:]

def buffer_fragment(view, pos):
  region = None
  for js_region in view.find_by_selector("source.js"):
    if js_region.a <= pos and js_region.b >= pos:
      region = js_region
      break
  if region is None: return sublime.Region(pos, pos)

  start = view.line(max(region.a, pos - 1000)).a
  if start < pos - 1500: start = pos - 1500
  cur = start
  min_indent = 10000
  while True:
    next = view.find("\\bfunction\\b", cur)
    if next is None or next.b > pos or (next.a == -1 and next.b == -1): break
    line = view.line(next.a)
    if line.a < pos - 1500: line = sublime.Region(pos - 1500, line.b)
    indent = count_indentation(view.substr(line))
    if indent < min_indent:
      min_indent = indent
      start = line.a
    cur = line.b
  return sublime.Region(start, min(pos + 500, region.b))

def count_indentation(line):
  count, pos = (0, 0)
  while pos < len(line):
    ch = line[pos]
    if ch == " ": count += 1
    elif ch == "\t": count += 4
    else: break
    pos += 1
  return count

def make_request(port, doc, silent=False):
  if python3:
    return make_request_py3(port, doc, silent)
  else:
    return make_request_py2(port, doc, silent)

def make_request_py2(port, doc, silent):
  import urllib2
  try:
    req = urllib2.urlopen("http://localhost:" + str(port) + "/", json.dumps(doc), 1)
    return json.loads(req.read())
  except urllib2.HTTPError as error:
    if not silent: sublime.error_message(error.read())
    return None

def make_request_py3(port, doc, silent):
  import urllib.request, urllib.error
  try:
    req = urllib.request.urlopen("http://localhost:" + str(port) + "/", json.dumps(doc).encode("utf-8"), 1)
    return json.loads(req.read().decode("utf-8"))
  except urllib.error.URLError as error:
    if not silent: sublime.error_message(error.read().decode("utf-8"))
    return None

def view_js_text(view):
  text, pos = ("", 0)
  for region in view.find_by_selector("source.js"):
    if region.a > pos: text += ";" + " " * (region.a - pos - 1)
    text += view.substr(region)
    pos = region.b
  return text

def run_command(view, query, pos=None, fragments=True, silent=False):
  pfile = get_pfile(view)
  if pfile is None: return

  if isinstance(query, str): query = {"type": query}
  if (pos is None): pos = view.sel()[0].b

  port, port_is_old = server_port(pfile.project)
  if port is None: return

  doc = {"query": query, "files": []}

  if not pfile.dirty:
    fname, sending_file = (relative_file(pfile), False)
  if fragments and view.size() > 8000:
    region = buffer_fragment(view, pos)
    doc["files"].append({"type": "part",
                         "name": relative_file(pfile),
                         "offset": region.a,
                         "text": view.substr(region)})
    pos -= region.a
    fname, sending_file = ("#0", False)
  else:
    doc["files"].append({"type": "full",
                         "name": relative_file(pfile),
                         "text": view_js_text(view)})
    fname, sending_file = ("#0", True)
  query["file"] = fname
  query["end"] = pos

  data = None
  try:
    data = make_request(port, doc, silent=silent)
    if data is None: return None
  except:
    pass

  if data is None and port_is_old:
    try:
      port = server_port(pfile.project, port)[0]
      if port is None: return
      data = make_request(port, doc, silent=silent)
      if data is None: return None
    except Exception as e:
      if not silent: sublime.error_message(str(e))

  if sending_file: pfile.dirty = False
  return data

def send_buffer(pfile, view):
  port = server_port(pfile.project)[0]
  if port is None: return False
  try:
    make_request(port,
                 {"files": [{"type": "full",
                             "name": relative_file(pfile),
                             "text": view_js_text(view)}]},
                 silent=True)
    pfile.dirty = False
    return True
  except:
    return False

def completion_icon(type):
  if type is None or type == "?": return " (?)"
  if type.startswith("fn("): return " (fn)"
  if type.startswith("["): return " ([])"
  if type == "number": return " (num)"
  if type == "string": return " (str)"
  if type == "bool": return " (bool)"
  return " (obj)"

def ensure_completions_cached(pfile, view):
  pos = view.sel()[0].b
  if pfile.cached_completions is not None:
    c_start, c_word, c_completions = pfile.cached_completions
    if c_start <= pos:
      slice = view.substr(sublime.Region(c_start, pos))
      if slice.startswith(c_word) and not re.match(".*\\W", slice):
        return (c_completions, False)

  data = run_command(view, {"type": "completions", "types": True})
  if data is None: return (None, False)

  completions = []
  for rec in data["completions"]:
    rec_name = re.escape(rec.get('name'))
    completions.append((rec.get("name") + completion_icon(rec.get("type", None)), rec_name))
  pfile.cached_completions = (data["start"], view.substr(sublime.Region(data["start"], pos)), completions)
  return (completions, True)

def locate_call(view):
  sel = view.sel()[0]
  if sel.a != sel.b: return (None, 0)
  context = view.substr(sublime.Region(max(0, sel.b - 500), sel.b))
  pos = len(context)
  depth = argpos = 0
  while pos > 0:
    pos -= 1
    ch = context[pos]
    if ch == "}" or ch == ")" or ch == "]":
      depth += 1
    elif ch == "{" or ch == "(" or ch == "[":
      if depth > 0: depth -= 1
      elif ch == "(": return (pos + sel.b - len(context), argpos)
      else: return (None, 0)
    elif ch == "," and depth == 0:
      argpos += 1
  return (None, 0)

def show_argument_hints(pfile, view):
  call_start, argpos = locate_call(view)
  if call_start is None: return render_argument_hints(pfile, None, 0)
  if pfile.cached_arguments is not None and pfile.cached_arguments[0] == call_start:
    return render_argument_hints(pfile, pfile.cached_arguments[1], argpos)

  data = run_command(view, {"type": "type", "preferFunction": True}, call_start, silent=True)
  parsed = data and parse_function_type(data)
  pfile.cached_arguments = (call_start, parsed)
  render_argument_hints(pfile, parsed, argpos)

def render_argument_hints(pfile, ftype, argpos):
  if ftype is None:
    if pfile.showing_arguments:
      sublime.status_message("")
      pfile.showing_arguments = False
    return

  msg = ftype["name"] + "("
  i = 0
  for name, type in ftype["args"]:
    if i > 0: msg += ", "
    if i == argpos: msg += "*"
    msg += name + ("" if type == "?" else ": " + type)
    i += 1
  msg += ")"
  if ftype["retval"] is not None:
    msg += " -> " + ftype["retval"]
  sublime.status_message(msg)
  pfile.showing_arguments = True

def parse_function_type(data):
  type = data["type"]
  if not re.match("fn\\(", type): return None
  pos = 3
  args, retval = ([], None)
  while pos < len(type) and type[pos] != ")":
    colon = type.find(":", pos)
    name = "?"
    if colon != -1:
      name = type[pos:colon]
      if not re.match("[\\w_$]+$", name): name = "?"
      else: pos = colon + 2
    type_start = pos
    depth = 0
    while pos < len(type):
      ch = type[pos]
      if ch == "(" or ch == "[" or ch == "{":
        depth += 1
      elif ch == ")" or ch == "]" or ch == "}":
        if depth > 0: depth -= 1
        else: break
      elif ch == "," and depth == 0:
        break
      pos += 1
    args.append((name, type[type_start:pos]))
    if type[pos] == ",": pos += 2
  if type[pos:pos + 5] == ") -> ":
    retval = type[pos + 5:]
  return {"name": data.get("exprName", None) or data.get("name", None) or "fn",
          "args": args,
          "retval": retval}

jump_stack = []

class TernJumpToDef(sublime_plugin.TextCommand):
  def run(self, edit, **args):
    data = run_command(self.view, {"type": "definition", "lineCharPositions": True})
    if data is None: return
    file = data.get("file", None)
    if file is not None:
      # Found an actual definition
      row, col = self.view.rowcol(self.view.sel()[0].b)
      cur_pos = self.view.file_name() + ":" + str(row + 1) + ":" + str(col + 1)
      jump_stack.append(cur_pos)
      if len(jump_stack) > 50: jump_stack.pop(0)
      real_file = (os.path.join(get_pfile(self.view).project.dir, file) +
        ":" + str(data["start"]["line"] + 1) + ":" + str(data["start"]["ch"] + 1))
      sublime.active_window().open_file(real_file, sublime.ENCODED_POSITION)
    else:
      url = data.get("url", None)
      if url is None:
        sublime.error_message("Could not find a definition")
      else:
        webbrowser.open(url)

class TernJumpBack(sublime_plugin.TextCommand):
  def run(self, edit, **args):
    if len(jump_stack) > 0:
      sublime.active_window().open_file(jump_stack.pop(), sublime.ENCODED_POSITION)

class TernSelectVariable(sublime_plugin.TextCommand):
  def run(self, edit, **args):
    data = run_command(self.view, "refs", fragments=False)
    if data is None: return
    file = relative_file(get_pfile(self.view))
    shown_error = False
    regions = []
    for ref in data["refs"]:
      if ref["file"] != file:
        if not shown_error:
          sublime.error_message("Not all uses of this variable are file-local. Selecting only local ones.")
          shown_error = True
      else:
        regions.append(sublime.Region(ref["start"], ref["end"]))
    self.view.sel().clear()
    for r in regions: self.view.sel().add(r)

plugin_dir = os.path.abspath(os.path.dirname(__file__))

def plugin_loaded():
  global arghints_enabled, tern_command, tern_arguments
  settings = sublime.load_settings("Preferences.sublime-settings")
  arghints_enabled = settings.get("tern_argument_hints", False)
  tern_arguments = settings.get("tern_arguments", [])
  tern_command = settings.get("tern_command", None)
  if tern_command is None:
    if not os.path.isdir(os.path.join(plugin_dir, "node_modules/tern")):
      if sublime.ok_cancel_dialog(
          "It appears Tern has not been installed. Do you want tern_for_sublime to try and install it? "
          "(Note that this will only work if you already have node.js and npm installed on your system.)"
          "\n\nTo get rid of this dialog, either uninstall tern_for_sublime, or set the tern_command setting.",
          "Yes, install."):
        try:
          subprocess.check_call(["npm", "install"], cwd=plugin_dir)
        except:
          sublime.error_message("Installation failed. Try doing 'npm install' manually in " + plugin_dir)
          return
    tern_command = ["node",  os.path.join(plugin_dir, "node_modules/tern/bin/tern")]

def cleanup():
  for f in files.values():
    kill_server(f.project)
  
atexit.register(cleanup)

if is_st2:
  sublime.set_timeout(plugin_loaded, 500)
