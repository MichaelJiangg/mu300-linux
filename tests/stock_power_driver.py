"""Compile actual UMP9620 helpers: python3 tests/stock_power_driver.py KERNEL."""
from pathlib import Path
import re, subprocess, sys, tempfile

top=Path(__file__).resolve().parents[1]
kernel=Path(sys.argv[1])
source=(kernel/'drivers/power/supply/sc27xx_fuel_gauge.c').read_text()


def function(name):
    m=re.search(r'(?m)^static (?:int|bool) '+name+r'\([^;{}]*\)\s*\{',source)
    assert m,name
    a=source.index('{',m.start());b=a+1;depth=1
    while depth:depth+=(source[b]=='{')-(source[b]=='}');b+=1
    return source[m.start():b]+'\n'


model=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
typedef uint32_t u32;
#define UMP9620_FGU_CAP_INTEGER_MASK 255
#define UMP9620_FGU_CAP_DECIMAL_MASK 0xf00
#define UMP9620_FGU_CAP_DECIMAL_SHIFT 8
#define SC27XX_FGU_CAP_AREA_MASK 0xfff
#define SC27XX_FGU_USER_AREA_STATUS 0xa8
#define SC27XX_FGU_NORMAIL_POWERTON 5
#define DIV_ROUND_CLOSEST(x,y) (((x)+(y)/2)/(y))
#define DIV_ROUND_UP(x,y) (((x)+(y)-1)/(y))
#define dev_info(...) ((void)0)
struct sc27xx_fgu_data {int regmap,base,saved_cap,boot_volt,cap_table,table_len,dev;u32 full_voltage_uv,full_current_ua;};
static unsigned raw;static int io_error,ocv_reads,saves,voltage_mv=4200,current_ma;
static int regmap_read(int map,int reg,int*value){*value=raw;return io_error;}
static int sc27xx_fgu_get_vbat_ocv(struct sc27xx_fgu_data*d,int*v){ocv_reads++;*v=3900000;return io_error;}
static int power_supply_ocv2cap_simple(int table,int len,int ocv){return 52;}
static int sc27xx_fgu_save_last_cap(struct sc27xx_fgu_data*d,int cap){saves++;return 0;}
static int sc27xx_fgu_save_boot_mode(struct sc27xx_fgu_data*d,int mode){assert(mode==5);return 0;}
static int sc27xx_fgu_get_vbat_vol(struct sc27xx_fgu_data*d,int*v){*v=voltage_mv;return io_error;}
static int sc27xx_fgu_get_current(struct sc27xx_fgu_data*d,int*v){*v=current_ma;return io_error;}
'''
tests=r'''
int main(void){
 struct sc27xx_fgu_data d={0};int cap;
 for(raw=0;raw<4096;raw++){
  unsigned whole=raw&255,tenths=raw>>8;bool valid=whole<=100&&tenths<=9&&!(whole==100&&tenths);
  ocv_reads=saves=0;assert(!ump9620_fgu_get_boot_capacity(&d,&cap));
  if(valid){assert(cap==(int)((whole*10+tenths+5)/10));assert(!ocv_reads&&!saves);}
  else assert(cap==52&&ocv_reads==1&&saves==1);
 }
 raw=580;ocv_reads=0;assert(!ump9620_fgu_get_boot_capacity(&d,&cap));assert(cap==68&&!ocv_reads);
 io_error=-EIO;assert(ump9620_fgu_get_boot_capacity(&d,&cap)==-EIO);io_error=0;
 assert(!ump9620_fgu_full_qualified(&d));d.full_voltage_uv=4200000;d.full_current_ua=120000;
 voltage_mv=4141;assert(!ump9620_fgu_full_qualified(&d));voltage_mv=4200;assert(ump9620_fgu_full_qualified(&d));
 current_ma=121;assert(!ump9620_fgu_full_qualified(&d));current_ma=-1;assert(!ump9620_fgu_full_qualified(&d));
 current_ma=120;assert(ump9620_fgu_full_qualified(&d));io_error=-EIO;assert(!ump9620_fgu_full_qualified(&d));return 0;
}
'''
header=(top/'upstream/port/include/linux/power/ump9620-battery.h').read_text().replace('#include <linux/of.h>','')
of_model=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
struct device_node {bool enabled;};
static struct device_node policy;static bool exists;static int gets,puts;
static struct device_node *of_find_node_by_path(const char*p){assert(!strcmp(p,"/charger_policy_service"));gets++;return exists?&policy:NULL;}
static bool of_device_is_available(struct device_node*p){return p->enabled;}
static void of_node_put(struct device_node*p){if(p)puts++;}
'''
of_tests=r'''
int main(void){assert(!ump9620_has_battery_policy());assert(gets==1&&puts==0);
exists=true;policy.enabled=false;assert(!ump9620_has_battery_policy());policy.enabled=true;
assert(ump9620_has_battery_policy());assert(gets==3&&puts==2);return 0;}
'''
with tempfile.TemporaryDirectory() as directory:
    p=Path(directory)
    for name,code in [('soc',model+function('ump9620_fgu_get_boot_capacity')+function('ump9620_fgu_full_qualified')+tests),('board',of_model+header+of_tests)]:
        (p/(name+'.c')).write_text(code)
        subprocess.run(['cc','-Wall','-Werror',str(p/(name+'.c')),'-o',str(p/name)],check=True)
        subprocess.run([str(p/name)],check=True)
assert 'regmap_write_bits(data->regmap,' not in source
for name,compat,access in [('sc27xx_fuel_gauge.c','sprd,ump9620-fgu','data = devm_kzalloc'),('bq256xx_charger.c','ti,bq2560x_chg','bq = devm_kzalloc')]:
    text=(kernel/'drivers/power/supply'/name).read_text();probe=text[text.index('static int '+('sc27xx_fgu_probe' if name.startswith('sc') else 'bq256xx_probe')):]
    assert probe.index('!ump9620_has_battery_policy()')<probe.index(access)
    assert f'of_device_is_compatible(dev->of_node, "{compat}")' in probe
pd=(top/'upstream/port/drivers/usb/typec/tcpm/sc27xx-ump9620.c').read_text();probe=pd[pd.index('static int sc27xx_probe'):]
assert probe.index('!ump9620_has_battery_policy()')<probe.index('sc27xx_cc_cal(')
print('PASS: all 4096 retained encodings, no valid-SOC migration, electrical full boundaries, I/O errors, battery-board isolation before hardware I/O')
