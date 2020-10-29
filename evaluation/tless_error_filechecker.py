'''
This script is used to check the error yaml files.
It only checks the number of records, used to make sure the batch doesn't output multiple times or miss part of data
'''

import ruamel.yaml as YAML
import numpy as np
import argparse
import os
import glob

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('--error_dir', required=True)

    arguments = parser.parse_args()

    error_dir = arguments.error_dir

    if os.path.exists(error_dir):
        yml_glob = os.path.join(error_dir, "./errors_*.yml")
        print (yml_glob)
        yaml_files = glob.glob(yml_glob)
    else:
        print ("Path %s doesn't exist" % error_dir)
        quit()

    # use 32 bits to represent obj data, the obj record should not be duplicated
    im_max = 503
    obj_range = (1, 30)

    for yml_file in yaml_files:
        with open(yml_file, 'r') as f:
            print ("checking %s" % yml_file)

            data = YAML.load(f, Loader=YAML.Loader)

            im_record = [0] * (im_max + 1)
            for rec in data:
                image_id = rec['im_id']
                if image_id < 0 or image_id > im_max:
                    print ("There exists a broken record:%s in file %s" % (rec, yml_file))
                    continue

                obj_id = rec['obj_id']
                if obj_id < obj_range[0] or obj_id > obj_range[1]:
                    print ("The record %s has an invalid obj id %d in file %s" % (rec, obj_id, yml_file))
                    continue
                
                obj_bitcode = 0x1 << (obj_id - 1)
                if (im_record[image_id] & obj_bitcode) != 0:
                    print ("The record %s is duplicated in file %s" % (rec, yml_file))
                    continue
                im_record[image_id] = (im_record[image_id] | obj_bitcode)
            
            # check record number
            standard = im_record[0]
            for i, code in enumerate(im_record):
                if code != standard:
                    print ("file %s isn't consistent, image %d is different from image 0" % (yml_file, i))

if __name__ == '__main__':
    main()