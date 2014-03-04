import os
import logging
logging.basicConfig(format='%(asctime)s - %(filename)s:%(funcName)s:%(lineno)d - %(message)s', level=logging.DEBUG)

##
## path to your web files
##

static_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static')
templates_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'templates')

##
## create an application
##

from tord.tord import Application
app = Application(
    #port = 8888,                         # (default: 8888) web server port
    debug = True,                         # (default: False) enable debugging
)

##
## configure http
##

app.configure('http',
    static_dir = static_dir,              # Static content (html, css, js) path
    #static_path = '/static',             # (default: /static) static http prefix
    templates_dir = templates_dir,        # See Loader class under `http://www.tornadoweb.org/en/stable/template.html`
)

##
## configure websockets
##

def custom_session_initializer(ws):
    'session initializers must return a 3-tuple represending session id, user id and session data dictionary'
    return 'sessionXXX', 'userXXX', dict(session_data="some data type")

app.configure('ws', 
    #path = '/ws',                        # (default: /ws) websocket path
    session_initializer = custom_session_initializer, # (default: tord.WebSocketHandler.start_anonymous_session) Can also be a dotted path
)

##
## configure pubsub support for the application
## See `https://github.com/abhinavsingh/async_pubsub` for more detail on pubsub support.
##

# Expects Redis server running at below configuration
app.configure('pubsub',
    klass = 'Redis',
    opts = {
        'host': '127.0.0.1',
        'port': 6379,
    }
)

'''
# Expects ZMQ Service running, See `https://github.com/abhinavsingh/async_pubsub/blob/master/examples/zmq_service.py`
from zmq.eventloop import ioloop as zmq_ioloop
zmq_ioloop.install()
app.configure('pubsub',
    klass = 'ZMQ',
    opts = {
        'device_ip': '127.0.0.1', 
        'fport': 5559, 
        'bport': 5560
    }
)
'''

##
## REST API over HTTP
##

@app.route(r'/api/user/(\w+)/')
def user_profile(request, user_id):
    request.write('%s profile' % user_id)

@app.route(r'/api/user/(\w+)/photo/')
def user_photo(request, user_id, async, partial, async2, partial2):
    request.write('%s photo' % user_id)

@app.route(r'.*$') # catch all
def index(request):
    template = app.template.load('index.html')
    ctx = {'title':'Tord Example', 'static_prefix':'/static',}
    request.write(template.generate(**ctx))

##
## REST API over Websocket
##

@app.route(r'/api/user/(\w+)/$', transport='ws')
def test_reply(pkt, user_id):
    # reply synchronously
    pkt.reply({'user_id':user_id})

@app.route(r'/api/user/(\w+)/photo/$', transport='ws')
def test_reply_async(pkt, user_id):
    # reply asynchronously
    _task = pkt.reply_async(test_reply_async_handler, user_id)

@app.route(r'/api/user/(?P<user_id>\w+)/(?P<stream>\w+)/$', transport='ws')
def test_reply_async_partially(pkt, user_id, stream):
    # reply asynchronously and send data in chunks
    _task = pkt.reply_async(test_reply_async_partial_handler, user_id, stream)

##
## WebSocket async reply handlers.
## These methods reply to the websocket request asynchronously.
## Configured pubsub server is used to send data asynchronously.
## See `https://github.com/abhinavsingh/task.py` for methods available on variable `_task` above and `t` below.
## `Task` can also be replaced or used in combination with frameworks like `celery`, `rq` etc
##

def test_reply_async_handler(t):
    pkt = t.args[0]
    user_id = t.args[1]
    pkt.reply({'user_id':user_id})
    return True

def test_reply_async_partial_handler(t):
    import time
    pkt = t.args[0]
    user_id = t.args[1]
    stream = t.args[2]
    
    i = 0
    while True:
        if i == 5:
            break
        i += 1
        pkt.reply({'user_id':user_id, 'stream':stream, 'i':i}, final=bool(i == 5))
        time.sleep(1)
    
    return True

##
## run application
##

if __name__ == '__main__':
    app.run()
