#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import json
import uuid
import logging

from tornado import ioloop
from tornado import web
from tornado import websocket

from async_pubsub import (RedisPubSub, ZMQPubSub, 
                          CALLBACK_TYPE_CONNECTED, CALLBACK_TYPE_DISCONNECTED, 
                          CALLBACK_TYPE_SUBSCRIBED, CALLBACK_TYPE_UNSUBSCRIBED,
                          CALLBACK_TYPE_MESSAGE)

# globals
HttpRoutes = list()
WSCmds = dict()
PubSubKlass = None
PubSubKWArgs = dict()

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
    
    def open(self):
        global PubSubKlass, PubSubKWArgs
        self.channel_id = uuid.uuid4().hex
        
        PubSubKWArgs['callback'] = self.pubsub_callback
        self.pubsub = PubSubKlass(**PubSubKWArgs)
        self.pubsub.connect()
        self.connected = False
    
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
        if self.connected:
            self.pubsub.disconnect()
    
    def pubsub_callback(self, evtype, *args, **kwargs):
        if evtype == CALLBACK_TYPE_CONNECTED:
            logging.info('Connected to pubsub')
            self.connected = True
            self.pubsub.subscribe(self.channel_id)
        elif evtype == CALLBACK_TYPE_DISCONNECTED:
            logging.info('Disconnected from pubsub')
            self.connected = False
        elif evtype == CALLBACK_TYPE_SUBSCRIBED:
            logging.info('Subscribed to channel %s' % args[0])
        elif evtype == CALLBACK_TYPE_UNSUBSCRIBED:
            logging.info('Unsubscribed to channel %s' % args[0])
        elif evtype == CALLBACK_TYPE_MESSAGE:
            logging.info('Rcvd message %s on channel %s' % (args[1], args[0]))
    
    def raw_to_json(self, raw):
        try:
            return json.loads(raw)
        except ValueError, e:
            raise WSCmdBadPacket(str(e))
    
    def get_ws_cmd(self, msg):
        global WSCmds
        
        if type(msg) is not dict or 'cmd' not in msg:
            raise WSCmdAttributeRequired()
        
        cmd = msg['cmd']
        if cmd not in WSCmds:
            raise WSCmdNotFound()
        return cmd
    
    def execute_cmd(self, cmd, msg):
        global WSCmds
        
        func = WSCmds[cmd]
        try:
            func(self, msg)
        except Exception, e:
            raise WSCmdException(str(e))
    
    def send(self, msg, binary=False):
        self.write_message(msg, binary)

class Application(object):
    
    def __init__(self, **options):
        self.options = options
    
    def add_route(self, path, func, options=None):
        global HttpRoutes
        HttpRoutes.append((path, func, options),)
    
    def route(self, path):
        def decorator(func):
            handler = create_http_route_handler(func)
            self.add_route(path, handler)
            return func
        return decorator
    
    def ws(self, cmd):
        global WSCmds
        def decorator(func):
            WSCmds[cmd] = func
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
    
    @property
    def pubsub_klass(self):
        return ZMQPubSub if self.options['pubsub'] == 'ZMQ' else RedisPubSub
    
    @property
    def pubsub_kwargs(self):
        return self.options['pubsub_kwargs']
    
    def run(self):
        global HttpRoutes, PubSubKlass, PubSubKWArgs
        
        # setup pubsub class to use
        PubSubKlass = self.pubsub_klass
        PubSubKWArgs = self.pubsub_kwargs
        
        # handle websocket requests on ws_path
        self.add_route(self.ws_path, WebSocketHandler)
        
        # server static content out of abs_www_path directory
        self.add_route(self.static_path, web.StaticFileHandler, {'path': self.abs_www_path})
        
        # initialize application with registered routes
        self.app = web.Application(HttpRoutes, debug=self.debug)
        
        # listen and start io loop
        self.app.listen(self.port)
        print 'Listening on port %s ...' % self.port
        
        try:
            ioloop.IOLoop.instance().start()
        except KeyboardInterrupt:
            pass
        finally:
            print 'Shutting down ...'
