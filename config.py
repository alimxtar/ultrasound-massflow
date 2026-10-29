# -*- coding: utf-8 -*-
"""
Konfigurasi bersama untuk massflo.py, massflo_single.py, dan massflo_single_rt.py
"""

# ==========================================
# KONEKSI RED PITAYA
# ==========================================
IP_ADDRESS   = 'RP-F0B91C.LOCAL'   # atau IP langsung, mis. '169.254.66.156'

# ==========================================
# GENERATOR (AWG) & AKUISISI (ADC)
# ==========================================
FREQ_HZ      = 5_000_000
N_CYCLES     = 1
AWG_VOLT     = 1.0
ACQ_DLY      = 8192
ACQ_DEC      = 2

# ==========================================
# DSP
# ==========================================
FILTER_LOW      = 3_000_000
FILTER_HIGH     = 4_800_000
DIGITAL_GAIN    = 12.0
MA_WINDOW       = 128
NOISE_THRESHOLD = 0.15
BLANK_US        = 2.5
