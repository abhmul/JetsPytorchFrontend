import time
from collections import deque
import numpy as np
import warnings
from tqdm import tqdm

from . import utils

try:
    import matplotlib
    import matplotlib.pyplot as plt
except ImportError:
    matplotlib = None
    plt = None


class CallbackList(object):
    """Container abstracting a list of callbacks.
    # Arguments
        callbacks: List of `Callback` instances.
        queue_length: Queue length for keeping
            running statistics over callback execution time.
    """

    def __init__(self, callbacks=None, queue_length=10):
        callbacks = callbacks or []
        self.callbacks = [c for c in callbacks]
        self.queue_length = queue_length

    def append(self, callback):
        self.callbacks.append(callback)

    def set_model(self, model):
        for callback in self.callbacks:
            callback.set_model(model)

    def release_model(self):
        for callback in self.callbacks:
            callback.release_model()

    def on_epoch_begin(self, logs):
        """Called at the start of an epoch.
        # Arguments
            epoch: integer, index of epoch.
            logs: dictionary of logs.
        """
        for callback in self.callbacks:
            callback.on_epoch_begin(logs)
        self._delta_t_batch = 0.0
        self._delta_ts_batch_begin = deque([], maxlen=self.queue_length)
        self._delta_ts_batch_end = deque([], maxlen=self.queue_length)

    def on_epoch_end(self, logs):
        """Called at the end of an epoch.
        # Arguments
            epoch: integer, index of epoch.
            logs: dictionary of logs.
        """
        for callback in self.callbacks:
            callback.on_epoch_end(logs)

    def on_batch_begin(self, logs):
        """Called right before processing a batch.
        # Arguments
            batch: integer, index of batch within the current epoch.
            logs: dictionary of logs.
        """
        t_before_callbacks = time.time()

        for callback in self.callbacks:
            callback.on_batch_begin(logs)

        self._delta_ts_batch_begin.append(time.time() - t_before_callbacks)
        delta_t_median = np.median(self._delta_ts_batch_begin)
        if (
            self._delta_t_batch > 0.0
            and delta_t_median > 0.95 * self._delta_t_batch
            and delta_t_median > 0.1
        ):
            warnings.warn(
                "Method on_batch_begin() is slow compared "
                "to the batch update (%f). Check your callbacks." % delta_t_median
            )
        self._t_enter_batch = time.time()

    def on_batch_end(self, logs):
        """Called at the end of a batch.
        # Arguments
            batch: integer, index of batch within the current epoch.
            logs: dictionary of logs.
        """
        if not hasattr(self, "_t_enter_batch"):
            self._t_enter_batch = time.time()
        self._delta_t_batch = time.time() - self._t_enter_batch

        t_before_callbacks = time.time()
        for callback in self.callbacks:
            callback.on_batch_end(logs)

        self._delta_ts_batch_end.append(time.time() - t_before_callbacks)
        delta_t_median = np.median(self._delta_ts_batch_end)
        if self._delta_t_batch > 0.0 and (
            delta_t_median > 0.95 * self._delta_t_batch and delta_t_median > 0.1
        ):
            warnings.warn(
                "Method on_batch_end() is slow compared "
                "to the batch update (%f). Check your callbacks." % delta_t_median
            )

    def on_train_begin(self, logs):
        """Called at the beginning of training.
        # Arguments
            logs: dictionary of logs.
        """
        for callback in self.callbacks:
            callback.on_train_begin(logs)

    def on_train_end(self, logs):
        """Called at the end of training.
        # Arguments
            logs: dictionary of logs.
        """
        for callback in self.callbacks:
            callback.on_train_end(logs)

    def __iter__(self):
        return iter(self.callbacks)


class Callback(object):
    """Abstract base class used to build new callbacks.
    # Properties
        params: dict. Training parameters
            (eg. verbosity, batch size, number of epochs...).
        model: instance of `keras.models.Model`.
            Reference of the model being trained.
    The `logs` dictionary that callback methods
    take as argument will contain keys for quantities relevant to
    the current batch or epoch.
    Currently, the `.fit()` method of the `Sequential` model class
    will include the following quantities in the `logs` that
    it passes to its callbacks:
        on_epoch_end: logs include `acc` and `loss`, and
            optionally include `val_loss`
            (if validation is enabled in `fit`), and `val_acc`
            (if validation and accuracy monitoring are enabled).
        on_batch_begin: logs include `size`,
            the number of samples in the current batch.
        on_batch_end: logs include `loss`, and optionally `acc`
            (if accuracy monitoring is enabled).
    """

    def __init__(self):
        self.validation_data = None

    def set_model(self, model):
        self.model = model

    def release_model(self):
        self.model = None

    def on_epoch_begin(self, logs):
        pass

    def on_epoch_end(self, logs):
        pass

    def on_batch_begin(self, logs):
        pass

    def on_batch_end(self, logs):
        pass

    def on_train_begin(self, logs):
        pass

    def on_train_end(self, logs):
        pass


