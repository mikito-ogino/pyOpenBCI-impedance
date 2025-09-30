# OpenBCI Cyton Impedance Check (Python)

This repository provides a **Python implementation of an impedance check tool for the OpenBCI Cyton Board**, developed using [BrainFlow](https://brainflow.org/).  
It reproduces the impedance check function of the official OpenBCI GUI and yields almost identical results when using a **5–50 Hz bandpass filter**.

---

## ✨ Features
- Performs **per-channel impedance measurement** on the Cyton board.
- Uses **lead-off detection (6 nA current)** and calculates impedance following the same formula as OpenBCI GUI.
- Bandpass filtering (5–50 Hz) for stable measurement.
- Color-coded output by electrode cable for quick identification.
- Reset function to restore ADS1299 registers to default values after measurement.

---

## 🧮 Impedance Calculation
The impedance is calculated using the same formula as the OpenBCI GUI:

\[
Z = \frac{\sqrt{2} \cdot V_\text{RMS}[V]}{I_\text{drive}} - R_\text{series}
\]

- \( I_\text{drive} = 6 \,\text{nA} \)  
- \( R_\text{series} = 2.2 \,\text{kΩ} \)  

---

## 🚀 Usage

1. Install dependencies:
   ```bash
   pip install brainflow numpy scipy matplotlib
