'use strict';
'require baseclass';

/* Independent, start-to-start polling lanes. Hidden pages do no background
 * work; an in-flight request finishes before its lane can start another. */
function poll(request, accept, interval, failed, reset, active) {
	var stopped = false, running = false, timer, epoch = 0;
	function stop() {
		stopped = true;
		epoch++;
		clearTimeout(timer);
		document.removeEventListener('visibilitychange', visibility);
	}
	function current(generation) {
		if (active && !active()) stop();
		return !stopped && !document.hidden && generation === epoch;
	}
	function tick() {
		clearTimeout(timer);
		if (active && !active()) stop();
		if (stopped || running || document.hidden) return;
		running = true;
		var started = performance.now(), generation = epoch;
		Promise.resolve().then(request).then(function(value) {
			if (current(generation)) accept(value);
		}, function(error) {
			if (current(generation) && failed) failed(error);
		}).catch(function(error) {
			if (current(generation) && failed) failed(error);
		}).finally(function() {
			running = false;
			if (!stopped && !document.hidden)
				timer = setTimeout(tick, Math.max(50, interval() - (performance.now() - started)));
		});
	}
	function visibility() {
		epoch++;
		clearTimeout(timer);
		if (reset) reset();
		if (!document.hidden) tick();
	}
	document.addEventListener('visibilitychange', visibility);
	// Allow LuCI to attach the returned view before the initial response arrives.
	timer = setTimeout(tick, 0);
	return stop;
}

function seconds(value) {
	var n = Number(value);
	return Number.isFinite(n) && n > 0 && n <= 60 ? Math.max(2, n) : 2;
}

function rateDelta(previous, current) {
	if (!previous || !current || !current.available || !previous.available ||
		previous.device !== current.device || previous.ifindex !== current.ifindex ||
		previous.boot_id !== current.boot_id) return null;
	var dt = current.ts - previous.ts;
	if (!(dt > 0) || current.rx < previous.rx || current.tx < previous.tx) return null;
	var dl = (current.rx - previous.rx) / dt, ul = (current.tx - previous.tx) / dt;
	return Number.isFinite(dl) && Number.isFinite(ul) ? { dl: dl, ul: ul } : null;
}

return baseclass.extend({ poll: poll, seconds: seconds, rateDelta: rateDelta });
