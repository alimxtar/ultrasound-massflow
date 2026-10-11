# -*- coding: utf-8 -*-
"""
Program Pemetaan Profil Pipa (16 Channel) - Smart DSP & Auto-Zero
"""

import numpy as np
import matplotlib.pyplot as plt
import time
import redpitaya_scpi as scpi
from scipy.signal import butter, filtfilt, hilbert

# ==========================================
# 1. KONFIGURASI
# ==========================================
IP = '169.254.66.156'
FREQ = 5000000      
AMPL = 1.0          
BURST_CYCLES = 1    
ACQ_DLY = 8192      
ACQ_DEC = 2         

# Parameter DSP Tingkat Lanjut
FILTER_LOW      = 3_000_000  
FILTER_HIGH     = 4_800_000  
DIGITAL_GAIN    = 12.0       
MA_WINDOW       = 128         
NOISE_THRESHOLD = 0.15       
BLANK_US        = 2.5  

# ==========================================
# 2. INISIALISASI
# ==========================================
rp = scpi.scpi(IP)
print('Berhasil Terhubung ke Red Pitaya')

rp.tx_txt('GEN:RST')
rp.tx_txt('ACQ:RST')

rp.tx_txt('SOUR1:FUNC SINE')
rp.tx_txt(f'SOUR1:FREQ:FIX {FREQ}')
rp.tx_txt(f'SOUR1:VOLT {AMPL}')
rp.tx_txt('SOUR1:BURS:STAT BURST')
rp.tx_txt(f'SOUR1:BURS:NCYC {BURST_CYCLES}')
rp.tx_txt('SOUR1:BURS:NOR 1')
rp.tx_txt('SOUR1:INITValue 0')
rp.tx_txt('SOUR1:BURS:LASTValue 0')

# Setup ADC
rp.tx_txt(f'ACQ:DEC {ACQ_DEC}')            
rp.tx_txt(f'ACQ:TRig:DLY {ACQ_DLY}')       
rp.tx_txt('ACQ:AVG OFF')
rp.tx_txt('ACQ:DATA:FORMAT ASCII')
rp.tx_txt('ACQ:DATA:Units VOLTS')
rp.tx_txt('ACQ:SOUR1:GAIN LV')

# Setup MUX Pins
for i in range(5):
    rp.tx_txt(f'DIG:PIN:DIR OUT,DIO{i}_P')
rp.tx_txt('DIG:PIN DIO4_P,1')

def set_mux_channel(channel):
    b0 = (channel >> 0) & 1
    b1 = (channel >> 1) & 1
    b2 = (channel >> 2) & 1
    b3 = (channel >> 3) & 1
    rp.tx_txt(f'DIG:PIN DIO0_P,{b0}')
    rp.tx_txt(f'DIG:PIN DIO1_P,{b1}')
    rp.tx_txt(f'DIG:PIN DIO2_P,{b2}')
    rp.tx_txt(f'DIG:PIN DIO3_P,{b3}')

# --- PERSIAPAN VARIABEL DSP ---
IDX_MAX = 8000 
fs = 125e6 / ACQ_DEC
nyq = 0.5 * fs
b, a = butter(8, [FILTER_LOW/nyq, FILTER_HIGH/nyq], btype='band')
trigger_sample = 8192 - ACQ_DLY
waktu_us_asli = (np.arange(IDX_MAX) / fs * 1e6 - trigger_sample / fs * 1e6) 
window_kernel = np.ones(MA_WINDOW) / MA_WINDOW

# ==========================================
# 3. PROSES AKUISISI SCANNING 16 CHANNEL
# ==========================================
print("Memulai Scanning Pipa 16 Channel...")
data_envelope_bersih = []
waktu_relatif_list = []
tof_air_list = []

