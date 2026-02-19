# -*- coding: utf-8 -*-
# Copyright (c) 2025 maintainers@energycrawler.local
#
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#
# This module provides Energy browser adapters for supported media platforms.

from .xhs_adapter import XHSEnergyAdapter, create_xhs_energy_adapter

__all__ = [
    # XHS
    'XHSEnergyAdapter',
    'create_xhs_energy_adapter',
]
