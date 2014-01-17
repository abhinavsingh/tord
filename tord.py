#!/usr/bin/env python
# -*- coding: utf-8 -*-
VERSION = (0, 1)
__version__ = '.'.join(map(str, VERSION[0:2]))
__description__ = 'Asynchronous websocket + pubsub based micro web framework'
__author__ = 'Abhinav Singh'
__author_email__ = 'mailsforabhinav@gmail.com'
__homepage__ = 'https://github.com/abhinavsingh/tord'
__license__ = 'BSD'

import os
import json
from tornado import ioloop
from tornado import web
from tornado import websocket
import logging

def create_http_route_handler(func):
    RequestHandler = type("RequestHandler", (web.RequestHandler,), {
        'get': func,
        'post': func,
        'head': func,
        'options': func,
        'put': func,
        'patch': func,
        'delete': func,
    })
    return RequestHandler

class WSCmdBadPacket(Exception): pass
class WSCmdAttributeRequired(Exception): pass
class WSCmdNotFound(Exception): pass
class WSCmdException(Exception): pass

class WebSocketHandler(websocket.WebSocketHandler):
    
    def open(self, *args):
        pass
    
    def on_message(self, raw):
        try:
            msg = self.raw_to_json(raw)
            cmd = self.get_ws_cmd(msg)
            self.execute_cmd(cmd, msg)
        
        except WSCmdBadPacket, e:
            logging.exception(e)
            self.close()
        
        except WSCmdAttributeRequired, e:
            logging.exception(e)
            self.close()
        
        except WSCmdNotFound, e:
            logging.exception(e)
            self.close()
        
        except WSCmdException, e:
            logging.exception(e)
            self.close()
    
    def on_close(self):
        pass
    
    def raw_to_json(self, raw):
        try:
            return json.loads(raw)
        except ValueError, e:
            raise WSCmdBadPacket(str(e))
    
    def get_ws_cmd(self, msg):
        if type(msg) is not dict or 'cmd' not in msg:
            raise WSCmdAttributeRequired()
        
        cmd = msg['cmd']
        if cmd not in self.cmds:
            raise WSCmdNotFound()
        return cmd
    
    def execute_cmd(self, cmd, msg):
        func = self.cmds[cmd]
        try:
            func(self, msg)
        except Exception, e:
            raise WSCmdException(str(e))
    
    def send(self, msg, binary=False):
        self.write_message(msg, binary)

class Application(object):
    
    def __init__(self, **options):
        self.options = options
        self.routes = list()
        self.cmds = dict()
    
    def add_route(self, path, func, options=None):
        self.routes.append((path, func, options),)
    
    def route(self, path):
        def decorator(func):
            handler = create_http_route_handler(func)
            self.add_route(path, handler)
            return func
        return decorator
    
    def ws(self, cmd):
        def decorator(func):
            self.cmds[cmd] = func
        return decorator
    
    @property
    def port(self):
        return self.options['port']
    
    @property
    def debug(self):
        return self.options['debug']
    
    @property
    def ws_path(self):
        return self.options['ws']
    
    @property
    def static_path(self):
        return self.options['static']
    
    @property
    def www_path(self):
        return self.options['www']
    
    @property
    def abs_www_path(self):
        return os.path.abspath(self.www_path)
    
    def run(self):
        # server static content out of abs_www_path directory
        self.add_route(self.static_path, web.StaticFileHandler, {'path': self.abs_www_path})
        
        # handle websocket requests on ws_path and pass ws cmd registry
        WebSocketHandler.cmds = self.cmds
        self.add_route(self.ws_path, WebSocketHandler)
        
        # initialize application with registered routes
        self.app = web.Application(self.routes, debug=self.debug)
        
        # listen and start io loop
        self.app.listen(self.port)
        print 'Listening on port %s ...' % self.port
        
        try:
            ioloop.IOLoop.instance().start()
        except KeyboardInterrupt:
            pass
        finally:
            print 'Shutting down ...'
