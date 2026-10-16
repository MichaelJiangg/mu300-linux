"""Selected upstream fixes: offline checks only, never a real device or disk."""
import unittest

from helpers import TOP, ShellTest


class WifiSource(unittest.TestCase):
    def test_power_transition_lock_and_lifetime(self):
        wlan = TOP / 'upstream/modules/sprd_wlan_combo'
        hif = (wlan / 'common/hif.h').read_text()
        iface = (wlan / 'common/iface.c').read_text()
        pcie = (wlan / 'sc2355/pcie.c').read_text()
        patch = (TOP / 'kernel/patches/wlan_combo-wcn-power-serialise.patch').read_text()
        self.assertIn('struct mutex power_lock;', hif)
        for call in ('mutex_init', 'mutex_lock', 'mutex_unlock'):
            self.assertIn(call + '(&hif->power_lock);', iface)
            self.assertIn(call + '(&hif->power_lock);', patch)
        body = iface.split('int sprd_iface_set_power(', 1)[1].split('\n}\n', 1)[0]
        self.assertNotIn('return ', body.split('mutex_unlock', 1)[0])
        remove = iface.split('int sprd_iface_remove(', 1)[1]
        self.assertLess(remove.index('sprd_iface_set_power(hif, false)'), remove.index('sprd_core_free(priv)'))
        for name in ('core init failed', 'notify init failed'):
            error = iface.split(name, 1)[1].split('return ret;', 1)[0]
            self.assertLess(error.index('sprd_iface_set_power(hif, false)'), error.index('sprd_core_free(priv)'))
        rx = pcie.split('static int pcie_rx_handle(', 1)[1].split('\n}\n', 1)[0]
        self.assertLess(rx.index('if (unlikely(!rx_mgmt))'), rx.index('rx_mgmt->rx_list'))
        self.assertIn('smp_load_acquire(&sc2355_hif.hif)', pcie)
        self.assertIn('smp_store_release(&sc2355_hif.hif, (void *)hif)', pcie)
        off = pcie.split('void pcie_post_deinit(', 1)[1].split('\n}\n', 1)[0]
        self.assertLess(off.index('sprdwcn_bus_chn_deinit'), off.index('WRITE_ONCE(sc2355_hif.hif, NULL)'))
        failure = hif.split('if (sprd_sync_version(hif))', 1)[1].split('return -EIO;', 1)[0]
        for call in ('sprd_clean_work', 'sprd_hif_post_deinit', 'stop_marlin'):
            self.assertIn(call, failure)

    def test_cleanup_dns_and_firmware_logging(self):
        root = TOP / 'upstream/modules'
        pcie = (root / 'sprd_wlan_combo/sc2355/pcie.c').read_text()
        self.assertIn('for (; chn >= 0; chn--)', pcie)
        pool = (root / 'wcn_bsp/pcie/mchn.c').read_text().split('int mbuf_pool_deinit(', 1)[1]
        self.assertLess(pool.index('if (!pool->mem)'), pool.index('memset(pool->mem'))
        tx = (root / 'sprd_wlan_combo/sc2355/tx.c').read_text().split('if (is_data2cmd)', 1)[1]
        self.assertLess(tx.index('(is_ipv4_dns || is_ipv6_dns)'), tx.index('skb->ip_summed = CHECKSUM_NONE'))
        resume = (root / 'wcn_bsp/pcie/pcie.c').read_text().split('static int sprd_ep_resume(', 1)[1]
        self.assertNotIn('wcn_set_armlog(true)', resume.split('\n}\n', 1)[0])
        init = (root / 'wcn_bsp/platform/sysfs.c').read_text().split('int init_wcn_sysfs(', 1)[1]
        self.assertIn('sysfs_info.armlog_status = 0;', init)
        rx = (root / 'sprd_wlan_combo/sc2355/rx.c').read_text()
        # Keep the deployed fork's conservative IPv6 fix; do not revive firmware checksum drops.
        fill = rx.split('int sc2355_fill_skb_csum(', 1)[1].split('\n}\n', 1)[0]
        self.assertIn('CHECKSUM_NONE', fill)
        self.assertNotIn('return -1', fill)

    def test_legacy_build_does_not_hide_patch_failure(self):
        build = (TOP / 'kernel/build-all.sh').read_text()
        wlan = (TOP / 'kernel/build-wlan.sh').read_text()
        self.assertIn('sprdwcn-mbuf-pool-deinit-null', build)
        self.assertIn('patched_copy /src/ext-wlan_combo', build)
        self.assertIn('Wi-Fi patches changed:', wlan)
        for line in (build + wlan).splitlines():
            if 'patch -p1' in line:
                self.assertNotIn('|| true', line)


