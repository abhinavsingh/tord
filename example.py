import logging
from tord import Application

logging.basicConfig(level=logging.DEBUG)

app = Application(
    port = 8888,
    ws = '/ws',
    static = '/(.*)',
    www = 'www',
    debug = True,
)

@app.route(r'/user/(\w+)/')
def user_profile(request, user_id):
    request.write('%s profile' % user_id)

@app.route(r'/user/(\w+)/photo/')
def user_photo(request, user_id):
    request.write('%s photo' % user_id)

@app.ws(r'test_ws_cmd')
def test_ws_cmd(ws, msg):
    ws.send({'hello':'world'})

if __name__ == '__main__':
    app.run()
