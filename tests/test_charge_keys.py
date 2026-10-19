"""Native tests of the production charger event wait using pipes, never evdev."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

TOP=Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name=='posix' and shutil.which('gcc'), 'native POSIX gcc required')
class ChargerKeys(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='charge-keys-')
        cls.path=Path(cls.temp.name)
        cls.addClassCleanup(cls.temp.cleanup)
        source=cls.path/'test.c'
        source.write_text(r'''
#define main keys_program
#include "mu300-keys.c"
#undef main
#include <signal.h>
#include <sys/wait.h>
static void key(int fd, int code, int value) {
    struct input_event e={.type=EV_KEY,.code=code,.value=value};
    if(write(fd,&e,sizeof(e))!=sizeof(e)) _exit(9);
}
int main(int argc, char **argv) {
    (void)argc;
    char event[]="change@/devices/test\0SUBSYSTEM=power_supply\0ONLINE=0\0";
    if(!charge_event(event,sizeof(event)) || charge_event("SUBSYSTEM=power_supply",22) ||
       charge_event("SUBSYSTEM=usb\0",14)) return 9;
    int p[2];if(pipe(p)) return 9;
    pid_t child=fork();if(child<0) return 9;
    if(!child) {
        usleep(20000);
        if(!strcmp(argv[2],"short")) {
            key(p[1],KEY_POWER,1);usleep(20000);key(p[1],KEY_POWER,0);
            usleep(140000);key(p[1],KEY_POWER,1);
        } else if(!strcmp(argv[2],"other")) {
            key(p[1],KEY_HELP,1);usleep(180000);key(p[1],KEY_POWER,1);
        } else if(!strcmp(argv[2],"power")) key(p[1],KEY_POWER,1);
        sleep(3);_exit(0);
    }
    struct pollfd fd={.fd=p[0],.events=POLLIN};
    int result=charge_wait(&fd,1,-1,argv[1],80);
    kill(child,SIGTERM);waitpid(child,NULL,0);close(p[0]);close(p[1]);
    return result;
}
''')
        cls.binary=cls.path/'test'
        subprocess.run(['gcc','-Wall','-Wextra','-Werror','-O2','-I',str(TOP/'tools/keys'),
                        str(source),'-o',str(cls.binary)],check=True,capture_output=True)

    def wait(self,value,mode):
        path=self.path/'online';path.write_text(value)
        import time
        start=time.monotonic()
        r=subprocess.run([str(self.binary),str(path),mode],timeout=2)
        return r.returncode,time.monotonic()-start

    def test_long_power_starts(self):
        code,elapsed=self.wait('1\n','power')
        self.assertEqual(code,0);self.assertLess(elapsed,1)

    def test_short_power_and_wifi_key_do_not_start(self):
        for mode in ('short','other'):
            code,elapsed=self.wait('1\n',mode)
            self.assertEqual(code,0);self.assertGreater(elapsed,.23)

    def test_unplug_debounced_and_invalid_supply_fails_open(self):
        code,elapsed=self.wait('0\n','idle')
        self.assertEqual(code,3);self.assertGreaterEqual(elapsed,.49)
        self.assertEqual(self.wait('invalid\n','idle')[0],1)