for ch in range(16):
    set_mux_channel(ch)
    time.sleep(0.01) 
    
    rp.tx_txt('ACQ:START')
    rp.tx_txt('OUTPUT1:STATE ON')
    time.sleep(0.001)                 

    rp.tx_txt('ACQ:TRig AWG_PE')
    rp.tx_txt('SOUR1:TRig:INT')
    
    while True:
        if rp.txrx_txt('ACQ:TRig:STAT?').strip() == 'TD': break
    while True:
        if rp.txrx_txt('ACQ:TRig:FILL?').strip() == '1': break
            
    # Ambil Data (C-Level Parser)
    raw_str = rp.txrx_txt('ACQ:SOUR1:DATA?').strip('{}\n\r')
    data_full = np.fromstring(raw_str, sep=',')
    rp.tx_txt('OUTPUT1:STATE OFF')
    
    # --- DSP PER CHANNEL ---
    data = data_full[:IDX_MAX]
    data_filtered = filtfilt(b, a, data) * DIGITAL_GAIN 
    env_raw = np.abs(hilbert(data_filtered))
    env = np.convolve(env_raw, window_kernel, mode='same')
    
    env[env < NOISE_THRESHOLD] = 0.0
    env[waktu_us_asli < BLANK_US] = 0.0
    
    # Auto-Zeroing Tiap Channel
    mask_cari_akrilik = (waktu_us_asli > 2.5) & (waktu_us_asli < 6.0) 
    waktu_relatif_us = np.copy(waktu_us_asli)
    tof_air = 0.0
    
    if np.any(mask_cari_akrilik):
        area_akrilik = env[mask_cari_akrilik]
        if np.max(area_akrilik) > NOISE_THRESHOLD:
            idx_akrilik = np.where(mask_cari_akrilik)[0][np.argmax(area_akrilik)]
            waktu_relatif_us = waktu_us_asli - waktu_us_asli[idx_akrilik]
            
            # Cari Air
            mask_cari_air = (waktu_relatif_us > 1.5) & (waktu_relatif_us < 120.0)
            if np.any(mask_cari_air):
                area_air = env[mask_cari_air]
                if np.max(area_air) > NOISE_THRESHOLD:
                    idx_air = np.where(mask_cari_air)[0][np.argmax(area_air)]
                    tof_air = waktu_relatif_us[idx_air]
                    
                    # Potong pantulan ganda (Reverberation)
                    env[waktu_relatif_us > (tof_air + 2.5)] = 0.0

    data_envelope_bersih.append(env)
    waktu_relatif_list.append(waktu_relatif_us)
    tof_air_list.append(tof_air)
    print(f"✅ CH {ch:02d} Terekam | ToF Air: {tof_air:.2f} µs")
    
    time.sleep(0.01)

rp.close()
data_envelope_bersih = np.array(data_envelope_bersih)

# ==========================================
# 4. VISUALISASI WATERFALL PLOT BERSIH
# ==========================================
print("\nMenampilkan Profil 2D Pipa...")
plt.figure(figsize=(14, 10))

for ch in range(16):
    offset = ch * 0.8  # Jarak antar grafik channel
    waktu_plot = waktu_relatif_list[ch]
    env_plot = data_envelope_bersih[ch] + offset
    
    # Plot dasar
    plt.plot(waktu_plot, env_plot, label=f'CH {ch}' if ch==0 else "", color='black', linewidth=0.8)
    
    # Warna isi (Fill-between) agar mirip peta kontur 2D industri
    plt.fill_between(waktu_plot, offset, env_plot, where=(env_plot > offset), color='red', alpha=0.5)

plt.axvline(0, color='blue', linestyle='--', linewidth=2, label="Dinding Dalam Pipa / Akrilik (0 µs)")
plt.title('Profil 2D Dinding Penampang Pipa (Auto-Zeroing DSP 16 Channel)', fontweight='bold')
plt.xlabel('Waktu Tempuh Relatif di Dalam Fluida (µs)')
plt.ylabel('Susunan Transduser 16 Channel')
plt.yticks(np.arange(0, 16 * 0.8, 0.8), [f"CH {i}" for i in range(16)])
plt.xlim(-5, 100) # Batasi fokus tampilan grafik
plt.grid(True, alpha=0.3, axis='x')
plt.legend(loc='upper right')
plt.tight_layout()

plt.savefig('massflow_16ch_profile.png', dpi=150)
np.save('massflow_16ch_envelope.npy', data_envelope_bersih)
plt.show()