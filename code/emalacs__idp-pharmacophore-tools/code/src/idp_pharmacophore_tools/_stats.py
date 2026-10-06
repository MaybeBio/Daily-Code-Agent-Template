import math

import numpy as np

from ._deps import pyblock, PYBLOCK_AVAILABLE


def get_blockerrors_pyblock_nanskip(Data: np.ndarray, bound_frac: float):
    """Per-column mean and block error using the pyblock library.

    Falls back to zero error when pyblock is unavailable or the column is
    constant (average == 0 or 1).

    Parameters
    ----------
    Data : np.ndarray, shape (n_frames, n_columns)
    bound_frac : float
        Divisor applied to both average and error (use 1.0 for no scaling).

    Returns
    -------
    (ave, be) : two np.ndarrays of shape (n_columns,)
    """
    n_cols = Data.shape[1]
    ave, block_errors = [], []
    for i in range(n_cols):
        col     = Data[:, i]
        average = np.average(col)
        if pyblock is not None and average not in (0.0, 1.0):
            reblock_data = pyblock.blocking.reblock(col)
            opt = pyblock.blocking.find_optimal_block(len(col), reblock_data)[0]
            if math.isnan(opt):
                be = max(row[4] for row in reblock_data)
            else:
                be = reblock_data[opt][4]
        else:
            be = 0.0
        ave.append(average)
        block_errors.append(be)
    return np.asarray(ave) / bound_frac, np.asarray(block_errors) / bound_frac


def get_blockerror_pyblock_nanskip(data: np.ndarray):
    """Block error for a single 1-D array (scalar average + scalar error).

    Used internally by get_Kd(). Returns (average, block_error).
    """
    average = np.average(data)
    if pyblock is not None and average not in (0.0, 1.0):
        reblock_data = pyblock.blocking.reblock(data)
        opt = pyblock.blocking.find_optimal_block(len(data), reblock_data)[0]
        if math.isnan(opt):
            be = max(row[4] for row in reblock_data)
        else:
            be = reblock_data[opt][4]
    else:
        be = 0.0
    return average, float(be)
