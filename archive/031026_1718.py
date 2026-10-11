# -*- coding: utf-8 -*-
"""
Program Uji Coba 1 Channel - Mass Flow Ultrasonik (FILTER DIGITAL & DETEKSI ToF)
"""

import numpy as np
import matplotlib.pyplot as plt
import time
import datetime
import redpitaya_scpi as scpi
import pandas as pd
from scipy.signal import butter, filtfilt, hilbert

# ==========================================
# 1. KONFIGURASI KUSTOMISASI — edit di sini saja
# ==========================================
IP_ADDRESS   = 'RP-F0B91C.LOCAL'
FREQ_HZ      = 6_400_000   # (Frekuensi resonansi asli transduser Anda)
N_CYCLES     = 1           # jumlah siklus per burst
AWG_VOLT     = 1.0         # amplitudo AWG ke MAX913 (V)
ACQ_DLY      = 8192        # Titik tembak (0 µs) berada di awal grafik
ACQ_DEC      = 2           # decimation (1 = 125 MSps)
WAIT_TIMEOUT = 100         # maksimal cek status WAIT (x10ms = 1 detik)

RANGEXLIM    = -5          # Batas awal sumbu X pada grafik
RANGEYXLIM   = 100         # Batas akhir sumbu X pada grafik

# -- KONFIGURASI FILTER & ToF (BARU) --
FILTER_LOW    = 3_500_000  # Batas bawah filter (3.5 MHz)
FILTER_HIGH   = 5_000_000  # Batas atas filter (5.0 MHz)
DIGITAL_GAIN  = 20.0        # Pengali untuk memperbesar visual sinyal echo
BLIND_ZONE_US = 3.4       # Abaikan 20 µs pertama agar tembakan awal tidak dihitung sebagai echo
SOUND_SPEED   = 1480       # Kecepatan suara di Air (m/s). Ubah ke 2700 jika pakai Akrilik statis.

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
# 7. KOREKSI WAKTU, FILTERING, & TGC
# ==========================================
fs = 125e6 / ACQ_DEC
trigger_sample = 8192 - ACQ_DLY
waktu_us = (np.arange(len(data)) / fs * 1e6 - trigger_sample / fs * 1e6)

# 7A. Desain Filter Bandpass (Meredam noise frekuensi rendah & tinggi)
nyq = 0.5 * fs
b, a = butter(4, [FILTER_LOW/nyq, FILTER_HIGH/nyq], btype='band')
data_filtered = filtfilt(b, a, data)

# 7B. Time-Gain Compensation (TGC) - Penguatan Eksponensial Seiring Waktu
# Hal ini akan mengangkat echo air yang jauh agar terlihat menonjol
tgc_curve = np.exp(3.0 * waktu_us / waktu_us[-1]) 
data_tgc = data_filtered * tgc_curve * DIGITAL_GAIN

# 7C. Ekstraksi Selubung (Envelope)
data_envelope = np.abs(hilbert(data_tgc))

# ==========================================
# 8. ALGORITMA PENCARIAN ToF (CERDAS)
# ==========================================
# Abaikan BLIND_ZONE (agar ledakan awal tidak terdeteksi) dan 
# abaikan 5 us di ujung akhir memori (mencegah artefak filter)
valid_indices = np.where((waktu_us > BLIND_ZONE_US) & (waktu_us < waktu_us[-1] - 5.0))[0]

# Terapkan batas ambang batas (Threshold) dinamis untuk meredam noise lantai
noise_floor = np.mean(data_envelope[valid_indices])
threshold = noise_floor * 2.5 # Sinyal harus 2.5x lipat lebih besar dari rata-rata noise

# Cari puncak tertinggi yang memenuhi threshold
peak_idx = valid_indices[np.argmax(data_envelope[valid_indices])]
maks_amplitudo = data_envelope[peak_idx]

if maks_amplitudo > threshold:
    tof_measured_us = waktu_us[peak_idx]
    # Hitung Jarak Fisik Air (d = v * t / 2)
    jarak_cm = (tof_measured_us * 1e-6 * SOUND_SPEED / 2) * 100
    
    print(f"\n[HASIL PENGUKURAN]")
    print(f"Waktu Tempuh (ToF) : {tof_measured_us:.2f} µs")
    print(f"Estimasi Kedalaman : {jarak_cm:.2f} cm\n")
else:
    tof_measured_us = BLIND_ZONE_US # Default jika tidak ada echo yang kuat
    jarak_cm = 0.0
    print("\n[PERINGATAN] Tidak ada pantulan signifikan yang terdeteksi di atas Noise Floor.")

# ==========================================
# 9. PLOT & SIMPAN GAMBAR DITUMPUK
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

# Grafik Bawah: FILTERED & ENVELOPE & ToF
ax2.plot(waktu_us, data_filtered, color='gray', linewidth=0.5, alpha=0.7, label="Filtered AC")
ax2.plot(waktu_us, data_envelope, color='red', linewidth=1.2, label="Envelope Sinyal")
ax2.set_title(f"Hasil Ekstraksi (Bandpass {FILTER_LOW/1e6}-{FILTER_HIGH/1e6} MHz | Gain x{DIGITAL_GAIN})")
ax2.set_xlabel("Waktu (µs) — t=0 saat AWG tembak")
ax2.set_ylabel("Tegangan (V)")

# Garis penanda Zona Buta
ax2.axvspan(RANGEXLIM, BLIND_ZONE_US, color='red', alpha=0.1, label="Blind Zone (Diabaikan)")

# Garis penanda ToF yang dideteksi
ax2.axvline(tof_measured_us, color='green', linestyle='-', linewidth=1.5, 
            label=f'ToF Terdeteksi: {tof_measured_us:.1f} µs ({jarak_cm:.1f} cm)')

ax2.set_xlim(RANGEXLIM, RANGEYXLIM)
# Limit Y otomatis menyesuaikan gain
ax2.set_ylim(-max(data_envelope)*1.2, max(data_envelope)*1.2)
ax2.grid(True, alpha=0.4)
ax2.legend(loc='upper right', fontsize=8)

plt.tight_layout()
nama_gambar = f'plot_tof_{timestamp}.png'
plt.savefig(nama_gambar, dpi=150)
print(f"Gambar disimpan: {nama_gambar}")

# ==========================================
# 10. SIMPAN CSV
# ==========================================
nama_csv = f'hasil_tof_{timestamp}.csv'
pd.DataFrame({
    'Waktu_us':       waktu_us,
    'Amplitudo_Volt': data,
    'Filtered_Volt':  data_filtered,
    'Envelope_Volt':  data_envelope
}).to_csv(nama_csv, index=False)
print(f"CSV disimpan: {nama_csv}")

plt.show()