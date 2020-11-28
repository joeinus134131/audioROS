#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
parameters.py: Parameters specific to the Crazyflie drone.
"""

HEIGHT_MIC_ARRAY = 0.0 # height of mic array with respect to drone center (in meters)
MIC_D = 0.108  # distance between mics (meters)
MIC_POSITIONS_UNIT = [[-1, -1], [1, -1], [-1, 1], [1, 1]]
MIC_POSITIONS = [[MIC_D / 2 * m for m in mics] for mics in MIC_POSITIONS_UNIT] # relative mic positions
N_MICS = 4 # number of mics
FS = 32000 # sampling frequency [Hz]
N_BUFFER = 2048 # number of samples in audio buffer
FFTSIZE = 32 # number of frequency bins that are sent. 

# name: (effect_number, [min_freq_Hz, max_freq_Hz], duration_sec)
SWEEPS = {
    'sweep': (15, [1000, 5000], 38.0),
    'sweep_low': (16, [900, 1100], 16.0),
    'sweep_high': (17, [3400, 3600], 16.0),
}
