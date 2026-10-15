"""Execute the actual callbacks against independent USB/power-role models."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from helpers import ShellTest, BIN

ROOT=Path(__file__).resolve().parents[1]
DRIVER=ROOT/'upstream/port/drivers/usb/typec/tcpm/sc27xx-ump9620.c'

def function(text,name):
    start=re.search(r'^static [^\n]*\b'+name+r'\(',text,re.M).start()
    end=text.index('{',start)+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]+'\n'

@unittest.skipUnless(shutil.which('cc'),'requires C compiler')
class PDRoles(unittest.TestCase):
    def test_power_sink_can_be_usb_host_without_enabling_boost(self):
        text=DRIVER.read_text()
        before=r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
enum usb_role {USB_ROLE_NONE,USB_ROLE_HOST,USB_ROLE_DEVICE};
enum typec_role {TYPEC_SINK,TYPEC_SOURCE};
enum typec_data_role {TYPEC_DEVICE,TYPEC_HOST};
enum tcpm_transmit_status {TCPC_TX_SUCCESS,TCPC_TX_FAILED};
struct tcpc_dev {void *pd;};
struct sc27xx_pd {void *role_sw,*dev,*port;bool attached,tx_pending,pd_capable;enum typec_role power_role;};
#define SC27XX_PD_CFG0 16
#define SC27XX_PD_SRC_SINK_MODE 512
#define dev_info(...) ((void)0)
static int writes,usb_calls,power_value,usb_value,write_error,usb_error,tx_completions;
static struct sc27xx_pd *to_pd(struct tcpc_dev *dev){return dev->pd;}
static int pd_update(struct sc27xx_pd *pd,int reg,int mask,int val){(void)pd;assert(reg==16&&mask==512);writes++;power_value=val;return write_error;}
static int usb_role_switch_set_role(void *sw,enum usb_role role){(void)sw;usb_calls++;usb_value=role;return usb_error;}
static void tcpm_pd_transmit_complete(void *port,enum tcpm_transmit_status status){(void)port;(void)status;tx_completions++;}
'''
        after=r'''
int main(void){
 struct sc27xx_pd pd={0};struct tcpc_dev tcpc={.pd=&pd};
 assert(!sc27xx_set_roles(&tcpc,true,TYPEC_SINK,TYPEC_HOST));
 assert(usb_value==USB_ROLE_HOST&&!power_value&&pd.attached&&pd.power_role==TYPEC_SINK);
 assert(!sc27xx_set_roles(&tcpc,true,TYPEC_SOURCE,TYPEC_HOST));
 assert(usb_value==USB_ROLE_HOST&&power_value==512&&pd.power_role==TYPEC_SOURCE);
 assert(!sc27xx_set_roles(&tcpc,true,TYPEC_SINK,TYPEC_DEVICE));
 assert(usb_value==USB_ROLE_DEVICE&&!power_value);
 assert(!sc27xx_set_roles(&tcpc,false,TYPEC_SINK,TYPEC_HOST));
 assert(usb_value==USB_ROLE_DEVICE&&!pd.attached);
 write_error=-EIO;int calls=usb_calls;
 assert(sc27xx_set_roles(&tcpc,true,TYPEC_SOURCE,TYPEC_HOST)==-EIO&&usb_calls==calls&&!pd.attached);
 write_error=0;usb_error=-EIO;
 assert(sc27xx_set_roles(&tcpc,true,TYPEC_SOURCE,TYPEC_HOST)==-EIO&&!pd.attached);
 pd.tx_pending=true;sc27xx_complete_tx(&pd,TCPC_TX_SUCCESS);sc27xx_complete_tx(&pd,TCPC_TX_SUCCESS);
 assert(tx_completions==1&&!pd.tx_pending);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'roles.c';binary=Path(d)/'roles'
            source.write_text(before+function(text,'sc27xx_set_roles')+function(text,'sc27xx_complete_tx')+after)
            result=subprocess.run(['cc','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            subprocess.run([str(binary)],check=True)


    def test_receive_frame_trailer_is_not_a_second_pd_message(self):
        text=DRIVER.read_text()
        regs=(DRIVER.parent/'sc27xx-ump9620-regs.h').read_text().split('enum sc27xx_state')[0]
        before=r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
typedef uint32_t u32;typedef uint16_t u16;typedef int irqreturn_t;
#define BIT(n) (1U<<(n))
#define GENMASK(h,l) ((~0U<<(l))&(~0U>>(31-(h))))
#define cpu_to_le16(v) (v)
#define cpu_to_le32(v) (v)
#define pd_header_cnt_le(v) (((v)>>12)&7)
#define pd_header_type_le(v) ((v)&31)
#define PD_CTRL_GOOD_CRC 1
#define TCPC_TX_SOP 0
#define IRQ_HANDLED 1
#define dev_warn_ratelimited(...) ((void)0)
"""
        model=r"""
enum tcpm_transmit_status {TCPC_TX_SUCCESS,TCPC_TX_FAILED};
struct pd_message {u16 header;u32 payload[7];};
struct sc27xx_pd {void *regmap,*port,*dev;u32 base,typec_base;int lock;bool tx_pending,pd_capable;};
static u32 fifo[8],flags;static int at,held,flushes,messages,completions,hard_resets,read_error;static struct pd_message received;
static void mutex_lock(int *p){(void)p;assert(!held);held=1;}
static void mutex_unlock(int *p){(void)p;assert(held);held=0;}
static int regmap_read(void *map,u32 reg,u32 *value){(void)map;assert(held);if(reg==SC27XX_INT_FLG){*value=flags;return 0;}assert(reg==SC27XX_PD_RX_BUF);if(read_error)return -EIO;assert(at<8);*value=fifo[at++];return 0;}
static int regmap_write(void *map,u32 reg,u32 value){(void)map;(void)value;assert(held&&reg==SC27XX_INT_CLR);return 0;}
static int regmap_write_bits(void *map,u32 reg,u32 mask,u32 value){(void)map;assert(held&&reg==SC27XX_PD_CTRL);if(mask&SC27XX_PD_RX_FLASH){assert(value&SC27XX_PD_RX_FLASH);flushes++;}return 0;}
static int cc_update(struct sc27xx_pd *pd,u32 reg,u32 mask,u32 value){(void)pd;(void)reg;(void)mask;(void)value;return 0;}
static void tcpm_pd_receive(void *port,const struct pd_message *msg,int sop){(void)port;assert(sop==TCPC_TX_SOP);received=*msg;messages++;}
static void tcpm_pd_transmit_complete(void *port,enum tcpm_transmit_status status){(void)port;(void)status;completions++;}
static void tcpm_pd_hard_reset(void *port){(void)port;hard_resets++;}
"""
        after=r"""
int main(void){
 struct sc27xx_pd pd={0};
 flags=SC27XX_PD_PKG_RV_FLAG;fifo[0]=0x1161;fifo[1]=0x90c8;fifo[2]=0x2601;fifo[3]=0xc0d8;fifo[4]=0xb104;
 sc27xx_pd_irq(1,&pd);assert(messages==1&&at==3&&flushes==1&&received.header==0x1161&&received.payload[0]==0x260190c8&&!held);
 at=0;fifo[0]=PD_CTRL_GOOD_CRC;flags|=SC27XX_PD_TX_OK_FLAG;pd.tx_pending=true;
 sc27xx_pd_irq(1,&pd);assert(messages==1&&completions==1&&!pd.tx_pending&&at==1&&flushes==2&&!held);
 read_error=1;flags=SC27XX_PD_PKG_RV_FLAG;sc27xx_pd_irq(1,&pd);assert(messages==1&&completions==1&&flushes==3&&!held);
 flags=SC27XX_PD_HARD_RST_FLAG;sc27xx_pd_irq(1,&pd);assert(hard_resets==1&&!held);
 return 0;
}
"""
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'receive.c';binary=Path(d)/'receive'
            source.write_text(before+regs+model+function(text,'sc27xx_complete_tx')+function(text,'sc27xx_receive')+function(text,'sc27xx_pd_irq')+after)
            result=subprocess.run(['cc','-Wall','-Wextra','-Werror','-Wno-unused-parameter',str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            subprocess.run([str(binary)],check=True)


class NativeRoleHelper(ShellTest):
    def test_pd_data_role_requests_never_force_charger_registers(self):
        root=self.tmp/'root'
        port=root/'sys/class/typec/port0'
        port.mkdir(parents=True)
        (port/'data_role').write_text('device\n')
        (port/'power_role').write_text('sink\n')
        self.stub('mu300-device','echo u30air')
        self.stub('id','echo 0')
        self.stub('i2cget','echo unexpected >> "$STUBLOG/i2c"; exit 1')
        self.stub('i2cset','echo unexpected >> "$STUBLOG/i2c"; exit 1')
        for shell in self.each_shell():
            for mode in ('boot','host','device','status'):
                result=self.script(shell,BIN/'mu300-usb',mode,MU300_SYSROOT=root)
                self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((port/'power_role').read_text(),'sink\n')
            self.assertFalse((self.tmp/'i2c').exists())
