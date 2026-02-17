#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@author Andrew Reed
@brief Implementation of Art Newhall's MATLAB survey software

"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def dms_to_dd(degrees, minutes, seconds, direction=None):
    """
    Convert degrees, minutes, seconds to decimal degrees.
    """
    if direction is None:
        # First, check the sign on the degrees to determine direction
        direction = np.where(np.asarray(degrees) < 0, 'S', 'W')
    # Convert inputs to numpy arrays (this also handles scalars)
    degrees = np.asarray(degrees, dtype=float)
    minutes = np.asarray(minutes, dtype=float)
    seconds = np.asarray(seconds, dtype=float)
    direction = np.asarray(direction)

    # Compute decimal degrees
    dd = degrees + minutes / 60 + seconds / 3600

    # Apply negative sign for south/west
    mask = np.isin(direction, ['S', 'W'])
    dd = np.where(mask, -dd, dd)

    # Return scalar if input was scalar
    if (np.isscalar(degrees) and np.isscalar(minutes)
            and np.isscalar(seconds) and np.isscalar(direction)):
        return float(dd)
    return dd


def latlon_to_xy(lat, lon, ref_lat, ref_lon):
    """
    Convert latitude and longitude to local x, y coordinates in meters
    relative to a reference latitude and longitude.

    Parameters
    ----------
    lat : array-like
        Latitudes to convert.
    lon : array-like
        Longitudes to convert.
    ref_lat : float
        Reference latitude.
    ref_lon : float
        Reference longitude.

    Returns
    -------
    x : array-like
        X coordinates in meters.
    y : array-like
        Y coordinates in meters.
    """
    # Approximate conversion factors
    R = 6371000  # Earth radius in meters
    dlat = np.radians(lat - ref_lat)
    dlon = np.radians(lon - ref_lon)
    x = R * dlon * np.cos(np.radians(ref_lat))
    y = R * dlat
    return x, y


def xy_to_latlon(x, y, ref_lat, ref_lon):
    """
    Convert local x,y coordinates back to latitude and longitude.

    Parameters:
    -----------
    x : float
        Local x coordinate (meters).
    y : float
        Local y coordinate (meters).
    ref_lat : float
        Reference latitude (degrees).
    ref_lon : float
        Reference longitude (degrees).

    Returns:
    --------
    lat : float
        Latitude (degrees).
    lon : float
        Longitude (degrees).
    """
    R = 6371000  # Earth radius in meters
    dlat = y / R
    dlon = x / (R * np.cos(np.radians(ref_lat)))
    lat = ref_lat + np.degrees(dlat)
    lon = ref_lon + np.degrees(dlon)
    return lat, lon


def calculate_anchor_position(x, y, d, tol=0.01, max_iter=100):
    """
    Calculate anchor given ship and drop positions and horizontal range.

    Parameters:
    ----------
    x : array_like
        Ship/station x positions (meters).
    y : array_like
        Ship/station y positions (meters).
    d : array_like
        Horizontal ranges from ship to drop (meters).
    tol : float
        Tolerance for convergence (meters).
    max_iter : int
        Maximum number of iterations.

    Returns:
    -------
    xi: float
        Estimated anchor x position (meters).
    yi: float
        Estimated anchor y position (meters).
    iterations: int
        Number of iterations performed.
    """
    # Initial guess for anchor position
    xi = np.mean(x)
    yi = np.mean(y)
    xx = [1.0, 1.0]

    for iteration in range(max_iter):
        # Calculate distances from estimated anchor to ship positions
        A = [2 * (x-xi),  2 * (y-yi)]
        b = (x-xi)**2 + (y-yi)**2 - d**2

        # Solve linear system to get residuals
        xx, residuals, rank, s = np.linalg.lstsq(np.transpose(A),
                                                 b, rcond=None)

        # Update positions
        xi = xi + xx[0]
        yi = yi + xx[1]

        # Check for convergence
        if np.linalg.norm(xx) < tol:
            break

    return xi, yi, iteration


