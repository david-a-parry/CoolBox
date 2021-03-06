import abc
import re

import numpy as np
from scipy.linalg import toeplitz
from scipy.ndimage import gaussian_filter
from scipy.signal import convolve2d

from coolbox.utilities.logtools import get_logger

log = get_logger(__name__)


class FetchHiC(abc.ABC):
    SMALL_VALUE = 1e-12

    def fetch_data(self, genome_range1, genome_range2=None, resolution=None):
        """
        Parameters
        ----------
        genome_range1 : {str, GenomeRange}

        genome_range2 : {str, GenomeRange}, optional.

        resolution : {int, 'auto'}, optional

        Return
        ------
        matrix : np.array
            Hi-C contact matrix.
        """
        if resolution is None:
            resolution = self.properties['resolution']
        arr = self.fetch_matrix(genome_range1, genome_range2, resolution=resolution)
        return self.normalize_matrix(arr)

    def normalize_matrix(self, arr: np.ndarray) -> np.ndarray:

        # process the matrix
        if 'transform' in self.properties and self.properties['transform'] != 'no':
            arr = self.__transform_matrix(arr)
        if 'normalize' in self.properties and self.properties['normalize'] != 'no':
            arr = self.__normalize_matrix(arr)
        if 'gaussian_sigma' in self.properties and self.properties['gaussian_sigma'] != 'no':
            arr = self.__gaussian_matrix(arr)
        if 'process_func' in self.properties and self.properties['process_func'] != 'no':
            # user-defined process function
            func = self.properties['process_func']
            try:
                if callable(func):
                    arr = func(arr)
                elif isinstance(func, str):
                    func = eval(func)
                    arr = func(arr)
                else:
                    raise ValueError("process_func")
            except Exception as e:
                log.error(str(e))
                raise ValueError(
                    "process_func should a one argument function "
                    "receive a matrix return a processed matrix.")
        return arr

    @abc.abstractmethod
    def fetch_pixels(self, genome_range, genome_range2=None, balance=None, resolution='auto'):
        pass

    @abc.abstractmethod
    def fetch_matrix(self, genome_range, genome_range2=None, resolution='auto') -> np.ndarray:
        pass

    def fill_zero_nan(self, arr):
        # fill zero and nan with small value
        small = self.SMALL_VALUE
        zero_indices = arr == 0
        nan_indices = np.isnan(arr)
        self.zero_indices = zero_indices
        self.nan_indices = nan_indices
        arr[zero_indices] = small
        arr[nan_indices] = small
        return arr

    @staticmethod
    def diagonal_mean(mat):
        return [np.diagonal(mat, i).mean() for i in range(mat.shape[0])]

    @staticmethod
    def diagonal_mean_std(mat):
        means = []
        stds = []
        for i in range(mat.shape[0]):
            diagonal = np.diagonal(mat, i)
            means.append(diagonal.mean())
            stds.append(diagonal.std())
        stds = np.array(stds)
        stds[stds == 0] = stds[stds > 0].min()
        return means, stds

    @staticmethod
    def __donut_kernel(p, w):
        k1 = np.ones((2 * w + 1, 2 * w + 1))
        k2 = np.zeros((2 * w + 1, 2 * w + 1))
        k2[w - p:w + p + 1, w - p:w + p + 1] = 1
        k3 = np.zeros((2 * w + 1, 2 * w + 1))
        k3[:w - p, w] = 1
        k3[w, :w - p] = 1
        k3[w, w + 2 * p - 1:2 * w + 1] = 1
        k3[w + 2 * p - 1:2 * w + 1, w] = 1
        k = k1 - k2 - k3
        return k

    def __normalize_matrix(self, mat):
        norm_mth = self.properties['normalize']
        res = mat
        if norm_mth == 'total':
            total = np.sum(mat)
            if total != 0:
                res = mat / total
        elif norm_mth == 'expect':
            means = self.diagonal_mean(mat)
            expect = toeplitz(means)
            res = mat / expect
        elif norm_mth == 'zscore':
            means, stds = self.diagonal_mean_std(mat)
            mat_mean = toeplitz(means)
            mat_std = toeplitz(stds)
            res = (mat - mat_mean) / mat_std
        elif re.match("hiccups:.:.", norm_mth):
            p, w = norm_mth.strip("hiccups:").split(":")
            p, w = int(w), int(p)
            kernel = self.__donut_kernel(p, w)

            def apply_donut(m):
                m_ext = np.zeros((m.shape[0] + 2 * (w - 1), m.shape[0] + 2 * (w - 1)))
                idx_center = slice(w, w + m.shape[0]), slice(w, w + m.shape[1])
                m_ext[idx_center] = m
                m_f = convolve2d(m_ext, kernel, mode='same')
                m_f = m_f[idx_center]
                return m_f

            means = self.diagonal_mean(mat)
            exp_decay = toeplitz(means)
            m_donut = apply_donut(mat)
            exp_donut = apply_donut(exp_decay)
            exp = (m_donut / exp_donut) * exp_decay
            res = mat / exp

        return res

    def __transform_matrix(self, arr):
        if self.properties['transform'] == 'log10':
            arr = np.log10(arr)
        elif self.properties['transform'] == 'log2':
            arr = np.log2(arr)
        elif self.properties['transform'] == 'log':
            arr = np.log(arr)
        return arr

    def __gaussian_matrix(self, arr):
        sigma = self.properties['gaussian_sigma']
        arr = gaussian_filter(arr, sigma)
        return arr
