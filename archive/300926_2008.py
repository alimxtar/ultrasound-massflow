# -*- coding: utf-8 -*-
"""
Program Uji Coba 1 Channel (Channel 0) - Mass Flow Ultrasonik (FILTER DIGITAL)
"""

import numpy as np
import matplotlib.pyplot as plt
import time
import datetime
import redpitaya_scpi as scpi
import pandas as pd
from scipy.signal import butter, filtfilt

# ==========================================
# 1. KONFIGURASI — edit di sini saja
# ==========================================
IP_ADDRESS   = 'RP-F0B91C.LOCAL'
FREQ_HZ      = 6_400_000   # (Frekuensi resonansi asli transduser Anda)
N_CYCLES     = 1           # jumlah siklus per burst
AWG_VOLT     = 1         # amplitudo AWG ke MAX913 (V)
ACQ_DLY      = 8192        # Titik tembak (0 µs) berada di awal grafik
ACQ_DEC      = 1           # decimation (1 = 125 MSps)
WAIT_TIMEOUT = 100         # maksimal cek status WAIT (x10ms = 1 detik)
RANGEYXLIM   = 100         # Batas sumbu X pada grafik
RANGEXLIM   = -5          # Batas sumbu X pada grafik (titik tembak)

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
# 4. KONFIGURASI MUX & KONEKSI JALUR FISIK
# ==========================================
for pin in ['DIO0_P', 'DIO1_P', 'DIO2_P', 'DIO3_P', 'DIO4_P']:
    rp.tx_txt(f'DIG:PIN:DIR OUT,{pin}')

rp.tx_txt('DIG:PIN DIO0_P,0')  # A0
rp.tx_txt('DIG:PIN DIO1_P,0')  # A1
rp.tx_txt('DIG:PIN DIO2_P,0')  # A2
rp.tx_txt('DIG:PIN DIO3_P,0')  # A3
rp.tx_txt('DIG:PIN DIO4_P,1')  # EN = HIGH (MUX Menyala!)
print("MUX terkunci di Channel 0.")

rp.tx_txt('OUTPUT1:STATE ON')
print("Menunggu 0.5 detik agar Kapasitor Kopling 100nF membuang DC Offset...")
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
    rp.tx_txt('ACQ:TRig:STAT?')
    if rp.rx_txt().strip() == 'WAIT':
        break
    time.sleep(0.01)

rp.tx_txt('SOUR1:TRig:INT')

for i in range(5000):
    rp.tx_txt('ACQ:TRig:STAT?')
    if rp.rx_txt().strip() == 'TD':
        break
    time.sleep(0.001)

print("Trigger diterima, mengisi buffer...")
for i in range(5000):
    rp.tx_txt('ACQ:TRig:FILL?')
    if rp.rx_txt().strip() == '1':
        break
    time.sleep(0.001)
print("Buffer penuh. Rekaman selesai.")

# ==========================================
# 6. MENGAMBIL DATA & MATIKAN ALAT
# ==========================================
print("Mengunduh data...")
rp.tx_txt('ACQ:SOUR1:DATA?')
raw = rp.rx_txt().strip('{}\n\r').replace('  ', '').split(',')
data = np.array(list(map(float, raw)))
print(f"Selesai: {len(data)} sampel.")

rp.tx_txt('OUTPUT1:STATE OFF')
rp.close()

# ==========================================
# 7. KOREKSI WAKTU & DIGITAL FILTERING
# ==========================================
fs = 125e6 / ACQ_DEC
trigger_sample = 8192 - ACQ_DLY
waktu_us = (np.arange(len(data)) / fs * 1e6 - trigger_sample / fs * 1e6)

# Desain Filter Bandpass (3 MHz - 7 MHz)
lowcut = 3_000_000   
highcut = 7_000_000  
nyq = 0.5 * fs
b, a = butter(4, [lowcut/nyq, highcut/nyq], btype='band')

# Terapkan zero-phase filter (filtfilt) agar posisi waktu echo tidak bergeser
data_filtered = filtfilt(b, a, data)

# ==========================================
# 8. PLOT & SIMPAN GAMBAR DITUMPUK
# ==========================================
timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

# Membuat 2 grafik atas dan bawah (sharex agar sumbu X terkunci bersama)
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

ACRYLIC_THICKNESS_M = 0.015  # 1.5 cm Akrilik
ACRYLIC_SOUND_SPEED = 2700
rt_us = (2 * ACRYLIC_THICKNESS_M / ACRYLIC_SOUND_SPEED) * 1e6

# Grafik Atas: RAW DATA
ax1.plot(waktu_us, data, color='blue', linewidth=0.5)
ax1.set_title(f"Sinyal Mentah (Raw) - Channel 0  [{timestamp}]")
ax1.set_ylabel("Tegangan (V)")
ax1.axvline(0, color='red', linestyle='--', linewidth=0.8, label='t=0 TX')
for n in range(1, 4):
    ax1.axvline(n * rt_us, color='purple', linestyle=':', linewidth=0.8, alpha=0.5)
ax1.set_ylim(-1.1, 1.1)
ax1.grid(True, alpha=0.4)
ax1.legend(loc='upper right', fontsize=8)

# Grafik Bawah: FILTERED DATA
ax2.plot(waktu_us, data_filtered, color='red', linewidth=0.6)
ax2.set_title("Sinyal Terfilter (Bandpass 3 MHz - 7 MHz)")
ax2.set_xlabel("Waktu (µs) — t=0 saat AWG tembak")
ax2.set_ylabel("Tegangan (V)")
ax2.axvline(0, color='black', linestyle='--', linewidth=0.8)
for n in range(1, 4):
    ax2.axvline(n * rt_us, color='purple', linestyle=':', linewidth=0.8, alpha=0.5, label=f'Echo ke-{n} ({n*rt_us:.1f}µs)')
ax2.set_xlim(RANGEXLIM, RANGEYXLIM)
ax2.set_ylim(-1.1, 1.1)
ax2.grid(True, alpha=0.4)
ax2.legend(loc='upper right', fontsize=8)

plt.tight_layout()
nama_gambar = f'plot_filtered_{timestamp}.png'
plt.savefig(nama_gambar, dpi=150)
print(f"Gambar disimpan: {nama_gambar}")

# ==========================================
# 9. SIMPAN CSV (RAW & FILTERED)
# ==========================================
nama_csv = f'hasil_filtered_{timestamp}.csv'
pd.DataFrame({
    'Waktu_us':       waktu_us,
    'Amplitudo_Volt': data,
    'Filtered_Volt':  data_filtered
}).to_csv(nama_csv, index=False)
print(f"CSV disimpan: {nama_csv}")

plt.show()