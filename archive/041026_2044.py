# -*- coding: utf-8 -*-
"""
Program Uji Coba 1 Channel - Mass Flow Ultrasonik (MURNI VISUALISASI)
"""

import numpy as np
import matplotlib.pyplot as plt
import time
import datetime
import redpitaya_scpi as scpi
import pandas as pd
from scipy.signal import butter, filtfilt, hilbert

# ==========================================
# 1. KONFIGURASI — edit di sini saja
# ==========================================
IP_ADDRESS   = 'RP-F0B91C.LOCAL'
FREQ_HZ      = 5_000_000   # (Frekuensi resonansi asli transduser Anda)
N_CYCLES     = 1           # jumlah siklus per burst
AWG_VOLT     = 1.0         # amplitudo AWG ke MAX913 (V)
ACQ_DLY      = 8192        # Titik tembak (0 µs) berada di awal grafik
ACQ_DEC      = 2           # decimation (2 = jendela waktu merenggang hingga ~262 us)
WAIT_TIMEOUT = 100         # maksimal cek status WAIT (x10ms = 1 detik)

RANGEXLIM    = -5          # Batas awal sumbu X pada grafik
RANGEYXLIM   = 150         # Batas akhir sumbu X pada grafik (Bebas diatur)

# -- KONFIGURASI FILTER --
FILTER_LOW    = 4_500_000  # Batas bawah filter
FILTER_HIGH   = 5_500_000  # Batas atas filter
DIGITAL_GAIN  = 8.0        # Pengali statis/rata untuk memperjelas grafik (tanpa distorsi ujung)

# ==========================================
# 2. KONEKSI & RESET AWAL
# ==========================================
rp = scpi.scpi(IP_ADDRESS)
print(f"Terhubung ke Red Pitaya: {IP_ADDRESS}")

rp.tx_txt('OUTPUT1:STATE OFF')
rp.tx_txt('GEN:RST')
rp.tx_txt('ACQ:RST')
time.sleep(0.1)

# ==========================================
# 3. KONFIGURASI AWG
# ==========================================
rp.tx_txt('SOUR1:FUNC SINE')
rp.tx_txt(f'SOUR1:FREQ:FIX {FREQ_HZ}')
rp.tx_txt(f'SOUR1:VOLT {AWG_VOLT}')
rp.tx_txt('SOUR1:BURS:STAT BURST')
rp.tx_txt(f'SOUR1:BURS:NCYC {N_CYCLES}')

rp.tx_txt('SOUR1:BURS:NOR 1')
rp.tx_txt('SOUR1:INITValue 0')
rp.tx_txt('SOUR1:BURS:LASTValue 0')

# ==========================================
# 4. KONFIGURASI MUX
# ==========================================
for pin in ['DIO0_P', 'DIO1_P', 'DIO2_P', 'DIO3_P', 'DIO4_P']:
    rp.tx_txt(f'DIG:PIN:DIR OUT,{pin}')

rp.tx_txt('DIG:PIN DIO0_P,0')  # A0
rp.tx_txt('DIG:PIN DIO1_P,0')  # A1
rp.tx_txt('DIG:PIN DIO2_P,0')  # A2
rp.tx_txt('DIG:PIN DIO3_P,0')  # A3
rp.tx_txt('DIG:PIN DIO4_P,1')  # EN = HIGH 
print("MUX terkunci di Channel 0.")

rp.tx_txt('OUTPUT1:STATE ON')
print("Menunggu 0.5 detik agar Kapasitor Kopling membuang DC Offset...")
time.sleep(0.5) 

# ==========================================
# 5. EKSEKUSI PENEMBAKAN & PEREKAMAN
# ==========================================
rp.tx_txt('ACQ:RST')
time.sleep(0.05)

rp.tx_txt(f'ACQ:DEC {ACQ_DEC}')
rp.tx_txt('ACQ:AVG OFF')
rp.tx_txt('ACQ:DATA:FORMAT ASCII')
rp.tx_txt('ACQ:DATA:Units VOLTS')
rp.tx_txt('ACQ:SOUR1:GAIN LV')
rp.tx_txt(f'ACQ:TRig:DLY {ACQ_DLY}')

