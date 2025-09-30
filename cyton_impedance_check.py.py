# -*- coding: utf-8 -*-
import time
import numpy as np
from scipy.signal import iirfilter, filtfilt

from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds
import csv
import os

import matplotlib.pyplot as plt

# --- Constants (GUI-based settings) ---
SERIES_R = 2200.0          # Keep series resistor at 2.2 kΩ
I_DRIVE = 6.0e-9           # Use the same value as GUI's leadOffDrive_amps (default: 6 nA)
MEAS_SEC = 2.0             # Measurement duration: 2s, but only the last 1s will be used
SETTLE_SEC = 2.0           # Settling time to discard transients (1.5–2.0s recommended)
BAND = (5, 50)             # Narrow bandpass filter: 5–50 Hz (depending on environment, can adjust to 30–32 Hz)
CABLE_COLORS = ['gray', 'purple', 'blue', 'green', 'yellow', 'orange', 'red', 'brown']

def set_ads_to_impedance_on(board, ch: int):
    """
    Configure ADS channel for impedance measurement.
    Format: xCH PWR GAIN INPUT BIAS SRB2 SRB1 X
    Example: x10...
    """
    ads_cmd = f"x{ch}0"  # POWER_DOWN=0 (power up)
    ads_cmd += "0"       # GAIN=0 (gain x1)
    ads_cmd += "0"       # INPUT=NORMAL
    ads_cmd += "1"       # Include in bias
    ads_cmd += "0"       # Disconnect SRB2
    ads_cmd += "0"       # Disconnect SRB1
    ads_cmd += "X"

    board.config_board(ads_cmd)
    time.sleep(0.02)     # Allow time for configuration to apply

def reset_to_defaults(board: BoardShim):
    """
    Reset all channels back to Cyton board default configuration (no restart required).
    Useful to ensure the board state is consistent after custom settings.
    """
    try:
        board.config_board("d")
        return True, "OK"
    except Exception as e:
        return False, f"ERR: {e}"
    time.sleep(0.05)    

def calc_impedance_from_vrms(vrms_uV):
    """
    Calculate electrode impedance based on Vrms value.
    Formula (same as PDE): Z = (sqrt(2) * Vrms[V]) / I_drive - R_series
    """
    Vrms_V = float(vrms_uV) * 1e-6
    Z = (np.sqrt(2.0) * Vrms_V) / I_DRIVE
    Z -= SERIES_R
    return max(Z, 0.0)   # Impedance cannot be negative

def take_recent_1s(x_uV, fs):
    """
    Extract the most recent 1 second of data, remove mean, 
    then compute RMS (here approximated via standard deviation).
    """
    n = int(fs * 1.0)
    seg = x_uV[-n:]       # Take the last n samples (1 second window)
    return float(np.std(seg, ddof=0))  # Return RMS in μV

def bandpass_apply(x, fs):
    """
    Apply a 4th-order Butterworth bandpass filter.
    To reduce edge effects from filtfilt, it's recommended to use >1s of data.
    Current usage: record 2s, then compute RMS only from the last 1s.
    """
    b, a = iirfilter(4, [BAND[0]/(fs/2.0), BAND[1]/(fs/2.0)],
                     btype='band', ftype='butter')
    return filtfilt(b, a, x)

def send_leadoff(board, ch, p_apply, n_apply):
    """
    Configure lead-off detection for a given channel.
    Cyton ASCII command format: z (CHANNEL, P, N) Z
    CHANNEL: '1'..'8'; P/N: '0' (off) or '1' (on)
    Example: ch1, only N side ON → 'z101Z'
    """
    cmd = f"z{ch}{p_apply}{n_apply}Z"
    board.config_board(cmd)
    time.sleep(0.02)

def check_impedance(channels=[1,2,3,4,5,6,7,8]):
    """
    Main impedance measurement routine.
    Steps:
    1) Configure ADS for impedance measurement.
    2) Turn ON lead-off (negative side).
    3) Wait for settling to discard transients.
    4) Clear buffer.
    5) Record data for a fixed duration (2s).
    6) Extract EEG channel data, apply bandpass filter, compute Vrms.
    7) Convert to impedance (kΩ).
    8) Print result and restore channel to default.
    """
    port = "/dev/cu.usbserial-DP04WG3L"  # Adjust according to your environment
    if not port:
        raise RuntimeError("Cyton serial port not found.")

    params = BrainFlowInputParams()
    params.serial_port = port
    board_id = BoardIds.CYTON_BOARD.value
    fs = BoardShim.get_sampling_rate(board_id)

    board = BoardShim(board_id, params)

    try:
        board.prepare_session()
        board.start_stream()

        z_list = []

        for ch in channels:
            set_ads_to_impedance_on(board, ch)

            # Step 1: Enable lead-off (N-side only)
            send_leadoff(board, ch, 0, 1)

            # Step 2: Discard transients
            time.sleep(SETTLE_SEC)

            # Step 3: Clear buffer
            board.get_board_data()

            # Step 4: Acquire new data
            time.sleep(MEAS_SEC+0.2) # Add small margin for safety
            data = board.get_board_data()

            # Step 5: Extract EEG data (in μV scale)
            eeg_idxs = BoardShim.get_eeg_channels(board_id)
            row = eeg_idxs[ch - 1]
            x_uV = data[row, :]

            # Step 6: Filter + RMS
            x_bp = bandpass_apply(x_uV, fs)
            uVrms = take_recent_1s(x_bp, fs)
            z_kohm = (calc_impedance_from_vrms(uVrms) / 1000.0) if np.isfinite(uVrms) else float('nan')

            print(f"CH{ch}({CABLE_COLORS[ch - 1]}): {z_kohm:.2f} kΩ")
            z_list.append((ch, z_kohm))

            # Step 7: Turn lead-off OFF
            send_leadoff(board, ch, 0, 0)

        board.stop_stream()

        # Step 8: Reset all channels to default
        reset_to_defaults(board)

        return z_list

    finally:
        try:
            board.release_session()
        except Exception:
            pass

if __name__ == "__main__":
    # Run impedance check across all 8 channels
    impedance_list = check_impedance(channels=[1,2,3,4,5,6,7,8])
    print("\n=== Summary ===")
    for ch, z in impedance_list:
        color = CABLE_COLORS[ch - 1] if 1 <= ch <= len(CABLE_COLORS) else 'black'
        print(f"CH{ch}({color}): {z:.2f} kΩ")
