import json
import sched
import time
import datetime
from ib.opt import ibConnection, Connection, message
from modules.router import TwsManager
try:
	from modules.live import DemoStrategy
except:
	from modules.dummy_live import DemoStrategy



''' As offsets from midnight EST '''
# 9:28am
premarket_check = 9 * 60 * 60 + 28 * 60 
# 9:30am
market_open = 9 * 60 * 60 + 30 * 60
# 8:00pm
end_of_day = 18 * 60 *60

# TWS default settings
tws_port = 7496
tws_client_id = 1234
default_order_id = 1  # not entirely safe...



def main():
	''' Entry into basic market functionality '''
	
	# See examples/data_config.json for some example formats 
	config = json.load(open('./data_config.json', 'r'))
	
	tws = Connection.create(port=tws_port, clientId=tws_client_id)
	tws_manager = (tws, config, default_order_id) 
	#demo_strat = DemoStrategy() # Soon...


	# This will be for the actual processes during active hours
	while True:
		break



if __name__ == '__main__':
	main()