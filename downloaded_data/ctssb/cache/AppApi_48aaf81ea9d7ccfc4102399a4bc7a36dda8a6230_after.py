import falcon
import json
import os
import spidev
import dbus
import commands

from waitress import serve

config = json.load(open('./serverConfig.json'))
CurrDirStr = str(os.getcwd());

GlobalPlayerInfo = {
    'mode': 'bluetooth',
    'status': 'Playing',
    'volume': 100,
    'artist': 'DJ Paul Elstak',
    'title': 'Rainbow in the Sky',
    'albumCover': 'https://img.discogs.com/ljTN0VrZXK5e3fh5co4obege7fY=/fit-in/600x518/filters:strip_icc():format(jpeg):mode_rgb():quality(90)/discogs-images/R-186742-1395703236-4006.jpeg.jpg',
    'totalTime': '02:00',
    'currentTime': '00:20',
    'elapsedTime': 20,
    'LEDon': True
}

BTData = {"Status": "nodata", "Name": "nodata", "Track": {"Album": "nodata", "NumberOfTracks": 0, "Artist": "nodata", "Title": "nodata", "Genre": "", "Duration": 202999, "TrackNumber": 0}, "Subtype": "Audio Book", "Device": "nodata", "Position": 39952, "Type": "Audio"}

GlobalLedInfo = {
    'r': 255,
    'g': 255,
    'b': 255,
    'a': 1
}

class InfoClass:
    def on_get(self, req, resp):
        print("TRYING TO GET INFO")
        getBluetooth(BT_Media_props)

class PauseClass:
    def on_get(self, req, resp):
        print("TRYING TO PAUSE")
        BT_Media_iface.Pause()

# PlayerInfo shows and changes current player info and settings
class PlayerInfo:
    def on_get(self, req, resp):
        #getBluetooth(BT_Media_props)
        resp.body = json.dumps([GlobalPlayerInfo])

    def on_post(self, req, resp):
        global GlobalPlayerInfo
        GlobalPlayerInfo = json.load(req.bounded_stream)
        sendVolume(spi)
        dataChangeHandler()


# LedInfo shows and changes current RGB
class LedInfo:
    def on_get(self, req, resp):
        resp.body = json.dumps([GlobalLedInfo])

    def on_post(self, req, resp):
        global GlobalLedInfo
        GlobalLedInfo = json.load(req.bounded_stream)
        dataChangeHandler()


# Automatic Index Redirect
class Index:
    def on_get(self, req, resp):
        raise falcon.HTTPMovedPermanently('/index.html')


def start_server(api, config):
    host = config['host']
    port = config['port']
    serve(api, host=host, port=port)
    print('this probably never gets executed, if it does: cry for help')


def add_routes(api):
    api.add_route('/player', PlayerInfo())
    api.add_route('/led', LedInfo())
    api.add_route('/pause', PauseClass())
    api.add_route('/getinf', InfoClass())
    api.add_route('/', Index())
    api.add_static_route('/', CurrDirStr + '/src')

def dataChangeHandler():
    print(GlobalPlayerInfo)
    print(GlobalLedInfo)

def sendVolume(spi):
    volume = GlobalPlayerInfo['volume']
    volume = int(volume)
    volume = str(volume).encode()
    value_to_send = [0x22]
    spi.xfer(value_to_send)
    print('Sending VOLUME through SPI!')


def getBluetooth(props):
    Dict = props.GetAll("org.bluez.MediaPlayer1")
    BTData = json.dumps(Dict)
    #GlobalPlayerInfo['title'] = Jsonprops['Track']['Title']
    print BTData
    print type(BTData)


def getbtaddress():
    output = commands.getstatusoutput('sudo qdbus --system  org.bluez')
    array = output[1].split('\n')
    for ad in array:
        if 'player' in ad:
            return ad

    #SPI
#spi = spidev.SpiDev()
#spi.open(0, 1)
#spi.max_speed_hz = 1000000
#sendVolume(spi)


#Define DBUS
bus = dbus.SystemBus()
BTAddress = getbtaddress()
player = bus.get_object('org.bluez', BTAddress)
BT_Media_iface = dbus.Interface(player, dbus_interface='org.bluez.MediaPlayer1')
BT_Media_props = dbus.Interface(player, "org.freedesktop.DBus.Properties")


api = falcon.API()
add_routes(api)
start_server(api, config)
