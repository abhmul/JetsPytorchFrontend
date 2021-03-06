import copy


class Metric(object):
    """
    The abstract metric that defines the metric API. Some notes on it:

    - Passing a function of the form `metric(y_pred, y_true)` to an abstract
    metric will use that function to calculate the score on a batch.

    - The accumulate method is called at the end of each batch to calculate the
    aggregate score over the entire epoch thus far.
        - See `AverageMetric` for an example what an accumulate method might
        look like.

    - The reset method is called at the end of each epoch or validation run. It
    simply overwrites the attributes of the metric with its attributes at
    initialization.

    Metrics are callable like any fuction and take as input:
    ```
    batch_score = metric(y_pred, y_true)
    ```
    where `y_true` are the labels for the batch and `y_pred` are the
    predictions

    To implement your own custom metric, override the `score` function and
    the `accumulate` function. If you just want to average the scores over
    the epoch, consider using `AverageMetric` and just overriding the `score`
    function.
    """
    def __init__(self, metric_func=None):
        self.metric_func = metric_func
        self.__name__ = self.__class__.__name__.lower() \
            if metric_func is None else metric_func.__name__
        self.__original_dict__ = None

    def __call__(self, y_pred, y_true):
        """
        Makes the metric a callable function. Used by some metrics to perform
        some overhead work like checking validity of the input, or storing
        values like batch size or input shape.
        """
        # Save the original dict on the first call
        if self.__original_dict__ is None:
            self.__original_dict__ = copy.deepcopy(self.__dict__)
        # Default metric will just score the predictions
        return self.score(y_pred, y_true)

    def score(self, y_pred, y_true):
        """
        Calculates the metric score over a batch of labels and predictions.

        Args:
            y_pred: The predictions for the batch
            y_true: The labels for the batch

        Returns:
            The metric score calculated over the batch input as a scalar
            torch tensor.
        """
        if self.metric_func is not None:
            return self.metric_func(y_pred, y_true)
        else:
            raise NotImplementedError()

    def accumulate(self):
        """
        """
        raise NotImplementedError()

    def reset(self):
        if self.__original_dict__ is not None:
            self.__dict__ = copy.deepcopy(self.__original_dict__)
        return self


class AverageMetric(Metric):
    """
    An abstract metric that accumulates the batch values from the metric
    by averaging them together. If any function is input into the fit
    function as a metric, it will automatically be considered an AverageMetric.
    """
    def __init__(self, metric_func=None):
        super(AverageMetric, self).__init__(metric_func=metric_func)
        self.metric_sum = 0.
        self.sample_count = 0

    def __call__(self, y_pred, y_true):
        assert y_true.size(0) == y_pred.size(0), "Batch Size of labels and" \
            "predictions must match for AverageMetric."
        score = super(AverageMetric, self).__call__(y_pred, y_true)
        self.sample_count += y_pred.size(0)
        self.metric_sum += (score.item() * y_pred.size(0))
        return score

    def accumulate(self):
        return self.metric_sum / self.sample_count
