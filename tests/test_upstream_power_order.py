"""Compile the real callbacks: runtime PM precedes thread startup, WDT stops only for system sleep."""
from pathlib import Path
import shutil, subprocess, tempfile, unittest
from helpers import TOP


def function(source, name):
    start=source.index(name+'(')
    start=source.rfind('\n',0,start)+1
    pos=source.index('{',start);end=pos+1;depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]


@unittest.skipUnless(shutil.which('cc'),'C compiler required')
class PowerOrder(unittest.TestCase):
    def compile_run(self, source):
        with tempfile.TemporaryDirectory() as path:
            p=Path(path);(p/'test.c').write_text(source)
            subprocess.run(['cc','-Wall','-Werror','-Wno-unused-function',str(p/'test.c'),'-o',str(p/'test')],check=True,capture_output=True)
            subprocess.run([str(p/'test')],check=True)

    def test_watchdog_suspend_resume_and_read_error(self):
        source=(TOP/'upstream/port/drivers/watchdog/ump9620-pmic-wdt.c').read_text()
        stub=r'''
#include <assert.h>
#include <stdbool.h>
typedef unsigned int u32;
#define WDT_CTRL 8
#define WDT_CNT_EN 2
struct ump9620_wdt { void *map; u32 base; bool suspended; struct { unsigned timeout; } wdd; };
struct device { struct ump9620_wdt *data; };
static unsigned ctrl, starts, stops, loads, read_error;
static void *dev_get_drvdata(struct device *d) { return d->data; }
static int regmap_read(void *m,unsigned r,u32 *v) { *v=ctrl; return read_error; }
static int ump9620_wdt_ctrl(struct ump9620_wdt *w,bool on) { if(on) starts++; else stops++; return 0; }
static int ump9620_wdt_load(struct ump9620_wdt *w,unsigned t) { assert(t==60); loads++; return 0; }
#define dev_warn(...) ((void)0)
'''
        self.compile_run(stub+function(source,'ump9620_wdt_suspend_noirq')+
                         function(source,'ump9620_wdt_resume_noirq')+r'''
int main(void) {
 struct ump9620_wdt w={.wdd={.timeout=60}};struct device d={&w};
 ctrl=0;assert(!ump9620_wdt_suspend_noirq(&d));assert(!ump9620_wdt_resume_noirq(&d));
 assert(!starts&&!stops&&!loads);
 ctrl=WDT_CNT_EN;assert(!ump9620_wdt_suspend_noirq(&d));assert(stops==1&&w.suspended);
 assert(!ump9620_wdt_resume_noirq(&d));assert(starts==1&&loads==1&&!w.suspended);
 assert(!ump9620_wdt_resume_noirq(&d));assert(starts==1);
 read_error=5;assert(ump9620_wdt_suspend_noirq(&d)==5);assert(stops==1);
 return 0;
}
''')

    def test_sipa_runtime_pm_is_ready_for_immediate_enable_and_failure_rolls_back(self):
        source=(TOP/'upstream/modules/sprd_modem/sipa_delegate/sipa_dele_cp_in_ap.c').read_text()
        stub=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#define GFP_KERNEL 0
#define ENOMEM 12
#define EINPROGRESS 115
#define SIPA_RM_RES_CONS_WIFI_UL 1
#define SIPA_RM_RES_CONS_WIFI_DL 2
#define kzalloc(n,f) calloc(1,n)
struct sipa_delegator_create_params { void *pdev; };
struct delegate { void *pdev; void (*on_cmd)(void); void (*local_request_prod)(void);
 bool pd_eb_flag,pd_get_flag; int smsg_cnt,prod_id; };
struct wrapper { struct delegate delegator; };
static struct wrapper *s_cp_delegator;
static int enabled, starts, failure, init_failure;
static void cp_dele_on_commad(void) {}
static void cp_dele_local_req_r_prod(void) {}
static int sipa_delegator_init(struct delegate *d,struct sipa_delegator_create_params *p) { d->pdev=p->pdev;return init_failure; }
static void pm_runtime_enable(void *p) { assert(!enabled);enabled=1; }
static void pm_runtime_disable(void *p) { assert(enabled);enabled=0; }
static int sipa_delegator_start(struct delegate *d) { assert(enabled);starts++;return failure; }
static int sipa_rm_add_dependency(int a,int b) { return 0; }
static void sipa_dele_init_sysfs(struct wrapper *w) {}
#define dev_warn(...) ((void)0)
'''
        self.compile_run(stub+function(source,'cp_delegator_init')+r'''
int main(void) {
 struct sipa_delegator_create_params p={0};
 assert(!cp_delegator_init(&p));assert(enabled&&starts==1);free(s_cp_delegator);
 enabled=0;failure=-5;assert(cp_delegator_init(&p)==-5);assert(!enabled&&starts==2);free(s_cp_delegator);
 init_failure=-6;assert(cp_delegator_init(&p)==-6);assert(!enabled&&starts==2);free(s_cp_delegator);
 return 0;
}
''')
