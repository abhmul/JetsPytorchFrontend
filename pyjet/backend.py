import torch

# Set up the use of cuda if available
use_cuda = torch.cuda.is_available()
FloatTensor = torch.cuda.FloatTensor if use_cuda else torch.FloatTensor
LongTensor = torch.cuda.LongTensor if use_cuda else torch.LongTensor
ByteTensor = torch.cuda.ByteTensor if use_cuda else torch.ByteTensor
Tensor = FloatTensor

def flatten(x):
    """Flattens along axis 0 (# rows in == # rows out)"""
    return x.view(x.size(0), -1)