"""Fairly basic set of tools for real-time data augmentation on image data.
Can easily be extended to include new transformations,
new preprocessing methods, etc...
"""
from __future__ import absolute_import
from __future__ import print_function

from collections import deque
import warnings
import logging

import numpy as np
import scipy.ndimage as ndi

try:
    from PIL import Image as pil_image
except ImportError:
    pil_image = None

from . import Augmenter


def flip_axis(x, axis):
    x = np.asarray(x).swapaxes(axis, 0)
    x = x[::-1, ...]
    x = x.swapaxes(0, axis)
    return x


def random_channel_shift(x, intensity, channel_axis=0):
    x = np.rollaxis(x, channel_axis, 0)
    min_x, max_x = np.min(x), np.max(x)
    channel_images = [
        np.clip(x_channel + np.random.uniform(-intensity, intensity), min_x,
                max_x) for x_channel in x
    ]
    x = np.stack(channel_images, axis=0)
    x = np.rollaxis(x, 0, channel_axis + 1)
    return x


def transform_matrix_offset_center(matrix, x, y):
    o_x = float(x) / 2 + 0.5
    o_y = float(y) / 2 + 0.5
    offset_matrix = np.array([[1, 0, o_x], [0, 1, o_y], [0, 0, 1]])
    reset_matrix = np.array([[1, 0, -o_x], [0, 1, -o_y], [0, 0, 1]])
    transform_matrix = np.dot(np.dot(offset_matrix, matrix), reset_matrix)
    return transform_matrix


def apply_transform(x,
                    transform_matrix,
                    channel_axis=0,
                    fill_mode='nearest',
                    cval=0.):
    """Apply the image transformation specified by a matrix.
    # Arguments
        x: 2D numpy array, single image.
        transform_matrix: Numpy array specifying the geometric transformation.
        channel_axis: Index of axis for channels in the input tensor.
        fill_mode: Points outside the boundaries of the input
            are filled according to the given mode
            (one of `{'constant', 'nearest', 'reflect', 'wrap'}`).
        cval: Value used for points outside the boundaries
            of the input if `mode='constant'`.
    # Returns
        The transformed version of the input.
    """
    x = np.rollaxis(x, channel_axis, 0)
    final_affine_matrix = transform_matrix[:2, :2]
    final_offset = transform_matrix[:2, 2]
    channel_images = [
        ndi.interpolation.affine_transform(
            x_channel,
            final_affine_matrix,
            final_offset,
            order=0,
            mode=fill_mode,
            cval=cval) for x_channel in x
    ]
    x = np.stack(channel_images, axis=0)
    x = np.rollaxis(x, 0, channel_axis + 1)
    return x


