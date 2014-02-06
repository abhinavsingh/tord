/*!
 * Author: Abhinav Singh <mailsforabhinav@gmail.com>
 * 
 * Javascript library for communication with Tord server.
 */
var Tord = {
	plugins: {},
	add_plugin: function(name, proto) {
		Tord.plugins[name] = proto;
	}
};

Tord.Channel = function(url, sid, tid) {
	// tord service ws url
	this.url = url || "http://localhost:8888/ws";
	
	// channel sid/tid/uid notes
	// 1) Tord framework binds every channel (browser tab) to certain 
	// session id and tab id. Depending upon session initializer module, 
	// session id and tab id are either extracted from cookies, headers or even auto-generated.
	// 2) Tord framework also allows for providing custom session id and tab id
	// from client side. However, sockjs specification doesn't allow for extra 
	// url arguments, cookies or even headers.
	// 3) To workaround this limitation in sockjs specification, we take advantage 
	// of sockjs server id configuration option. Server id is default set to tid,
	// or sid_tid if a custom sid is provided to Tord constructor.
	// PS: usually backend session module will assign sid to web auth session id 
	// PS: backend session will also assign uid based upon web auth
	this.sid = sid;
	this.tid = tid || Math.floor(Math.random() * 4294967295);
	this.uid = null;
	
	// ws connection reference
	this.sock = null;
	
	// connection state variables
	this.connecting = false;
	this.connected = false;
	this.connect_tref = null;
	this.max_retry = 4;
	this.retry = 0;
	
	// outgoing message queue and auto-increment id
	this.id = Math.floor(Math.random() * 4294967295);
	this.q = [];
	
	// registered callbacks and handlers for response
	this.cbs = {};
	this.handlers = {};
	
	// upon channel open backend sends assigned sid/tid/uid, grab that packet and cache
	this.handlers['on_channel_open'] = this._on_channel_open.bind(this);
	
	// discover and register tord plugins
	// plugin init method is called upon discovery
	for(var k in Tord.plugins) {
		if(Tord.plugins.hasOwnProperty(k)) {
			var proto = Tord.plugins[k];
			var F = function() {};
			F.prototype = proto;
			this[k] = new F();
			if(this[k].init) {
				this[k].init(this);
			}
		}
	}
};

Tord.Channel.prototype = {
	
	// @public API to initiate connection to tord service
	connect: function() {
		// clear any previous connect timer
		if(this.connect_tref) {
			clearTimeout(this.connect_tref);
			this.connect_tref = null;
		}
		
		// call connect with exponential backoff strategy
		this.connect_tref = setTimeout(this._connect.bind(this), 1000 * Math.pow(2, this.retry++));
		if(this.retry > this.max_retry) this.retry = 0;
	},
	
	// @public API to terminate connection with tord service
	disconnect: function() {
		// clear any connect timer
		if(this.connect_tref) {
			clearTimeout(this.connect_tref);
			this.connect_tref = null;
		}
		
		// if connection is alive, close and cleanup
		if(this.sock) {
			this.sock.onclose = function() {};
			this.sock.close();
			this.sock = null;
		}
		
		// re-initialize
		this.connecting = false;
		this.connected = false;
		this.retry = 0;
		this.q = [];
		
		// call disconnected method of registered plugins
		for(var k in Tord.plugins) {
			if(Tord.plugins.hasOwnProperty(k)) {
				var handler = this[k];
				if(handler.disconnected) {
					handler.disconnected();
				}
			}
		}
	},
	
	// @public API to immediate restart aborting any timer
	reconnect: function() {
		// clear any connect timer
		this.disconnect()
		this.connect()
	},
	
	// @public API to send messages to tord service
	// path: (required) specify RESTful path for this request
	// payload: (optional) must be an object, defaults to empty object
	// cb: (optional) callback that will handle response received for this payload
	request: function(path, data, cb) {
		data = data || {};
		var id = this.id++;
		if(cb) this.cbs[id] = cb;
		this._request({'_id_': id, '_path_': path, '_data_': data});
		return id;
	},
	
	// @public API for logging
	log: function(msg) {
		if(window.console) {
			console.log((new Date).getTime(), msg);
		}
	},
	
	_on_channel_open: function(msg) {
		this.sid = msg['sid'];
		this.tid = msg['tid'];
		this.uid = msg['uid'];
	},
	
	// @private API that establish connection with tord service
	_connect: function() {
		this.connect_tref = null;
		this.connected = false;
		this.connecting = true;
		
		var server_id = this.sid ? this.sid + '_' + this.tid : this.tid;
		this.sock = new SockJS(this.url, null, {'server':server_id, 'debug':true});
		
		this.sock.onopen = this._on_open.bind(this);
		this.sock.onclose = this._on_close.bind(this);
		this.sock.onmessage = this._on_msg.bind(this);
	},
	
	// @private API that is called when connection to tord service succeeds
	_on_open: function() {
		// setup connection state variables
		this.connecting = false;
		this.connected = true;
		this.retry = 0;
		
		this.log("tord connected");
		
		// flush any pending queue of messages
		while(this.q.length > 0) 
			this._request(this.q.shift());
		
		// notify registered plugins about successful connection
		for(var k in Tord.plugins) {
			if(Tord.plugins.hasOwnProperty(k)) {
				var handler = this[k];
				if(handler._on_open) {
					handler._on_open();
				}
			}
		}
	},
	
	// @private API that is called when connection to tord service terminates
	_on_close: function(e) {
		// setup connection state variable
		this.connecting = false;
		this.connected = false;

		this.log("connection closed (" + e.code + ")");
		
		// cleanup and retry connection
		this.sock = null;
		this.connect();
		
		// notify registered plugins about termination of connection
		for(var k in Tord.plugins) {
			if(Tord.plugins.hasOwnProperty(k)) {
				var handler = this[k];
				if(handler._on_close) {
					handler._on_close();
				}
			}
		}
	},
	
	// @private API that is called when connection encounters an error
	_on_error: function(e) {
		// setup connection state variables
		this.connecting = false;
		this.connected = false;
		this.log("connection error (" + e.data + ")");
	},
	
	// @private API that is called when a message is received from tord service
	_on_msg: function(e) {
		try {
			// only json objects are valid response
			var msg = JSON.parse(e.data);
			
			// flag that is true if response
			// has been delegated to corresponding
			// callback or handler
			var handled = false;
			
			// if there is a registered callback for this response by id
			if(msg['_id_'] in this.cbs) {
				// and it's a valid callback
				if(this.cbs[msg['_id_']]) {
					// delegate response for further handling
					this.cbs[msg['_id_']](msg);
					handled = true;
				}
				
				// cleanup callback references
				if(!('_final_' in msg && msg['_final_'] == false)) {
					delete this.cbs[msg['_id_']];
				}
			}
			
			// if response hasn't been delegated to any callback
			// try to delegate response to a handler that handles
			// response of this path
			if(!handled && msg['_path_'] in this.handlers) {
				this.handlers[msg['_path_']](msg);
			}
		}
		catch(err) {
			console.log(err.message);
			this.log(err.message);
		}
	},
	
	// @private API that is responsible for flushing messages to the tord service
	// if we are connected, message is sent immediately
	// otherwise it is queued and flushed when we reconnect
	// NOTE: outgoing objects must have a mandatory path and id attribute
	_request: function(obj) {
		if(typeof obj == 'object' && obj._path_ && obj._id_) {
			if(this.connected) {
				this.sock.send(JSON.stringify(obj));
			}
			else {
				this.q.push(obj);
			}
		}
		else {
			this.log('invalid packet dropped');
			this.log(obj);
		}
	}
};