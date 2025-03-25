'''EchoAPI: simple chat server.

Demonstrates use of RemoteAPI as well as StdioTransport and TcpServerTransport.

The server responds to a "say" call with "echo" of the text to all clients.
The message "quit":
 - if coming from stdio, shuts the server down
 - if coming over a tcp connection, makes the server close the connection.

Run with python3 -m quickrpc.echo_api.
Enter json messages on the commandline to test stdio transport.
Use `telnet localhost 8888` to test tcp functionality.
Use `tail -F echo_api.log` in another terminal to watch logged events.
'''
import logging
L = lambda: logging.getLogger(__name__)
from .remote_api import RemoteAPI, incoming, outgoing


class EchoAPI(RemoteAPI):
    '''Demo of how to use RemoteAPI.

    Echo API answers incoming `say` calls with an `echo` call.
    '''
    @incoming
    def say(self, sender="", text=""): pass

    @outgoing
    def echo(self, receivers=None, text=""): pass

    @incoming
    def quit(self, sender=""): pass



def test():
    from .codecs import JsonRpcCodec, TerseCodec
    from .transports import StdioTransport, MuxTransport, TcpServerTransport
    
    L().info('Start echo_api.test')

    mt = MuxTransport()
    mt += StdioTransport()
    server = TcpServerTransport(port=8888)
    mt += server
    print('serving on port 8888')
    api = EchoAPI(codec=TerseCodec(), transport=mt)
    
    # on incoming "say", call "echo"
    api.say.connect(lambda sender="", text="": api.echo(text=text))
    
    # on incoming "quit", differentiate by sender.
    def onquit(sender):
        if sender=='stdio':
            print('Server stops.')
            mt.stop()
        else:
            print('Disconnect %s.'%sender)
            server.close(sender)
    api.quit.connect(onquit)
    
    mt.run()
    
    L().info('Exit echo_api.test')

if __name__ == '__main__':
    import logging
    print('supported: {"__method":"say", "text": "hello world"} and {"__method":"quit"}')
    logging.basicConfig(level='DEBUG', filename='echo_api.log')
    test()
