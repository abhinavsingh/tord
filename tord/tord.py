#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import re
import json
import uuid
import task
import random
import logging
import async_pubsub

from tornado import ioloop, web, template
from sockjs.tornado import SockJSConnection, SockJSRouter

logger = logging.getLogger(__name__)

# settings
class Settings(): pass
settings = Settings()
settings.routes = dict()
settings.routes['http'] = list()
settings.routes['ws'] = dict()
settings.pubsub = dict()
settings.pubsub['klass'] = None
settings.pubsub['opts'] = dict()

# custom exceptions
class WSBadPkt(Exception): pass
class WSPktPathAttrMissing(Exception): pass
class WSPktIDAttrMissing(Exception): pass
class WSRouteNotFound(Exception): pass
class WSRouteException(Exception): pass

def import_path(path):
    '''Import and return object representing dotted path.

    Args:
        path (str): Dotted path to import.

    Example, for path `package.module.method`, it returns 
    an object representing `method`. This is similar to:

    >>> from package.module import method

    Wildcards (*) are also supported. e.g. providing 
    `package.module.*` is similar to doing:

    >>> from package import module

    '''
    parts = path.split('.')
    prefix = '.'.join(parts[:-1])
    suffix = '.'.join(parts[-1:])
    method = suffix if suffix is not '*' else [suffix]

    try:
        module = __import__(prefix, globals(), locals(), method, -1)
        return getattr(module, method) if suffix is not '*' else module
    except AttributeError as e:
        logger.error('failed to import path %s with reason Attribute error, prefix %s, suffix %s' % (path, prefix, suffix))
        raise ImportError(e)

class WSJSONPkt(object):
    'json serializer for websocket channels (implement your own)'
    
    def __init__(self, ws, raw):
        self.ws = ws
        self.raw = raw
        self.sid = self.ws.sid

    def __getitem__(self, key):
        return self.msg[key]
    
    def __setitem__(self, key, value):
        self.msg[key] = value
    
    def __delitem__(self, key):
        del self.msg[key]
    
    def __contains__(self, key):
        return key in self.msg
    
    def reply(self, data, final=True):
        out = dict(_id_=self.msg['_id_'], _data_=data)
        if not final:
            out['_final_'] = final
        
        if self.ws:
            self.ws.send(out)
        else:
            settings.pubsub['klass'].publish(self.sid, json.dumps(out))
    
    def reply_async(self, handler):
        self.ws = None
        t = task.Task(handler, self)
        t.start()
        return t
    
    def load(self):
        try:
            self.msg = json.loads(self.raw)
        except ValueError, e:
            raise WSBadPkt(str(e))
    
    def validate(self):
        if '_path_' not in self:
            raise WSPktPathAttrMissing()
        
        if '_id_' not in self:
            raise WSPktIDAttrMissing()
    
    def apply_handler(self):
        path = self['_path_']
        if path not in settings.routes['ws']:
            raise WSRouteNotFound()
        
        func = settings.routes['ws'][path]
        try:
            func(self)
        except Exception, e:
            raise WSRouteException(str(e))

class HTTPRequestHandler(web.RequestHandler):
    
    def handler(self, *args, **kwargs):
        return self.func(*args, **kwargs)
    
    head = handler
    get = handler
    post = handler
    options = handler
    put = handler
    patch = handler
    delete = handler

class WSInvalidInfoPath(Exception):
    
    def __init__(self, message, path):
        Exception.__init__(self, message)
        self.path = path
class WSSessionInitializationFailed(Exception): Exception

