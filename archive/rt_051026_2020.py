# -*- coding: utf-8 -*-
"""
Program Mass Flow Ultrasonik - REAL-TIME OSCILLOSCOPE & TOF TRACKER
Tekan Ctrl+C di terminal/console untuk menghentikan program.
"""

import numpy as np
import matplotlib.pyplot as plt
import time
import redpitaya_scpi as scpi
from scipy.signal import butter, filtfilt, hilbert, find_peaks

# ==========================================
# 1. KONFIGURASI
# ==========================================
IP_ADDRESS   = 'RP-F0B91C.LOCAL'
FREQ_HZ      = 5_000_000   
N_CYCLES     = 1           
AWG_VOLT     = 1.0         
ACQ_DLY      = 8192        
ACQ_DEC      = 2           

RANGEXLIM    = -5          
RANGEYXLIM   = 150         

FILTER_LOW      = 3_000_000  
FILTER_HIGH     = 4_800_000  
DIGITAL_GAIN    = 12.0       
MA_WINDOW       = 32         
NOISE_THRESHOLD = 0.05       
BLANK_US        = 2.0  # Mute awal agar ledakan listrik tidak terdeteksi 

# ==========================================
# 2. INISIALISASI RED PITAYA
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
print("Mempersiapkan alat... (0.5 detik)")
time.sleep(0.5)

fs = 125e6 / ACQ_DEC
nyq = 0.5 * fs
b, a = butter(8, [FILTER_LOW/nyq, FILTER_HIGH/nyq], btype='band')
trigger_sample = 8192 - ACQ_DLY
waktu_us = (np.arange(16384) / fs * 1e6 - trigger_sample / fs * 1e6) 
blank_mask = waktu_us < BLANK_US
window_kernel = np.ones(MA_WINDOW) / MA_WINDOW

# ==========================================
# 3. PERSIAPAN GRAFIK REAL-TIME
# ==========================================
plt.ion()  
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=False)

line_raw, = ax1.plot(waktu_us, np.zeros_like(waktu_us), color='blue', linewidth=0.5)
ax1.set_title("Real-Time Sinyal Mentah AC")
ax1.set_ylabel("Tegangan (V)")
ax1.set_xlim(RANGEXLIM, RANGEYXLIM)
ax1.set_ylim(-1.0, 1.0)
ax1.grid(True, alpha=0.3)

waktu_relatif_us = np.copy(waktu_us)
line_env, = ax2.plot(waktu_relatif_us, np.zeros_like(waktu_relatif_us), color='red', linewidth=1.5)
ax2.set_title("Real-Time Echo | Menunggu Sinyal...")
ax2.set_xlabel("Waktu Tempuh Relatif di dalam Air (µs)")
ax2.set_ylabel("Amplitudo")
ax2.set_xlim(-5, 100) 
ax2.set_ylim(-0.05, 1.5) 
ax2.grid(True, alpha=0.3)

# Tambahan Indikator Angka ToF & Marker
line_akrilik = ax2.axvline(0, color='black', linestyle='--', linewidth=1, label="Batas Akrilik (0 µs)")
marker_air = ax2.scatter([], [], color='blue', s=60, zorder=5, label='Deteksi Permukaan Air')
teks_tof = ax2.text(0.02, 0.85, 'ToF Air: - µs', transform=ax2.transAxes, fontsize=14, 
                    fontweight='bold', color='blue', bbox=dict(facecolor='white', alpha=0.8, edgecolor='blue'))
ax2.legend(loc='upper right')

plt.tight_layout()
plt.show(block=False)

print("-------------------------------------------------")
print("🚀 SISTEM REAL-TIME & TOF TRACKER BERJALAN!")
print("Tekan Ctrl+C di terminal ini untuk menghentikan.")
print("-------------------------------------------------")

