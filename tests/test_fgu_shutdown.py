"""Compile the actual shutdown callback against a live-counter/retention model."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PATCH=ROOT/'upstream/patches/0017-power-sc27xx-retain-live-soc-before-reset.patch'

@unittest.skipUnless(shutil.which('cc'),'requires C compiler')
class ShutdownCapacity(unittest.TestCase):
    def test_live_soc_is_saved_and_errors_do_not_write_stale_state(self):
        added='\n'.join(line[1:] for line in PATCH.read_text().splitlines() if line.startswith('+') and not line.startswith('+++'))
        start=added.index('static void sc27xx_fgu_shutdown(');pos=added.index('{',start);depth=1;end=pos+1
        while depth:
            depth+=(added[end]=='{')-(added[end]=='}');end+=1
        function=added[start:end]
        before=r"""
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
static int ump9620_info,other;
struct sc27xx_fgu_data { const void *var; bool bat_present; int lock; void *dev; };
struct platform_device { struct sc27xx_fgu_data *data; };
#define SC27XX_FGU_NORMAIL_POWERTON 5
static int held,read_error,save_error,mode_error,reads,saves,modes,warnings,fresh,saved;
static struct sc27xx_fgu_data *platform_get_drvdata(struct platform_device *p){return p->data;}
static void mutex_lock(int *p){(void)p;assert(!held);held=1;}
static void mutex_unlock(int *p){(void)p;assert(held);held=0;}
static int sc27xx_fgu_get_capacity(struct sc27xx_fgu_data *d,int *v){(void)d;assert(held);reads++;*v=fresh;return read_error;}
static int sc27xx_fgu_save_last_cap(struct sc27xx_fgu_data *d,int v){(void)d;assert(held);saves++;if(!save_error)saved=v;return save_error;}
static int sc27xx_fgu_save_boot_mode(struct sc27xx_fgu_data *d,int v){(void)d;assert(held&&v==5);modes++;return mode_error;}
#define dev_warn(...) do {warnings++;} while(0)
"""
        after=r"""
static void reset(void){held=reads=saves=modes=warnings=read_error=save_error=mode_error=0;fresh=76;saved=18;}
int main(void){
 struct sc27xx_fgu_data d={.var=&ump9620_info,.bat_present=true};struct platform_device p={.data=&d};
 reset();sc27xx_fgu_shutdown(&p);assert(saved==76&&reads==1&&saves==1&&modes==1&&!held&&!warnings);
 reset();read_error=-5;sc27xx_fgu_shutdown(&p);assert(saved==18&&reads==1&&!saves&&!modes&&!held&&warnings==1);
 reset();save_error=-5;sc27xx_fgu_shutdown(&p);assert(saved==18&&saves==1&&!modes&&!held&&warnings==1);
 reset();mode_error=-5;sc27xx_fgu_shutdown(&p);assert(saved==76&&modes==1&&!held&&warnings==1);
 reset();d.bat_present=false;sc27xx_fgu_shutdown(&p);assert(!reads&&!saves&&!modes&&!held);
 reset();d.bat_present=true;d.var=&other;sc27xx_fgu_shutdown(&p);assert(!reads&&!saves&&!modes&&!held);
 puts("PASS: live SOC, retention errors and battery/PMIC gating");return 0;
}
"""
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'test.c';binary=Path(tmp)/'test';source.write_text(before+function+after)
            subprocess.run(['cc','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)],check=True,capture_output=True)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
