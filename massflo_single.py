# -*- coding: utf-8 -*-
"""
Program Uji Coba 1 Channel - Mass Flow (STATIK / SEKALI TEMBAK)
Telah menggunakan algoritma DSP terbaru & Auto-Zeroing
"""

import numpy as np
import matplotlib.pyplot as plt
import time
import datetime
import redpitaya_scpi as scpi
import pandas as pd
from scipy.signal import butter, filtfilt, hilbert

# ==========================================
# 1. KONFIGURASI
# ==========================================
IP_ADDRESS   = 'RP-F0B91C.LOCAL'
FREQ_HZ      = 5_000_000   
N_CYCLES     = 1           
AWG_VOLT     = 1.0         
ACQ_DLY      = 8192        
ACQ_DEC      = 2           

FILTER_LOW      = 3_000_000  
FILTER_HIGH     = 4_800_000  
DIGITAL_GAIN    = 12.0       
MA_WINDOW       = 128         
NOISE_THRESHOLD = 0.15       
BLANK_US        = 2.5  

# ==========================================
# 2. INISIALISASI & PENGAMBILAN DATA
# ==========================================
rp = scpi.scpi(IP_ADDRESS)
print(f"Terhubung ke Red Pitaya: {IP_ADDRESS}")

rp.tx_txt('OUTPUT1:STATE OFF')
rp.tx_txt('GEN:RST')
rp.tx_txt('ACQ:RST')
time.sleep(0.1)

rp.tx_txt('SOUR1:FUNC SINE')
rp.tx_txt(f'SOUR1:FREQ:FIX {FREQ_HZ}')
rp.tx_txt(f'SOUR1:VOLT {AWG_VOLT}')
rp.tx_txt('SOUR1:BURS:STAT BURST')
rp.tx_txt(f'SOUR1:BURS:NCYC {N_CYCLES}')
rp.tx_txt('SOUR1:BURS:NOR 1')
rp.tx_txt('SOUR1:INITValue 0')
rp.tx_txt('SOUR1:BURS:LASTValue 0')

for pin in ['DIO0_P', 'DIO1_P', 'DIO2_P', 'DIO3_P', 'DIO4_P']:
    rp.tx_txt(f'DIG:PIN:DIR OUT,{pin}')
rp.tx_txt('DIG:PIN DIO0_P,0')
rp.tx_txt('DIG:PIN DIO1_P,0')
rp.tx_txt('DIG:PIN DIO2_P,0')
rp.tx_txt('DIG:PIN DIO3_P,0')
rp.tx_txt('DIG:PIN DIO4_P,1')

rp.tx_txt('OUTPUT1:STATE ON')
time.sleep(0.5) 

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

print("Menembak burst...")
rp.tx_txt('SOUR1:TRig:INT')

while True:
    if rp.txrx_txt('ACQ:TRig:STAT?').strip() == 'TD':
        break
while True:
    if rp.txrx_txt('ACQ:TRig:FILL?').strip() == '1':
        break

print("Mengunduh data...")
raw_str = rp.txrx_txt('ACQ:SOUR1:DATA?').strip('{}\n\r')
data_full = np.fromstring(raw_str, sep=',')

rp.tx_txt('OUTPUT1:STATE OFF')
rp.close()

# ==========================================
# 3. DSP & AUTO-ZEROING
# ==========================================
IDX_MAX = 8000
data = data_full[:IDX_MAX]
fs = 125e6 / ACQ_DEC
nyq = 0.5 * fs
trigger_sample = 8192 - ACQ_DLY
waktu_us = (np.arange(IDX_MAX) / fs * 1e6 - trigger_sample / fs * 1e6) 

b, a = butter(8, [FILTER_LOW/nyq, FILTER_HIGH/nyq], btype='band')
data_filtered = filtfilt(b, a, data) * DIGITAL_GAIN 
data_envelope_raw = np.abs(hilbert(data_filtered))
window_kernel = np.ones(MA_WINDOW) / MA_WINDOW
data_envelope = np.convolve(data_envelope_raw, window_kernel, mode='same')

data_envelope[data_envelope < NOISE_THRESHOLD] = 0.0
data_envelope[waktu_us < BLANK_US] = 0.0

mask_cari_akrilik = (waktu_us > 2.5) & (waktu_us < 6.0) 
waktu_akrilik = 0.0
waktu_relatif_us = np.copy(waktu_us)
waktu_air = 0.0
amp_air = 0.0

if np.any(mask_cari_akrilik):
    area_akrilik_env = data_envelope[mask_cari_akrilik]
    if np.max(area_akrilik_env) > NOISE_THRESHOLD:
        idx_lokal_akrilik = np.argmax(area_akrilik_env)
        idx_akrilik = np.where(mask_cari_akrilik)[0][idx_lokal_akrilik] 
        waktu_akrilik = waktu_us[idx_akrilik]
        waktu_relatif_us = waktu_us - waktu_akrilik 
        
        mask_cari_air = (waktu_relatif_us > 1.5) & (waktu_relatif_us < 120.0)
        if np.any(mask_cari_air):
            area_air_env = data_envelope[mask_cari_air]
            if np.max(area_air_env) > NOISE_THRESHOLD:
                idx_lokal_air = np.argmax(area_air_env)
                idx_air = np.where(mask_cari_air)[0][idx_lokal_air]
                waktu_air = waktu_relatif_us[idx_air]
                amp_air = data_envelope[idx_air]
                
                # Dynamic Reverberation Blanking
                mask_pantulan_ganda = waktu_relatif_us > (waktu_air + 2.5)
                data_envelope[mask_pantulan_ganda] = 0.0

# ==========================================
# 4. PLOT & SIMPAN
# ==========================================
timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=False)

ax1.plot(waktu_us, data, color='blue', linewidth=0.5)
ax1.set_title(f"Sinyal Mentah AC [{timestamp}]")
ax1.set_ylabel("Tegangan (V)")
ax1.set_xlim(-5, 120)
ax1.grid(True, alpha=0.3)

ax2.plot(waktu_relatif_us, data_envelope, color='red', linewidth=1.5)
ax2.axvline(0, color='black', linestyle='--', linewidth=1, label="Batas Akrilik (0 µs)")
if waktu_air > 0:
    ax2.scatter([waktu_air], [amp_air], color='blue', s=60, zorder=5, label='Permukaan Air')
    ax2.text(0.02, 0.85, f'ToF Air: {waktu_air:.2f} µs', transform=ax2.transAxes, fontsize=12, fontweight='bold', color='blue', bbox=dict(facecolor='white', alpha=0.8))

ax2.set_title(f"Hasil Ekstraksi Murni | Terkalibrasi Akrilik: -{waktu_akrilik:.2f} µs")
ax2.set_xlabel("Waktu Tempuh Relatif di dalam Air (µs)")
ax2.set_ylabel("Amplitudo")
ax2.set_xlim(-5, 100)
ax2.legend(loc='upper right')
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(f'plot_visual_{timestamp}.png', dpi=150)

pd.DataFrame({
    'Waktu_Relatif_us': waktu_relatif_us,
    'Amplitudo_Raw': data,
    'Envelope_Volt': data_envelope
}).to_csv(f'hasil_visual_{timestamp}.csv', index=False)

print(f"Data tersimpan: hasil_visual_{timestamp}.csv")
plt.show()