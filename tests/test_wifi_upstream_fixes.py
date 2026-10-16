"""Regression guards for upstream #140/#146, retaining local latency/pressure work."""
import unittest
from helpers import TOP

class WirelessFixes(unittest.TestCase):
    def test_wifi_remove_tears_the_driver_down(self):
        # issue #146: the port's platform remove only logged (the vendor's calls sprd_iface_remove), so rmmod freed
        # the module with the recovery watchdog's delayed work still armed: __run_timers panicked within a second
        wlan = TOP / 'upstream' / 'modules' / 'sprd_wlan_combo'
        drv = (wlan / 'common' / 'sprd_wlan.c').read_text()
        rm = drv[drv.index('static void sprd_wlan_remove('):]
        rm = rm[:rm.index('\n}\n')]
        self.assertIn('\tif (p_match_data->hw_type == SPRD_HW_SC2355_PCIE)\n\t\tsprd_iface_remove(pdev);', rm)
        iface = (wlan / 'common' / 'iface.c').read_text()
        body = iface[iface.index('int sprd_iface_remove('):]
        body = body[:body.index('\n}\n')]
        # the watchdog stops first, and a failed power-on does not leave the teardown undone
        self.assertLess(body.index('iface_wd_stop();'), body.index('sprd_iface_set_power(hif, true);'))
        self.assertEqual(body.count('\n\treturn '), 1)
        self.assertIn('\tif (!ret)\n\t\tsprd_iface_set_power(hif, false);', body)
        wd = iface[iface.index('static void iface_wd_stop(void)'):]
        wd = wd[:wd.index('\n}\n')]
        self.assertIn('cancel_delayed_work_sync(&iface_wd.tick);', wd)
        # the timers that live in priv are shut down where priv is freed
        core_free = (wlan / 'common' / 'cfg80211.c').read_text()
        core_free = core_free[core_free.index('void sprd_core_free('):]
        core_free = core_free[:core_free.index('\n}\n')]
        self.assertLess(core_free.index('timer_shutdown_sync(&priv->scan_timer);'), core_free.index('wiphy_free(wiphy);'))
        ack = (wlan / 'sc2355' / 'tcp_ack.c').read_text()
        ack = ack[ack.index('void sc2355_tcp_ack_deinit('):]
        ack = ack[:ack.index('\n}\n')]
        self.assertLess(ack.index('sprd_chip_drop_tcp_msg('), ack.index('timer_shutdown_sync(&ack_m->ack_info[i].timer);'))

    def test_wifi_routine_events_are_not_logged_as_errors(self):
        # issue #140: the vendor printed per-poll survey data, the multicast default of the peer lookup, the
        # short-frame copy path, reordering drops, dup-ACK skips, EAPOL sends and DELBA for an unknown session with
        # pr_err/netdev_err. Both drivers trace them at debug level, the 5.4 one through its patch; the real errors
        # next to them ("too short", "alloc skb fail", BAR for an unknown session) keep their level
        wlan = TOP / 'upstream' / 'modules' / 'sprd_wlan_combo' / 'sc2355'
        patch = (TOP / 'kernel' / 'patches' / 'wlan_combo-routine-not-err.patch').read_text()
        src = {f: (wlan / f).read_text() for f in ('acs.c', 'pcie.c', 'sdio.c', 'mm.c', 'defrag.c', 'tx.c', 'reorder.c',
                                                   'tcp_ack.c')}
        # all of acs.c's error lines were dump_survey's trace
        self.assertNotIn('netdev_err(', src['acs.c'])
        self.assertIn('-\t\t\tnetdev_err(vif->ndev, "Not AP mode, exit %s!\\n",', patch)
        self.assertEqual(patch.count('+\t\t\t\t\tnetdev_dbg(vif->ndev,'), 2)
        lowered = (('pcie.c', '\t\tpr_debug("%s,%d,bssid not found, multicast?\\n"', 3),
                   ('sdio.c', '\t\tpr_debug("%s,%d,bssid not found, multicast?\\n"', 3),
                   ('mm.c', '\t\t\tpr_debug_ratelimited("%s: data len is %d, skb need %d\\n",', 1),
                   ('defrag.c', '\t\tpr_debug("%s:msdu len %d\\n", __func__, node->msdu_len);', 1),
                   ('tx.c', '\t\tpr_debug("send %s frame by CMD_TX_DATA\\n",', 1),
                   ('reorder.c', '\t\tpr_debug_ratelimited("%s: seq_num: %d is less than win_start: %d\\n",', 1),
                   ('reorder.c', '\t\tpr_debug_ratelimited("%s: kfree skb %d", __func__, ret);', 1),
                   ('reorder.c', '\t\tpr_debug("%s: NOT FOUND sta_lut_index: %d, tid: %d\\n",', 1),
                   ('tcp_ack.c', '\t\t\tpr_debug_ratelimited("%s before abnormal ack: %d, %d\\n",', 1))
        def hunks(f):  # the patch's section for one file
            s = patch[patch.index('--- a/sc2355/' + f + '\n'):]
            end = s.find('\n--- a/', 1)
            return s if end < 0 else s[:end]
        for f, line, n in lowered:
            with self.subTest(file=f, line=line):
                self.assertEqual(src[f].count(line), n)
                self.assertEqual(hunks(f).count('+' + line), n)
                self.assertEqual(hunks(f).count('-' + line.replace('pr_debug_ratelimited(', 'pr_err(')
                                                .replace('pr_debug(', 'pr_err(')), n)
        # the errors next to them stay
        self.assertIn('pr_err_ratelimited("%s: data len is %d, too short\\n"', src['mm.c'])
        self.assertIn('pr_err_ratelimited("%s: alloc skb fail\\n"', src['mm.c'])
        bar = src['reorder.c'][src['reorder.c'].index('static void reorder_wlan_bar_event('):]
        self.assertIn('pr_err("%s: NOT FOUND sta_lut_index: %d, tid: %d\\n"', bar[:bar.index('\n}\n')])
        for kept in ('too short', 'alloc skb fail'):
            self.assertNotIn(kept, patch[patch.index('--- a/'):])
