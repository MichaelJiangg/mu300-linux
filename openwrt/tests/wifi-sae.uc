import { configure } from '../hostapd-unisoc.uc';

function check(c, module, pmf, pwe, enabled) {
	configure(c, module);
	if (c.ieee80211w != pmf || c.sae_pwe != pwe || c.unisoc_sae != enabled)
		die('Unisoc SAE policy mismatch: ' + sprintf('%J', c));
	if (enabled && (c.rsn_override != 0 || c.rsn_override_pairwise != null || c.rsn_override_key_mgmt != null))
		die('Unsupported RSN Override must not be advertised');
}
const native = '/sys/module/sprd_wlan_combo';
check({auth_type: 'sae', ieee80211w: 0}, native, 2, 0, 1);
check({auth_type: 'sae', ieee80211w: 1}, native, 2, 0, 1);
check({auth_type: 'sae'}, native, 2, 0, 1);
check({auth_type: 'psk-sae', ieee80211w: 0}, native, 1, 0, 1);
check({auth_type: 'psk-sae', rsn_override: 1, rsn_override_pairwise: 'GCMP-256'}, native, 1, 0, 1);
check({auth_type: 'psk-sae', ieee80211w: 2, sae_pwe: 1}, native, 2, 1, 1);
check({auth_type: 'psk', ieee80211w: 0}, native, 0, null, null);
check({auth_type: 'sae', ieee80211w: 0}, '/sys/module/mt76', 2, null, null);
check({auth_type: 'psk-sae', ieee80211w: 0}, null, 1, null, null);
print('PASS: actual ucode SAE/PMF generation policy\n');
