#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@author Andrew Reed
@brief Unit tests for survey.py
"""

import numpy as np
from cruise_tools.anchor_survey.survey.survey import (
    dms_to_dd,
    latlon_to_xy,
    xy_to_latlon,
    calculate_anchor_position,
    rms_error,
    calculate_fallback,
)


def test_dms_to_dd_scalar():
    # 35°57'4" N should be about 35.9511
    dd = dms_to_dd(35, 57, 4, 'N')
    assert np.isclose(dd, 35.9511, atol=1e-4)

    # 75°7'49" W should be about -75.1303
    dd = dms_to_dd(75, 7, 49, 'W')
    assert np.isclose(dd, -75.1303, atol=1e-4)


def test_latlon_xy_conversion_roundtrip():
    lat, lon = 35.9511, -75.1303
    ref_lat, ref_lon = lat, lon
    x, y = latlon_to_xy(lat, lon, ref_lat, ref_lon)
    lat2, lon2 = xy_to_latlon(x, y, ref_lat, ref_lon)
    assert np.isclose(lat, lat2, atol=1e-6)
    assert np.isclose(lon, lon2, atol=1e-6)


def test_calculate_anchor_position():
    # Simple geometry test: three stations at known offsets
    x = np.array([0.0, 100.0, 0.0])
    y = np.array([0.0, 0.0, 100.0])
    true_anchor = (50.0, 50.0)
    d = np.sqrt((x - true_anchor[0])**2 + (y - true_anchor[1])**2)
    xi, yi, iters = calculate_anchor_position(x, y, d)
    assert np.isclose(xi, true_anchor[0], atol=1e-3)
    assert np.isclose(yi, true_anchor[1], atol=1e-3)
    assert iters < 20


def test_rms_error_simple():
    x = np.array([0, 1])
    y = np.array([0, 0])
    dist = np.array([1, 0])
    p = (0, 0)
    err = rms_error(p, x, y, dist)
    assert err >= 0


def test_calculate_fallback_distance():
    drop_lat, drop_lon = 35.9511, -75.1303
    anchor_lat, anchor_lon = 35.9515, -75.1301
    fb = calculate_fallback(anchor_lat, anchor_lon, drop_lat, drop_lon)
    assert fb > 0
    assert fb < 100  # should be only a few tens of meters apart
