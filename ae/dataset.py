# -*- coding: utf-8 -*-

import multiprocessing
import numpy as np
import time
import hashlib
import glob
import os
import bitarray

import progressbar
from pysixd_stuff import transform
from pysixd_stuff import view_sampler

import cv2

from meshrenderer import meshrenderer, meshrenderer_phong
from utils import lazy_property

from imgaug.augmenters import *

class Dataset(object):

    def __init__(self, dataset_path, **kw):
        
        self.shape = (int(kw['h']), int(kw['w']), int(kw['c']))
        self.noof_training_imgs = int(kw['noof_training_imgs'])
        self.dataset_path = dataset_path

        self.bg_img_paths = glob.glob( kw['background_images_glob'] )
        self.noof_bg_imgs = min(int(kw['noof_bg_imgs']), len(self.bg_img_paths))
        
        self._aug = eval(kw['code'])
        self._kw = kw

        self.train_x = np.empty( (self.noof_training_imgs,) + self.shape, dtype=np.uint8 )
        self.mask_x = np.empty( (self.noof_training_imgs,) + self.shape[:2], dtype= bool)
        self.train_y = np.empty( (self.noof_training_imgs,) + self.shape, dtype=np.uint8 )
        self.bg_imgs = np.empty( (self.noof_bg_imgs,) + self.shape, dtype=np.uint8 )
        self.random_syn_masks


    @lazy_property
    def viewsphere_for_embedding(self):
        kw = self._kw
        num_cyclo = int(kw['num_cyclo'])
        azimuth_range = (0, 2 * np.pi)
        elev_range = (-0.5 * np.pi, 0.5 * np.pi)
        views, _ = view_sampler.sample_views(
            int(kw['min_n_views']), 
            float(kw['radius']), 
            azimuth_range, 
            elev_range
        )
        Rs = np.empty( (len(views)*num_cyclo, 3, 3) )
        i = 0
        for view in views:
            for cyclo in np.linspace(0, 2.*np.pi, num_cyclo):
                rot_z = np.array([[np.cos(-cyclo), -np.sin(-cyclo), 0], [np.sin(-cyclo), np.cos(-cyclo), 0], [0, 0, 1]])
                Rs[i,:,:] = rot_z.dot(view['R'])
                i += 1
        return Rs

    @lazy_property
    def renderer(self):
        if self._kw['model'] == 'cad':
            renderer = meshrenderer.Renderer(
               [self._kw['model_path']], 
               int(self._kw['antialiasing']), 
               self.dataset_path, 
               float(self._kw['vertex_scale'])
            )
        elif self._kw['model'] == 'reconst':
            renderer = meshrenderer_phong.Renderer(
               [self._kw['model_path']], 
               int(self._kw['antialiasing']), 
               self.dataset_path, 
               float(self._kw['vertex_scale'])
            )
        else:
            'Error: neither cad nor reconst in model path!'
            exit()
        return renderer

    def get_training_images(self, dataset_path, args):

        current_config_hash = hashlib.md5(str(args.items('Dataset')+args.items('Paths'))).hexdigest()
        current_file_name = os.path.join(dataset_path, current_config_hash + '.npz')

        if os.path.exists(current_file_name):
            training_data = np.load(current_file_name)
            self.train_x = training_data['train_x'].astype(np.uint8)
            self.mask_x = training_data['mask_x']
            self.train_y = training_data['train_y'].astype(np.uint8)
        else:
            self.render_training_images()
            np.savez(current_file_name, train_x = self.train_x, mask_x = self.mask_x, train_y = self.train_y)
        print 'loaded %s training images' % len(self.train_x)

    def get_sprite_training_images(self, train_args):
        
        dataset_path= train_args.get('Paths','MODEL_PATH')
        dataset_zip = np.load(dataset_path)

        # print('Keys in the dataset:', dataset_zip.keys())
        imgs = dataset_zip['imgs']
        latents_values = dataset_zip['latents_values']
        latents_classes = dataset_zip['latents_classes']
        metadata = dataset_zip['metadata'][()]

        latents_sizes = metadata['latents_sizes']
        latents_bases = np.concatenate((latents_sizes[::-1].cumprod()[::-1][1:],
                                        np.array([1,])))

        latents_classes_heart = latents_classes[-245760:]
        latents_classes_heart_rot = latents_classes_heart.copy()

        latents_classes_heart_rot[:, 0] = 0
        latents_classes_heart_rot[:, 1] = 2
        latents_classes_heart_rot[:, 2] = 5
        latents_classes_heart_rot[:, 4] = 16
        latents_classes_heart_rot[:, 5] = 16

        def latent_to_index(latents):
          return np.dot(latents, latents_bases).astype(int)

        indices_sampled = latent_to_index(latents_classes_heart_rot)
        imgs_sampled_rot = imgs[indices_sampled]
        indices_sampled = latent_to_index(latents_classes_heart)
        imgs_sampled_all = imgs[indices_sampled]

        self.train_x = np.expand_dims(imgs_sampled_all, 3)*255
        self.train_y = np.expand_dims(imgs_sampled_rot, 3)*255


    # def get_embedding_images(self, dataset_path, args):

    #     current_config_hash = hashlib.md5(str(args.items('Embedding') + args.items('Dataset')+args.items('Paths'))).hexdigest()
    #     current_file_name = os.path.join(dataset_path, current_config_hash + '.npz')

    #     if os.path.exists(current_file_name):
    #         embedding_data = np.load(current_file_name)
    #         self.embedding_data = embedding_data.astype(np.uint8)
    #     else:
    #         self.render_embedding_images()
    #         np.savez(current_file_name, train_x = self.train_x, mask_x = self.mask_x, train_y = self.train_y)
    #     print 'loaded %s training images' % len(self.train_x)

    def load_bg_images(self, dataset_path):
        current_config_hash = hashlib.md5(str(self.shape) + str(self.bg_img_paths)).hexdigest()
        current_file_name = os.path.join(dataset_path, current_config_hash + '.npy')
        if os.path.exists(current_file_name):
            self.bg_imgs = np.load(current_file_name)
        else:
            file_list = self.bg_img_paths[:self.noof_bg_imgs]

            for j,fname in enumerate(file_list):
                print 'loading bg img %s/%s' % (j,self.noof_bg_imgs)
                bgr = cv2.imread(fname)
                bgr = cv2.resize(bgr, self.shape[:2])

                self.bg_imgs[j] = bgr
            np.save(current_file_name,self.bg_imgs)
        print 'loaded %s bg images' % self.noof_bg_imgs


    def render_rot(self, R, downSample = 1):
        kw = self._kw
        h, w = self.shape[:2]
        radius = float(kw['radius'])
        render_dims = eval(kw['render_dims'])
        K = eval(kw['k'])
        K = np.array(K).reshape(3,3)
        K[:2,:] = K[:2,:] / downSample

        clip_near = float(kw['clip_near'])
        clip_far = float(kw['clip_far'])
        pad_factor = float(kw['pad_factor'])

        t = np.array([0, 0, float(kw['radius'])])

        bgr_y, depth_y = self.renderer.render( 
            obj_id=0,
            W=render_dims[0]/downSample, 
            H=render_dims[1]/downSample,
            K=K.copy(), 
            R=R, 
            t=t,
            near=clip_near,
            far=clip_far,
            random_light=False
        )

        ys, xs = np.nonzero(depth_y > 0)
        obj_bb = view_sampler.calc_2d_bbox(xs, ys, render_dims)
        x, y, w, h = obj_bb

        size = int(np.maximum(h, w) * pad_factor)
        left = x+w/2-size/2
        right = x+w/2+size/2
        top = y+h/2-size/2
        bottom = y+h/2+size/2

        bgr_y = bgr_y[top:bottom, left:right]
        return cv2.resize(bgr_y, self.shape[:2])


    def render_training_images(self):
        kw = self._kw
        H, W = int(kw['h']), int(kw['w'])
        render_dims = eval(kw['render_dims'])
        K = eval(kw['k'])
        K = np.array(K).reshape(3,3)
        clip_near = float(kw['clip_near'])
        clip_far = float(kw['clip_far'])
        pad_factor = float(kw['pad_factor'])
        crop_offset_sigma = float(kw['crop_offset_sigma'])
        t = np.array([0, 0, float(kw['radius'])])


        bar = progressbar.ProgressBar(
            maxval=self.noof_training_imgs, 
            widgets=[' [', progressbar.Timer(), ' | ', 
                            progressbar.Counter('%0{}d / {}'.format(len(str(self.noof_training_imgs)), 
                                self.noof_training_imgs)), ' ] ', progressbar.Bar(), ' (', progressbar.ETA(), ') ']
            )
        bar.start()

        for i in np.arange(self.noof_training_imgs):
            bar.update(i)

            # print '%s/%s' % (i,self.noof_training_imgs)
            # start_time = time.time()
            R = transform.random_rotation_matrix()[:3,:3]
            bgr_x, depth_x = self.renderer.render( 
                obj_id=0,
                W=render_dims[0], 
                H=render_dims[1],
                K=K.copy(), 
                R=R, 
                t=t,
                near=clip_near,
                far=clip_far,
                random_light=True
            )
            bgr_y, depth_y = self.renderer.render( 
                obj_id=0,
                W=render_dims[0], 
                H=render_dims[1],
                K=K.copy(), 
                R=R, 
                t=t,
                near=clip_near,
                far=clip_far,
                random_light=False
            )
            # render_time = time.time() - start_time
            # cv2.imshow('bgr_x',bgr_x)
            # cv2.imshow('bgr_y',bgr_y)
            # cv2.waitKey(0)
            
            ys, xs = np.nonzero(depth_x > 0)
            try:
                obj_bb = view_sampler.calc_2d_bbox(xs, ys, render_dims)
            except ValueError as e:
                print 'Object in Rendering not visible. Have you scaled the vertices to mm?'
                break

            x, y, w, h = obj_bb

            rand_trans_x = np.random.uniform(-crop_offset_sigma, crop_offset_sigma)
            rand_trans_y = np.random.uniform(-crop_offset_sigma, crop_offset_sigma)

            size = int(np.maximum(h, w) * pad_factor)
            left = int(x+w/2-size/2 + rand_trans_x)
            right = int(x+w/2+size/2 + rand_trans_x)
            top = int(y+h/2-size/2 + rand_trans_y)
            bottom = int(y+h/2+size/2 + rand_trans_y)

            bgr_x = bgr_x[top:bottom, left:right]
            depth_x = depth_x[top:bottom, left:right]
            bgr_x = cv2.resize(bgr_x, (W, H), interpolation = cv2.INTER_NEAREST)
            depth_x = cv2.resize(depth_x, (W, H), interpolation = cv2.INTER_NEAREST)

            mask_x = depth_x == 0.

            ys, xs = np.nonzero(depth_y > 0)
            obj_bb = view_sampler.calc_2d_bbox(xs, ys, render_dims)
            x, y, w, h = obj_bb

            size = int(np.maximum(h, w) * pad_factor)
            left = x+w/2-size/2
            right = x+w/2+size/2
            top = y+h/2-size/2
            bottom = y+h/2+size/2

            bgr_y = bgr_y[top:bottom, left:right]
            bgr_y = cv2.resize(bgr_y, (W, H), interpolation = cv2.INTER_NEAREST)

            self.train_x[i] = bgr_x.astype(np.uint8)
            self.mask_x[i] = mask_x
            self.train_y[i] = bgr_y.astype(np.uint8)

            #print 'rendertime ', render_time, 'processing ', time.time() - start_time
        bar.finish()

    def render_embedding_image_batch(self, start, end):
        kw = self._kw
        h, w = self.shape[:2]
        azimuth_range = (0, 2 * np.pi)
        elev_range = (-0.5 * np.pi, 0.5 * np.pi)
        radius = float(kw['radius'])
        render_dims = eval(kw['render_dims'])
        K = eval(kw['k'])
        K = np.array(K).reshape(3,3)

        clip_near = float(kw['clip_near'])
        clip_far = float(kw['clip_far'])
        pad_factor = float(kw['pad_factor'])

        t = np.array([0, 0, float(kw['radius'])])
        batch = np.empty( (end-start,)+ self.shape)
        obj_bbs = np.empty( (end-start,)+ (4,))

        for i, R in enumerate(self.viewsphere_for_embedding[start:end]):
            bgr_y, depth_y = self.renderer.render( 
                obj_id=0,
                W=render_dims[0], 
                H=render_dims[1],
                K=K.copy(), 
                R=R, 
                t=t,
                near=clip_near,
                far=clip_far,
                random_light=False
            )

            ys, xs = np.nonzero(depth_y > 0)
            obj_bb = view_sampler.calc_2d_bbox(xs, ys, render_dims)
            x, y, w, h = obj_bb
            obj_bbs[i] = obj_bb

            size = int(np.maximum(h, w) * pad_factor)
            left = x+w/2-size/2
            right = x+w/2+size/2
            top = y+h/2-size/2
            bottom = y+h/2+size/2

            bgr_y = bgr_y[top:bottom, left:right]
            batch[i] = cv2.resize(bgr_y, self.shape[:2], interpolation = cv2.INTER_NEAREST) / 255.
        return (batch, obj_bbs)

    @property
    def embedding_size(self):
        if self.noof_bg_imgs > 0:
            return len(self.viewsphere_for_embedding)
        else:
            kw = self._kw
            return int(kw['min_n_views'])
    
    @lazy_property
    def random_syn_masks(self):
        random_syn_masks = bitarray.bitarray()
        with open("/home_local2/sund_ma/src/vae/bin_syn_masks_6deg/arbitrary_syn_masks_1000.bin", 'r') as fh:
            random_syn_masks.fromfile(fh)
        occlusion_masks = np.fromstring(random_syn_masks.unpack(), dtype=np.bool)
        occlusion_masks = occlusion_masks.reshape(-1,224,224,1).astype(np.float32)
        print occlusion_masks.shape

        occlusion_masks = np.array([cv2.resize(mask,(self.shape[0],self.shape[1]), interpolation = cv2.INTER_NEAREST) for mask in occlusion_masks])           
        return occlusion_masks


    def augment_occlusion(self, masks, verbose=False, min_trans = 0.2, max_trans=0.7, max_occl = 0.25,min_occl = 0.0):

        
        new_masks = np.zeros_like(masks,dtype=np.bool)
        occl_masks_batch = self.random_syn_masks[np.random.choice(len(self.random_syn_masks),len(masks))]
        for idx,mask in enumerate(masks):
            occl_mask = occl_masks_batch[idx]
            while True:
                trans_x = int(np.random.choice([-1,1])*(np.random.rand()*(max_trans-min_trans) + min_trans)*occl_mask.shape[0])
                trans_y = int(np.random.choice([-1,1])*(np.random.rand()*(max_trans-min_trans) + min_trans)*occl_mask.shape[1])
                M = np.float32([[1,0,trans_x],[0,1,trans_y]])

                transl_occl_mask = cv2.warpAffine(occl_mask,M,(occl_mask.shape[0],occl_mask.shape[1]))

                overlap_matrix = np.invert(mask.astype(np.bool)) * transl_occl_mask.astype(np.bool)
                overlap = len(overlap_matrix[overlap_matrix==True])/float(len(mask[mask==0]))

                if overlap < max_occl and overlap > min_occl:
                    new_masks[idx,...] = np.logical_xor(mask.astype(np.bool), overlap_matrix)
                    if verbose:
                        print 'overlap is ', overlap    
                    break

        return new_masks

    def batch(self, batch_size):


        # batch_x = np.empty( (batch_size,) + self.shape, dtype=np.uint8 )
        # batch_y = np.empty( (batch_size,) + self.shape, dtype=np.uint8 )
        
        rand_idcs = np.random.choice(self.noof_training_imgs, batch_size, replace=False)
        
        if self.noof_bg_imgs > 0:
            rand_idcs_bg = np.random.choice(self.noof_bg_imgs, batch_size, replace=False)
            
            batch_x, masks, batch_y = self.train_x[rand_idcs], self.mask_x[rand_idcs], self.train_y[rand_idcs]
            rand_vocs = self.bg_imgs[rand_idcs_bg]

            if np.float(self._kw['realistic_occlusion']):
                masks = self.augment_occlusion(masks.copy(),max_occl=np.float(self._kw['realistic_occlusion']))


            # masks
            
            batch_x[masks] = rand_vocs[masks]
        else:
            batch_x, batch_y = self.train_x[rand_idcs], self.train_y[rand_idcs]

            for i in xrange(batch_size):
              rot_angle= np.random.rand()*360
              cent = int(self.shape[0]/2)
              M = cv2.getRotationMatrix2D((cent,cent),rot_angle,1)
              batch_x[i] = cv2.warpAffine(batch_x[i],M,self.shape[:2])[:,:,np.newaxis]
              batch_y[i] = cv2.warpAffine(batch_y[i],M,self.shape[:2])[:,:,np.newaxis]


        #needs uint8
        batch_x = self._aug.augment_images(batch_x)

        #slow...
        batch_x = batch_x / 255.
        batch_y = batch_y / 255.
        

        return (batch_x, batch_y)