class ImageDataAugmenter(Augmenter):
    """Augment minibatches of image data with real-time data augmentation.
    # Arguments
        labels: Whether or not the minibatches have labels
        augment_labels: Whether or not to augment the labels as well
        samplewise_center: set each sample mean to 0.
        samplewise_std_normalization: divide each input by its std.
        rotation_range: degrees (0 to 180).
        width_shift_range: fraction of total width.
        height_shift_range: fraction of total height.
        shear_range: shear intensity (shear angle in radians).
        zoom_range: amount of zoom. if scalar z, zoom will be randomly picked
            in the range [1-z, 1+z]. A sequence of two can be passed instead
            to select this range.
        channel_shift_range: shift range for each channels.
        fill_mode: points outside the boundaries are filled according to the
            given mode ('constant', 'nearest', 'reflect' or 'wrap'). Default
            is 'nearest'.
        cval: value used for points outside the boundaries when fill_mode is
            'constant'. Default is 0.
        horizontal_flip: whether to randomly flip images horizontally.
        vertical_flip: whether to randomly flip images vertically.
        rescale: rescaling factor. If None or 0, no rescaling is applied,
            otherwise we multiply the data by the value provided. This is
            applied after the `preprocessing_function` (if any provided)
            but before any other transformation.
        preprocessing_function: function that will be implied on each input.
            The function will run before any other modification on it.
            The function should take one argument:
            one image (Numpy tensor with rank 3),
            and should output a Numpy tensor with the same shape.
        data_format: 'channels_first' or 'channels_last'. In 'channels_first'
            mode, the channels dimension (the depth) is at index 1, in
            'channels_last' mode it is at index 3. It defaults to
            "channels_last".
    """

    def __init__(self,
                 labels=True,
                 augment_labels=False,
                 samplewise_center=False,
                 samplewise_std_normalization=False,
                 rotation_range=0.,
                 width_shift_range=0.,
                 height_shift_range=0.,
                 shear_range=0.,
                 zoom_range=0.,
                 channel_shift_range=0.,
                 fill_mode='nearest',
                 cval=0.,
                 horizontal_flip=False,
                 vertical_flip=False,
                 rescale=None,
                 preprocessing_function=None,
                 seed=None,
                 data_format='channels_last',
                 save_inverses=False):

        super(ImageDataAugmenter, self).__init__(labels, augment_labels)
        self.samplewise_center = samplewise_center
        self.samplewise_std_normalization = samplewise_std_normalization
        self.rotation_range = rotation_range
        self.width_shift_range = width_shift_range
        self.height_shift_range = height_shift_range
        self.shear_range = shear_range
        self.zoom_range = zoom_range
        self.channel_shift_range = channel_shift_range
        self.fill_mode = fill_mode
        self.cval = cval
        self.horizontal_flip = horizontal_flip
        self.vertical_flip = vertical_flip
        self.rescale = rescale
        self.preprocessing_function = preprocessing_function
        self.save_inverses = save_inverses
        self.inverse_transforms = deque()

        if self.channel_shift_range != 0 and self.save_inverses:
            warnings.warn("Image augmenter cannot invert channel shifting")
        if self.augment_labels and self.save_inverses:
            warnings.warn("Be careful how you invert images. \
                Masks are augmented in batch first before images!")
        if (self.samplewise_center or self.samplewise_std_normalization) \
                and self.save_inverses:
            warnings.warn("Image augmenter cannot invert samplewise mean"
                          " and std normalization!")

        if data_format not in {'channels_last', 'channels_first'}:
            raise ValueError("`data_format` should be `channels_last` (channel\
             after row and column) or `channels_first` (channel before row and\
             column). Received arg: {} data_format".format(data_format))
        self.data_format = data_format
        if data_format == 'channels_first':
            self.channel_axis = 1
            self.row_axis = 2
            self.col_axis = 3
        if data_format == 'channels_last':
            self.channel_axis = 3
            self.row_axis = 1
            self.col_axis = 2

        self.mean = None
        self.std = None
        self.principal_components = None

        if np.isscalar(zoom_range):
            self.zoom_range = [1 - zoom_range, 1 + zoom_range]
        elif len(zoom_range) == 2:
            self.zoom_range = [zoom_range[0], zoom_range[1]]
        else:
            raise ValueError(
                '`zoom_range` should be a float or '
                'a tuple or list of two floats. '
                'Received arg: ', zoom_range)
        if seed is not None:
            np.random.seed(seed)

        logging.info("Creating %r" % self)

    def __str__(self):
        return "ImageDataAugmenter(\n\tlabels={labels} \
            \n\taugment_labels={augment_labels}, \
            \n\tsamplewise_center={samplewise_center}, \
            \n\tsamplewise_std_normalization={samplewise_std_normalization}, \
            \n\trotation_range={rotation_range}, \
            \n\twidth_shift_range={width_shift_range}, \
            \n\theight_shift_range={height_shift_range}, \
            \n\tshear_range={shear_range}, \
            \n\tzoom_range={zoom_range}, \
            \n\tchannel_shift_range={channel_shift_range}, \
            \n\tfill_mode={fill_mode}, \
            \n\tcval={cval}, \
            \n\thorizontal_flip={horizontal_flip}, \
            \n\tvertical_flip={vertical_flip}, \
            \n\trescale = {rescale}, \
            \n\tpreprocessing_function = {preprocessing_function}, \
            \n\tsave_inverses = {save_inverses}, \
            \n)".format(**self.__dict__)

    def __repr__(self):
        return str(self)

    def augment(self, x):
        for i in range(len(x)):
            x[i] = self.random_transform(x[i], np.random.randint(2**32))
        return x

    def standardize(self, x):
        """Apply the normalization configuration to a batch of inputs.
        # Arguments
            x: batch of inputs to be normalized.
        # Returns
            The inputs, normalized.
        """
        if self.preprocessing_function:
            x = self.preprocessing_function(x)
        if self.rescale:
            x *= self.rescale
        # x is a single image, so it doesn't have image number at index 0
        img_channel_axis = self.channel_axis - 1
        # Check if x has any channels and is the right dimensions
        remove_channel_axis = False
        if x.ndim == 2:
            remove_channel_axis = True
            x = np.expand_dims(x, axis=img_channel_axis)
        elif x.ndim != 3:
            raise ValueError("Dim of input image must be 2 or 3, given ",
                             x.ndim)
        if self.samplewise_center:
            x -= np.mean(x, axis=img_channel_axis, keepdims=True)
        if self.samplewise_std_normalization:
            x /= (np.std(x, axis=img_channel_axis, keepdims=True) + 1e-7)

        # If we added a dimension for the channel, remove it
        if remove_channel_axis:
            x = np.squeeze(x, axis=img_channel_axis)
        return x

    def random_transform(self, x, seed=None):
        """Randomly augment a single image tensor.
        # Arguments
            x: 3D tensor, single image.
            seed: random seed.
        # Returns
            A randomly transformed version of the input (same shape).
        """
        # x is a single image, so it doesn't have image number at index 0
        img_row_axis = self.row_axis - 1
        img_col_axis = self.col_axis - 1
        img_channel_axis = self.channel_axis - 1

        # Check if x has any channels and is the right dimensions
        remove_channel_axis = False
        if x.ndim == 2:
            remove_channel_axis = True
            x = np.expand_dims(x, axis=img_channel_axis)
        elif x.ndim != 3:
            raise ValueError("Dim of input image must be 2 or 3, given ",
                             x.ndim)

        if seed is not None:
            np.random.seed(seed)

        # use composition of homographies
        # to generate final transform that needs to be applied
        if self.rotation_range:
            theta = np.pi / 180 * \
                np.random.uniform(-self.rotation_range, self.rotation_range)
        else:
            theta = 0

        if self.height_shift_range:
            tx = np.random.uniform(-self.height_shift_range,
                                   self.height_shift_range) * \
                                   x.shape[img_row_axis]
        else:
            tx = 0

        if self.width_shift_range:
            ty = np.random.uniform(
                -self.width_shift_range,
                self.width_shift_range) * x.shape[img_col_axis]
        else:
            ty = 0

        if self.shear_range:
            shear = np.random.uniform(-self.shear_range, self.shear_range)
        else:
            shear = 0

        if self.zoom_range[0] == 1 and self.zoom_range[1] == 1:
            zx, zy = 1, 1
        else:
            zx, zy = np.random.uniform(self.zoom_range[0], self.zoom_range[1],
                                       2)

        transform_matrix = None
        if theta != 0:
            rotation_matrix = np.array([[np.cos(theta), -np.sin(theta), 0],
                                        [np.sin(theta),
                                         np.cos(theta), 0], [0, 0, 1]])
            transform_matrix = rotation_matrix

        if tx != 0 or ty != 0:
            shift_matrix = np.array([[1, 0, tx], [0, 1, ty], [0, 0, 1]])
            transform_matrix = shift_matrix if transform_matrix is None else \
                np.dot(transform_matrix, shift_matrix)

        if shear != 0:
            shear_matrix = np.array([[1, -np.sin(shear), 0],
                                     [0, np.cos(shear), 0], [0, 0, 1]])
            transform_matrix = shear_matrix if transform_matrix is None else \
                np.dot(transform_matrix, shear_matrix)

        if zx != 1 or zy != 1:
            zoom_matrix = np.array([[zx, 0, 0], [0, zy, 0], [0, 0, 1]])
            transform_matrix = zoom_matrix if transform_matrix is None else \
                np.dot(transform_matrix, zoom_matrix)

        inverse_transform = None
        if transform_matrix is not None:
            h, w = x.shape[img_row_axis], x.shape[img_col_axis]
            transform_matrix = transform_matrix_offset_center(
                transform_matrix, h, w)
            x = apply_transform(
                x,
                transform_matrix,
                img_channel_axis,
                fill_mode=self.fill_mode,
                cval=self.cval)
            inverse_transform = np.linalg.inv(transform_matrix)

        if self.channel_shift_range != 0:
            x = random_channel_shift(x, self.channel_shift_range,
                                     img_channel_axis)

        horizontal_flipped = False
        if self.horizontal_flip:
            if np.random.random() < 0.5:
                x = flip_axis(x, img_col_axis)
                horizontal_flipped = True

        vertically_flipped = False
        if self.vertical_flip:
            if np.random.random() < 0.5:
                x = flip_axis(x, img_row_axis)
                vertically_flipped = True

        # If we added a dimension for the channel, remove it
        if remove_channel_axis:
            x = np.squeeze(x, axis=img_channel_axis)

        # If we want to save inverses, push onto the inverse queue
        if self.save_inverses:
            self.inverse_transforms.appendleft(
                (inverse_transform, horizontal_flipped, vertically_flipped))
        return x

    def apply_inversion_transform(self, x):
        """
        Invert a random augment of a single image tensor.
        # Arguments
            x: 3D tensor, single image.
        # Returns
            The orignal image before the random transformed version
            of the input (same shape).
        """
        # x is a single image, so it doesn't have image number at index 0
        img_row_axis = self.row_axis - 1
        img_col_axis = self.col_axis - 1
        img_channel_axis = self.channel_axis - 1

        # Check if x has any channels and is the right dimensions
        remove_channel_axis = False
        if x.ndim == 2:
            remove_channel_axis = True
            x = np.expand_dims(x, axis=img_channel_axis)
        elif x.ndim != 3:
            raise ValueError("Dim of input image must be 2 or 3, given ",
                             x.ndim)

        # Pop from the queue
        inverse_transform, horizontally_flipped, vertically_flipped = \
            self.inverse_transforms.pop()
        # Undo any flipping
        if vertically_flipped:
            x = flip_axis(x, img_row_axis)

        if horizontally_flipped:
            x = flip_axis(x, img_col_axis)

        # Apply the inverse transform
        x = apply_transform(
            x,
            inverse_transform,
            img_channel_axis,
            fill_mode=self.fill_mode,
            cval=self.cval)

        # Remove the channel axis if we added it
        if remove_channel_axis:
            x = np.squeeze(x, img_channel_axis)

        return x

    def invert_images(self, x_images):
        if len(x_images) != len(self.inverse_transforms):
            warnings.warn("Have %s images, but only %s inverse transforms. "
                          "Using first transforms and discarding rest" %
                          (len(x_images), len(self.inverse_transforms)))
        inverted = np.stack(
            [self.apply_inversion_transform(x) for x in x_images], axis=0)
        self.inverse_transforms = deque()
        return inverted
