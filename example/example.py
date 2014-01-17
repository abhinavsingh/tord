import os
import logging
from tord import Application

logging.basicConfig(level=logging.DEBUG)

app = Application(
    port = 8888,
    ws = '/ws',
    static = '/(.*)',
    www = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'www'),
    debug = True,
    pubsub = 'Redis', # or 'ZMQ'
    pubsub_kwargs = {'host':'127.0.0.1', 'port':6379},
)

@app.route(r'/user/(\w+)/')
def user_profile(request, user_id):
    request.write('%s profile' % user_id)

@app.route(r'/user/(\w+)/photo/')
def user_photo(request, user_id):
    request.write('%s photo' % user_id)

@app.ws(r'/test/reply/')
def test_reply(pkt):
    pkt.reply({'test':'reply'})

@app.ws(r'/test/reply/async/')
def test_reply_async(pkt):
    _task = pkt.reply_async(test_async_reply_handler)

def test_async_reply_handler(t):
    pkt = t.args[0]
    pkt.reply({'test':'reply', 'async':True})
    return True

if __name__ == '__main__':
    app.run()
