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

from task import Task

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

class WSBadPkt(Exception): pass
class WSPktCmdAttrMissing(Exception): pass
class WSPktIDAttrMissing(Exception): pass
class WSCmdNotFound(Exception): pass
class WSCmdException(Exception): pass

class WSJSONPkt(object):
    
    def __init__(self, ws, raw):
        self.ws = ws
        self.channel_id = self.ws.channel_id
        self.raw = raw
    
    def load(self):
        try:
            self.msg = json.loads(self.raw)
        except ValueError, e:
            raise WSBadPkt(str(e))
    
    def validate(self):
        if 'cmd' not in self:
            raise WSPktCmdAttrMissing()
        
        if 'id' not in self:
            raise WSPktIDAttrMissing()

    def __getitem__(self, key):
        return self.msg[key]
    
    def __setitem__(self, key, value):
        self.msg[key] = value
    
    def __delitem__(self, key):
        del self.msg[key]
    
    def __contains__(self, key):
        return key in self.msg
    
    def reply(self, response, partial=False):
        out = {
            'meta': {
                'id': self.msg['id'],
                'partial': partial,
            }, 
            'response': response,
        }
        
        if self.ws:
            self.ws.send(out)
        else:
            PubSubKlass.publish(self.channel_id, json.dumps(out))
    
    def reply_async(self, handler):
        self.ws = None
        t = Task(handler, self)
        t.start()
        return t
    
    def apply_handler(self):
        global WSCmds
        
        cmd = self['cmd']
        if cmd not in WSCmds:
            raise WSCmdNotFound()
        
        func = WSCmds[cmd]
        try:
            func(self)
        except Exception, e:
            raise WSCmdException(str(e))

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
            pkt = WSJSONPkt(self, raw)
            pkt.load()
            pkt.validate()
            pkt.apply_handler()
        
        except WSBadPkt, e:
            logging.exception(e)
        
        except WSPktCmdAttrMissing, e:
            logging.exception(e)
        
        except WSPktIDAttrMissing, e:
            logging.exception(e)
        
        except WSCmdNotFound, e:
            logging.exception(e)
        
        except WSCmdException, e:
            logging.exception(e)
    
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
            if args[0] == self.channel_id:
                self.send(args[1])
            else:
                logging.debug('Rcvd msg %s on unhandled channel id %s' % (args[1], args[0]))
    
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