class ProgressBar(Callback):
    def __init__(self, steps_per_epoch, total_epochs=0):
        super(ProgressBar, self).__init__()
        self.steps_per_epoch = steps_per_epoch
        self.total_epochs = total_epochs
        self.last_step = 0
        self.progbar = None

    def on_epoch_begin(self, logs):
        epoch = logs.epochs
        if self.total_epochs:
            print(
                "Epoch {curr}/{total}".format(curr=epoch + 1, total=self.total_epochs)
            )
        # Create a new progress bar for the epoch
        self.progbar = tqdm(total=self.steps_per_epoch)
        self.last_step = 0

    def on_batch_end(self, logs):
        current_steps = logs.epoch_steps
        self.progbar.set_postfix(logs.epoch_logs)
        self.progbar.update(current_steps - self.last_step)
        self.last_step = current_steps

    def on_epoch_end(self, logs):
        self.progbar.set_postfix(logs.epoch_logs)
        # 0 because we've already finished all steps
        self.progbar.update(0)
        self.progbar.close()


class ModelCheckpoint(Callback):
    """Save the model after every epoch.
    `filepath` can contain named formatting options,
    which will be filled the value of `epoch` and
    keys in `logs` (passed in `on_epoch_end`).
    For example: if `filepath` is `weights.{epoch:02d}-{val_loss:.2f}.hdf5`,
    then the model checkpoints will be saved with the epoch number and
    the validation loss in the filename.
    # Arguments
        filepath: string, path to save the model file.
        monitor: quantity to monitor.
        monitor_val: whether or not to monitor the validation quantity.
        verbose: verbosity mode, 0 or 1.
        save_best_only: if `save_best_only=True`,
            the latest best model according to
            the quantity monitored will not be overwritten.
        mode: one of {auto, min, max}.
            If `save_best_only=True`, the decision
            to overwrite the current save file is made
            based on either the maximization or the
            minimization of the monitored quantity. For `val_acc`,
            this should be `max`, for `val_loss` this should
            be `min`, etc. In `auto` mode, the direction is
            automatically inferred from the name of the monitored quantity.
        save_weights_only: if True, then only the model's weights will be
            saved (`model.save_weights(filepath)`), else the full model
            is saved (`model.save(filepath)`).
        period: Interval (number of epochs) between checkpoints.
    """

    def __init__(
        self, filepath, monitor, verbose=0, save_best_only=False, mode="auto", period=1
    ):
        super(ModelCheckpoint, self).__init__()
        self.monitor = monitor
        self.verbose = verbose
        self.filepath = filepath
        self.save_best_only = save_best_only
        self.period = period
        self.epochs_since_last_save = 0

        if mode not in ["auto", "min", "max"]:
            warnings.warn(
                "ModelCheckpoint mode %s is unknown, "
                "fallback to auto mode." % (mode),
                RuntimeWarning,
            )
            mode = "auto"

        if mode == "min":
            self.monitor_op = np.less
            self.best = np.Inf
        elif mode == "max":
            self.monitor_op = np.greater
            self.best = -np.Inf
        else:
            if (
                "acc" in self.monitor
                or "auc" in self.monitor
                or "iou" in self.monitor
                or self.monitor.startswith("fmeasure")
            ):
                self.monitor_op = np.greater
                self.best = -np.Inf
            else:
                self.monitor_op = np.less
                self.best = np.Inf

    def on_epoch_end(self, logs):
        epoch = logs.epochs
        logs = logs.epoch_logs

        self.epochs_since_last_save += 1
        # Continue if we haven't reached the period
        if self.epochs_since_last_save < self.period:
            return

        filepath = self.filepath.format(epoch=epoch)
        if self.save_best_only:
            current = logs[self.monitor]
            if current is None:
                warnings.warn(
                    "Can save best model only with %s available, "
                    "skipping." % self.monitor,
                    RuntimeWarning,
                )
            else:
                if self.monitor_op(current, self.best):
                    if self.verbose > 0:
                        print(
                            "Epoch %05d: %s improved from %0.5f to %0.5f,"
                            " saving model to %s"
                            % (epoch, self.monitor, self.best, current, filepath)
                        )
                    self.best = current
                    self.model.save_state(filepath)
                    self.epochs_since_last_save = 0
                else:
                    if self.verbose > 0:
                        print("Epoch %05d: %s did not improve" % (epoch, self.monitor))
        else:
            if self.verbose > 0:
                print("Epoch %05d: saving model to %s" % (epoch, filepath))
            self.model.save_state(filepath)
            self.epochs_since_last_save = 0


