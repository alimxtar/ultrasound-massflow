# -*- coding: utf-8 -*-
"""
Program Uji Coba 1 Channel (Channel 0) - Mass Flow Ultrasonik
"""

import numpy as np
import matplotlib.pyplot as plt
import time
import redpitaya_scpi as scpi
import pandas as pd
from scipy.signal import butter, filtfilt, hilbert

# ==========================================
# 1. KONFIGURASI AWAL
# ==========================================
IP_ADDRESS = '169.254.66.156'  # Ganti dengan IP Red Pitaya Anda
rp = scpi.scpi(IP_ADDRESS)
print(f"Berhasil terhubung ke Red Pitaya di IP: {IP_ADDRESS}")

# Reset sistem bawaan Red Pitaya agar bersih dari program sisa
rp.tx_txt('GEN:RST')
rp.tx_txt('ACQ:RST')

# ==========================================
# 2. PERSIAPAN SINYAL PULSER (AWG)
# ==========================================
rp.tx_txt('SOUR1:FUNC SINE')          # Bentuk gelombang Sinus
rp.tx_txt('SOUR1:FREQ:FIX 6400000')   # Frekuensi tembakan 5 MHz
rp.tx_txt('SOUR1:VOLT 1.0')           # Amplitudo 1.0V (Untuk logic IC MAX913)
rp.tx_txt('SOUR1:BURS:STAT BURST')    # Aktifkan mode Burst (Bukan Continuous)
rp.tx_txt('SOUR1:BURS:NCYC 3')        # Tembakkan tepat 3 gelombang (cycles)

# ==========================================
# 3. PERSIAPAN PEREKAMAN (ADC)
# ==========================================
rp.tx_txt('ACQ:DEC 1')           # Ambil sampel secepat mungkin (125 Juta Sampel/detik)
rp.tx_txt('ACQ:TRig:DLY 8192')      # Tidak ada penundaan waktu rekaman

# ==========================================
# 4. MEMILIH CHANNEL MUX (KHUSUS CHANNEL 0)
# ==========================================
# Karena kita tes 1 channel (Channel 0), maka biner-nya adalah 0000.
rp.tx_txt('DIG:PIN:DIR OUT,DIO0_P')
rp.tx_txt('DIG:PIN:DIR OUT,DIO1_P')
rp.tx_txt('DIG:PIN:DIR OUT,DIO2_P')
rp.tx_txt('DIG:PIN:DIR OUT,DIO3_P')
rp.tx_txt('DIG:PIN:DIR OUT,DIO4_P') # Pin EN (Enable MUX)

# Set A0, A1, A2, A3 menjadi LOW (0)
rp.tx_txt('DIG:PIN DIO0_P,0')
rp.tx_txt('DIG:PIN DIO1_P,0')
rp.tx_txt('DIG:PIN DIO2_P,0')
rp.tx_txt('DIG:PIN DIO3_P,0')

# Nyalakan MUX (Asumsi pin EN aktif HIGH)
rp.tx_txt('DIG:PIN DIO4_P,1')

print("MUX terkunci di Channel 0. Bersiap menembak...")
time.sleep(0.1) # Waktu tunggu kestabilan hardware MUX

# ==========================================
# 5. EKSEKUSI PENEMBAKAN & PEREKAMAN
# ==========================================
# A. Nyalakan mode rekaman dan set dia untuk menunggu sinyal AWG
# rp.tx_txt('ACQ:START')
# rp.tx_txt('ACQ:TRig AWG_PE')
# rp.tx_txt('OUTPUT1:STATE ON')
# time.sleep(0.01) # Delay singkat agar sistem internal siap

# # B. TEMBAKKAN PULSA! (Memicu AWG menembak 3 siklus)
# print("Duar! Pulsa ditembakkan.")
# rp.tx_txt('SOUR1:TRig:INT')
# time.sleep(0.000016)

# # C. Tunggu sampai Red Pitaya membalas "Ya, saya sudah merekam trigger-nya"
# while True:
#     rp.tx_txt('ACQ:TRig:STAT?')
#     if rp.rx_txt().strip() == 'TD':
#         break

# # D. Tunggu sampai memori internal ADC benar-benar terisi penuh
# while True:
#     rp.tx_txt('ACQ:TRig:FILL?')
#     if rp.rx_txt().strip() == '1':
#         break

# # E. Matikan output AWG agar aman
# rp.tx_txt('OUTPUT1:STATE OFF')

# # ==========================================
# # 6. MENGAMBIL & MEMPLOT DATA
# # ==========================================
# print("Mengunduh data dari Red Pitaya...")
# rp.tx_txt('ACQ:SOUR1:DATA?')
# data_string = rp.rx_txt().strip('{}\n\r').replace("  ", "").split(',')
# data = np.array(list(map(float, data_string)))