def rms_error(p, x, y, dist):
    """
    Calculate the RMS error between calculated and measured distances.
    """
    xi, yi = p
    r = np.sqrt((x - xi)**2 + (y - yi)**2)
    return np.sqrt(np.mean((r - dist)**2))


def calculate_fallback(anchor_x, anchor_y, drop_x, drop_y):
    """
    Calculate the estimate fallback from the drop position
    to the surveyed anchor position.
    """
    fallback = np.sqrt((anchor_x - drop_x)**2 + (anchor_y - drop_y)**2)
    return fallback


if __name__ == '__main__':
    # Read in the stations data
    stations = pd.read_csv('stations.dat', delim_whitespace=True,
                           header=None).to_numpy()

    # Convert to decimal degrees
    station_lats = dms_to_dd(stations[:, 0], stations[:, 1], 0, 'N')
    station_lons = dms_to_dd(stations[:, 2], stations[:, 3], 0, 'W')
    times = np.asarray(stations[:, 4], dtype=float)

    # Similarly, read in the drop positions and drop_depth
    drop_data = [35, 57.068, 75, 7.822, 36]
    drop_lat = dms_to_dd(drop_data[0], drop_data[1], 0, 'N')
    drop_lon = dms_to_dd(drop_data[2], drop_data[3], 0, 'W')
    drop_depth = drop_data[4]  # in meters

    # Now set the other constants
    trans_depth = 5.0  # ship transducer depth (positive down)
    sound_speed = 1500.0  # sound speed in water (m/s)

    # Calculate the station depths
    # assuming same transducer depth for all stations
    station_depths = np.tile(trans_depth, station_lats.shape)

    # Next, want to start the triangulation process
    # First, set the reference latitude and longitude
    ref_lat = drop_lat
    ref_lon = drop_lon

    # Next, convert to local distances (in meters)
    station_x, station_y = latlon_to_xy(station_lats, station_lons,
                                        ref_lat, ref_lon)
    drop_x, drop_y = latlon_to_xy(drop_lat, drop_lon, ref_lat, ref_lon)

    # Next, calculate the slant and horizontal ranges
    slant_range = (times / 2) * sound_speed
    horizontal_range = np.sqrt(slant_range**2 - (drop_depth - trans_depth)**2)

    # Calculate the anchor positions
    anchor_x, anchor_y, iterations = calculate_anchor_position(
        station_x, station_y, horizontal_range)

    # Compute RMS error for the fitted results
    rms = rms_error((station_x, station_y), anchor_x,
                    anchor_y, horizontal_range)

    # Next, recompute the actual lat/lon from the xi, yi coordinates
    anchor_lat, anchor_lon = xy_to_latlon(anchor_x, anchor_y, ref_lat, ref_lon)

    # Now calculate the fallback
    fallback = calculate_fallback(anchor_lat, anchor_lon, drop_lat, drop_lon)
    print(f'Estimated anchor location: {np.round(anchor_lat, 4)} lat,'
          f'{np.round(anchor_lon, 4)} /n')
    print(f'Estimated fallback: {np.round(fallback, 2)} m')

    # --- Plot horizontal view ---
    fig, ax = plt.subplots(figsize=(6, 6))
    theta = np.linspace(0, 2*np.pi, 100)
    nstations = len(stations)
    for i in range(nstations):
        ax.plot(station_x[i] + horizontal_range[i]*np.cos(theta),
                station_y[i] + horizontal_range[i]*np.sin(theta),
                'b--')

    ax.plot(station_x, station_y, 'k*', label="Stations")
    ax.plot(anchor_x, anchor_y, 'ro', label="Estimated Anchor")
    ax.plot(np.nan, np.nan, linestyle='', label=f"Lat: {anchor_lat:.6f}")
    ax.plot(np.nan, np.nan, linestyle='', label=f"Lon: {anchor_lon:.6f}")
    ax.plot(np.nan, np.nan, linestyle='', label=f"RMS: {rms:.6f} m")

    ax.set_xlabel("East (m)")
    ax.set_ylabel("North (m)")
    ax.set_title("Anchor Triangulation (Horizontal View)")
    ax.axis('equal')
    ax.legend()
    ax.grid()
    plt.show()
