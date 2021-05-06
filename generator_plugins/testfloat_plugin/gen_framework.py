# See LICENSE for details

import os
import sys
import pluggy
import shutil
from river_core.log import logger
import river_core.utils as utils
from river_core.constants import *
import random
import re
import datetime
import pytest
from envyaml import EnvYAML

# Output globals.
# This is done, because writing to file is complicated business
test_file = []
# Parameter list is a list designed to get all useful info while generating things from testfloat
# It is a nested list.
# Main = [Sub1, Sub2, Sub3]
# Sub1 = [Inst, Dest, Reg1, Reg2, Mode]
# Dest, Reg1, Reg2 are again a list of values to generate the addresses from
parameter_list = []
run_command = []
folder_dir = ''
# File_ctr is a variable to account for total number of test_cases
file_ctr = 0

# ASM Filter
header = '''#include "test.h"
#include "model.h"
.section .text.init
.globl rvtest_entry_point
rvtest_entry_point:

li t0, 0x00006000
csrs mstatus, t0

la x1, rvtest_data
'''

code_footer = '''rvtest_code_end:
RVMODEL_HALT'''


def inst_precision(inst):
    inst_prefix = ''
    if '.s' in inst:
        inst_prefix = 'f32'
    elif '.d' in inst:
        inst_prefix = 'f64'
    elif '.q' in inst:
        inst_prefix = 'f128'
    else:
        logger.error('Failed to get the proper precision')
    return inst_prefix


def inst_alignment(inst):
    inst_align = 0
    if '.s' in inst:
        inst_align = 4
    elif '.d' in inst:
        inst_align = 8
    # TODO Could be possibly wrong, can remove Q parts for now as well
    elif '.q' in inst:
        inst_align = 16
    else:
        logger.error('Failed to get the proper precision')
    return inst_align


def create_asm(gen_file):
    offset_mem = []
    work_dir = os.path.dirname(os.path.realpath(gen_file))
    local_folder_dir = folder_dir + '/testfloat_plugin/asm/'

    # copy stuff for asm
    logger.info('Copying Header files')
    shutil.copy(local_folder_dir + 'test.h',
                os.path.splitext(gen_file)[0] + '.h')
    shutil.copy(local_folder_dir + 'model.h',
                os.path.splitext(gen_file)[0] + '-model.h')
    shutil.copy(local_folder_dir + 'link.ld',
                os.path.splitext(gen_file)[0] + '.ld')

    # Parsing from parameters
    asm_inst = parameter_list[file_ctr][0]
    # TODO check if this needs to change
    # Can come from the inst as well
    # Create test.S
    # Clean up the file data
    with open(gen_file, 'r') as gen_file_data:
        logger.debug('Reading gen files')
        gen_data = gen_file_data.read().splitlines()
    # Add steps to write to file
    assembly_file = os.path.splitext(gen_file)[0] + '.S'
    with open(assembly_file, 'w+') as asm_file_pointer:
        logger.info('Generating in the ASM file')
        generation_header = "; ASM file generated by testfloat plugin at {0}, from testfloatgen command: \n; {1} \n".format(
            datetime.datetime.now(), run_command[file_ctr])
        asm_file_pointer.write(generation_header)
        asm_file_pointer.write(header)

        # Need to maintain an offset for the values
        offset_ctr = 0
        for case_index in range(0, len(gen_data)):
            # Get alignment values
            align = inst_alignment(asm_inst)
            # Move the selection here to ensure max variety in the tests cases
            dest = random.randint(int(parameter_list[file_ctr][1][0]),
                                  int(parameter_list[file_ctr][1][1]))
            dest_reg = 'f' + str(dest)
            reg_1 = random.randint(int(parameter_list[file_ctr][2][0]),
                                   int(parameter_list[file_ctr][2][1]))
            reg_1_str = 'f' + str(reg_1)
            reg_2 = random.randint(int(parameter_list[file_ctr][3][0]),
                                   int(parameter_list[file_ctr][3][1]))
            reg_2_str = 'f' + str(reg_2)

            # Instruction types

            arthematic_inst = ['fadd.', 'fsub.', 'fmul.', 'fdiv.']

            # TODO: Improve, nested list parsing, regex is a good alt, but need to be pefomant heavy
            if any(element in asm_inst for element in arthematic_inst):
                mode = parameter_list[file_ctr][4]
                case_data = gen_data[case_index].split(' ')
                offset_mem.append('0x' + str(case_data[0]))
                offset_mem.append('0x' + str(case_data[1]))
                # expected_result = '0x' + str(case_data[2])
                # exception_flag = '0x' + str(case_data[3])
                generated_asm_inst = '\ninst_{0}:\nTEST_RR_OP({1}, {2}, {3}, {4}, {5}, {6}, {7})\n'.format(
                    case_index, asm_inst, dest_reg, reg_1_str, reg_2_str, mode,
                    offset_ctr, offset_ctr + align)
                # Ensure that the offset generated is twice the amount
                offset_ctr += 2 * align
                asm_file_pointer.write(generated_asm_inst)

            else:
                logger.warning(
                    'Failed to detect any instructions \n empty ASM file will be generated'
                )
        # Finish the code section
        asm_file_pointer.write(code_footer + '\n\n')
        # Need to write the offsets here
        data_header = 'RVTEST_DATA_BEGIN\n.align {0}\nrvtest_data:\n'.format(
            align)
        asm_file_pointer.write(data_header)
        for memory in offset_mem:
            asm_file_pointer.write('.word ' + str(memory) + '\n')
        asm_file_pointer.write('RVTEST_DATA_END \n')


