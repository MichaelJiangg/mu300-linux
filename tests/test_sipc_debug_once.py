"""Global SIPC debug classes must be initialized once per module, not per CPU."""
from pathlib import Path
import shutil,subprocess,tempfile,unittest

TOP=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('cc'),'requires C compiler')
class SipcDebug(unittest.TestCase):
    def test_multiple_remote_processors_and_failed_registration(self):
        text=(TOP/'upstream/modules/sprd_modem/sipc/sipc.c').read_text()
        def function(name):
            pos=text.index(name+'(');a=text.rfind('static ',0,pos);b=text.index('\n}',pos)+2
            return text[a:b]
        probe=function('sprd_ipc_probe')
        self.assertNotIn('_init_debug();',probe)
        before=r'''
#include <assert.h>
#define __init
#define __exit
#define CONFIG_DEBUG_FS 1
#define CONFIG_SPRD_SIPC 1
#define IS_ENABLED(x) (x)
static int sprd_ipc_driver,panic_notifier_list,senddie_panic_nb;
static int wake,notifier,debug[4],probes,register_error;
static void smsg_init_wakeup(void){wake++;}
static void smsg_remove_wakeup(void){wake--;}
static void smsg_init_channel2index(void){}
static void atomic_notifier_chain_register(int*a,int*b){notifier++;}
static void atomic_notifier_chain_unregister(int*a,int*b){notifier--;}
static int platform_driver_register(int*p){if(!register_error)probes+=4;return register_error;}
static void platform_driver_unregister(int*p){}
static void smem_init_debug(void){assert(!debug[0]);debug[0]++;}
static void smsg_init_debug(void){assert(!debug[1]);debug[1]++;}
static void sbuf_init_debug(void){assert(!debug[2]);debug[2]++;}
static void sblock_init_debug(void){assert(!debug[3]);debug[3]++;}
static void smem_destroy_debug(void){debug[0]--;}
static void smsg_destroy_debug(void){debug[1]--;}
static void sbuf_destroy_debug(void){debug[2]--;}
static void sblock_destroy_debug(void){debug[3]--;}
'''
        after=r'''
int main(void){assert(!sprd_ipc_init());assert(probes==4&&wake==1&&notifier==1);
for(int i=0;i<4;i++)assert(debug[i]==1);
sprd_ipc_exit();assert(!wake&&!notifier);for(int i=0;i<4;i++)assert(!debug[i]);
register_error=-5;assert(sprd_ipc_init()==-5);assert(!wake&&!notifier);
for(int i=0;i<4;i++)assert(!debug[i]);return 0;}
'''
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'test.c').write_text(before+function('sprd_ipc_init')+function('sprd_ipc_exit')+after)
            subprocess.run(['cc','-Wall','-Werror',str(p/'test.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)