# ==========================================
# 4. LOOP PENGAMBILAN DATA
# ==========================================
try:
    while True:
        rp.tx_txt(f'ACQ:DEC {ACQ_DEC}')
        rp.tx_txt('ACQ:AVG OFF')
        rp.tx_txt('ACQ:DATA:FORMAT ASCII')
        rp.tx_txt('ACQ:DATA:Units VOLTS')
        rp.tx_txt('ACQ:SOUR1:GAIN LV')
        rp.tx_txt(f'ACQ:TRig:DLY {ACQ_DLY}')
        
        rp.tx_txt('ACQ:START')
        rp.tx_txt('ACQ:TRig AWG_PE')
        rp.tx_txt('SOUR1:TRig:INT')
        
        while True:
            if rp.txrx_txt('ACQ:TRig:STAT?').strip() == 'TD':
                break
        while True:
            if rp.txrx_txt('ACQ:TRig:FILL?').strip() == '1':
                break
        
        raw_str = rp.txrx_txt('ACQ:SOUR1:DATA?').strip('{}\n\r').replace('  ', '').split(',')
        data = np.array(list(map(float, raw_str)))
        
        data_filtered = filtfilt(b, a, data) * DIGITAL_GAIN 
        data_envelope_raw = np.abs(hilbert(data_filtered))
        data_envelope = np.convolve(data_envelope_raw, window_kernel, mode='same')
        
        data_envelope[data_envelope < NOISE_THRESHOLD] = 0.0
        data_envelope[blank_mask] = 0.0
        
        # --- 1. DETEKSI AKRILIK (Auto-Zeroing) ---
        mask_cari_akrilik = (waktu_us > 2.0) & (waktu_us < 15.0)
        waktu_akrilik = 0.0
        waktu_relatif_us = np.copy(waktu_us)
        waktu_air = 0.0
        amp_air = 0.0
        
        if np.any(mask_cari_akrilik):
            area_akrilik_env = data_envelope[mask_cari_akrilik]
            if np.max(area_akrilik_env) > NOISE_THRESHOLD:
                puncak_lokal = np.argmax(area_akrilik_env)
                idx_akrilik = np.where(mask_cari_akrilik)[0][puncak_lokal] 
                waktu_akrilik = waktu_us[idx_akrilik]
                waktu_relatif_us = waktu_us - waktu_akrilik 
                ax2.set_title(f"Real-Time Echo | Terkalibrasi di Akrilik: -{waktu_akrilik:.2f} µs")
                
                # --- 2. DETEKSI PERMUKAAN AIR (ToF Tracker) ---
                # Mencari puncak echo setelah zona denging akrilik mereda (> 10 us setelah akrilik)
                mask_cari_air = (waktu_relatif_us > 10.0) & (waktu_relatif_us < 120.0)
                if np.any(mask_cari_air):
                    area_air_env = data_envelope[mask_cari_air]
                    puncak_air, properties = find_peaks(area_air_env, height=NOISE_THRESHOLD, distance=30)
                    
                    if len(puncak_air) > 0:
                        # PERBAIKAN: Cari puncak dengan amplitudo TERTINGGI, bukan yang pertama muncul
                        amplitudo_puncak = properties['peak_heights']
                        idx_tertinggi_lokal = puncak_air[np.argmax(amplitudo_puncak)]
                        
                        # Kembalikan ke index utama
                        idx_air = np.where(mask_cari_air)[0][idx_tertinggi_lokal]
                        waktu_air = waktu_relatif_us[idx_air]
                        amp_air = data_envelope[idx_air]
            else:
                ax2.set_title("Real-Time Echo | Akrilik Tidak Terdeteksi")
        
        # Update Sumbu dan Plot
        line_raw.set_ydata(data)
        line_env.set_xdata(waktu_relatif_us)
        line_env.set_ydata(data_envelope)
        
        # Update Teks dan Titik Tracker Air
        if waktu_air > 0.0:
            marker_air.set_offsets([[waktu_air, amp_air]])
            teks_tof.set_text(f"⏱ ToF Air: {waktu_air:.2f} µs")
        else:
            marker_air.set_offsets(np.empty((0, 2)))
            teks_tof.set_text("⏱ ToF Air: Mencari...")
        
        # Auto-scale Y axis
        max_env = np.max(data_envelope)
        if max_env > ax2.get_ylim()[1]:
            ax2.set_ylim(-0.05, max_env * 1.2)
            
        fig.canvas.draw()
        fig.canvas.flush_events() 

except KeyboardInterrupt:
    print("\nMenghentikan Sistem Real-Time...")
    rp.tx_txt('OUTPUT1:STATE OFF')
    rp.close()
    plt.ioff()
    plt.show()
    print("Sistem dihentikan dengan aman.")