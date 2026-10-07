"""LossCurve: training vs validation loss for a fitted XGBoost, LightGBM or CatBoost model."""
import matplotlib.pyplot as plt
import numpy as np


class LossCurve:
    """Holds the loss after each tree, for training and validation data."""

    def __init__(self, train, val, metric="loss", name="model"):
        self.train = np.asarray(train, dtype=float)
        self.val = np.asarray(val, dtype=float)
        self.metric = metric
        self.name = name
        if len(self.train) != len(self.val):
            raise ValueError("train and val must have one value per tree each")

    @classmethod
    def from_model(cls, model, name=None):
        """Read the history a fitted model recorded. It must have been fit with an eval_set."""
        if hasattr(model, "get_evals_result"):        # CatBoost
            history = model.get_evals_result()
        elif hasattr(model, "evals_result_"):         # LightGBM
            history = model.evals_result_
        elif hasattr(model, "evals_result"):          # XGBoost
            history = model.evals_result()
        else:
            raise TypeError(f"Don't know how to read a history from {type(model).__name__}")

        sets = list(history.values())                 # first = training, last = validation
        if len(sets) < 2:
            raise ValueError("Need both training and validation history; pass both in eval_set")
        metric = next(iter(sets[0]))                  # first metric the model tracked
        return cls(sets[0][metric], sets[-1][metric], metric, name or type(model).__name__)

    @property
    def best_iteration(self):
        """The tree count where validation loss is lowest."""
        return int(np.argmin(self.val))

    @property
    def best_loss(self):
        return float(self.val.min())

    @property
    def gap(self):
        """How much worse validation is than training at the best point."""
        return float(self.val[self.best_iteration] - self.train[self.best_iteration])

    def diagnose(self):
        """A one-line reading of the curve's shape."""
        last, best = len(self.val) - 1, self.best_iteration
        if best >= last - 1:
            return "Still improving at the last tree: allow more trees."
        if self.val[last] > self.best_loss * 1.02:
            return f"Overfitting after tree {best}: validation loss rises from there."
        return f"Leveled off around tree {best}: more trees won't help, better features might."

    def plot(self, ax=None):
        ax = ax or plt.subplots(figsize=(7, 4))[1]
        ax.plot(self.train, label="train")
        ax.plot(self.val, label="validation")
        ax.axvline(self.best_iteration, linestyle="--", color="gray",
                   label=f"best: tree {self.best_iteration}")
        ax.set_xlabel("Number of trees")
        ax.set_ylabel(self.metric)
        ax.set_title(f"{self.name} loss curve")
        ax.legend()
        return ax

    def __repr__(self):
        return (f"LossCurve({self.name}: best {self.metric} {self.best_loss:.4f} "
                f"at tree {self.best_iteration}, gap {self.gap:.4f})")