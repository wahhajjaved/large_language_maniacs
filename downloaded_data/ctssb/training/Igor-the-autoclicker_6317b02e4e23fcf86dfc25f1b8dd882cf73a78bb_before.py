# @delay minimum time in seconds between each click
#        chrome browser has trouble handling anything
#        below this number.
DELAY = 0.001

import win32api, win32con, time, os

# left click at given cordinates
def click (x, y) -> int:
  win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN,x,y,0,0)
  win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP,x,y,0,0)
  return 1

# Igor provides what others can't.
def igor ():
  a, b = win32api.GetCursorPos()
  ref = a
  timer = time.clock()
  count = 0
  while (ref == a):
    a, b = win32api.GetCursorPos()
    count += click(a, b)
    if (time.clock() - timer > 0.0999999):
      timer = time.clock()
      win32api.SetConsoleTitle("click/s: " + str(count*10))
      count = 0
        
    time.sleep(DELAY)

def keyboardHandler():
  _click = _esc = False
  while (not _esc):
    if (_click):
      igor()
      print("= Cursor movement, stoped clicking.")
      
    _click = _esc = False
    while (not _esc and not _click):
      if (abs(win32api.GetKeyState(120)) > 1):
        _click = True
        print("= F9 pressed, now clicking!")

      elif (abs(win32api.GetKeyState(0x1B)) > 1):
        _esc = True
        print("= ESC pressed, exiting")
        
      else:
        time.sleep(0.01)

def main():
  print("========================")
  print("= Welcome " + os.getlogin())
  print("= Press F9 to start/resume.")
  print("= Move the cursor to pause")
  print("= Press ESC to exit.")
  print("= Clicks/s is displayed in the title.")
  print("=========================")
  print("= Press F9 to begin auto clicking")
  keyboardHandler()
  print("========================")

if __name__ == "__main__":
  main()
