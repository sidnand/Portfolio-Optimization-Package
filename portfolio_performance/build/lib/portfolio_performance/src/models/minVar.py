import numpy as np

from ..modelNoGamma import ModelNoGamma


class MinVar(ModelNoGamma):
    def __init__(self, name):
        super().__init__(name)

    def alpha(self, invSigmaMLE, amle, n):
        return (1/amle) * invSigmaMLE @ np.ones((n - 1, 1))