def gen_cmd_list(gen_config, seed, count, output_dir, module_dir):

    global folder_dir, run_command, parameter_list
    folder_dir = module_dir
    logger.debug('Now generating commands for gen plugin')
    try:
        env_gen_list = EnvYAML(gen_config)
    except:
        logger.error("Is your plugin YAML file properly configured?")
        raise SystemExit

    inst_yaml_list = utils.load_yaml(gen_config)

    # INIT Vars
    setup_dir = ''
    testfloat_bin = ''
    global test_file

    for key, value in inst_yaml_list.items():
        if key == 'gen_binary_path':
            testfloat_bin = inst_yaml_list[key]

            # Check if testfloat is there on path
            if shutil.which(testfloat_bin) is None:
                logger.error(
                    'Plugin requires testfloat to be installed and executable')
                raise SystemExit

        # Directory for output
        dirname = output_dir + '/testfloat'

        if re.search('^set', key):

            inst_list = inst_yaml_list[key]['inst']
            # Using index so as to ensure that we can iterate both
            for inst_list_index in range(0, len(inst_list)):
                rounding_mode_gen = ''
                rounding_mode_int = 0
                param_list = []
                inst = inst_list[inst_list_index]
                param_list.append(inst)
                # Dest
                dest = inst_yaml_list[key]['dest'].split(',')
                param_list.append(dest)
                # Register 1
                reg1 = inst_yaml_list[key]['reg1'].split(',')
                param_list.append(reg1)
                # Register 2
                reg2 = inst_yaml_list[key]['reg2'].split(',')
                param_list.append(reg2)
                tests_per_instruction = int(
                    inst_yaml_list[key]['tests_per_instruction'])

                # Get inst info
                arthematic_inst = ['fadd.', 'fsub.', 'fmul.', 'fdiv.']
                gen_inst = ''

                # TODO: Improve, nested list parsing, regex is a good alt, but need to be pefomant heavy
                if any(element in inst for element in arthematic_inst):
                    gen_inst = inst[1:-2]
                    inst_prefix = inst_precision(inst)
                gen_inst = str(inst_prefix) + '_' + gen_inst

                # Check for all suported inst using rounding-mode
                rounding_mode = inst_yaml_list[key].get('rounding-mode')
                if rounding_mode:
                    for rounding_mode_index in range(0, len(rounding_mode)):
                        rounding_mode_str = rounding_mode[rounding_mode_index]
                        # Convert the string to values
                        if rounding_mode_str == 'RNE':
                            rounding_mode_int = 0
                            rounding_mode_gen = '-rnear_even'
                        elif rounding_mode_str == 'RTZ':
                            rounding_mode_int = 1
                            rounding_mode_gen = '-rminMag'
                        elif rounding_mode_str == 'RDN':
                            rounding_mode_int = 2
                            rounding_mode_gen = '-rmin'
                        elif rounding_mode_str == 'RUP':
                            rounding_mode_int = 3
                            rounding_mode_gen = '-rmax'
                        elif rounding_mode_str == 'RMM':
                            rounding_mode_int = 4
                            rounding_mode_gen = '-rnear_maxMag'
                        else:
                            logger.error(
                                'Something went wrong while parsing YAML file \nIncorrect Rounding Mode for block {0}\n'
                                .format(key))
                            raise SystemExit
                        # Get other info
                        param_list.append(rounding_mode_int)
                        num_tests = inst_yaml_list[key]['num_tests']
                        for num_index in range(int(num_tests)):
                            if seed == 'random':
                                gen_seed = random.randint(0, 10000)
                            else:
                                gen_seed = int(seed)

                            now = datetime.datetime.now()
                            gen_prefix = '{0:06}_{1}'.format(
                                gen_seed, now.strftime('%d%m%y%h%m%s%f'))
                            test_prefix = 'testfloat_{0}_{1}_{2}_{3}_{4}'.format(
                                key, inst, rounding_mode_str, num_index,
                                gen_prefix)
                            testdir = '{0}/asm/{1}/'.format(
                                dirname, test_prefix)

                            try:
                                os.makedirs(testdir, exist_ok=True)
                            except:
                                logger.error(
                                    "unable to create a directory, exiting Pytest"
                                )
                                raise SystemExit

                            run_command.append(
                                '{0} -seed {1} -n {2} {3} {4}'.format(
                                    testfloat_bin, gen_seed,
                                    tests_per_instruction, rounding_mode_gen,
                                    gen_inst))
                            test_file.append(testdir + test_prefix + '.gen')
                            parameter_list.append(param_list)

    return run_command


def idfnc(val):
    return val


def pytest_generate_tests(metafunc):
    if 'test_input' in metafunc.fixturenames:
        test_list = gen_cmd_list(metafunc.config.getoption("configlist"),
                                 metafunc.config.getoption("seed"),
                                 metafunc.config.getoption("count"),
                                 metafunc.config.getoption("output_dir"),
                                 metafunc.config.getoption("module_dir"))
        metafunc.parametrize('test_input', test_list, ids=idfnc, indirect=True)


@pytest.fixture
def test_input(request):
    # compile tests
    global file_ctr
    logger.debug('Generating commands from test_input fixture')
    program = request.param
    (ret, out, err) = utils.sys_command_file(program, test_file[file_ctr])
    create_asm(test_file[file_ctr])
    file_ctr = file_ctr + 1
    return ret, err


def test_eval(test_input):
    assert test_input[0] == 0
