# Copyright 2022 MosaicML Composer authors
# SPDX-License-Identifier: Apache-2.0

"""Enum class for the numerical precision to be used by the model."""

import contextlib
import os
import textwrap
from typing import Any, Dict, Generator, Optional, Union
import logging
import torch

from composer.utils import StringEnum

try:
    import transformer_engine.pytorch as te
    te_installed = True
except ImportError:
    te_installed = False

__all__ = ['Precision', 'get_precision_context']


class Precision(StringEnum):
    """Enum class for the numerical precision to be used by the model.

    Attributes:
        FP32: Use 32-bit floating-point precision. Compatible with CPUs and GPUs.
        AMP_FP16: Use :mod:`torch.cuda.amp` with 16-bit floating-point precision. Only compatible
            with GPUs.
        AMP_BF16: Use :mod:`torch.cuda.amp` with 16-bit BFloat precision.
        AMP_FP8: Use :mod:`transformer_engine.pytorch.fp8_autocast` with 8-bit FP8 precison.
    """
    FP32 = 'fp32'
    AMP_FP16 = 'amp_fp16'
    AMP_BF16 = 'amp_bf16'
    AMP_FP8 = 'amp_fp8'


@contextlib.contextmanager
def get_precision_context(precision: Union[str, Precision],
                          precision_config: Optional[Dict[str, Any]] = None) -> Generator[None, None, None]:
    """Returns a context manager to automatically cast to a specific precision.

    Args:
        precision (str | Precision): Precision for the context
        precision_config (Optional[Dict[str, Any]]): Config for FP8 scaling strategy. See parameters for
            `DelayedScaling <https://docs.nvidia.com/deeplearning/transformer-engine/user-guide/api/common.html?highlight=delayedscaling#transformer_engine.common.recipe.DelayedScaling>`_.
    """
    precision = Precision(precision)
    if precision == Precision.FP32:
        if torch.cuda.is_available():
            with torch.cuda.amp.autocast(False):
                yield
        else:
            # Yield here to avoid warnings about cuda not being available
            yield
    elif precision == Precision.AMP_FP16:
        # Retain compatibility with PyTorch < 1.10
        with torch.cuda.amp.autocast(True):
            yield
    elif precision == Precision.AMP_BF16:
        if torch.cuda.is_available():
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                yield
        else:
            os.environ['XLA_USE_BF16'] = '1'
            yield
    elif precision == Precision.AMP_FP8:
        if te_installed and torch.cuda.get_device_capability() >= (8, 9):
            from transformer_engine.common.recipe import DelayedScaling, Format

            if precision_config is None:
                precision_config = {
                    'fp8_format': Format.HYBRID,
                    'amax_history_len': 16,
                    'amax_compute_algo': 'max',
                }
            fp8_recipe = DelayedScaling(**precision_config)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                with te.fp8_autocast(enabled=True, fp8_recipe=fp8_recipe):
                    yield
        else:
            if te_installed:
                raise RuntimeError('AMP_FP8 precision is used but current device does not support it.')
            else:
                raise ImportError(
                    textwrap.dedent("""\
                        AMP_FP8 precision is used but TransformerEngine is not installed.
                        After making sure torch is already installed, please install it using
                        pip install --upgrade git+https://github.com/NVIDIA/TransformerEngine.git@stable"""))
    else:
        raise ValueError(f'Unsupported precision: {precision}')
