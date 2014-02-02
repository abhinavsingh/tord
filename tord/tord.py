#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import json
import uuid
import task
import logging
import async_pubsub

from tornado import ioloop
from tornado import web
from tornado import websocket
from tornado import template

# globals
logger = logging.getLogger(__name__)
settings = dict()
settings['routes'] = dict()
settings['routes']['http'] = list()
settings['routes']['ws'] = dict()
settings['pubsub'] = dict()
settings['pubsub']['klass'] = None
settings['pubsub']['opts'] = dict()

class WSBadPkt(Exception): pass
class WSPktPathAttrMissing(Exception): pass
class WSPktIDAttrMissing(Exception): pass
class WSRouteNotFound(Exception): pass
class WSRouteException(Exception): pass

class WSJSONPkt(object):
    
    def __init__(self, ws, raw):
        self.ws = ws
        self.raw = raw
        self.channel_id = self.ws.channel_id
    
    def load(self):
        try:
            self.msg = json.loads(self.raw)
        except ValueError, e:
            raise WSBadPkt(str(e))
    
    def validate(self):
        if 'path' not in self:
            raise WSPktPathAttrMissing()
        
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
    
    def reply(self, response, final=True):
        global settings
        
        out = {
            'meta': {
                'id': self.msg['id'],
                'final': final,
            }, 
            'response': response,
        }
        
        if self.ws:
            self.ws.send(out)
        else:
            settings['pubsub']['klass'].publish(self.channel_id, json.dumps(out))
    
    def reply_async(self, handler):
        self.ws = None
        t = task.Task(handler, self)
        t.start()
        return t
    
    def apply_handler(self):
        global settings
        
        path = self['path']
        if path not in settings['routes']['ws']:
            raise WSRouteNotFound()
        
        func = settings['routes']['ws'][path]
        try:
            func(self)
        except Exception, e:
            raise WSRouteException(str(e))

class WebSocketHandler(websocket.WebSocketHandler):
    
    def open(self):
        global settings
        self.channel_id = uuid.uuid4().hex
        
        settings['pubsub']['opts']['callback'] = self.pubsub_callback
        self.pubsub = settings['pubsub']['klass'](**settings['pubsub']['opts'])
        self.pubsub.connect()
        self.connected = False
    
    def on_message(self, raw):
        try:
            logger.debug('websocket rcvd: %s' % raw)
            pkt = WSJSONPkt(self, raw)
            pkt.load()
            pkt.validate()
            pkt.apply_handler()
        
        except WSBadPkt, e:
            logger.exception(e)
        
        except WSPktPathAttrMissing, e:
            logger.exception(e)
        
        except WSPktIDAttrMissing, e:
            logger.exception(e)
        
        except WSRouteNotFound, e:
            logger.exception(e)
        
        except WSRouteException, e:
            logger.exception(e)
    
    def on_close(self):
        if self.connected:
            self.pubsub.disconnect()
    
    def pubsub_callback(self, evtype, *args, **kwargs):
        if evtype == async_pubsub.CALLBACK_TYPE_CONNECTED:
            logger.info('Connected to pubsub')
            self.connected = True
            self.pubsub.subscribe(self.channel_id)
        elif evtype == async_pubsub.CALLBACK_TYPE_DISCONNECTED:
            logger.info('Disconnected from pubsub')
            self.connected = False
        elif evtype == async_pubsub.CALLBACK_TYPE_SUBSCRIBED:
            logger.info('Subscribed to channel %s' % args[0])
        elif evtype == async_pubsub.CALLBACK_TYPE_UNSUBSCRIBED:
            logger.info('Unsubscribed to channel %s' % args[0])
        elif evtype == async_pubsub.CALLBACK_TYPE_MESSAGE:
            if args[0] == self.channel_id:
                logging.debug('pubsub channel: %s rcvd: %s' % (args[0], args[1]))
                self.send(args[1])
            else:
                logging.debug('Rcvd msg %s on unhandled channel id %s' % (args[1], args[0]))
    
    def send(self, msg, binary=False):
        logging.debug('websocket send: %s' % msg)
        self.write_message(msg, binary)

class Application(object):
    
    def __init__(self, **options):
        global settings
        settings['options'] = options
    
    def add_route(self, path, func, options=None, prepend=False):
        global settings
        if prepend:
            settings['routes']['http'] = [(path, func, options),] + settings['routes']['http']
        else:
            settings['routes']['http'].append((path, func, options),)
    
    @staticmethod
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
    
    def _http_route(self, path):
        def decorator(func):
            handler = self.create_http_route_handler(func)
            self.add_route(path, handler)
            return func
        return decorator
    
    def _ws_route(self, path):
        global settings
        def decorator(func):
            settings['routes']['ws'][path] = func
        return decorator
    
    def route(self, path, transport='http'):
        return self._ws_route(path) if transport == 'ws' else self._http_route(path)
    
    def pubsub(self, klass, opts):
        self.pubsub_klass = klass
        self.pubsub_opts = opts
    
    @property
    def port(self):
        global settings
        return settings['options']['port'] if 'port' in settings['options'] else 8888
    
    @property
    def ws_path(self):
        global settings
        return settings['options']['ws_path'] if 'ws_path' in settings['options'] else '/ws'
    
    @property
    def static_dir(self):
        global settings
        return settings['options']['static_dir']
    
    @property
    def static_path(self):
        global settings
        return settings['options']['static_path'] if 'static_path' in settings['options'] else '/static'
    
    @property
    def templates_dir(self):
        global settings
        return settings['options']['templates_dir']
    
    @property
    def debug(self):
        global settings
        return settings['options']['debug'] if 'debug' in settings['options'] else False
    
    def run(self):
        global settings
        settings['pubsub']['klass'] = getattr(async_pubsub, self.pubsub_klass)
        settings['pubsub']['opts'] = self.pubsub_opts
        
        self.add_route('%s/(.*)' % self.static_path, web.StaticFileHandler, {'path': os.path.abspath(self.static_dir)}, True)
        self.add_route(self.ws_path, WebSocketHandler, None, True)
        self.template = template.Loader(os.path.abspath(self.templates_dir))
        
        self.app = web.Application(settings['routes']['http'], debug=self.debug, cache_compiled_templates=False)
        self.app.listen(self.port)
        print 'Listening on port %s ...' % self.port
        
        try:
            ioloop.IOLoop.instance().start()
        except KeyboardInterrupt:
            pass
        finally:
            print 'Shutting down ...'
