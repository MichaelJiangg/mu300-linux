#!/usr/bin/env python3
"""Compile the actual SDHCI MMIO callbacks and check their DMA/API contract.

Run on Linux with a prepared kernel tree; temporary copies are patched, never the
supplied tree. Also exercises upgrade from cached relaxed accessors and idempotence.
"""
from pathlib import Path
import argparse, re, runpy, shutil, subprocess, tempfile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('kernel',type=Path)
parser.add_argument('--adapter',type=Path,default=Path(__file__).resolve().parents[1]/'upstream/port/emmc.py')
parser.add_argument('--legacy-patch',type=Path,help='exercise the vendor 5.4 patch instead of the mainline adapter')
args=parser.parse_args()
if args.legacy_patch:
 def apply(root):
  patch=str(args.legacy_patch.resolve())
  cmd=['patch','--batch','--force','--fuzz=0','-p1','-d',str(root),'-i',patch]
  if subprocess.run(cmd+['--reverse','--dry-run'],capture_output=True).returncode==0:return
  subprocess.run(cmd+['--forward','--dry-run'],check=True,capture_output=True)
  subprocess.run(cmd+['--forward'],check=True,capture_output=True)
else:
 apply=runpy.run_path(str(args.adapter))['apply']
paths=['include/linux/mmc/host.h','drivers/mmc/core/block.c',
       'drivers/mmc/core/mmc.c','drivers/mmc/host/sdhci-sprd.c']
with tempfile.TemporaryDirectory(prefix='mmc-dma-contract-') as tmp:
 root=Path(tmp)
 for name in paths:
  dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(args.kernel/name,dest)
 apply(root)
 before={name:(root/name).read_bytes() for name in paths};apply(root)
 assert before=={name:(root/name).read_bytes() for name in paths},'adapter is not idempotent'
 source=(root/paths[-1]).read_text()
 a=source.index('static inline u32 sdhci_sprd_readl(');b=source.index('static inline void sdhci_sprd_sd_clk_off(',a)
 callbacks=source[a:b]
 # A reused build tree must receive the fix too, not just fresh checkouts.
 old=callbacks.replace('\t/* Shared SDHCI policy: order ADMA descriptors and DMA completion. */\n','')
 old=old.replace('return readl(', 'return readl_relaxed(')
 for width in ('b','w','l'):old=re.sub(r'\bwrite'+width+r'\(', 'write'+width+'_relaxed(',old)
 (root/paths[-1]).write_text(source[:a]+old+source[b:]);apply(root)
 repaired=(root/paths[-1]).read_text()
 assert 'return readl(host->ioaddr + reg);' in repaired
 a=repaired.index('static inline u32 sdhci_sprd_readl(');b=repaired.index('static inline void sdhci_sprd_sd_clk_off(',a)
 callbacks=repaired[a:b]
 prelude=r'''
#include <stdint.h>
#include <assert.h>
#include <string.h>
typedef uint32_t u32; typedef uint16_t u16; typedef uint8_t u8; typedef uint64_t u64;
#define unlikely(x) (x)
#define SDHCI_MAX_CURRENT 0x48
#define SDHCI_SPRD_MAX_CUR 0xffffff
#define SDHCI_SIGNAL_ENABLE 0x38
#define SDHCI_INT_ENABLE 0x34
#define SDHCI_SPRD_INT_SIGNAL_MASK 0x027f000b
#define SDHCI_BLOCK_COUNT 0x06
#define SDHCI_SOFTWARE_RESET 0x2f
#define SDHCI_HW_RESET_CARD 0x08
#define SDHCI_COMMAND 0x0e
#define SDHCI_INT_STATUS 0x30
#define SDHCI_INT_TIMEOUT 0x10000
#define SDHCI_INT_DATA_TIMEOUT 0x100000
#define SDHCI_INT_DATA_END_BIT 0x400000
#define SDHCI_INT_DATA_END 0x02
#define SDHCI_INT_CMD_MASK 0x10001
#define SDHCI_RESET_DATA 0x04
#define cpu_relax() ((void)0)
static int writes, ordered_write, ordered_read;
struct mmc_data { int error; };
struct sdhci_sprd_host { u32 int_status; struct mmc_data *data; };
struct sdhci_host { unsigned char *ioaddr; void *cmd; struct sdhci_sprd_host *sprd; };
#define TO_SPRD_HOST(host) ((host)->sprd)
static u32 load(void *p,int n,int ordered){u32 v=0;memcpy(&v,p,n);ordered_read+=ordered;return v;}
static void store(u32 v,void *p,int n,int ordered){memcpy(p,&v,n);writes++;ordered_write+=ordered;}
#define readl(p) load(p,4,1)
#define readl_relaxed(p) load(p,4,0)
#define readb_relaxed(p) load(p,1,0)
#define writel(v,p) store(v,p,4,1)
#define writew(v,p) store(v,p,2,1)
#define writeb(v,p) store(v,p,1,1)
#define writel_relaxed(v,p) store(v,p,4,0)
#define writew_relaxed(v,p) store(v,p,2,0)
#define writeb_relaxed(v,p) store(v,p,1,0)
'''
 cases=r'''
int main(void){
 unsigned char regs[256]={0};struct sdhci_sprd_host sprd={0};
 struct sdhci_host h={.ioaddr=regs,.sprd=&sprd};
 assert(sdhci_sprd_readl(&h,SDHCI_MAX_CURRENT)==SDHCI_SPRD_MAX_CUR);
 assert(!ordered_read);
 sdhci_sprd_writel(&h,123,SDHCI_MAX_CURRENT);assert(!writes);
 sdhci_sprd_writew(&h,123,SDHCI_BLOCK_COUNT);assert(!writes);
 sdhci_sprd_writel(&h,0xffffffff,SDHCI_INT_ENABLE);
 assert(load(regs+SDHCI_INT_ENABLE,4,0)==SDHCI_SPRD_INT_SIGNAL_MASK);
 assert(ordered_write==1);
 sdhci_sprd_writew(&h,0x193a,SDHCI_COMMAND);
 assert(load(regs+SDHCI_COMMAND,2,0)==0x193a && ordered_write==2);
 sdhci_sprd_readl(&h,SDHCI_INT_STATUS);assert(ordered_read==1);
 regs[SDHCI_SOFTWARE_RESET]=SDHCI_HW_RESET_CARD;
 sdhci_sprd_writeb(&h,1,SDHCI_SOFTWARE_RESET);
 assert(regs[SDHCI_SOFTWARE_RESET]==9 && ordered_write==3);
 return 0;
}
'''
 c=root/'contract.c';c.write_text(prelude+callbacks+cases)
 exe=root/'contract';subprocess.run(['cc','-Wall','-Werror','-O2',str(c),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
 # Missing anchors must fail closed rather than publish a partially fixed tree.
 broken=(root/paths[-1]).read_text().replace('return readl(host->ioaddr + reg);','return readl_relaxed(host->ioaddr + reg);')
 (root/paths[-1]).write_text(broken)
 try:apply(root)
 except (ValueError,subprocess.CalledProcessError):pass
 else:raise AssertionError('partially modified callbacks accepted')
print('PASS: ordered DMA submission/completion, reserved registers, IRQ mask, reset bit, cached upgrade, idempotence and fail-closed checks')
