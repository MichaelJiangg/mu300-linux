'use strict';
'require view';
'require rpc';

var callStatus = rpc.declare({ object: 'mu300dash', method: 'status', expect: { '': {} }, nobatch: true });

function registeredPlmn(status) {
	var cell = status?.cell;
	var plmn = cell?.operator?.plmn;
	if (typeof plmn !== 'string' || !/^[0-9]{5,6}$/.test(plmn) || cell.error ||
		!Number.isInteger(status.cell_age) || status.cell_age < 0 || status.cell_age > 5 ||
		status.info?.modem?.sim_state === 'absent')
		return null;

	var sig = status.sig;
	var latest = sig && sig.ts >= cell.ts ? sig : cell;
	if (latest.error || (latest.cfun != null && latest.cfun !== 1))
		return null;
	return [latest.reg5g, latest.reg].some(function(reg) {
		return reg && [1, 5, 9, 10].includes(reg.stat);
	}) ? plmn : null;
}

return view.extend({
	render: function() {
		this.unload();
		var viewInstance = this;
		var frame = E('iframe', {
			'title': _('Network Speed Test'),
			'src': L.resource('mu300-speedtest/r13/index.html'),
			'referrerpolicy': 'no-referrer',
			'style': 'display:block;width:100%;height:70vh;min-height:26rem;border:0'
		});
		var origin = window.location.origin;
		var attached = false;
		var active = true;
		var detachObserver = new MutationObserver(function() {
			if (frame.isConnected)
				attached = true;
			else if (attached)
				dispose();
		});

		async function handleCarrierRequest(event) {
			var request = event.data;
			if (!active || !frame.isConnected || event.origin !== origin || event.source !== frame.contentWindow ||
				request?.type !== 'mu300-speedtest:carrier-request' || typeof request.requestId !== 'string')
				return;
			var frameDocument = frame.contentDocument;
			if (!frameDocument || frameDocument.URL !== frame.src)
				return;

			attached = true;
			var plmn = null;
			function frameStillActive() {
				return active && frame.isConnected && frame.contentDocument === frameDocument;
			}
			try {
				// A status call can trigger the modem collector and return its previous snapshot.
				for (var attempt = 0; attempt < 5 && frameStillActive(); attempt++) {
					var status = await callStatus();
					plmn = registeredPlmn(status);
					if (plmn || status?.refreshing !== 1 || attempt === 4)
						break;
					await new Promise(function(resolve) { setTimeout(resolve, 900); });
				}
			} catch {
				// The standalone speed test also runs on LuCI installations without mu300dash.
			}
			if (frameStillActive())
				event.source.postMessage({ type: 'mu300-speedtest:carrier-response', requestId: request.requestId, plmn: plmn }, origin);
		}

		function onPageHide(event) {
			if (!event.persisted)
				dispose();
		}

		function dispose() {
			active = false;
			window.removeEventListener('message', handleCarrierRequest);
			window.removeEventListener('pagehide', onPageHide);
			detachObserver.disconnect();
			viewInstance._disposeCarrierBridge = null;
		}

		this._disposeCarrierBridge = dispose;
		window.addEventListener('message', handleCarrierRequest);
		window.addEventListener('pagehide', onPageHide);
		detachObserver.observe(document.documentElement, { childList: true, subtree: true });

		frame.addEventListener('load', function() {
			var body = frame.contentDocument && frame.contentDocument.body;
			var page = frame.contentWindow;

			if (!body || !page)
				return;

			function fit() {
				var height = Math.ceil(body.getBoundingClientRect().height);

				if (height > 0)
					frame.style.height = height + 'px';
			}

			fit();

			if (typeof page.ResizeObserver === 'function') {
				var observer = new page.ResizeObserver(function() {
					if (frame.isConnected)
						fit();
					else
						observer.disconnect();
				});

				observer.observe(body);
				page.addEventListener('pagehide', function(event) {
					if (!event.persisted)
						observer.disconnect();
				});
			}
		});

		return frame;
	},
	unload: function() {
		if (this._disposeCarrierBridge)
			this._disposeCarrierBridge();
	},

	handleSaveApply: null,
	handleSave: null,
	handleReset: null
});
