/* SPDX-License-Identifier: GPL-2.0-only */
/* SC2355 firmware SAE; shared by SDIO and PCIe. Included by cmdevt.c. */
static int sc2355_prepare_sae(struct sprd_priv *priv, struct sprd_vif *vif,
			    struct cfg80211_ap_settings *settings)
{
	struct sc2355_sae_password {
		__le16 request_type;
		__le16 entry_type, entry_len;
		__le16 password_type, password_len;
		u8 data[];
	} __packed;
	const struct cfg80211_crypto_settings *crypto = &settings->crypto;
	struct sc2355_sae_password *p;
	struct sprd_msg *msg;
	bool sae = false;
	int i;

	for (i = 0; i < crypto->n_akm_suites; i++) {
		if (crypto->akm_suites[i] == WLAN_AKM_SUITE_FT_OVER_SAE)
			return -EOPNOTSUPP;
		if (crypto->akm_suites[i] == WLAN_AKM_SUITE_SAE)
			sae = true;
	}
	if (!sae)
		return 0; /* Preserve the existing WPA2/EAP/open path. */
	if (!(priv->extend_feature & SPRD_EXTEND_SOATAP_WPA3) ||
	    !(priv->fw_capa & SPRD_CAPA_AP_SME) ||
	    !(priv->fw_std & SPRD_STD_11W))
		return -EOPNOTSUPP;
	/* The recovered BSP interface supports hunting-and-pecking. Do not
	 * advertise H2E while feeding the firmware a legacy password entry.
	 */
	if (crypto->sae_pwe == NL80211_SAE_PWE_HASH_TO_ELEMENT ||
	    crypto->sae_pwe == NL80211_SAE_PWE_BOTH)
		return -EOPNOTSUPP;
	if (!crypto->sae_pwd || !crypto->sae_pwd_len ||
	    crypto->sae_pwd_len > 63)
		return -EINVAL;

	/* Same wire format as Android's vendor command 43:
	 * request 2, ENTRY(0), PWD(7), END(255), 16-bit LE TLV headers.
	 * No terminator is included in the password length. Four-way/EAPOL
	 * remains in hostapd, using the firmware's 40:45:da:04 PMK indication.
	 */
	msg = get_cmdbuf(priv, vif, sizeof(*p) + crypto->sae_pwd_len + 4,
			 CMD_SET_SAE_PARAM);
	if (!msg)
		return -ENOMEM;
	p = (struct sc2355_sae_password *)msg->data;
	memset(p, 0, sizeof(*p) + crypto->sae_pwd_len + 4);
	p->request_type = cpu_to_le16(SPRD_SAE_PASSWORD_ENTRY);
	p->password_type = cpu_to_le16(7);
	p->password_len = cpu_to_le16(crypto->sae_pwd_len);
	memcpy(p->data, crypto->sae_pwd, crypto->sae_pwd_len);
	p->data[crypto->sae_pwd_len] = 0xff;
	return send_cmd_recv_rsp(priv, msg, NULL, NULL);
}