class DiskBounds(ShellTest):
    def test_each_shell_probe_rejects_out_of_disk_offsets(self):
        for path in ('install.sh', 'uninstall.sh', 'tools/reset-password.sh'):
            source = (TOP / path).read_text()
            loop = source.split('for cand in ', 1)[1]
            guard = next(line for line in loop.splitlines() if 'cand + 2048' in line)
            self.assertLess(loop.index(guard), loop.index('m=$(su_do'))
            for shell in self.each_shell():
                # Includes a legacy 25.8-GiB offset on a 16-GiB eMMC and the exact boundary.
                r = self.sh(shell, 'disk=33554432\nfor cand in -1 0 17179867136 17179867137 27762098176; do\n'
                            + guard + '\nprintf "%s\\n" "$cand"\ndone')
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stdout.splitlines(), ['0', '17179867136'])

    def test_full_partition_table_yields_zero_region(self):
        source = (TOP / 'install.sh').read_text()
        calc = source.split('last_end=$1; disk=$2', 1)[1].split('\ngib()', 1)[0]
        for shell in self.each_shell():
            for disk in (33554432, 67108864):
                r = self.sh(shell, f'last_end={disk - 34}; disk={disk}\n' + calc + '\nprintf "%s" "$SIZE"')
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stdout, '0')


class UsbHandoff(ShellTest):
    def test_rndis_bridged_before_address_cleanup_without_extra_rebind(self):
        source = (TOP / 'openwrt/overlay/etc/hotplug.d/iface/10-mu300-usb').read_text()
        self.assertNotIn('/UDC', source)  # the established procd re-enumeration stays in mu300-post
        net = self.tmp / 'net'
        (net / 'rndis0').mkdir(parents=True)
        source = source.replace('/sys/class/net', str(net)).replace('/run/mu300-early-udhcpd.pid', str(self.tmp / 'absent-pid'))
        self.stub('ip', '''
printf '%s\n' "$*" >> "$STUBLOG/ip-calls"
case "$*" in
 'link set rndis0 master br-lan') touch "$STUBLOG/bridged" ;;
 '-4 -o addr show dev br-lan') echo '2: br-lan inet 192.168.77.1/24 scope global br-lan' ;;
 '-o link show dev rndis0') [ -f "$STUBLOG/bridged" ] && echo '3: rndis0 master br-lan' ;;
 '-o link show dev usb0') echo '4: usb0' ;;
 '-4 -o addr show dev rndis0') echo "3: rndis0 inet $PORT_ADDR scope global rndis0" ;;
esac
exit 0
''')
        for shell in self.each_shell():
            for address in ('192.168.77.1/24', '192.168.77.1/16', '192.168.88.1/24'):
                for name in ('bridged', 'ip-calls'):
                    (self.tmp / name).unlink(missing_ok=True)
                r = self.sh(shell, source, ACTION='ifup', INTERFACE='lan', PORT_ADDR=address)
                self.assertEqual(r.returncode, 0, r.stderr)
                calls = (self.tmp / 'ip-calls').read_text()
                self.assertLess(calls.index('link set rndis0 master br-lan'), calls.index('-4 -o addr show dev br-lan'))
                if address.startswith('192.168.77.1/'):
                    self.assertIn(f'addr del {address} dev rndis0', calls)
                else:
                    self.assertNotIn('addr del ', calls)
                self.assertNotIn('addr del 192.168.77.1/24 dev usb0', calls)


if __name__ == '__main__':
    unittest.main()
