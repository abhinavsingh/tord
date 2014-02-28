$(function() {
	window.tord = new Tord.Channel();
	tord.connect();
	
	var id1 = tord.request('/api/user/1/', {'a':'ç'}, function(msg) {
		console.assert(msg._id_ == id1);
		console.assert(msg._data_.user_id == '1');
		console.assert(msg._path_ == '/api/user/1/');
	});
	
	var id2 = tord.request('/api/user/1/photo/', {'a':'≈'}, function(msg) {
		console.assert(msg._async_ == true);
		console.assert(msg._id_ == id2);
		console.assert(msg._data_.user_id == '1');
		console.assert(msg._path_ == '/api/user/1/photo/');
	});
	
	var id3 = tord.request('/api/user/1/streaming/', {'a':'√'}, function(msg) {
		console.assert(msg._async_ == true);
		console.assert(msg._id_ == id3);
		if(msg._data_.i < 5)
			console.assert(msg._final_ == false);
		console.assert(msg._data_.stream == 'streaming');
	});
});
