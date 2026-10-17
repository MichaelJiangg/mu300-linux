'use strict';
'require fs';
'require baseclass';

const suites = {ccmp:['4'],ccmp256:['10'],gcmp:['8'],gcmp256:['9'],tkip:['2'],'tkip+ccmp':['2','4']};

function apply(option, capabilities) {
    if (!Array.isArray(capabilities?.suites)) return; // Unknown is not unsupported.
    const supported = value => !suites[value] || suites[value].every(n => capabilities.suites.includes('00-0f-ac:' + n));
    const keys = option.keylist || [], labels = option.vallist || [];
    option.keylist = keys.filter(supported);
    option.vallist = labels.filter((_, i) => supported(keys[i]));
    const read = option.cfgvalue, validate = option.validate;
    option.cfgvalue = function(section) {
        const value = read.call(this, section);
        // Missing choices make a native select silently select its first item.
        // Retain only the existing invalid value; do not permit saving it.
        if (suites[value] && !this.keylist.includes(value))
            this.value(value, value.toUpperCase() + ' (' + _('Unsupported') + ')');
        return value;
    };
    option.validate = function(section, value) {
        if (!supported(value))
            return /^zh/.test(L.env.lang) ? '无线驱动不支持此密码套件，请选择支持的套件。' :
                /^tr/.test(L.env.lang) ? 'Kablosuz sürücüsü bu şifreleme paketini desteklemiyor. Desteklenen bir paket seçin.' :
                'The wireless driver does not support this cipher. Select a supported cipher.';
        return typeof validate === 'function' ? validate.call(this, section, value) : true;
    };
}

return baseclass.extend({
    load: radio => fs.exec_direct('/usr/libexec/unisoc-modem/wifi-ciphers', [radio], 'json').catch(() => ({})),
    apply
});
