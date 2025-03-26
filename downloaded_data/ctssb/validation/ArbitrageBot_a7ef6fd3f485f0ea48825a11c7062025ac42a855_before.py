#!/usr/bin/env python
#Imports
from bittrex import bittrex
from time import sleep
import time
import sys
from poloniex import poloniex
import argparse
def main(argv):
	# Setup Argument Parser
	parser = argparse.ArgumentParser(description='Poloniex/Bittrex Arbitrage Bot')
	parser.add_argument('-d', '--dryrun', action='store_true', required=False, help='simulates without trading (API keys not required)')
	args = parser.parse_args()

	if args.dryrun:
		print("Dryrun Mode Enabled (will not trade)")

	#Inputs and set variables
	period = float(raw_input("Period(Delay Between Each Check in seconds): "))
	targetCurrency = raw_input("Coin (Example: ETH): ")
	minArb = float(raw_input("Minimum Arbitrage % (Recomended to set above 100.5 as fees from both sides add up to 0.5%): "))
	baseCurrency = 'BTC'
	tradePlaced = False

	#Bittrex API Keys
	bittrexAPI = bittrex('APIKEY','APISECRET')

	#Polo API Keys
	poloniexAPI = poloniex('APIKEY','APISECRET')

	# Pair Strings for accessing API responses
	bittrexPair = '{0}-{1}'.format(baseCurrency,targetCurrency)
	poloniexPair = '{0}_{1}'.format(baseCurrency,targetCurrency)

	# Trade Function
	def trade(_buyExchange, _ask, _bid, _srcBalance, _buyBalance):
		# _buyExchange:
		# 0 = Poloniex
		# 1 = Bittrex

		arbitrage = (_bid/_ask) * 100
		# Return minumum arbitrage percentage is not met
		if ((arbitrage) <= minArb):
			return

		if (_buyExchange == 0):
			buyExchangeString = 'Poloniex'
			sellExchangeString = 'Bittrex'
			sellbook = poloniexAPI.returnOrderBook(poloniexPair)["asks"][0][1]
			buybook = bittrexAPI.getorderbook(bittrexPair, "sell")[0]["Quantity"]
		elif (_buyExchange == 1):
			buyExchangeString = 'Bittrex'
			sellExchangeString = 'Poloniex'
			buybook = poloniexAPI.returnOrderBook(poloniexPair)["bids"][0][1]
			sellbook = bittrexAPI.getorderbook(bittrexPair, "sell")[0]["Quantity"]

		print('Buy from ' + buyExchangeString + ', sell to ' + sellExchangeString + '. Arbitrage Rate: ' + str(arbitrage) + '%')

		#Find minimum order size
		tradesize = min(sellbook, buybook)

		#Setting order size incase balance not enough
		if (_srcBalance < tradesize):
			tradesize = _srcBalance

		if ((tradesize*_ask) > _buyBalance):
			tradesize = _buyBalance / _ask

		#Check if above min order size
		if ((tradesize*_bid)>0.0005001):
			print("Selling {0} {1} @ {2} @ {3} and buying {4} {5} @ {6} @ {7}".format(tradesize, targetCurrency, sellExchangeString, _bid, tradesize, targetCurrency, buyExchangeString, _ask))
			#Execute order
			if not args.dryrun:
				if (_buyExchange == 0):
					bittrexAPI.selllimit(bittrexPair, tradesize, _bid)
					orderNumber = poloniexAPI.buy(poloniexPair, _ask, tradesize)
				elif (_buyExchange == 1):
					bittrexAPI.buylimit(bittrexPair, tradesize, _ask)
					orderNumber = poloniexAPI.sell(poloniexPair, _bid, tradesize)
			else:
				print("Dryrun: skipping order")
		else:
			print("Order size not above min order size, no trade was executed")

	while True:

		#Poloniex Prices
		currentValues = poloniexAPI.api_query("returnTicker")
		poloBid = float(currentValues[poloniexPair]["highestBid"])
		poloAsk = float(currentValues[poloniexPair]["lowestAsk"])
		print("Bid @ Poloniex:	" + str(poloBid))
		print("Ask @ Poloniex:	" + str(poloAsk))

		#Bittrex Prices
		summary=bittrexAPI.getmarketsummary(bittrexPair)
		bittrexAsk = summary[0]['Ask']
		print("Ask @ Bittrex:	" + str(bittrexAsk))
		bittrexBid = summary[0]['Bid']
		print("Bid @ Bittrex:	" + str(bittrexBid))

		# Get Balance Information, fake numbers if dryrun.
		if not args.dryrun:
			# Query Bittrex API
			bittrexTargetBalance = bittrexAPI.getbalance(targetCurrency)
			bittrexBaseBalance = bittrexAPI.getbalance(baseCurrency)
			# Query Poloniex API
			allpolobalance = poloniexAPI.api_query('returnBalances')
			# Copy Poloniex Balance Variables
			poloniexTargetBalance = allpolobalance[targetCurrency]
			poloniexBaseBalance = allpolobalance[baseCurrency]
		else:
			# Faking Balance Numbers for Dryrun Simulation
			bittrexTargetBalance=100.0
			bittrexBaseBalance=100.0
			poloniexTargetBalance=100.0
			poloniexBaseBalance=100.0

		#Buy from Polo, Sell to Bittrex
		if (poloAsk<bittrexBid):
			trade(0, poloAsk, bittrexBid, bittrexTargetBalance, poloniexBaseBalance)
		#Sell to polo, Buy from Bittrex
		elif(bittrexAsk<poloBid):
			trade(1, bittrexAsk, poloBid, bittrexBaseBalance, poloniexTargetBalance)

		time.sleep(period)


if __name__ == "__main__":
	main(sys.argv[1:])
