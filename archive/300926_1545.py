# -*- coding: utf-8 -*-
"""
Program Uji Coba 1 Channel (Channel 0) - Mass Flow Ultrasonik
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
FREQ_HZ      = 6_400_000   # frekuensi AWG (Hz)
N_CYCLES     = 2           # jumlah siklus per burst
AWG_VOLT     = 1         # amplitudo AWG ke MAX913 (V)
ACQ_DLY      = 0        # samples post-trigger yang disimpan
ACQ_DEC      = 1           # decimation (1 = 125 MSps)
WAIT_TIMEOUT = 100         # maksimal cek status WAIT (x10ms = 1 detik)

# ==========================================
# 2. KONEKSI & RESET AWAL (sekali saja)
# ==========================================
rp = scpi.scpi(IP_ADDRESS)
print(f"Terhubung ke Red Pitaya: {IP_ADDRESS}")

# Pastikan kondisi bersih di awal program
rp.tx_txt('OUTPUT1:STATE OFF')
rp.tx_txt('GEN:RST')
rp.tx_txt('ACQ:RST')
time.sleep(0.1)

# ==========================================
# 3. KONFIGURASI AWG (sekali saja, tidak diulang tiap akuisisi)
# ==========================================
rp.tx_txt('SOUR1:FUNC SINE')
rp.tx_txt(f'SOUR1:FREQ:FIX {FREQ_HZ}')
rp.tx_txt(f'SOUR1:VOLT {AWG_VOLT}')
rp.tx_txt('SOUR1:BURS:STAT BURST')
rp.tx_txt(f'SOUR1:BURS:NCYC {N_CYCLES}')
# OUTPUT1 ON di sini tapi BURST mode = tidak ada sinyal keluar
# sampai SOUR1:TRig:INT dipanggil
rp.tx_txt('OUTPUT1:STATE ON')
time.sleep(0.05)  # beri waktu AWG settle dalam mode idle BURST

# ==========================================
# 4. KONFIGURASI MUX — Channel 0 (A3A2A1A0 = 0000)
# ==========================================
for pin in ['DIO0_P', 'DIO1_P', 'DIO2_P', 'DIO3_P', 'DIO4_P']:
    rp.tx_txt(f'DIG:PIN:DIR OUT,{pin}')

rp.tx_txt('DIG:PIN DIO0_P,0')  # A0
rp.tx_txt('DIG:PIN DIO1_P,0')  # A1
rp.tx_txt('DIG:PIN DIO2_P,0')  # A2
rp.tx_txt('DIG:PIN DIO3_P,0')  # A3
rp.tx_txt('DIG:PIN DIO4_P,1')  # EN = HIGH (ADG1206 aktif HIGH)
print("MUX terkunci di Channel 0.")
time.sleep(0.1)

# ==========================================
# 5. EKSEKUSI PENEMBAKAN & PEREKAMAN
# ==========================================

# Pastikan AWG benar-benar berhenti sebelum akuisisi berikutnya
rp.tx_txt('OUTPUT1:STATE OFF')
time.sleep(0.1)

# Reset acquisition
rp.tx_txt('ACQ:RST')
time.sleep(0.05)

# Konfigurasi ADC
rp.tx_txt(f'ACQ:DEC {ACQ_DEC}')
rp.tx_txt('ACQ:AVG OFF')
rp.tx_txt('ACQ:DATA:FORMAT ASCII')
rp.tx_txt('ACQ:DATA:Units VOLTS')
rp.tx_txt('ACQ:SOUR1:GAIN LV')
rp.tx_txt(f'ACQ:TRig:DLY {ACQ_DLY}')

# ARM ADC
rp.tx_txt('ACQ:START')

# Beri waktu ADC benar-benar masuk mode acquisition
time.sleep(0.05)

# Set sumber trigger AWG
rp.tx_txt('ACQ:TRig AWG_PE')

# Pastikan ADC benar-benar WAIT
print("Menunggu ADC siap...")

for i in range(WAIT_TIMEOUT):
    rp.tx_txt('ACQ:TRig:STAT?')
    status = rp.rx_txt().strip()

    if status == 'WAIT':
        break

    time.sleep(0.01)

else:
    print(f"ERROR: ADC tidak WAIT. Status: {status}")
    rp.tx_txt('OUTPUT1:STATE OFF')
    rp.close()
    raise SystemExit(1)

print("ADC siap. Menembak burst...")

# Trigger AWG
rp.tx_txt('SOUR1:TRig:INT')

# Tunggu ADC menerima trigger
for i in range(5000):
    rp.tx_txt('ACQ:TRig:STAT?')
    status = rp.rx_txt().strip()

    if status == 'TD':
        break

    time.sleep(0.001)

else:
    print("ERROR: ADC tidak menerima trigger.")
    rp.tx_txt('OUTPUT1:STATE OFF')
    rp.close()
    raise SystemExit(1)

print("Trigger diterima.")

# Tunggu seluruh buffer selesai diisi
for i in range(5000):
    rp.tx_txt('ACQ:TRig:FILL?')
    fill = rp.rx_txt().strip()

    if fill == '1':
        break

    time.sleep(0.001)

else:
    print("ERROR: Buffer ADC tidak penuh.")
    rp.tx_txt('OUTPUT1:STATE OFF')
    rp.close()
    raise SystemExit(1)

print("Buffer penuh. Rekaman selesai.")

# Matikan output setelah acquisition selesai
rp.tx_txt('OUTPUT1:STATE OFF')
time.sleep(0.05)

# ==========================================
# 6. AMBIL DATA
# ==========================================
print("Mengunduh data...")
rp.tx_txt('ACQ:SOUR1:DATA?')
raw = rp.rx_txt().strip('{}\n\r').replace('  ', '').split(',')
data = np.array(list(map(float, raw)))
print(f"Selesai: {len(data)} sampel.")

rp.tx_txt('OUTPUT1:STATE OFF')
rp.close()

# ==========================================
# 7. KOREKSI WAKTU
# ==========================================
# DLY=8192, buffer=16384 -> trigger di sample (16384 - 8192) = 8192
# t=0 = saat AWG tembak
fs = 125e6 / ACQ_DEC
trigger_sample = 8192 - ACQ_DLY
waktu_us = (
    np.arange(len(data)) / fs * 1e6
    - trigger_sample / fs * 1e6
)
# ==========================================
# 8. PLOT & SIMPAN GAMBAR
# ==========================================
timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

fig, ax = plt.subplots(figsize=(12, 5))
ax.plot(waktu_us, data, color='blue', linewidth=0.5)
ax.set_title(f"Echo Uji Coba Transduser - Channel 0  [{timestamp}]")
ax.set_xlim(-5, 80)
ax.set_ylim(-1.1, 1.1)
ax.set_xlabel("Waktu (µs) — t=0 saat AWG tembak")
ax.set_ylabel("Tegangan (V)")
ax.axvline(0, color='red', linestyle='--', linewidth=0.8, label='t=0 TX')

# Tandai posisi echo teoritis akrilik 1.5 cm @ 2700 m/s
ACRYLIC_THICKNESS_M = 0.010
ACRYLIC_SOUND_SPEED = 2700

rt_us = (
    2 * ACRYLIC_THICKNESS_M /
    ACRYLIC_SOUND_SPEED
) * 1e6

for n in range(1, 7):
    ax.axvline(n * rt_us, color='purple', linestyle=':', linewidth=0.8,
               alpha=0.5, label=f'Echo ke-{n} ({n*rt_us:.1f}µs)' if n <= 3 else '_')

ax.legend(fontsize=8, loc='upper right')
ax.grid(True, alpha=0.4)
plt.tight_layout()

nama_gambar = f'plot_{timestamp}.png'
plt.savefig(nama_gambar, dpi=150)
print(f"Gambar disimpan: {nama_gambar}")

# ==========================================
# 9. SIMPAN CSV
# ==========================================
nama_csv = f'hasil_{timestamp}.csv'
pd.DataFrame({
    'Waktu_us':       waktu_us,
    'Amplitudo_Volt': data,
}).to_csv(nama_csv, index=False)
print(f"CSV disimpan: {nama_csv}")

plt.show()