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

```

Z = (sqrt(2) * Vrms[V]) / I_drive - R_series

```

- I_drive = 6 nA  
- R_series = 2.2 kΩ  
```

---

## 🚀 Usage

1. Install dependencies:
   ```bash
   pip install brainflow numpy scipy matplotlib
   ```

2. Connect your **OpenBCI Cyton** via USB and adjust the `serial_port` in `check_impedance()`:

   ```python
   port = "/dev/cu.usbserial-XXXX"  # Change to match your environment
   ```

3. Run the script:

   ```bash
   python cyton_impedance_check.py
   ```

4. Example output:

   ```
   CH1(gray): 5.12 kΩ
   CH2(purple): 12.45 kΩ
   ...
   === Summary ===
   CH1(gray): 5.12 kΩ
   CH2(purple): 12.45 kΩ
   ```

---

## 📊 Notes

* Measurement duration is set to **2 seconds**, with the last **1 second** used for RMS calculation.
* Settling time before measurement is **2 seconds** to avoid transient artifacts.
* Works with the default **8-channel Cyton Board** configuration.

---

## 📜 License

MIT License (feel free to modify for your needs).

---

## 🙌 Acknowledgements

* [OpenBCI](https://openbci.com/) for hardware and GUI reference
* [BrainFlow](https://brainflow.org/) for Python interface


---
