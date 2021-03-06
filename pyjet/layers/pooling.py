import logging
from functools import partial

import torch
import torch.nn as nn
import torch.nn.functional as F

from . import layer
from . import functions as L
from .. import backend as J


def build_strided_pool(name, kernel_size, stride=None, padding=1, dilation=1):

    params = dict(
        kernel_size=kernel_size, stride=stride, padding=padding, dilation=dilation
    )
    # Average pooling does not have dilation in pytorch
    if "avg" in name:
        params.pop("dilation")
    layer = StridedPool.pool_funcs[name](**params)
    logging.info("Creating layer: %r" % layer)
    return layer


class UpSampling(layer.Layer):
    def __init__(self, size=None, scale_factor=None, mode="nearest"):
        super(UpSampling, self).__init__()
        self.upsampling = partial(
            F.interpolate, size=size, scale_factor=scale_factor, mode=mode
        )
        self.size = size
        self.scale_factor = scale_factor
        self.mode = mode

    def calc_output_size(self, input_size):
        if self.size is not None:
            return J.LongTensor(self.size)
        else:
            return input_size * self.scale_factor

    def calc_input_size(self, output_size):
        if self.size is not None:
            raise ValueError(
                "Cannot know input size if deterministic output size is used"
            )
        else:
            return output_size / self.scale_factor

    def forward(self, x):
        # Expect x as BatchSize x Length1 x ... x LengthN x Filters
        if J.channels_mode == "channels_last":
            return self.unfix_input(self.upsampling(self.fix_input(x)))
        else:
            return self.upsampling(x)

    def fix_input(self, x):
        raise NotImplementedError()

    def unfix_input(self, x):
        raise NotImplementedError()

    def __str__(self):
        return "%r" % self.upsampling


class UpSampling2D(UpSampling):
    def fix_input(self, inputs):
        return inputs.permute(0, 3, 1, 2).contiguous()

    def unfix_input(self, outputs):
        return outputs.permute(0, 2, 3, 1).contiguous()


class StridedPool(layer.Layer):

    pool_funcs = {
        "max1d": nn.MaxPool1d,
        "max2d": nn.MaxPool2d,
        "max3d": nn.MaxPool3d,
        "avg1d": nn.AvgPool1d,
        "avg2d": nn.AvgPool2d,
        "avg3d": nn.AvgPool3d,
    }

    def __init__(self, pool_type, kernel_size, stride=None, padding="same", dilation=1):
        super(StridedPool, self).__init__()
        padding = (kernel_size - 1) // 2 if padding == "same" else padding
        self.pool_type = pool_type
        self.kernel_size = kernel_size
        if stride is None:
            stride = kernel_size
        self.stride = stride
        self.padding = padding
        self.dilation = dilation

        self.pool = build_strided_pool(
            pool_type, kernel_size, stride=stride, padding=padding, dilation=dilation
        )

    def calc_output_size(self, input_size):
        """
        NOTE: This is designed for pytorch longtensors, if you pass an integer, make sure to cast it back to an
        integer as python3 will perform float division on it
        """
        output_size = (
            input_size - self.dilation * (self.kernel_size - 1) + 2 * self.padding - 1
        ) // self.stride + 1
        return output_size

    def calc_input_size(self, output_size):
        return (
            (output_size - 1) * self.stride
            - 2 * self.padding
            + 1
            + self.dilation * (self.kernel_size - 1)
        )

    def forward(self, x):
        # Expect x as BatchSize x Length1 x ... x LengthN x Filters
        if J.channels_mode == "channels_last":
            return self.unfix_input(self.pool(self.fix_input(x)))
        else:
            return self.pool(x)

    def fix_input(self, x):
        raise NotImplementedError()

    def unfix_input(self, x):
        raise NotImplementedError()

    def __str__(self):
        return "%r" % self.pool


class Strided1D(StridedPool):
    def fix_input(self, inputs):
        return inputs.transpose(1, 2)

    def unfix_input(self, outputs):
        return outputs.transpose(1, 2)


class Strided2D(StridedPool):
    def fix_input(self, inputs):
        return inputs.permute(0, 3, 1, 2).contiguous()

    def unfix_input(self, outputs):
        return outputs.permute(0, 2, 3, 1).contiguous()


class MaxPooling1D(Strided1D):
    def __init__(self, kernel_size, stride=None, padding="same", dilation=1):
        super(MaxPooling1D, self).__init__(
            "max1d", kernel_size, stride=stride, padding=padding, dilation=dilation
        )


class SequenceMaxPooling1D(MaxPooling1D):
    def forward(self, seq_inputs):
        return [
            super(SequenceMaxPooling1D, self).forward(sample.unsqueeze(0)).squeeze(0)
            for sample in seq_inputs
        ]


class AveragePooling1D(Strided1D):
    def __init__(self, kernel_size, stride=None, padding="same"):
        super(AveragePooling1D, self).__init__(
            "avg1d", kernel_size, stride=stride, padding=padding
        )


class AveragePooling2D(Strided2D):
    def __init__(self, kernel_size, stride=None, padding="same"):
        super(AveragePooling2D, self).__init__(
            "avg2d", kernel_size, stride=stride, padding=padding
        )


class MaxPooling2D(Strided2D):
    def __init__(self, kernel_size, stride=None, padding="same", dilation=1):
        super(MaxPooling2D, self).__init__(
            "max2d", kernel_size, stride=stride, padding=padding, dilation=dilation
        )


class GlobalMaxPooling1D(layer.Layer):
    def __init__(self):
        super(GlobalMaxPooling1D, self).__init__()

        # Logging
        logging.info("Creating layer: {}".format(str(self)))

    def calc_output_size(self, input_size):
        return input_size / input_size

    def forward(self, x):
        # The input comes in as B x L x E
        return torch.max(x, dim=1)[0]


class SequenceGlobalMaxPooling1D(layer.Layer):
    def __init__(self):
        super(SequenceGlobalMaxPooling1D, self).__init__()

        # Logging
        logging.info("Creating layer: {}".format(str(self)))

    def calc_output_size(self, input_size):
        return input_size / input_size

    def forward(self, x):
        # The input comes in as B x Li x E
        return torch.stack([torch.max(seq, dim=0)[0] for seq in x])


class GlobalAveragePooling1D(layer.Layer):
    def __init__(self):
        super(GlobalAveragePooling1D, self).__init__()

        # Logging
        logging.info("Creating layer: {}".format(str(self)))

    def calc_output_size(self, input_size):
        return input_size / input_size

    def forward(self, x):
        # The input comes in as B x L x E
        return torch.mean(x, dim=1)


class SequenceGlobalAveragePooling1D(layer.Layer):
    def __init__(self):
        super(SequenceGlobalAveragePooling1D, self).__init__()

        # Logging
        logging.info("Creating layer: {}".format(str(self)))

    def calc_output_size(self, input_size):
        return input_size / input_size

    def forward(self, x):
        # The input comes in as B x Li x E
        return torch.stack([torch.mean(seq, dim=0) for seq in x])


class KMaxPooling1D(layer.Layer):
    def __init__(self, k):
        super(KMaxPooling1D, self).__init__()
        self.k = k

        # Logging
        logging.info("Creating layer: {}".format(str(self)))

    def calc_output_size(self, input_size):
        return self.k * input_size / input_size

    def forward(self, x):
        # B x L x E
        return L.kmax_pooling(x, 1, self.k)

    def __str__(self):
        return self.__class__.__name__ + "(k=%s)" % self.k
