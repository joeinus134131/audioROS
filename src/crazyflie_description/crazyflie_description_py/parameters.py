#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
parameters.py: Parameters specific to the Crazyflie drone.
"""

HEIGHT_MIC_ARRAY = 0.0 # height of mic array with respect to drone center (in meters)
HEIGHT_BUZZER = 0.01 # height of buzzer with resepect to drone center (in meteers) 
MIC_D = 0.108  # distance between mics (meters)
MIC_POSITIONS_UNIT = [[-1, -1], [1, -1], [-1, 1], [1, 1]]
MIC_POSITIONS = [[MIC_D / 2 * m for m in mics] for mics in MIC_POSITIONS_UNIT] # relative mic positions
BUZZER_POSITION = [[0.0, 0.0]] # relative buzzer position (in meters)
N_MICS = 4 # number of mics
FS = 32000 # sampling frequency [Hz]
N_BUFFER = 2048 # number of samples in audio buffer
FFTSIZE = 32 # number of frequency bins that are sent. 

TUKEY_ALPHA = 0.2 # alpha parameter for tukey window

# name: (effect_number, [min_freq_Hz, max_freq_Hz], duration_sec)
SOUND_EFFECTS = {
    'sweep':      (15, [1000, 5000], 38.0),  
    'sweep_high': (16, [2000, 6000], 38.0),  
    'sweep_short': (17, [3000, 5000], 20.0), 
    'sweep_all':    (18, [0,   16000],  513),  
    'sweep_buzzer':  (20, [0,   16000],  185),
    'sweep_slow':   (21,  [1000, 5000], 0), # will be overwritten
    'sweep_fast':   (22,  [1000, 5000], 0), # will be overwritten
}

WINDOW_TYPES = {
    0: '',
    1: 'hann',
    2: 'flattop',
    3: 'tukey'
}

# below is found by increasing n_buffer and finding to what sum(window)/n_buffer converges.
WINDOW_CORRECTION = {
    '': 1.0,
    'hann': 0.5, 
    'flattop': 0.215579,
    'tukey': 0.9,
}
