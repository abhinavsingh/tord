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

def get_http_handler(func):
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

class WebSocketHandler(websocket.WebSocketHandler):
    
    def open(self, *args):
        pass
    
    def on_message(self, raw):
        try:
            msg = json.loads(raw)
            cmd = msg['cmd']
            func = self.cmd[cmd]
            func(self, msg)
        except Exception, e:
            logging.exception(e)
    
    def on_close(self):
        pass
    
    def send(self, msg):
        self.write_message(msg)

class Application(object):
    
    def __init__(self, **options):
        self.options = options
        self.routes = list()
        self.cmd = dict()
    
    def add_route(self, path, func, options=None):
        self.routes.append((path, func, options),)
    
    def route(self, path):
        def decorator(func):
            handler = get_http_handler(func)
            self.add_route(path, handler)
            return func
        return decorator
    
    def ws(self, cmd):
        def decorator(func):
            self.cmd[cmd] = func
        return decorator
    
    @property
    def abs_static_path(self):
        return os.path.abspath(self.options['static_dir'])
    
    def run(self):
        self.add_route(self.options['static_path'], web.StaticFileHandler, {'path': self.abs_static_path})
        
        WebSocketHandler.cmd = self.cmd
        self.add_route(self.options['ws_path'], WebSocketHandler)
        
        self.app = web.Application(self.routes, debug=self.options['debug'])
        self.app.listen(self.options['port'])
        ioloop.IOLoop.instance().start()
