import os
import logging
from tord import Application

logging.basicConfig(level=logging.DEBUG)

##
## path to your web files
##

static_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static')
templates_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'templates')

##
## create an application
##

app = Application(
    #port = 8888,                         # (default: 8888) web server port
    #ws_path = '/ws',                     # (default: /ws) websocket path
    static_dir = static_dir,              # Static content (html, css, js) path
    #static_path = '/static',             # (default: /static) static http prefix
    templates_dir = templates_dir,        # See Loader class under `http://www.tornadoweb.org/en/stable/template.html`
    debug = True,                         # (default: False) enable debugging
)

##
## add pubsub support to the application
## See `https://github.com/abhinavsingh/async_pubsub` for more detail on pubsub support.
##

app.pubsub(
    klass = 'Redis', # or 'ZMQ'.
    opts = { # RedisPubSub expects redis server running at below configuration
        'host': '127.0.0.1',
        'port': 6379,
    }
)

##
## REST API over HTTP
##

@app.route(r'/api/user/(\w+)/')
def user_profile(request, user_id):
    request.write('%s profile' % user_id)

@app.route(r'/api/user/(\w+)/photo/')
def user_photo(request, user_id):
    request.write('%s photo' % user_id)

@app.route(r'.*$') # catch all
def index(request):
    template = app.template.load('index.html')
    ctx = {
        'title':'Tord Example', 
        'static_prefix':'/static',
        'tord_js_path':'/static/tord/tord.js',
    }
    request.write(template.generate(**ctx))

##
## REST API over Websocket
##

@app.route(r'/test/reply/', transport='ws')
def test_reply(pkt):
    # reply synchronously
    pkt.reply({'test':'reply'})

@app.route(r'/test/reply/async/', transport='ws')
def test_reply_async(pkt):
    # reply asynchronously
    _task = pkt.reply_async(test_reply_async_handler)

@app.route(r'/test/reply/async/partial/', transport='ws')
def test_reply_async_partially(pkt):
    # reply asynchronously and send data in chunks
    _task = pkt.reply_async(test_reply_async_partial_handler)

##
## WebSocket async reply handlers.
## These methods reply to the websocket request asynchronously.
## Configured pubsub server is used to send data asynchronously.
## See `https://github.com/abhinavsingh/task.py` for methods available on variable `_task` above and `t` below.
## `Task` can also be replaced by `celery`, `rq` etc
##

def test_reply_async_handler(t):
    pkt = t.args[0]
    pkt.reply({'test':'reply', 'async':True})
    return True

def test_reply_async_partial_handler(t):
    import time
    pkt = t.args[0]
    
    i = 0
    while True:
        if i == 5:
            break
        i += 1
        pkt.reply({'test':'reply', 'async':True, 'i':i}, final=bool(i == 5))
        time.sleep(1)
    
    return True

##
## run application
##

if __name__ == '__main__':
    app.run()
