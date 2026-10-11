# -*- coding: utf-8 -*-
"""
Program Uji Coba 1 Channel (Channel 0) - Mass Flow Ultrasonik (REVISI FINAL)
"""

import numpy as np
import matplotlib.pyplot as plt
import time
import datetime
import redpitaya_scpi as scpi
import pandas as pd

# ==========================================
# 1. KONFIGURASI — edit di sini saja
# ==========================================
IP_ADDRESS   = 'RP-F0B91C.LOCAL'
FREQ_HZ      = 6_400_000   # Diset ke 4.14 MHz (Frekuensi resonansi asli transduser Anda)
N_CYCLES     = 1           # jumlah siklus per burst
AWG_VOLT     = 1.0         # amplitudo AWG ke MAX913 (V)
ACQ_DLY      = 8192        # DIUBAH: Agar titik tembak (0 µs) berada di awal grafik, bukan di tengah
ACQ_DEC      = 1           # decimation (1 = 125 MSps)
WAIT_TIMEOUT = 100         # maksimal cek status WAIT (x10ms = 1 detik)

RANGEYXLIM = 100
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

# 3 Aturan Wajib untuk Keamanan IC TC4427 & MAX913
rp.tx_txt('SOUR1:BURS:NOR 1')          # Pastikan hanya tembak 1 rentetan
rp.tx_txt('SOUR1:INITValue 0')         # Pastikan mulai dari 0 Volt mutlak
rp.tx_txt('SOUR1:BURS:LASTValue 0')    # Pastikan istirahat di 0 Volt mutlak!

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

# SETELAH MUX NYALA, HUBUNGKAN OUTPUT AWG
rp.tx_txt('OUTPUT1:STATE ON')

# -------------------------------------------------------------
# FASE KRITIS: WAKTU TUNGGU KAPASITOR (RC TIME CONSTANT)
# -------------------------------------------------------------
print("Menunggu 0.5 detik agar Kapasitor Kopling 100nF membuang DC Offset...")
time.sleep(0.5) 
# Jangan pernah mengecilkan nilai sleep ini, atau grafik Anda akan flat/saturasi lagi!

# ==========================================
# 5. EKSEKUSI PENEMBAKAN & PEREKAMAN
# ==========================================
rp.tx_txt('ACQ:RST')
time.sleep(0.05)

# Konfigurasi ADC
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

# Trigger AWG!
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

# Baru matikan AWG di sini setelah semua data aman direkam
rp.tx_txt('OUTPUT1:STATE OFF')
rp.close()

# ==========================================
# 7. KOREKSI WAKTU
# ==========================================
fs = 125e6 / ACQ_DEC
trigger_sample = 8192 - ACQ_DLY
waktu_us = (np.arange(len(data)) / fs * 1e6 - trigger_sample / fs * 1e6)

# ==========================================
# 8. PLOT & SIMPAN GAMBAR
# ==========================================
timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

fig, ax = plt.subplots(figsize=(12, 5))
ax.plot(waktu_us, data, color='blue', linewidth=0.5)
ax.set_title(f"Echo Uji Coba Transduser - Channel 0  [{timestamp}]")
ax.set_xlim(-5, RANGEYXLIM)
ax.set_ylim(-1.1, 1.1)
ax.set_xlabel("Waktu (µs) — t=0 saat AWG tembak")
ax.set_ylabel("Tegangan (V)")
ax.axvline(0, color='red', linestyle='--', linewidth=0.8, label='t=0 TX')

ACRYLIC_THICKNESS_M = 0.015  # 1.5 cm Akrilik
ACRYLIC_SOUND_SPEED = 2700

rt_us = (2 * ACRYLIC_THICKNESS_M / ACRYLIC_SOUND_SPEED) * 1e6

for n in range(1, 4):
    ax.axvline(n * rt_us, color='purple', linestyle=':', linewidth=0.8,
               alpha=0.5, label=f'Echo ke-{n} ({n*rt_us:.1f}µs)')

ax.legend(fontsize=8, loc='upper right')
ax.grid(True, alpha=0.4)
plt.tight_layout()

nama_gambar = f'plot_{timestamp}.png'
plt.savefig(nama_gambar, dpi=150)

# ==========================================
# 9. SIMPAN CSV
# ==========================================
nama_csv = f'hasil_{timestamp}.csv'
pd.DataFrame({
    'Waktu_us':       waktu_us,
    'Amplitudo_Volt': data,
}).to_csv(nama_csv, index=False)

plt.show()