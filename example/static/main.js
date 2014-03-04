Tord.add_plugin('example', {
	
	// tord channel reference
	channel: null,
	
	// plugin initialization callback
	initialize: function(channel) {
		this.channel = channel;
	},
	
	// ws connection established
	opened: function() {
		this.channel.log('opened');
	},
	
	// tord ws session initialized + pubsub channel opened/subscribed
	connected: function() {
		this.channel.log(this.channel.sid + ' ' + this.channel.tid + ' ' + this.channel.uid);
		this.test();
	},
	
	// ws connection dropped
	closed: function(e) {
		this.channel.log('closed ' + e.code);
	},
	
	// your own custom plugin method
	// here we test against our example app ws api routes
	test: function() {
		var id1 = this.channel.request('/api/user/1/', {'a':'ç'}, function(msg) {
			console.assert(msg._id_ == id1);
			console.assert(msg._data_.user_id == '1');
			console.assert(msg._path_ == '/api/user/1/');
		});
		
		var id2 = this.channel.request('/api/user/1/photo/', {'a':'≈'}, function(msg) {
			console.assert(msg._async_ == true);
			console.assert(msg._id_ == id2);
			console.assert(msg._data_.user_id == '1');
			console.assert(msg._path_ == '/api/user/1/photo/');
		});
		
		var id3 = this.channel.request('/api/user/1/streaming/', {'a':'√'}, function(msg) {
			console.assert(msg._async_ == true);
			console.assert(msg._id_ == id3);
			if(msg._data_.i < 5)
				console.assert(msg._final_ == false);
			console.assert(msg._data_.stream == 'streaming');
		});
	}
});

$(function() {
	window.tord = new Tord.Channel();
	tord.connect();
});