rp.tx_txt('ACQ:START')
time.sleep(0.05)
rp.tx_txt('ACQ:TRig AWG_PE')

print("ADC siap. Menembak burst...")
for i in range(WAIT_TIMEOUT):
    if rp.txrx_txt('ACQ:TRig:STAT?').strip() == 'WAIT':
        break
    time.sleep(0.01)

rp.tx_txt('SOUR1:TRig:INT')

for i in range(5000):
    if rp.txrx_txt('ACQ:TRig:STAT?').strip() == 'TD':
        break
    time.sleep(0.001)

print("Trigger diterima, mengisi buffer...")
for i in range(5000):
    if rp.txrx_txt('ACQ:TRig:FILL?').strip() == '1':
        break
    time.sleep(0.001)
print("Buffer penuh. Rekaman selesai.")

# ==========================================
# 6. MENGAMBIL DATA
# ==========================================
print("Mengunduh data...")
raw = rp.txrx_txt('ACQ:SOUR1:DATA?').strip('{}\n\r').replace('  ', '').split(',')
data = np.array(list(map(float, raw)))
print(f"Selesai: {len(data)} sampel.")

rp.tx_txt('OUTPUT1:STATE OFF')
rp.close()

# ==========================================
# 7. FILTERING & ENVELOPE MURNI
# ==========================================
fs = 125e6 / ACQ_DEC
trigger_sample = 8192 - ACQ_DLY
waktu_us = (np.arange(len(data)) / fs * 1e6 - trigger_sample / fs * 1e6)

nyq = 0.5 * fs
b, a = butter(4, [FILTER_LOW/nyq, FILTER_HIGH/nyq], btype='band')

# Murni dikali konstan, TANPA kompensasi eksponensial
data_filtered = filtfilt(b, a, data) * DIGITAL_GAIN 
data_envelope = np.abs(hilbert(data_filtered))

# ==========================================
# 8. PLOT & SIMPAN GAMBAR DITUMPUK
# ==========================================
timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

# Grafik Atas: RAW DATA
ax1.plot(waktu_us, data, color='blue', linewidth=0.5)
ax1.set_title(f"Sinyal Mentah (Raw) - Channel 0  [{timestamp}]")
ax1.set_ylabel("Tegangan (V)")
ax1.axvline(0, color='red', linestyle='--', linewidth=0.8, label='t=0 TX')
ax1.set_ylim(-1.1, 1.1)
ax1.grid(True, alpha=0.4)
ax1.legend(loc='upper right', fontsize=8)

# Grafik Bawah: FILTERED & ENVELOPE (TANPA Asumsi Jarak)
ax2.plot(waktu_us, data_filtered, color='gray', linewidth=0.5, alpha=0.7, label="Filtered AC")
ax2.plot(waktu_us, data_envelope, color='red', linewidth=1.2, label="Envelope Sinyal")
ax2.set_title(f"Hasil Ekstraksi Murni (Bandpass {FILTER_LOW/1e6}-{FILTER_HIGH/1e6} MHz | Gain Konstan x{DIGITAL_GAIN})")
ax2.set_xlabel("Waktu (µs) — t=0 saat AWG tembak")
ax2.set_ylabel("Tegangan (V)")

ax2.set_xlim(RANGEXLIM, RANGEYXLIM)
ax2.set_ylim(-max(data_envelope)*1.2, max(data_envelope)*1.2)
ax2.grid(True, alpha=0.4)
ax2.legend(loc='upper right', fontsize=8)

plt.tight_layout()
nama_gambar = f'plot_visual_{timestamp}.png'
plt.savefig(nama_gambar, dpi=150)
print(f"Gambar disimpan: {nama_gambar}")

# ==========================================
# 9. SIMPAN CSV
# ==========================================
nama_csv = f'hasil_visual_{timestamp}.csv'
pd.DataFrame({
    'Waktu_us':       waktu_us,
    'Amplitudo_Volt': data,
    'Filtered_Volt':  data_filtered,
    'Envelope_Volt':  data_envelope
}).to_csv(nama_csv, index=False)
print(f"CSV disimpan: {nama_csv}")

plt.show()