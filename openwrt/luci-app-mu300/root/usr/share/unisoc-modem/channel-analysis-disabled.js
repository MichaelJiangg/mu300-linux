'use strict';
'require view';

// No network discovery, RPC calls or polling, even through an old direct link.
return view.extend({
    render: function() {
        var lang = (document.documentElement.lang || '').toLowerCase();
        var text = lang.indexOf('zh') === 0 ? '信道扫描已禁用。' :
            lang.indexOf('tr') === 0 ? 'Kanal taraması devre dışı.' :
            'Channel scanning is disabled.';
        return E('div', { 'class': 'cbi-map' }, [ E('p', {}, text) ]);
    },
    handleSaveApply: null,
    handleSave: null,
    handleReset: null
});
