import torch
from torch.autograd import Variable
import torch.nn.functional as F

epsilon = 1e-11

# Optimization for casting things to cuda tensors


def cudaFloatTensor(x):
    return torch.FloatTensor(x).cuda()


def cudaLongTensor(x):
    return torch.LongTensor(x).cuda()


def cudaByteTensor(x):
    return torch.ByteTensor(x).cuda()


def flatten(x):
    """Flattens along axis 0 (# rows in == # rows out)"""
    return x.view(x.size(0), -1)


def softmax(x):
    # BUG some shape error
    normalized_exp = (x - x.max(1)[0].expand(*x.size())).exp()  # .clamp(epsilon, 1.)
    return normalized_exp / normalized_exp.sum(1).expand(*x.size())


def zero_center(x):
    return (x - x.mean().expand(*x.size()))


def standardize(x):
    std = (x.pow(2).mean() - x.mean().pow(2)).sqrt()
    return zero_center(x) / std.expand(*x.size()).clamp(min=epsilon)


# Set up the use of cuda if available
use_cuda = torch.cuda.is_available()
# use_cuda = False
FloatTensor = cudaFloatTensor if use_cuda else torch.FloatTensor
LongTensor = cudaLongTensor if use_cuda else torch.LongTensor
ByteTensor = cudaByteTensor if use_cuda else torch.ByteTensor
Tensor = FloatTensor

print("PyJet is using " + ("CUDA" if use_cuda else "CPU") + ".")
