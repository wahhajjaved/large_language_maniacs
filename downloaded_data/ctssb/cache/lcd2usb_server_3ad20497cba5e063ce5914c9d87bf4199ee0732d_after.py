import time
import sys
import threading
import socket 

from lcd2usb import LCD

line_0 = "%I:%M%p"
line_1 = " "
line_2 = "Waiting for"
line_3 = "connection..."

server_address = ('localhost',8080)

lcd = LCD.find_or_die()

def input_handler(ctl_data, str_data):
  global line_0, line_1, line_2, line_3, lcd
  if ctl_data == "0":
    line_0 = str_data
  elif ctl_data == "1":
    line_1 = str_data
  elif ctl_data == "2":
    line_2 = str_data
  elif ctl_data == "3":
    line_3 = str_data
  elif ctl_data == "@":
    lcd.set_brightness(int(str_data))
  else:
    print "Bad ctl_data value"


class lcd_thread(threading.Thread):
  def run(self):
    self.lcd_refresh_loop()
  def lcd_refresh_loop(self):
    while True:
      import datetime
      dt = datetime.datetime.now()
      lcd.home()
      lcd.fill_center(dt.strftime(line_0),0)
      lcd.fill_center(dt.strftime(line_1),1)
      lcd.fill_center(dt.strftime(line_2),2)
      lcd.fill_center(dt.strftime(line_3),3)
      time.sleep(2)    


lcd.info()

lcd_update = lcd_thread(name = "lcd_update_thread")
lcd_update.start()

serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#only alow connections from same device
serversocket.bind(server_address)

serversocket.listen(5)
print "Listening on port 8080"
#Wait for connection
try:
  while True:
    connection, client_address = serversocket.accept()
    try: 
      print 'connection from', client_address
      while True:
        ctldata = connection.recv(1)
        if ctldata:
          lendata = connection.recv(2)
          if lendata:  
            lendata = int(lendata)
            data = connection.recv(32)
            if data:
              data = data[:lendata] 
              input_handler(ctldata, data)
            else:
              break
          else:
            break
        else:
          break
    finally:
      print "Disconnected"
      connection.close()
except KeyboardInterrupt:
  sys.exit()



