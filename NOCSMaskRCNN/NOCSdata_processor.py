'''
    Script used to split NOCS transformation matrix RTs to unit orthogonal matrix, translation vector and scale vector.
'''

import pickle
import numpy as np
import os
import glob
import argparse

def decompose_RT(RTs):
    assert (RTs.ndim == 3)
    RSMatrix = RTs[:,:3,:3]
    SMatrix = np.linalg.norm(RSMatrix, axis=1)
    RMatrix = RSMatrix / SMatrix[:,:,np.newaxis]
    TMatrix = RTs[:,:3,3]
    return RMatrix, SMatrix, TMatrix

def obj2cam_fromworld(RTs):
    m2c_matrix = np.dot(np.array([[1, 0, 0, 0], [0, -1, 0, 0], [0, 0, -1, 0], [0, 0, 0, 1]]),RTs)
    return m2c_matrix

def process_pkl_file(file_path, flip_z = False):
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        print ('pkl file:{} does not exist'.format(file_path))
        return None
    
    with open(file_path, 'rb') as f:
        try:
            data = pickle.load(file_path)
            if 'pred_RTs' not in data.keys():
                print ("Wrong format of pkl file {}, there is no key called pred_RTs".format(file_path))
                return None
            RTs = data.keys['pred_RTs']
            R, S, T = decompose_RT(RTs)

            data['pred_Rs'] = R
            data['pred_Ts'] = T
            data['pred_Ss'] = S

        except Exception as e:
            print ('Failed to process file:{}'.format(file_path))
        
def process_pkls_infolder(folder, flip_z = False):
    if not os.path.isdir(folder):
        print ('the input {} is not a folder'.format(folder))
        return
    
    process_glob = os.path.join(folder, "results_*_*_*.pkl")
    pkl_files = glob.glob(process_glob)

    for pkl in pkl_files:
        print ('processing file {}'.format(pkl))
        process_pkl_file(pkl)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", help="the path to prediction files", required=True)
    parser.add_argument("--flip_z", htlp="If the z axis should be flipped", default="False")

    arguments = parser.parse_args()

    folder = arguments.data
    process_pkls_infolder()

if __name__ == '__main__':
    main()
