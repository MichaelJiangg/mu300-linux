#!/usr/bin/env python3
"""Shared MMC durability policy; preserve runtime PM and idle clock gating."""
from pathlib import Path
import re


def apply(kernel):
    kernel = Path(kernel)
    # SDHCI core builds coherent ADMA descriptors immediately before ringing
    # SDHCI_COMMAND. Coherent allocation does not order these stores against
    # relaxed MMIO; likewise completion status must order subsequent DMA reads.
    # Match the ordered accessors provided by the generic SDHCI helpers.
    io = kernel / 'drivers/mmc/host/sdhci-sprd.c'
    text = io.read_text()
    start = text.index('static inline u32 sdhci_sprd_readl(')
    end = text.index('static inline void sdhci_sprd_sd_clk_off(', start)
    accessors = text[start:end]
    marker = 'Shared SDHCI policy: order ADMA descriptors and DMA completion'
    if marker not in accessors:
        accessors = accessors.replace(
            'return readl_relaxed(host->ioaddr + reg);',
            '/* ' + marker + '. */\n\treturn readl(host->ioaddr + reg);',
        )
        for width in ('b', 'w', 'l'):
            accessors = accessors.replace('write' + width + '_relaxed(', 'write' + width + '(')
    required = ('return readl(host->ioaddr + reg);',
                'writel(val, host->ioaddr + reg);',
                'writew(val, host->ioaddr + reg);',
                'writeb(val, host->ioaddr + reg);')
    if (marker not in accessors or any(item not in accessors for item in required)
            or re.search(r'write[bwl]_relaxed\(', accessors)):
        raise ValueError('SDHCI MMIO accessor anchors changed')
    io.write_text(text[:start] + accessors + text[end:])

    header = kernel / 'include/linux/mmc/host.h'
    text = header.read_text()
    if '#define MMC_CAP2_NO_REL_WR' not in text:
        if re.search(r'^#define MMC_CAP2_.*(?:<<\s*29|BIT\(29\))', text, re.M):
            raise ValueError('MMC capability bit 29 is no longer free')
        pos = text.index('\n', text.index('#define MMC_CAP2_ALT_GPT_TEGRA'))
        text = text[:pos] + '\n#define MMC_CAP2_NO_REL_WR\t(1 << 29)\t/* Emulate FUA with cache flushes */' + text[pos:]
        header.write_text(text)

    block = kernel / 'drivers/mmc/core/block.c'
    text = block.read_text()
    if '!(card->host->caps2 & MMC_CAP2_NO_REL_WR)' not in text:
        anchor = '\tif (md->flags & MMC_BLK_CMD23 &&\n'
        if text.count(anchor) != 1:
            raise ValueError('MMC reliable-write anchor changed')
        text = text.replace(anchor, anchor + '\t    !(card->host->caps2 & MMC_CAP2_NO_REL_WR) &&\n', 1)
        block.write_text(text)

    path = kernel / 'drivers/mmc/host/sdhci-sprd.c'
    text = path.read_text()
    # Clean old shared and V50-only policies from cached build trees as well.
    for start in (
        '\t/* Shared eMMC policy: keep the non-removable memory controller awake.',
        '\tif (!mmc_card_is_removable(host->mmc)) {\n\t\tstruct device_node *aw =',
    ):
        if start in text:
            a = text.index(start)
            b = text.index('\tsdhci_sprd_phy_param_parse(', a)
            text = text[:a] + text[b:]
    text = re.sub(
        r'\tif \(sprd_host->runtime_keep_awake\) \{\n'
        r'\t\tpm_runtime_forbid\(&pdev->dev\);\n.*?\n\t\}\n',
        '', text, flags=re.S,
    )
    text = text.replace('\tif (sprd_host->runtime_keep_awake)\n\t\tpm_runtime_allow(&pdev->dev);\n', '')
    text = text.replace('''\t/* Keep eMMC clocks and PHY state across runtime and system idle. */
\tif (sprd_host->runtime_keep_awake)
\t\treturn 0;

''', '')
    text = text.replace('''\t/* Shared eMMC policy: no autonomous inner/outer clock gating. */
\tif (clk > 400000 && !sprd_host->runtime_keep_awake) {''', '''\t/* Enable CLK_AUTO when the clock is greater than 400K. */
\tif (clk > 400000) {''')
    text = text.replace('\tbool runtime_keep_awake;\n', '')
    if 'runtime_keep_awake' in text:
        raise ValueError('Unrecognized cached eMMC keep-awake policy')

    marker = 'Shared eMMC policy: preserve FUA durability'
    if marker not in text:
        anchor = '\tsprd_host = TO_SPRD_HOST(host);\n\tsdhci_sprd_phy_param_parse(sprd_host, pdev->dev.of_node);'
        if text.count(anchor) != 1:
            raise ValueError('eMMC host policy anchor changed')
        text = text.replace(anchor, '''\tsprd_host = TO_SPRD_HOST(host);
\t/* Shared eMMC policy: preserve FUA durability through flush emulation.
\t * Runtime PM, aggressive PM and CLK_AUTO retain their normal behavior. */
\tif (!mmc_card_is_removable(host->mmc) &&
\t    !(host->mmc->caps2 & MMC_CAP2_NO_MMC) &&
\t    of_property_match_string(pdev->dev.of_node, "sprd,name", "sdio_wlan") < 0 &&
\t    of_property_match_string(pdev->dev.of_node, "sprd,name", "sdio_sd") < 0)
\t\thost->mmc->caps2 |= MMC_CAP2_NO_REL_WR;
\tsdhci_sprd_phy_param_parse(sprd_host, pdev->dev.of_node);''', 1)
    path.write_text(text)

    path = kernel / 'drivers/mmc/core/mmc.c'
    text = path.read_text()
    # _mmc_suspend serves both runtime and system callbacks. The old guard
    # would still block aggressive runtime sleep even without pm_forbid.
    text = text.replace('''
\t/* Shared eMMC policy: system suspend preserves powered card and state.
\t * The cache flush above remains mandatory; do not mark it suspended. */
\tif (pm_type == MMC_POWEROFF_SUSPEND && !mmc_card_is_removable(host))
\t\tgoto out;
''', '')
    marker = 'Shared eMMC policy: system-only power retention'
    if marker not in text:
        start = text.index('static int mmc_suspend(struct mmc_host *host)')
        end = text.index('\n}', start)
        body = text[start:end]
        anchor = '\terr = _mmc_suspend(host, MMC_POWEROFF_SUSPEND);'
        if body.count(anchor) != 1:
            raise ValueError('MMC system suspend anchor changed')
        body = body.replace(anchor, '''\t/* Shared eMMC policy: system-only power retention. Runtime suspend
\t * still uses _mmc_suspend unchanged; an already suspended card stays
\t * suspended and will be restored by its normal runtime resume. */
\tif (!mmc_card_is_removable(host)) {
\t\tmmc_claim_host(host);
\t\terr = mmc_card_suspended(host->card) ? 0 : _mmc_flush_cache(host);
\t\tmmc_release_host(host);
\t} else {
\t\terr = _mmc_suspend(host, MMC_POWEROFF_SUSPEND);
\t}''', 1)
        text = text[:start] + body + text[end:]
    path.write_text(text)


if __name__ == '__main__':
    import sys
    apply(sys.argv[1])
