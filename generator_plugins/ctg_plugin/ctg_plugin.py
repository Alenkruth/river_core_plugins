# See LICENSE for details

import os
import sys
import pluggy
import shutil
import subprocess
import random
import re
import datetime
import pytest
import glob
import re
import configparser

from river_core.log import logger
import river_core.utils as utils
from river_core.constants import *
import riscof

gen_hookimpl = pluggy.HookimplMarker("generator")

this = os.path.abspath(os.path.dirname(__file__))
class ctg_plugin(object):
    @gen_hookimpl
    def pre_gen(self, spec_config, output_dir):
        '''
            Spec Config Fields and their meanings.
            jobs: number of parallel processes to spawn for ctg
            isa: The isa for the tests. The key should exist in the ctg configuration file.
            ctg_gen_config: A yaml file where the nodes are accessed using the isa and the node supplies details pertaining to base isa and cgf files for CTG.
            riscof_config: config file for riscof
            randomize: Specify the SAT solver to use in ctg.
        '''
        logger.debug("RISCV-CTG Pre Gen.")
        self.name = 'ctg'
        output_dir = os.path.abspath(output_dir)
        if (os.path.isdir(output_dir)):
            logger.debug('Output Directory exists. Removing Contents.')
            shutil.rmtree(output_dir, ignore_errors=True)
        os.makedirs(output_dir)
        self.jobs = int(spec_config['jobs'])
        self.randomize = bool(spec_config['randomize'])
        self.isa = str(spec_config['test_cfg'])
        self.gen_config = os.path.abspath(spec_config['ctg_gen_config'])
        self.config_file = os.path.abspath(spec_config['riscof_config'])

    @gen_hookimpl
    def gen(self, module_dir, output_dir):
        riscof_config = configparser.ConfigParser()
        riscof_config.read(self.config_file)
        output_dir = os.path.abspath(output_dir)
        logger.debug("CTG Gen phase.")
        asm_path = os.path.join(output_dir,"ctg/")
        pytest_file = os.path.join(this,'gen_framework.py')
        os.makedirs(asm_path, exist_ok=True)
        # ctg("debug",os.path.join(output_dir,asm_path), self.randomize, self.xlen, self.cgf_files, self.jobs, self.base_isa)
        # ctg_command = 'riscv_ctg -v info -bi {0} -d {1} -p {2}'.format(self.base_isa, asm_path, self.jobs)+('' if not self.randomize else ' -r ') + '-cf ' + ' -cf '.join(self.cgf_files)
        # shellCommand(ctg_command).run(cwd=os.path.join(output_dir,"ctg/"))
        report_file_name = '{0}/{1}_{2}'.format(
            os.path.join(output_dir,".json/"), self.name,
            datetime.datetime.now().strftime("%Y%m%d-%H%M"))
        pytest.main([
            pytest_file, '-n=1',
            '--configfile={0}'.format(self.config_file), '-v',
            '--isa={0}'.format(self.isa), '--jobs={0}'.format(self.jobs),
            '--html={0}/reports/ctg.html'.format(output_dir),
            '--report-log={0}.json'.format(report_file_name),
            '--self-contained-html', '--output_dir={0}'.format(asm_path),
            '--module_dir={0}'.format(this),('' if not self.randomize else '--randomize')
        ])
        work_dir = os.path.join(output_dir,"ctg/riscof_work/")
        includes = os.path.dirname(riscof.__file__)+'/suite/env'
        model_include = riscof_config['RISCOF']['DUTPluginPath']+'/env/'
#        riscof_command = "riscof testlist --config {0} ".format(self.config_file)
#        logger.debug('Running ' + str(riscof_command))
#        utils.shellCommand(riscof_command).run(cwd=os.path.join(output_dir,"ctg/"))
        riscof_test_list = utils.load_yaml(os.path.join(work_dir,"test_list.yaml"))
        if len(riscof_test_list) == 0:
            logger.error('No tests selected by RISCOF')
            raise SystemExit
        test_list = {}
        for entry in riscof_test_list.keys():
            key = os.path.basename(entry)[:-2]
            new_entry = {}
            if '64' in riscof_test_list[entry]["isa"].lower():
                mabi_str = 'lp64'
            elif 'd' not in riscof_test_list[entry]["isa"].lower():
                mabi_str = 'ilp32'
            new_entry["isa"] = riscof_test_list[entry]["isa"]
            new_entry['work_dir'] = riscof_test_list[entry]['work_dir']
            new_entry['asm_file'] = riscof_test_list[entry]['test_path']
            new_entry['generator'] = self.name
            new_entry['include'] = [includes, model_include]
            new_entry['cc'] = 'riscv64-unknown-elf-gcc'
            new_entry['result'] = "Unavailable"
            new_entry['cc_args'] = ' -mcmodel=medany -static -std=gnu99 -O2 -fno-common -fno-builtin-printf -fvisibility=hidden '
            new_entry['linker_args'] = '-static -nostdlib -nostartfiles -lm -lgcc -T'
            new_entry['linker_file'] = riscof_config['RISCOF']['DUTPluginPath']+'/env/link.ld'
            new_entry['mabi'] = mabi_str
            new_entry['compile_macros'] = riscof_test_list[entry]['macros']
            new_entry['extra_compile'] = []
            new_entry['march'] = new_entry['isa'].lower()
            test_list[key] = new_entry
        return test_list

    @gen_hookimpl
    def post_gen(self, output_dir):
        pass
