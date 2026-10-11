# -*- coding: utf-8 -*-
"""
Program Mass Flow Ultrasonik - REAL-TIME OSCILLOSCOPE
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
MA_WINDOW       = 32 #128        
NOISE_THRESHOLD = 0.05 #0.15       
BLANK_US        = 25.0       

# ==========================================
# 2. INISIALISASI RED PITAYA
# ==========================================
rp = scpi.scpi(IP_ADDRESS)
print(f"Terhubung ke Red Pitaya: {IP_ADDRESS}")

rp.tx_txt('OUTPUT1:STATE OFF')
rp.tx_txt('GEN:RST')
rp.tx_txt('ACQ:RST')
time.sleep(0.1)

# Setting AWG
rp.tx_txt('SOUR1:FUNC SINE')
rp.tx_txt(f'SOUR1:FREQ:FIX {FREQ_HZ}')
rp.tx_txt(f'SOUR1:VOLT {AWG_VOLT}')
rp.tx_txt('SOUR1:BURS:STAT BURST')
rp.tx_txt(f'SOUR1:BURS:NCYC {N_CYCLES}')
rp.tx_txt('SOUR1:BURS:NOR 1')
rp.tx_txt('SOUR1:INITValue 0')
rp.tx_txt('SOUR1:BURS:LASTValue 0')

# Setting MUX
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

# Hitung variabel waktu & filter sekali saja di awal untuk mempercepat loop
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
plt.ion()  # Aktifkan Mode Interaktif (Animasi)
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

# Buat garis kosong yang akan di-update terus menerus
line_raw, = ax1.plot(waktu_us, np.zeros_like(waktu_us), color='blue', linewidth=0.5)
ax1.set_title("Real-Time Sinyal Mentah AC")
ax1.set_ylabel("Tegangan (V)")
ax1.set_xlim(RANGEXLIM, RANGEYXLIM)
ax1.set_ylim(-1.0, 1.0)
ax1.grid(True, alpha=0.3)

line_env, = ax2.plot(waktu_us, np.zeros_like(waktu_us), color='red', linewidth=1.5)
ax2.set_title("Real-Time Echo (Filtered + Mute)")
ax2.set_xlabel("Waktu (µs)")
ax2.set_ylabel("Amplitudo")
ax2.set_ylim(-0.05, 1.5) # Ubah angka 1.5 ke nilai yang lebih tinggi jika puncak echo terpotong
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.show(block=False)

print("-------------------------------------------------")
print("🚀 SISTEM REAL-TIME BERJALAN!")
print("Tekan Ctrl+C di terminal ini untuk menghentikan.")
print("-------------------------------------------------")

# ==========================================
# 4. LOOP PENGAMBILAN DATA (Terus Menerus)
# ==========================================
try:
    while True:
        # A. Tembak dan Rekam
        rp.tx_txt(f'ACQ:DEC {ACQ_DEC}')
        rp.tx_txt('ACQ:AVG OFF')
        rp.tx_txt('ACQ:DATA:FORMAT ASCII')
        rp.tx_txt('ACQ:DATA:Units VOLTS')
        rp.tx_txt('ACQ:SOUR1:GAIN LV')
        rp.tx_txt(f'ACQ:TRig:DLY {ACQ_DLY}')
        
        rp.tx_txt('ACQ:START')
        rp.tx_txt('ACQ:TRig AWG_PE')
        rp.tx_txt('SOUR1:TRig:INT')
        
        # Tunggu buffer penuh dengan cara cepat
        while True:
            if rp.txrx_txt('ACQ:TRig:STAT?').strip() == 'TD':
                break
        while True:
            if rp.txrx_txt('ACQ:TRig:FILL?').strip() == '1':
                break
        
        # B. Unduh Data Mentah
        raw_str = rp.txrx_txt('ACQ:SOUR1:DATA?').strip('{}\n\r').replace('  ', '').split(',')
        data = np.array(list(map(float, raw_str)))
        
        # C. Pemrosesan Sinyal Digital (DSP)
        data_filtered = filtfilt(b, a, data) * DIGITAL_GAIN 
        data_envelope_raw = np.abs(hilbert(data_filtered))
        data_envelope = np.convolve(data_envelope_raw, window_kernel, mode='same')
        
        data_envelope[data_envelope < NOISE_THRESHOLD] = 0.0
        data_envelope[blank_mask] = 0.0
        
        # D. Update Gambar di Layar
        line_raw.set_ydata(data)
        line_env.set_ydata(data_envelope)
        
        # Auto-scale Y axis pada grafik Envelope jika sinyal tiba-tiba membesar
        max_env = np.max(data_envelope)
        if max_env > ax2.get_ylim()[1]:
            ax2.set_ylim(-0.05, max_env * 1.2)
            
        fig.canvas.draw()
        fig.canvas.flush_events() # Paksa layar me-refresh tanpa nge-hang

except KeyboardInterrupt:
    # Program akan masuk ke sini jika Anda menekan Ctrl+C
    print("\nMenghentikan Sistem Real-Time...")
    rp.tx_txt('OUTPUT1:STATE OFF')
    rp.close()
    plt.ioff()
    plt.show()
    print("Sistem dihentikan dengan aman.")