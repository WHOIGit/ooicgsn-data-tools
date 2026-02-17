#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@author Andrew Reed
@brief GUI for Art Newhall's MATLAB survey software using Panel
"""
import tempfile
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import panel as pn
from cruise_tools.anchor_survey.survey.survey import (
    dms_to_dd, latlon_to_xy, xy_to_latlon,
    calculate_anchor_position, rms_error, calculate_fallback
)


pn.extension('matplotlib')


# -----------------------------
# Core survey computation logic
# -----------------------------
def run_survey(station_file, trans_depth, drop_lat_dd, drop_lon_dd,
               drop_depth, sound_speed):
    if station_file is None:
        return "Please select a .dat file.", None
    try:
        stations = pd.read_csv(station_file, delim_whitespace=True,
                               header=None).to_numpy()
    except Exception as e:
        return f"Error reading file: {e}", None

    # Convert to decimal degrees
    station_lats = dms_to_dd(stations[:, 0], stations[:, 1], 0, 'N')
    station_lons = dms_to_dd(stations[:, 2], stations[:, 3], 0, 'W')
    times = np.asarray(stations[:, 4], dtype=float)

    ref_lat = drop_lat_dd
    ref_lon = drop_lon_dd

    station_x, station_y = latlon_to_xy(station_lats, station_lons,
                                        ref_lat, ref_lon)
    drop_x, drop_y = latlon_to_xy(drop_lat_dd, drop_lon_dd, ref_lat, ref_lon)

    slant_range = (times / 2) * sound_speed
    horizontal_range = np.sqrt(slant_range**2 - (drop_depth - trans_depth)**2)

    anchor_x, anchor_y, iterations = calculate_anchor_position(station_x,
                                                               station_y,
                                                               horizontal_range
                                                               )
    rms = rms_error((station_x, station_y), anchor_x, anchor_y,
                    horizontal_range)
    anchor_lat, anchor_lon = xy_to_latlon(anchor_x, anchor_y, ref_lat, ref_lon)
    fallback = calculate_fallback(anchor_x, anchor_y, drop_x, drop_y)

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(6, 6))
    theta = np.linspace(0, 2 * np.pi, 100)
    for i in range(len(stations)):
        x_circle = station_x[i] + horizontal_range[i] * np.cos(theta)
        y_circle = station_y[i] + horizontal_range[i] * np.sin(theta)
        ax.plot(x_circle, y_circle, 'b--')
    ax.plot(station_x, station_y, 'k*', label="Stations")
    ax.plot(anchor_x, anchor_y, 'ro', label="Estimated Anchor")
    ax.plot(np.nan, np.nan, linestyle='', label=f"Lat: {anchor_lat:.6f}")
    ax.plot(np.nan, np.nan, linestyle='', label=f"Lon: {anchor_lon:.6f}")
    ax.plot(np.nan, np.nan, linestyle='', label=f"RMS: {rms:.3f} m")
    ax.axis('equal')
    ax.legend()
    ax.grid(True)
    ax.set_title("Anchor Triangulation")
    ax.set_xlabel("East (m)")
    ax.set_ylabel("North (m)")

    result_text = (
        f"### 🧭 Estimated Anchor Position\n"
        f"- **Latitude:** {anchor_lat:.6f}\n"
        f"- **Longitude:** {anchor_lon:.6f}\n"
        f"- **Fallback:** {fallback:.2f} m\n"
        f"- **RMS Error:** {rms:.3f} m\n"
        f"- **Iterations:** {iterations}"
    )

    return result_text, fig


# -----------------------------
# Panel widgets and layout
# -----------------------------
file_input = pn.widgets.FileInput(name="Select .dat file", accept=".dat")
transducer_depth = pn.widgets.FloatInput(name="Transducer Depth (m)",
                                         value=5.0, step=0.1)
drop_depth = pn.widgets.FloatInput(name="Drop Depth (m)", value=36.0, step=0.1)
sound_speed = pn.widgets.FloatSlider(name="Sound Speed (m/s)", value=1500,
                                     start=1400, end=1600, step=1)

# --- DMS input fields ---
lat_deg = pn.widgets.IntInput(name="Lat °", value=35)
lat_min = pn.widgets.FloatInput(name="Lat ′", value=57.068, step=0.001)
lat_sec = pn.widgets.FloatInput(name="Lat ″", value=0.0, step=0.01)
lat_dir = pn.widgets.Select(name="Dir", options=["N", "S"], value="N")

lon_deg = pn.widgets.IntInput(name="Lon °", value=75)
lon_min = pn.widgets.FloatInput(name="Lon ′", value=7.822, step=0.001)
lon_sec = pn.widgets.FloatInput(name="Lon ″", value=0.0, step=0.01)
lon_dir = pn.widgets.Select(name="Dir", options=["E", "W"], value="W")

result_pane = pn.pane.Markdown("Results will appear here.",
                               sizing_mode="stretch_width")
plot_pane = pn.pane.Matplotlib(height=500, sizing_mode="stretch_width")


# -----------------------------
# Run button callback
# -----------------------------
def on_run(event):
    if file_input.value is None:
        result_pane.object = "⚠️ Please select a station file first."
        return

    with tempfile.NamedTemporaryFile(delete=False, suffix=".dat") as tmp:
        tmp.write(file_input.value)
        tmp_path = tmp.name

    # Convert DMS → decimal degrees using your helper
    drop_lat_dd = dms_to_dd(lat_deg.value, lat_min.value,
                            lat_sec.value, lat_dir.value)
    drop_lon_dd = dms_to_dd(lon_deg.value, lon_min.value,
                            lon_sec.value, lon_dir.value)

    result_text, fig = run_survey(
        tmp_path,
        transducer_depth.value,
        drop_lat_dd,
        drop_lon_dd,
        drop_depth.value,
        sound_speed.value,
    )

    result_pane.object = result_text
    if fig is not None:
        plot_pane.object = fig


run_button = pn.widgets.Button(name="Run Triangulation", button_type="primary")
run_button.on_click(on_run)

# -----------------------------
# Layout
# -----------------------------
lat_row = pn.Row(lat_deg, lat_min, lat_sec, lat_dir)
lon_row = pn.Row(lon_deg, lon_min, lon_sec, lon_dir)

app = pn.Column(
    pn.pane.Markdown("# ⚓ Anchor Triangulation Tool"),
    pn.Row(file_input),
    pn.Row(transducer_depth, drop_depth),
    pn.pane.Markdown("### Drop Latitude"),
    lat_row,
    pn.pane.Markdown("### Drop Longitude"),
    lon_row,
    pn.Row(sound_speed),
    run_button,
    pn.layout.Divider(),
    result_pane,
    plot_pane,
    sizing_mode="stretch_width"
)

app.servable()