class Plotter(Callback):
    def __init__(
        self,
        monitor,
        scale="linear",
        plot_during_train=True,
        save_to_file=None,
        block_on_end=True,
    ):
        super().__init__()
        if plt is None:
            raise ValueError("Must be able to import Matplotlib to use the Plotter.")
        self.scale = scale
        self.monitor = monitor
        self.plot_during_train = plot_during_train
        self.save_to_file = save_to_file
        self.block_on_end = block_on_end

        if self.plot_during_train:
            plt.ion()

        self.fig = plt.figure()
        self.title = "{} per Epoch".format(self.monitor)
        self.xlabel = "Epoch"
        self.ylabel = self.monitor
        self.ax = self.fig.add_subplot(
            111, title=self.title, xlabel=self.xlabel, ylabel=self.ylabel
        )
        self.ax.set_yscale(self.scale)
        self.x = []
        self.y_train = []
        self.y_val = []

    def on_train_end(self, logs):
        if self.plot_during_train:
            plt.ioff()
        if self.block_on_end:
            plt.show()
        return

    def on_epoch_end(self, logs):
        logs = logs.epoch_logs

        self.x.append(len(self.x))
        self.y_train.append(logs[self.monitor])
        self.y_val.append(logs["val_" + self.monitor])
        self.ax.clear()
        # # Set up the plot
        self.fig.suptitle(self.title)

        self.ax.set_yscale(self.scale)
        # Actually plot
        self.ax.plot(self.x, self.y_train, "b-", self.x, self.y_val, "g-")
        self.fig.canvas.draw()
        # plt.pause(0.5)
        if self.save_to_file is not None:
            self.fig.savefig(self.save_to_file)
        return


# TODO: Change the name to something that implies its real role more. This can change any learning parameter, not just LR.
# Todo: Consider making special optimizer class that we can pass a schedule?
class LRScheduler(Callback):
    def __init__(
        self,
        optimizer,
        schedule=lambda epoch: {},
        batch_schedule=lambda total_steps, steps_per_epoch: {},
        verbose=0,
    ):
        """A callback to execute a schedule for the parameters
        of an optimizer.
        
        Arguments:
            optimizer -- The pytorch optimizer to schedule
            schedule -- A function that takes as input the number of completed epochs
            batch_schedule -- A function that takes as input the number of completed training steps within an epoch and the number of completed epochs
        
        Keyword Arguments:
            verbose  -- (default: {0})
        """
        super().__init__()
        self.optimizer = optimizer
        self.schedule = schedule
        self.batch_schedule = batch_schedule
        self.verbose = verbose

    def on_epoch_begin(self, logs):
        epoch = logs.epochs

        new_param_dict = utils.standardize_dict_input(self.schedule(logs), default="lr")

        for param_name in new_param_dict:
            # Ignore params that aren't in the param group
            for param_group in self.optimizer.param_groups:
                if param_name not in param_group:
                    logging.warn(f"{param_name} not found in param group {param_group}")
                    continue
                param_group[param_name] = new_param_dict[param_name]
        if self.verbose > 0:
            print(
                f"\nEpoch {epoch+1}: LRScheduler setting {', '.join(f'{name}->{val}' for name, val in new_param_dict.values())}"
            )

    def on_batch_begin(self, logs):
        steps = logs.steps

        new_param_dict = utils.standardize_dict_input(
            self.batch_schedule(logs), default="lr"
        )

        for param_name in new_param_dict:
            # Ignore params that aren't in the param group
            for param_group in self.optimizer.param_groups:
                if param_name not in param_group:
                    logging.warn(f"{param_name} not found in param group {param_group}")
                    continue
                param_group[param_name] = new_param_dict[param_name]
        if self.verbose > 1:
            print(
                f"\{steps}: LRScheduler setting {', '.join(f'{name}->{val}' for name, val in new_param_dict.values())}"
            )


class OneCycleScheduler(LRScheduler):
    def __init__(self, optimizer, lr_range, momentum_range, period, verbose=0):
        self.period = period
        self.lr_range = lr_range
        self.momentum_range = momentum_range

        self.lr_start = lr_range[0]
        self.lr_amplitude = lr_range[1] - lr_range[0]
        self.momentum_start = momentum_range[0]
        self.momentum_amplitude = momentum_range[1] - momentum_range[0]

        self.lr = self.lr_start
        self.momentum = self.momentum_start

        def batch_schedule(logs):
            steps = logs.steps
            self.lr = self.get_step(steps, self.lr_start, self.lr_amplitude)
            self.momentum = self.get_step(
                steps, self.momentum_start, self.momentum_amplitude
            )
            return {"lr": self.lr, "momentum": self.momentum}

        super().__init__(optimizer, batch_schedule=batch_schedule)

    def get_step(self, total_steps, start_val, amplitude):
        half_period = self.period / 2
        change = (total_steps % half_period) / half_period * amplitude
        if self.period / 2 >= (total_steps % self.period):
            # In LR Ascension
            return change + start_val
        if self.period / 2 < (total_steps % self.period):
            return start_val + amplitude - change

