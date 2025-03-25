from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import logging
import threading
import time
import sys
import dateutil.parser
import mysqlinterface
import structures as ds
from structures import Device, User, Room, House, UserAction, CompAction
import json
import parser
from sys import argv

class HATSPersistentStorageRequestHandler(BaseHTTPRequestHandler):

    #When responsding to a request, the server instantiates a DeviceHubRequestHandler
    #and calls one of these functions on it.
    
    def do_GET(self):
        try:
            if parser.validateGetRequest(self.path):
                queryType = self.path.strip('/').split('/')[0]
                if queryType == 'HD':
                    houseID = parser.getHouseID(self.path)
                    if not houseID:
                      self.send_response(400)
                    body = ds.DumpJsonList(self.server.sqldb.get_house_devices(houseID))
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    body = ds.DumpJsonList(self.server.sqldb.get_house_devices(houseID))
                    self.wfile.write(body)
                elif queryType == 'RD':
                    houseID = parser.getHouseID(self.path)
                    roomID = parser.getRoomID(self.path)
                    if not houseID or not roomID:
                      self.send_response(400)
                    body = ds.DumpJsonList(self.server.sqldb.get_room_devices(houseID, roomID))
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(body)
                elif queryType == 'HT':
                    houseID = parser.getHouseID(self.path)
                    deviceType = parser.getDeviceType(self.path)
                    if not houseID or not deviceType:
                      send_response(400)
                    body = ds.DumpJsonList(self.server.sqldb.get_house_devices(houseID, deviceType))
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(body)
                elif queryType == 'RT':
                    houseID = parser.getHouseID(self.path)
                    roomID = parser.getRoomID(self.path)
                    deviceType = parser.getDeviceType(self.path)
                    if not houseID or not roomID or not deviceType:
                      send_response(400)
                    body = ds.DumpJsonList(self.server.sqldb.get_room_devices(houseID, roomID, deviceType))
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(body)
                elif queryType == 'BH':
                    houseID = parser.getHouseID(self.path)
                    if not houseID:
                      self.send_response(400)
                      self.end_headers()
                      return
                    blob = self.server.sqldb.get_house_data(int(houseID))
                    if blob is None or blob == '':
                        self.send_response(404)
                        self.end_headers()
                    else:
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.end_headers()
                        self.wfile.write(blob)
                elif queryType == 'BU':
                    userID = parser.getUserID(self.path)
                    if not userID:
                      send_response(400)
                    blob = self.server.sqldb.get_user_data(userID)

                    if blob is None or blob == '':
                        self.send_response(404)
                        self.end_headers()
                    else:
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(blob)
                elif queryType == 'BR':
                    houseID = parser.getHouseID(self.path)
                    roomID = parser.getRoomID(self.path)
                    if not houseID or not roomID:
                      send_response(400)
                    blob = self.server.sqldb.get_room_data(houseID,roomID)
                    if blob is None or blob == '':
                        self.send_response(404)
                        self.end_headers()
                    else:
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(blob)
                elif queryType == 'BD':
                    # Retrieve and verify device info from request.
                    houseID = parser.getHouseID(self.path)
                    deviceID = parser.getDeviceID(self.path)
                    roomID = parser.getRoomID(self.path)
                    if not houseID or not deviceID or not roomID:
                        self.send_response(400)
                        self.end_headers()
                        return

                    # Retrieve the blob from the server
                    blob = self.server.sqldb.get_device_data(houseID,deviceID,roomID)
                    if blob is None or blob == '':
                        self.send_response(404)
                        self.end_headers()
                        return

                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(blob)
                elif queryType == 'DD':
                    # Retrieve and verify device info from request.
                    houseID = parser.getHouseID(self.path)
                    roomID = parser.getRoomID(self.path)
                    deviceID = parser.getDeviceID(self.path)
                    if not houseID or not roomID or not deviceID:
                      self.send_response(400)
                      self.end_headers()
                      return

                    # Retrieve the blob from the server
                    blob = self.server.sqldb.get_device_data(houseID,deviceID,roomID)
                    if blob is None or blob == '':
                        self.send_response(404)
                        self.end_headers()
                        return

                    # Return the blob. Adjust to return type, too.
                    body = self.server.sqldb.get_device_data(houseID,deviceID,roomID)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(blob) 
                elif queryType == 'AL':
                    userID = parser.getUserID(self.path)
                    houseID = parser.getHouseID(self.path)
                    roomID = parser.getRoomID(self.path)
                    endTime = parser.getTimeFrame(self.path)
                    if not userID or not houseID or not roomID or not endTime:
                        print userID
                        print houseID
                        print roomID
                        print deviceID
                        print endTime
                        self.send_response(400)
                        self.end_headers()
                        return
                    startTime = dateutil.parser.parse('2013-04-20T12:00:00Z')
                    blob = self.server.sqldb.get_user_actions(userID, houseID, roomID, None, startTime, endTime)
                    if blob is None or blob == '':
                        self.send_response(404)
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(blob) 
                else:
                    self.stubResponseOK()
            else:
                self.stubResponseBadReq()
        except:
            #For any other uncaught internal error, respond HTTP 500:
            e = sys.exc_info()
            print e
            self.stubResponseInternalErr()

    def do_POST(self):
        try:
            if parser.validatePostRequest(self.path):
              queryType = self.path.strip('/').split('/')[0]
              if queryType == 'RESET':
                self.server.sqldb.reset_tables()
                self.send_response(200)
                self.end_headers()
              if queryType == 'D':
                houseID = parser.getHouseID(self.path)
                roomID = parser.getRoomID(self.path)
                deviceType = parser.getDeviceType(self.path)
                if not houseID or not roomID or not deviceType:
                  self.send_response(400)
                  self.end_headers()
                  return
                else:
                  length = int(self.headers.getheader('content-length', 0))
                  data = self.rfile.read(length)
                  newDevice = Device(houseID, None, deviceType, data, roomID)
                  deviceID = ''
                  if roomID == 0:
                    deviceID = self.server.sqldb.insert_house_device(newDevice)
                  else:
                    deviceID = self.server.sqldb.insert_room_device(newDevice)
                  self.send_response(200)
                  self.send_header('Content-Type', 'text')
                  self.end_headers()
                  self.wfile.write(deviceID)
              elif queryType == 'R':
                houseID = parser.getHouseID(self.path)
                if not houseID:
                  self.send_response(400)
                length = int(self.headers.getheader('content-length', 0))
                data = self.rfile.read(length)
                newRoom = Room(houseID, None, data, None)
                roomID = self.server.sqldb.insert_room(newRoom)
                self.send_response(200)
                self.send_header('Content-Type', 'text')
                self.end_headers()
                self.wfile.write(roomID)
              elif queryType == 'H':
                length = int(self.headers.getheader('content-length', 0))
                data = self.rfile.read(length)
                newHouse = House(None, data, None, None)
                try:
                  houseID = self.server.sqldb.insert_house(newHouse)
                except:
                  self.send_response(333)
                  self.end_headers()
                self.send_response(200)
                self.send_header('Content-Type', 'text')
                self.end_headers()
                self.wfile.write(houseID)
              elif queryType == 'U':
                length = int(self.headers.getheader('content-length', 0))
                data = self.rfile.read(length)
                newUser = User(None, data)
                userID = self.server.sqldb.insert_user(newUser)
                self.send_response(200)
                self.send_header('Content-Type', 'text')
                self.end_headers()
                self.wfile.write(userID)
              elif queryType == 'UU':
                length = int(self.headers.getheader('content-length', 0))
                data = self.rfile.read(length)
                userID = parser.getUserID(self.path)

                # Ensure data is already there.
                stored = self.server.sqldb.get_user_data(userID)
                if stored is None or stored == '':
                    self.send_response(404)
                    self.end_headers()
                    return

                # Update the user data and send a 200.
                self.server.sqldb.update_user(userID, data)
                self.send_response(200)
                self.end_headers()
                
              elif queryType == 'UH':
                length = int(self.headers.getheader('content-length', 0))
                data = self.rfile.read(length)
                houseID = parser.getHouseID(self.path)

                # Ensure data is already there.
                stored = self.server.sqldb.get_house_data(houseID)
                if stored is None or stored == '':
                    self.send_response(404)
                    self.end_headers()
                    return

                # Update the house data and send a 200.
                self.server.sqldb.update_house(houseID, data)
                self.send_response(200)
                self.end_headers()

              elif queryType == 'UR':
                length = int(self.headers.getheader('content-length', 0))
                data = self.rfile.read(length)
                houseID = parser.getHouseID(self.path)
                roomID = parser.getRoomID(self.path)

                # Ensure data is already there.
                stored = self.server.sqldb.get_room_data(houseID, roomID)
                if stored is None or stored == '':
                    self.send_response(404)
                    self.end_headers()
                    return

                # Update the room data and send a 200.
                self.server.sqldb.update_room(houseID, roomID, data)
                self.send_response(200)
                self.end_headers()

              elif queryType == 'UD':
                length = int(self.headers.getheader('content-length', 0))
                data = self.rfile.read(length)
                houseID = parser.getHouseID(self.path)
                roomID = parser.getRoomID(self.path)
                deviceID = parser.getDeviceID(self.path)

                # Ensure data is already there.
                stored = self.server.sqldb.get_device_data(houseID,
                    deviceID, roomID)
                if stored is None or stored == '':
                    self.send_response(404)
                    self.end_headers()
                    return

                # Update the device data and send a 200.
                self.server.sqldb.update_device(houseID, deviceID, data, roomID)
                self.send_response(200)
                self.end_headers()
            else:
                self.stubResponseBadReq()
        except:
            e = sys.exc_info()
            print e
            self.stubResponseInternalErr()

    def do_PATCH(self):
        try:
            if parser.validatePatchRequest(self.path):

                queryType = self.path.strip('/').split('/')[0]
                if queryType == 'A':
                    userID = parser.getUserID(self.path)
                    timeFrame = parser.getTimeFrame(self.path)
                    houseID = parser.getHouseID(self.path)
                    roomID = parser.getRoomID(self.path)
                    deviceID = parser.getDeviceID(self.path)
                    if not userID or not timeFrame or not houseID or not roomID or not deviceID:
                      self.send_response(400)
                      self.end_headers()
                      print "Stopped"
                      return
                    length = int(self.headers.getheader('content-length', 0))
                    data = self.rfile.read(length)
                    newUserAction = UserAction(userID, timeFrame, houseID, roomID, deviceID, data)
                    self.server.sqldb.insert_user_action(newUserAction)
                    self.send_response(200)
                    self.end_headers()
                elif queryType == 'C':
                    userID = parser.getUserID(self.path)
                    timeFrame = parser.getTimeFrame(self.path)
                    houseID = parser.getHouseID(self.path)
                    roomID = parser.getRoomID(self.path)
                    deviceID = parser.getDeviceID(self.path)
                    if not userID or not timeFrame or not houseID or not roomID or not deviceID:
                      self.send_response(400)
                      self.end_headers()
                      return
                    length = int(self.headers.getheader('content-length', 0))
                    data = self.rfile.read(length)
                    newCompAction = CompAction(userID, timeFrame, houseID, roomID, deviceID, data)
                    self.server.sqldb.insert_comp_action(newCompAction)
                    self.send_response(200)
                    self.end_headers()
            else:
                self.stubResponseBadReq()
        except:
            e = sys.exc_info()
            print e
            self.stubResponseInternalErr()

    def do_DELETE(self):
        try:
            if parser.validateDeleteRequest(self.path):
                queryType = self.path.strip('/').split('/')[0]
                if queryType == 'A':
                    userID = parser.getUserID(self.path)
                    if not userID:
                        self.send_response(400)
                        self.end_headers()
                        return
                    self.server.sqldb.delete_user(userID)
                    self.send_response(200)
                    self.end_headers()
                elif queryType == 'D':
                    houseID = parser.getHouseID(self.path)
                    roomID = parser.getRoomID(self.path)
                    deviceID = parser.getDeviceID(self.path)
                    if not houseID or not roomID or not deviceID:
                        self.send_response(400)
                        self.end_headers()
                        return
                    self.server.sqldb.delete_device(houseID, deviceID, roomID)
                    self.send_response(200)
                    self.end_headers()
                elif queryType == 'R':
                    houseID = parser.getHouseID(self.path)
                    roomID = parser.getRoomID(self.path)
                    if not houseID or not roomID:
                        self.send_response(400)
                        self.end_headers()
                        return
                    self.server.sqldb.delete_room(houseID, roomID)
                    self.send_response(200)
                    self.end_headers()
                elif queryType == 'H':
                    houseID = parser.getHouseID(self.path)
                    if not houseID:
                        self.send_response(400)
                        self.end_headers()
                        return
                    self.server.sqldb.delete_house(houseID)
                    self.send_response(200)
                    self.end_headers()
            else:
                self.stubResponseBadReq()
        except:
            e = sys.exc_info()
            print e
            self.stubResponseInternalErr()

    def stubResponseOK(self):
        self.send_response(200)
        self.end_headers()

    def stubResponseBadReq(self):
        self.send_response(400)
        self.end_headers()

    def stubResponseInternalErr(self):
        self.send_response(500)
        self.end_headers()

class HATSPersistentStorageServer(HTTPServer):

    def __init__(self, server_address, RequestHandlerClass, user, password, database):
        HTTPServer.__init__(self, server_address, RequestHandlerClass)
        self.shouldStop = False
        self.timeout = 1
        self.sqldb = mysqlinterface.MySQLInterface(user, password, database)

    def serve_forever (self):
        while not self.shouldStop:
            self.handle_request()

def runServer(server):
    server.serve_forever()

## Starts a server on a background thread.
#  @param server the server object to run.
#  @return the thread the server is running on.
#          Retain this reference because you should attempt to .join() it before exiting.
def serveInBackground(server):
    thread = threading.Thread(target=runServer, args =(server,))
    thread.start()
    return thread

if __name__ == "__main__":
    script, port, user, password, database = argv
    
    server = HATSPersistentStorageServer(('', int(port)),
        HATSPersistentStorageRequestHandler, user, password, database)
    serverThread = serveInBackground(server)
    try:
        while serverThread.isAlive():
            time.sleep(120)
    except KeyboardInterrupt:
        print 'Attempting to stop server (timeout in 30s)...'
        server.shouldStop = True
        serverThread.join(30)
        if serverThread.isAlive():
            print 'WARNING: Failed to gracefully halt server.'