class WebSocketHandler(SockJSConnection):
    'Implements tornado web socket handler and delegate packets to handlers'
    
    def on_open(self, info):
        self.info = info
        self.parse_sid_tid_from_path()
        
        # TODO: session initializer klass can be defined via app settings
        params = self.start_anonymous_session(self)
        
        if len(params) == 3:
            self.sid, self.uid, self.ses = params
            self.connect_pubsub()
        else:
            raise WSSessionInitializationFailed('session initializer returned params tuple/list of length %s, expected 3' % len(params))
    
    def connect_pubsub(self):
        settings.pubsub['opts']['callback'] = self.pubsub_callback
        self.pubsub = settings.pubsub['klass'](**settings.pubsub['opts'])
        self.pubsub.connect()
        self.connected = False
    
    @staticmethod
    def start_anonymous_session(ws):
        sid = uuid.uuid4().hex
        user = 'guest.%s' % random.randint(111, 9999)
        session = dict()
        return sid, user, session
    
    def parse_sid_tid_from_path(self):
        parts = self.info.path.split('/')[2].split('_')
        if len(parts) > 2:
            raise WSInvalidInfoPath("invalid info.path %s, dropping connection" % self.info.path)
        
        if len(parts) == 1:
            self.sid = None
            self.tid = parts[0]
        elif len(parts) == 2:
            self.sid = parts[0]
            self.tid = parts[1]
    
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
        if evtype == async_pubsub.constants.CALLBACK_TYPE_CONNECTED:
            logger.info('Connected to pubsub')
            self.connected = True
            self.pubsub.subscribe(self.sid)
        elif evtype == async_pubsub.constants.CALLBACK_TYPE_DISCONNECTED:
            logger.info('Disconnected from pubsub')
            self.connected = False
        elif evtype == async_pubsub.constants.CALLBACK_TYPE_SUBSCRIBED:
            logger.info('Subscribed to channel %s' % args[0])
            if args[0] == self.sid:
                self.send({'sid':self.sid, 'tid':self.tid, 'uid':self.uid, '_path_':'on_channel_open'})
        elif evtype == async_pubsub.constants.CALLBACK_TYPE_UNSUBSCRIBED:
            logger.info('Unsubscribed to channel %s' % args[0])
        elif evtype == async_pubsub.constants.CALLBACK_TYPE_MESSAGE:
            if args[0] == self.sid:
                logging.debug('pubsub channel: %s rcvd: %s' % (args[0], args[1]))
                self.send(args[1])
            else:
                logging.debug('Rcvd msg %s on unhandled channel id %s' % (args[1], args[0]))
    
    def send(self, msg):
        logging.debug('websocket send: %s' % msg)
        if type(msg) not in (str, unicode):
            msg = json.dumps(msg)
        super(WebSocketHandler, self).send(msg)

class Application(object):
    'Handles initial bootstrapping of the application.'
    
    def __init__(self, **options):
        settings.options = options
        self.tord_static_path = os.path.join(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'static'), 'tord')
        self.template = template.Loader(os.path.abspath(self.templates_dir))
    
    def add_http_route(self, path, func, options=None, prepend=False):
        if prepend:
            settings.routes['http'] = [(path, func, options),] + settings.routes['http']
        else:
            settings.routes['http'].append((path, func, options),)
    
    def add_ws_route(self, path, func):
        settings.routes['ws'][path] = func
    
    @staticmethod
    def new_http_request_handler(func):
        return type("WebRequestHandler", (HTTPRequestHandler,), {'func': func,})
    
    def _add_http_route(self, path):
        def decorator(func):
            handler = self.new_http_request_handler(func)
            self.add_http_route(path, handler)
            return func
        return decorator
    
    def _add_ws_route(self, path):
        def decorator(func):
            self.add_ws_route(path, func)
        return decorator
    
    def route(self, path, transport='http'):
        '''Add route for particular path.
        
        Both `http` and `ws` routes can be registered using this method.
        '''
        return self._add_ws_route(path) if transport == 'ws' else self._add_http_route(path)
    
    def pubsub(self, klass, opts):
        '''Configure pubsub module for this application.
        
        `klass` must be one of `async_pubsub` implementation
        or must implement it's base API.
        
        `opts` is a dictionary passed as kwargs to the pubsub constructor
        '''
        self.pubsub_klass = klass
        self.pubsub_opts = opts
    
    @property
    def port(self):
        return settings.options['port'] if 'port' in settings.options else 8888
    
    @property
    def ws_path(self):
        return settings.options['ws_path'] if 'ws_path' in settings.options else '/ws'
    
    @property
    def static_dir(self):
        return settings.options['static_dir']
    
    @property
    def static_path(self):
        return settings.options['static_path'] if 'static_path' in settings.options else '/static'
    
    @property
    def templates_dir(self):
        return settings.options['templates_dir']
    
    @property
    def debug(self):
        return settings.options['debug'] if 'debug' in settings.options else False
    
    def run(self):
        settings.pubsub['klass'] = import_path('async_pubsub.%s_pubsub.%sPubSub' % (self.pubsub_klass.lower(), self.pubsub_klass))
        settings.pubsub['opts'] = self.pubsub_opts
        
        self.add_http_route('%s/(.*)' % self.static_path, web.StaticFileHandler, {'path': os.path.abspath(self.static_dir)}, True)
        self.add_http_route('%s/tord/(.*)' % self.static_path, web.StaticFileHandler, {'path': self.tord_static_path}, True)
        
        self.app = web.Application(
            SockJSRouter(WebSocketHandler, self.ws_path).urls + settings.routes['http'], 
            debug=self.debug
        )
        self.app.listen(self.port)
        print 'Listening on port %s ...' % self.port
        
        try:
            ioloop.IOLoop.instance().start()
        except KeyboardInterrupt:
            pass
        finally:
            print 'Shutting down ...'