# print(f"Selesai! Mendapatkan {len(data)} titik sampel.")

N_AVERAGE = 32
accumulator = None
rp.tx_txt('OUTPUT1:STATE ON')

for shot in range(N_AVERAGE):
    rp.tx_txt('ACQ:RST')
    rp.tx_txt('ACQ:DEC 1')
    rp.tx_txt('ACQ:TRig:DLY 8192')
    rp.tx_txt('ACQ:START')
    rp.tx_txt('ACQ:TRig AWG_PE')      # arm dulu
    rp.tx_txt('SOUR1:TRig:INT')       # baru tembak — TANPA sleep setelahnya

    while True:
        rp.tx_txt('ACQ:TRig:STAT?')
        if rp.rx_txt().strip() == 'TD': break

    while True:
        rp.tx_txt('ACQ:TRig:FILL?')
        if rp.rx_txt().strip() == '1': break

    rp.tx_txt('ACQ:SOUR1:DATA?')
    raw = rp.rx_txt().strip('{}\n\r').replace('  ','').split(',')
    shot_data = np.array(list(map(float, raw)))
    if accumulator is None:
        accumulator = np.zeros(len(shot_data))
    accumulator += shot_data
    print(f'Shot {shot+1}/{N_AVERAGE}')

rp.tx_txt('OUTPUT1:STATE OFF')
data = accumulator / N_AVERAGE
data = data - np.mean(data)          # <-- tambahkan ini

# Membuat grafik visualisasi dengan satuan Waktu (Mikrodetik)
# waktu_us = np.linspace(0, len(data)*(1/125e6)*1e6, len(data))
# t=0 di sample tempat burst mulai (~sample 45)
# Setelah loop averaging, ganti seluruh bagian plotting:

# --- Koreksi waktu ---
ACQ_DLY = 8192
trigger_sample = len(data) - ACQ_DLY
t_trigger_us   = trigger_sample / 125e6 * 1e6
waktu_us       = np.linspace(0, len(data)/125e6*1e6, len(data)) - t_trigger_us

# --- Bandpass filter 5.4–7.4 MHz ---
nyq  = 125e6 / 2
b, a = butter(4, [(6.4e6-1e6)/nyq, (6.4e6+1e6)/nyq], btype='band')
data_filtered = filtfilt(b, a, data)

# --- Envelope Hilbert ---
data_envelope = np.abs(hilbert(data_filtered)) * 1000  # mV

# --- Plot 3 panel ---
fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
fig.suptitle(f'Akuisisi Channel 0 — N={N_AVERAGE} shots averaged, 6.4 MHz', fontsize=13)

axes[0].plot(waktu_us, data,          color='steelblue',  lw=0.4)
axes[0].set_ylabel('Tegangan (V)')
axes[0].set_title('Sinyal Averaged (raw)')
axes[0].set_ylim(-1.1, 1.1)

axes[1].plot(waktu_us, data_filtered, color='darkorange', lw=0.5)
axes[1].set_ylabel('Tegangan (V)')
axes[1].set_title('Setelah Bandpass Filter (5.4–7.4 MHz)')
axes[1].set_ylim(-0.3, 0.3)

axes[2].plot(waktu_us, data_envelope, color='green',      lw=1.2)
axes[2].set_ylabel('Amplitudo (mV)')
axes[2].set_xlabel('Waktu (µs)')
axes[2].set_title('Envelope — Hilbert Transform')

# Tandai echo teoritis (akrilik 1.5cm @ 2700 m/s)
rt_us = 2 * 0.015 / 2700 * 1e6
for n in range(1, 8):
    axes[2].axvline(n * rt_us, color='purple', lw=1, ls=':', alpha=0.6,
                    label=f'Echo ke-{n} ({n*rt_us:.1f}µs)' if n <= 4 else '')
axes[2].axvline(0, color='red', lw=1, ls='--', label='t=0 TX')
axes[2].legend(fontsize=8, loc='upper right')

for ax in axes:
    ax.axvline(0, color='red', lw=0.8, ls='--', alpha=0.4)
    ax.set_xlim(-3, 70)
    ax.grid(True, alpha=0.4)

plt.tight_layout()
plt.savefig('hasil_akuisisi_Channel0.png', dpi=150)

# --- Simpan CSV ---
pd.DataFrame({
    'Waktu_us':     waktu_us,
    'Averaged_V':   data,
    'Filtered_V':   data_filtered,
    'Envelope_mV':  data_envelope,
}).to_csv('hasil_akuisisi_Channel0.csv', index=False)

print(f"Data disimpan. Echo pertama teoritis: {rt_us:.2f}us")
plt.show()