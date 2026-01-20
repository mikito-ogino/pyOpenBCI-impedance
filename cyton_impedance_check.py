# -*- coding: utf-8 -*-
"""
Impedance check utility for OpenBCI Cyton using BrainFlow.

This script measures electrode impedance by enabling Cyton's lead-off current,
band-pass filtering the recorded signal, and estimating impedance from Vrms.

Design goals:
- Reproduce OpenBCI GUI–like impedance measurement behavior
- Use BrainFlow only (no GUI dependency)
- Keep parameters explicit and well-documented for reproducibility

Author: (add your name)
License: (e.g. MIT)
"""

import time
import numpy as np
from scipy.signal import iirfilter, filtfilt
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds


class ImpedanceCheck:
    """
    Impedance measurement class for OpenBCI Cyton.

    Typical usage:
        checker = ImpedanceCheck(port="/dev/ttyUSB0")
        checker.prepare_board()
        z_kohm = checker.check_impedance(ch=1)
        checker.stop_board()

    Notes:
    - Only the last 1 second of data is used for impedance estimation
    - Measurement uses Cyton's internal lead-off current
    """

    # ------------------------------------------------------------------
    # Constants (aligned with OpenBCI GUI defaults)
    # ------------------------------------------------------------------

    SERIES_R = 2200.0       # Series resistor on Cyton board [ohm]
    I_DRIVE = 6.0e-9        # Lead-off drive current [A] (GUI default: 6 nA)
    MEAS_SEC = 6.0          # Total measurement time [s]
    BAND = (5, 50)          # Band-pass range [Hz] for impedance estimation
    fs = 250                # Default sampling rate (will be overwritten)

    def __init__(self, port: str):
        """
        Initialize impedance checker.

        Parameters
        ----------
        port : str
            Serial port name (e.g. '/dev/cu.usbserial-XXXX' or 'COM3')
        """
        self.port = port
        self.impedance_data = []

        # Cyton channel configuration presets
        #
        # Channel config command format:
        #   x(CH, POWER_DOWN, GAIN, INPUT, BIAS, SRB2, SRB1)X
        #
        # gain: 0..6 → (1,2,4,6,8,12,24)
        # input_type: 0 = normal
        # bias, srb2, srb1: 0/1 flags
        self.STREAM_CFG_DEFAULT = dict(
            gain=6,
            input_type=0,
            bias=1,
            srb2=1,
            srb1=0
        )

        # GUI-like impedance measurement configuration
        self.IMP_CFG = dict(
            gain=0,
            input_type=0,
            bias=1,
            srb2=0,
            srb1=0
        )

        # Track current and previous channel configurations
        self._ch_cfg = [self.STREAM_CFG_DEFAULT.copy() for _ in range(8)]
        self._ch_last_cfg = [None for _ in range(8)]

        self.board = None

    # ------------------------------------------------------------------
    # Command builders (Cyton ASCII protocol)
    # ------------------------------------------------------------------

    def build_channel_settings_cmd(
        self,
        ch: int,
        gain: int,
        input_type: int,
        bias: int,
        srb2: int,
        srb1: int,
        power_down: int = 0
    ) -> str:
        """
        Build Cyton channel settings command.

        Returns
        -------
        str
            ASCII command string for Cyton
        """
        return f"x{ch}{power_down}{gain}{input_type}{bias}{srb2}{srb1}X"

    def build_impedance_cmd(self, ch: int, active: bool, is_n: bool) -> str:
        """
        Build Cyton impedance (lead-off) command.

        Parameters
        ----------
        ch : int
            Channel number (1-based)
        active : bool
            Enable or disable lead-off current
        is_n : bool
            If True, apply current to N input; otherwise P input
        """
        p = "0"
        n = "0"
        if active:
            if is_n:
                n = "1"
            else:
                p = "1"
        return f"z{ch}{p}{n}Z"

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def reset_to_defaults(self, board: BoardShim):
        """
        Reset Cyton board to default configuration.

        Equivalent to pressing 'd' in OpenBCI GUI.
        """
        try:
            board.config_board("d")
            time.sleep(0.1)
            return True, "OK"
        except Exception as e:
            return False, f"ERR: {e}"

    def calc_impedance_from_vrms(self, vrms_uV: float) -> float:
        """
        Convert Vrms [µV] to impedance [ohm].

        Z = (sqrt(2) * Vrms) / I_drive - R_series
        """
        Vrms_V = vrms_uV * 1e-6
        Z = (np.sqrt(2.0) * Vrms_V) / self.I_DRIVE
        Z -= self.SERIES_R
        return max(Z, 0.0)

    def take_recent_1s(self, x_uV: np.ndarray, fs: int) -> float:
        """
        Compute RMS value of the last 1 second of signal.
        """
        n = int(fs * 1.0)
        seg = x_uV[-n:]
        return float(np.sqrt(np.mean(seg ** 2)))

    def bandpass_apply(self, x: np.ndarray, fs: int) -> np.ndarray:
        """
        Apply zero-phase Butterworth band-pass filter.
        """
        b, a = iirfilter(
            4,
            [self.BAND[0] / (fs / 2.0), self.BAND[1] / (fs / 2.0)],
            btype='band',
            ftype='butter'
        )
        return filtfilt(b, a, x)

    # ------------------------------------------------------------------
    # Board control
    # ------------------------------------------------------------------

    def change_leadoff(self, ch: int, is_on: bool):
        """
        Enable or disable lead-off current for a channel.

        This method:
        1. Stores previous channel settings
        2. Applies impedance-measurement configuration
        3. Sends both channel config and lead-off commands
        """
        ch_idx = ch - 1
        is_n = True  # Measure N input (OpenBCI GUI convention)

        if is_on:
            self._ch_last_cfg[ch_idx] = self._ch_cfg[ch_idx].copy()
            self._ch_cfg[ch_idx] = self.IMP_CFG.copy()
        else:
            if self._ch_last_cfg[ch_idx] is not None:
                self._ch_cfg[ch_idx] = self._ch_last_cfg[ch_idx].copy()
                self._ch_last_cfg[ch_idx] = None
            else:
                self._ch_cfg[ch_idx] = self.STREAM_CFG_DEFAULT.copy()

        cfg = self._ch_cfg[ch_idx]

        x_cmd = self.build_channel_settings_cmd(
            ch=ch,
            gain=cfg["gain"],
            input_type=cfg["input_type"],
            bias=cfg["bias"],
            srb2=cfg["srb2"],
            srb1=cfg["srb1"],
            power_down=0
        )

        z_cmd = self.build_impedance_cmd(ch=ch, active=is_on, is_n=is_n)
        cmd = x_cmd + z_cmd

        try:
            resp = self.board.config_board(cmd)
            print(f"Ch{ch} Cmd: {cmd} | Resp: {resp}")
        except UnicodeDecodeError:
            # Known BrainFlow issue: command succeeds but response decode fails
            print(f"Ch{ch} Cmd: {cmd} | (Success, decode error ignored)")

        time.sleep(0.1)

    def prepare_board(self):
        """
        Initialize BrainFlow session and prepare Cyton board.
        """
        if not self.port:
            raise RuntimeError("Cyton serial port not specified.")

        params = BrainFlowInputParams()
        params.serial_port = self.port

        board_id = BoardIds.CYTON_BOARD.value
        self.fs = BoardShim.get_sampling_rate(board_id)

        self.board = BoardShim(board_id, params)
        self.board.prepare_session()

    def stop_board(self):
        """
        Stop streaming and release BrainFlow session.
        """
        self.reset_to_defaults(self.board)
        try:
            self.board.release_session()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_impedance(self, ch: int) -> float:
        """
        Measure impedance of a single channel.

        Parameters
        ----------
        ch : int
            Channel number (1-based)

        Returns
        -------
        float
            Estimated impedance [kΩ]
        """
        self.reset_to_defaults(self.board)
        self.change_leadoff(ch, True)

        self.board.start_stream()
        self.board.get_board_data()  # Clear buffer
        time.sleep(self.MEAS_SEC + 0.2)

        data = self.board.get_board_data()
        eeg_idxs = BoardShim.get_eeg_channels(self.board.get_board_id())
        row = eeg_idxs[ch - 1]

        x_uV = data[row, :]
        x_bp = self.bandpass_apply(x_uV, self.fs)
        uVrms = self.take_recent_1s(x_bp, self.fs)

        z_ohm = (
            self.calc_impedance_from_vrms(uVrms)
            if np.isfinite(uVrms)
            else float('nan')
        )

        self.board.stop_stream()
        self.change_leadoff(ch, False)

        return z_ohm / 1000.0  # Convert to kΩ


# ----------------------------------------------------------------------
# Standalone execution example
# ----------------------------------------------------------------------

if __name__ == "__main__":
    impedance_checker = ImpedanceCheck(
        port="/dev/cu.usbserial-XXXX"  # Adjust for your system
    )

    impedance_checker.prepare_board()

    ch = 1
    print(f"Checking impedance for Channel {ch}...")
    z_kohm = impedance_checker.check_impedance(ch)
    print(f"Channel {ch}: {z_kohm:.2f} kΩ")

    impedance_checker.stop_board()
