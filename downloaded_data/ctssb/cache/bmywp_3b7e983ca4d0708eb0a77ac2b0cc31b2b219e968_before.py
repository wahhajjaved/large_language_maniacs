from main import bmybit

class Exchange():

    def createOrder(self, exchange, pair, currency, amount):
        try:
	    # should be a post request !!
            bmybit.get('/exchanges/order',
                        data={'exchange':   exchange,
                              'pair':       pair,
                              'currency':   currency,
                              'condition':  amount})
        except:
            print 'Could not create the order'


    def getExchange(self, id):
        try:
            bmybit.get('/exchanges',
                        params={'id': id})
        except:
            print 'Could not get exchange'

    def getExchanges():
        try:
            bmybit.get('/exchanges')
        except:
            print 'Could not get exchange list'
