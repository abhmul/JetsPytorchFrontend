import logging
from functools import partialmethod

import torch
import torch.nn as nn

from . import layer
from . import layer_utils as utils


def build_rnn(
    rnn_type,
    input_size,
    output_size,
    num_layers=1,
    bidirectional=False,
    input_dropout=0.0,
    dropout=0.0,
):
    # Create the sequential
    layer = nn.Sequential()
    # Add the input dropout
    if input_dropout:
        layer.add_module(name="input-dropout", module=nn.Dropout(input_dropout))
    layer.add_module(
        name="rnn",
        module=RNN.layer_constructors[rnn_type](
            input_size,
            output_size,
            num_layers=num_layers,
            dropout=dropout,
            bidirectional=bidirectional,
            batch_first=True,
        ),
    )
    logging.info("Creating layer: %r" % layer)
    return layer


class RNN(layer.Layer):

    layer_constructors = {
        "gru": nn.GRU,
        "lstm": nn.LSTM,
        "tanh_simple": lambda *args, **kwargs: nn.RNN(
            *args, nonlinearity="tanh", **kwargs
        ),
        "relu_simple": lambda *args, **kwargs: nn.RNN(
            *args, nonlinearity="relu", **kwargs
        ),
    }

    def __init__(
        self,
        rnn_type,
        units,
        input_shape=None,
        num_layers=1,
        bidirectional=False,
        input_dropout=0.0,
        dropout=0.0,
        return_sequences=False,
        return_state=False,
    ):
        """The base RNN class. Used by specific RNN types to construct and RNN.
        
        Arguments:
            rnn_type {str} -- A string describing the RNN type {gru|lstm|tanh_simple|relu_simple}
            units {int} -- The number of output units in the RNN
        
        Keyword Arguments:
            input_shape {tuple[3]} -- A specific input size to make the rnn layer. Leave as None to infer the input shape. (default: {None})
            num_layers {int} -- The number of RNN layers to stack. (default: {1})
            bidirectional {bool} -- Whether or not to make this a bidirectional RNN (default: {False})
            input_dropout {float} -- Dropout to put on the input to the layer (default: {0.0})
            dropout {float} -- Dropout to put within the RNN (default: {0.0})
            return_sequences {bool} -- Whether or not to return the sequence of outputs rather than the final output (default: {False})
            return_state {bool} -- Whether or not to return the sequence of hidden states (default: {False})
        """
        super(RNN, self).__init__()
        units = units // 2 if bidirectional else units

        # Set up the attributes
        self.rnn_type = rnn_type
        self.input_shape = input_shape
        self.units = units
        self.num_layers = num_layers
        self.bidirectional = bidirectional
        self.input_dropout = input_dropout
        self.dropout = dropout
        self.return_sequences = return_sequences
        self.return_state = return_state

        # Build the layers
        self.rnn_layers = []
        # Registrations
        self.register_builder(self.__build_layer)

    def __build_layer(self, inputs):
        if self.input_shape is None:
            # We weren't passed in an input shape, so deduce from dummy inputs
            self.input_shape = utils.get_input_shape(inputs)
        self.rnn_layers = build_rnn(
            self.rnn_type,
            self.input_shape[-1],
            self.units,
            num_layers=self.num_layers,
            bidirectional=self.bidirectional,
            input_dropout=self.input_dropout,
            dropout=self.dropout,
        )

    def calc_output_size(self, input_size):
        return input_size

    def forward(self, x):
        x, states = self.rnn_layers(x)
        if not self.return_sequences:
            if self.bidirectional:
                x = torch.cat([x[:, -1, : self.units], x[:, 0, self.units :]], dim=-1)
            else:
                x = x[:, -1]
        if self.return_state:
            return x, states
        return x

    def reset_parameters(self):
        for layer in self.rnn_layers:
            if isinstance(layer, nn.RNNBase):
                logging.info("Resetting layer %s" % layer)
                layer.reset_parameters()

    def __str__(self):
        return ("%r\n\treturn_sequences={}, return_state={}" % self.rnn_layers).format(
            self.return_sequences, self.return_state
        )


class SimpleRNN(RNN):
    def __init__(
        self,
        units,
        input_shape=None,
        num_layers=1,
        bidirectional=False,
        input_dropout=0.0,
        dropout=0.0,
        return_sequences=False,
        return_state=False,
        nonlinearity="tanh",
    ):
        rnn_type = nonlinearity + "_" + "simple"
        super(SimpleRNN, self).__init__(
            rnn_type,
            units,
            input_shape=input_shape,
            num_layers=num_layers,
            bidirectional=bidirectional,
            input_dropout=input_dropout,
            dropout=dropout,
            return_sequences=return_sequences,
            return_state=return_state,
        )


class GRU(RNN):
    def __init__(
        self,
        units,
        input_shape=None,
        num_layers=1,
        bidirectional=False,
        input_dropout=0.0,
        dropout=0.0,
        return_sequences=False,
        return_state=False,
    ):
        super(GRU, self).__init__(
            "gru",
            units,
            input_shape=input_shape,
            num_layers=num_layers,
            bidirectional=bidirectional,
            input_dropout=input_dropout,
            dropout=dropout,
            return_sequences=return_sequences,
            return_state=return_state,
        )


class LSTM(RNN):
    def __init__(
        self,
        units,
        input_shape=None,
        num_layers=1,
        bidirectional=False,
        input_dropout=0.0,
        dropout=0.0,
        return_sequences=False,
        return_state=False,
    ):
        super(LSTM, self).__init__(
            "lstm",
            units,
            input_shape=input_shape,
            num_layers=num_layers,
            bidirectional=bidirectional,
            input_dropout=input_dropout,
            dropout=dropout,
            return_sequences=return_sequences,
            return_state=return_state,
        )

