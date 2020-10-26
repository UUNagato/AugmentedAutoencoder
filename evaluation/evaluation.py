'''
    This script is used to read in real data and output Error measure result.
'''

import numpy as np
import configparser
import argparse

import sys
sys.path.append('D:/MSRA/repos/Evaluation')
from sixd_toolkit.tools import eval_calc_errors, eval_loc

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('--eval_dir', required=True)    # evaluation file folder
    # parser.add_argument('--model_path', default=None, required=True)    # the path to model
    parser.add_argument('--eval_cfg', required=True)    # evaluation config file folder
    parser.add_argument('--scene_list')                 
    # not necessary, specify a specific scene to make program deal with a subset of scenes to avoid too high memory occupation.

    arguments = parser.parse_args()

    eval_dir = arguments.eval_dir
    eval_args = configparser.ConfigParser(inline_comment_prefixes='#')
    eval_args.read(arguments.eval_cfg)      # read config file

    scene_list = eval(arguments.scene_list)

    print ("Some important parameters:\n eval_dir:{}".format(eval_dir))

    # now evaluate error
    if eval_args.getboolean('EVALUATION','COMPUTE_ERRORS'):
        print ("Start to call eval_calc_errors")
        if (scene_list != None):
            print ("Subset {} is evaluated".format(scene_list))
        eval_calc_errors.eval_calc_errors(eval_args, eval_dir, scene_list)
    if eval_args.getboolean('EVALUATION','EVALUATE_ERRORS'):
        print ("Start to call eval_loc.match_and_eval_performance_scores")
        eval_loc.match_and_eval_performance_scores(eval_args, eval_dir)


if __name__ == '__main__':
    main()