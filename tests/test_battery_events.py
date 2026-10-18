"""Compile real UMP9620 IRQ helper; no device, register or poweroff access."""
from pathlib import Path
import subprocess
import sys
import tempfile

kernel = Path(sys.argv[1])
source = (kernel/'drivers/power/supply/sc27xx_fuel_gauge.c').read_text()
start = source.index('static int ump9620_fgu_enable_events(')
a = source.index('{', start)
b, depth = a+1, 1
while depth:
    depth += (source[b] == '{') - (source[b] == '}')
    b += 1
function = source[start:b]
model = r'''
#include <assert.h>
#include <errno.h>
static int ump9620_info, other_info, writes, failure, last_value;
#define SC27XX_FGU_INT_EN 0x14
#define SC27XX_FGU_LOW_OVERLOAD_INT 1
#define SC27XX_FGU_CLBCNT_DELTA_INT 4
struct sc27xx_fgu_data {void *var; int regmap,base,bat_present;};
static int regmap_update_bits(int map,int address,int mask,int value)
{ assert(map==7 && address==0x114 && mask==5); last_value=value; writes++; return failure; }
'''
tests = r'''
int main(void) {
 struct sc27xx_fgu_data data={.var=&other_info,.regmap=7,.base=0x100,.bat_present=1};
 assert(!ump9620_fgu_enable_events(&data)); assert(writes==0);
 data.var=&ump9620_info;
 assert(!ump9620_fgu_enable_events(&data)); assert(writes==1 && last_value==5);
 failure=-EIO; assert(ump9620_fgu_enable_events(&data)==-EIO); assert(writes==2);
 failure=0; data.bat_present=0; assert(!ump9620_fgu_enable_events(&data)); assert(writes==3 && last_value==0);
 data.bat_present=1; assert(!ump9620_fgu_enable_events(&data)); assert(writes==4 && last_value==5);
}
'''
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    (path/'events.c').write_text(model+function+tests)
    subprocess.run(['cc','-Wall','-Werror',str(path/'events.c'),'-o',str(path/'events')], check=True)
    subprocess.run([str(path/'events')], check=True)
probe = source[source.index('static int sc27xx_fgu_probe('):source.index('#ifdef CONFIG_PM_SLEEP')]
assert probe.index('!ump9620_has_battery_policy()') < probe.index('devm_request_threaded_irq')
assert probe.rindex('ump9620_fgu_enable_events(data)') > probe.rindex('devm_request_threaded_irq')
resume = source[source.index('static int sc27xx_fgu_resume('):source.index('static int sc27xx_fgu_suspend(')]
assert resume.index('return ump9620_fgu_enable_events(data)') < resume.index('ret = regmap_update_bits(')
assert 'sc27xx_fgu_cap_to_clbcnt(data, 1)' in source
detect = source[source.index('static irqreturn_t sc27xx_fgu_bat_detection'):source.index('static int sc27xx_fgu_calibration')]
assert detect.index('data->bat_present = !!state') < detect.index('ump9620_fgu_enable_events(data)')
print('PASS: actual FGU helper, non-UMP isolation, I/O failure, IRQ registration order, resume and existing 1% delta')
