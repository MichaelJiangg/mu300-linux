"""Compile/execute the patch's real fallback function against fake MMC caps."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from helpers import TOP


class Timing(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc'),'C compiler required')
    def test_failed_mode_only_and_card_removal_preserves_capabilities(self):
        patch=(TOP/'upstream/patches/0021-mmc-failed-timing-falls-back.patch').read_text()
        code='\n'.join(line[1:] for line in patch.splitlines() if line.startswith(('+',' ')) and not line.startswith('+++'))
        start=code.index('static void mmc_timing_fallback(')
        function=code[start:code.index('\n}',start)+2]
        before=r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#define EXT_CSD_CARD_TYPE_HS400ES 1
#define EXT_CSD_CARD_TYPE_HS200 2
#define EXT_CSD_CARD_TYPE_HS400 4
#define EXT_CSD_CARD_TYPE_DDR_52 8
#define MMC_CAP2_HS400_ES 1
#define MMC_CAP2_HS200 6
#define MMC_CAP2_HS400 24
#define MMC_CAP_DDR 3
struct mmc_host {unsigned caps,caps2;};
struct mmc_card {struct mmc_host *host; unsigned mmc_avail_type; struct {unsigned raw_card_type;} ext_csd;};
static unsigned warnings; static const char *last_failed,*last_next;
static const char *mmc_hostname(struct mmc_host *h){(void)h;return "mmc0";}
#define pr_warn(fmt,name,failed,error,next) do {(void)(fmt);(void)(name);(void)(error);warnings++;last_failed=failed;last_next=next;} while(0)
'''
        after=r'''
int main(void) {
 struct mmc_host h={.caps=MMC_CAP_DDR,.caps2=31};
 struct mmc_card c={.host=&h,.mmc_avail_type=1|2|4|8,.ext_csd={.raw_card_type=2|8}};
 mmc_timing_fallback(&c,-ENOMEDIUM); assert(h.caps2==31&&h.caps==3&&!warnings);
 mmc_timing_fallback(&c,-EILSEQ); assert(h.caps2==6&&h.caps==3&&warnings==1);
 assert(!strcmp(last_failed,"HS400ES")&&!strcmp(last_next,"HS200"));
 c.mmc_avail_type=2|8; mmc_timing_fallback(&c,-EIO);
 assert(h.caps2==0&&h.caps==3&&warnings==2&&!strcmp(last_next,"HS/DDR52"));
 c.mmc_avail_type=8; mmc_timing_fallback(&c,-EILSEQ);
 assert(!h.caps&&!h.caps2&&warnings==3&&!strcmp(last_failed,"DDR52")&&!strcmp(last_next,"HS"));
 c.mmc_avail_type=0;mmc_timing_fallback(&c,-EIO);assert(warnings==3);
 h.caps=0;h.caps2=31;c.mmc_avail_type=1;c.ext_csd.raw_card_type=0;
 mmc_timing_fallback(&c,-EIO);assert(!strcmp(last_next,"HS"));
 puts("PASS: only failed timing removes capabilities, removal untouched, complete ladder and supported-card modes");
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'test.c';binary=Path(directory)/'test'
            source.write_text(before+function+after)
            subprocess.run(['cc','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)],check=True,capture_output=True)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
