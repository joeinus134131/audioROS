#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
correlator.py: 
"""

import os
import sys
import time

from scipy import signal
import numpy as np

import rclpy
from rclpy.node import Node
from rcl_interfaces.msg import SetParametersResult

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir + '/../../../crazyflie-audio/python/')
from noise_cancellation import filter_iir_bandpass
from algos_beamforming import select_frequencies

from audio_interfaces.msg import Signals, SignalsFreq, Correlations
from .live_plotter import LivePlotter

# Denoising method.
METHOD_NOISE = "bandpass"
METHOD_NOISE_DICT = {
    "bandpass": {
        "fmin": 100,
        "fmax": 300,
        "order": 3
    }
}

# Windowing method. Available: 
# - "" (no window)
# - "tukey" (flat + cosine on borders)
METHOD_WINDOW = "tukey" 

# Frequency selection
N_FREQUENCIES = 10
METHOD_FREQUENCY = "uniform" 
METHOD_FREQUENCY_DICT = {
    "uniform": { # uniform frequencies between min and max
        "num_frequencies": N_FREQUENCIES,
        "min_freq": 200,
        "max_freq": 500,
    },
    "single": { # one single frequency (beam width between min and max)
        "num_frequencies": 1,
        "min_freq": 150,
        "max_freq": 250,
    },
    "between": { # random, between propeller frequencies
        "num_frequencies": N_FREQUENCIES,
        "min_freq": 100,
        "max_freq": 1000,
        "delta": 1
    },
    "between_snr": { # choose highest snr between propeller frequencies
        "num_frequencies": N_FREQUENCIES,
        "min_freq": 100,
        "max_freq": 1000,
        "amp_ratio": 1, 
        "delta": 1
    }
}

# Plotting parameters
MIN_YLIM = 1e-3 # set to -inf for no effect.
MAX_YLIM = 1e5 # set to inf for no effect.
MIN_FREQ = 100 # set to -inf for no effect
MAX_FREQ = 800 # set to inf for no effect

def get_stft(signals, Fs, method_window, method_noise):
    if method_window == "tukey":
        window = signal.tukey(signals.shape[1])
        signals *= window
    elif method_window == "":
        pass
    else:
        raise ValueError(method_window)

    if method_noise == "bandpass":
        signals = filter_iir_bandpass(signals, Fs=Fs, method='cheby2', plot=False, 
                                      **METHOD_NOISE_DICT[method_noise])
    elif method_noise == "single":
        signals = filter_iir_bandpass(signals, Fs=Fs, method='single', plot=False, 
                                      **METHOD_NOISE_DICT[method_noise])
    elif method_noise == "":
        pass
    else:
        ValueError(method_noise)

    signals_f = np.fft.rfft(signals, n=signals.shape[1], axis=1).T # n_samples x n_mics
    freqs = np.fft.rfftfreq(n=signals.shape[1], d=1/Fs)
    return signals_f, freqs


def create_correlations_message(signals_f, freqs, Fs, n_buffer, method_frequency): 
    
    # calculate Rs for chosen frequency bins 
    R = 1 / signals_f.shape[1] * signals_f[:, :, None] @ signals_f[:, None, :].conj()

    msg = Correlations()
    msg.n_mics = int(signals_f.shape[1])
    msg.n_frequencies = len(freqs)
    msg.frequencies = [int(f) for f in freqs]
    msg.corr_real_vect = [float(f) for f in R.real.flatten()]
    msg.corr_imag_vect = [float(f) for f in R.imag.flatten()]
    return msg


class Correlator(Node):
    """ Node to subscribe to audio/signals or audio/signals_f and publish correlations.
    """
    def __init__(self, plot_freq=False, plot_time=False):
        super().__init__('correlator')

        self.plot_freq = plot_freq
        self.plot_time = plot_time
        self.subscription_signals = self.create_subscription(Signals,
            'audio/signals',
            self.listener_callback_signals, 10)
        self.subscription_signals_f = self.create_subscription(SignalsFreq,
            'audio/signals_f',
            self.listener_callback_signals_f, 10)
        self.publisher_correlations = self.create_publisher(Correlations, 'audio/correlations', 10)

        self.current_n_buffer = None
        self.current_n_frequencies = None

        if self.plot_freq:
            self.plotter_freq = LivePlotter(MAX_YLIM, MIN_YLIM)
            self.plotter_freq.ax.set_xlabel('frequency [Hz]')
            self.plotter_freq.ax.set_ylabel('magnitude [-]')

        if self.plot_time:
            self.plotter_time = LivePlotter(MAX_YLIM, MIN_YLIM, log=False)
            self.plotter_time.ax.set_xlabel('time idx [-]')
            self.plotter_time.ax.set_ylabel('magnitude [-]')

        self.methods = {
                "noise": METHOD_NOISE,
                "window": METHOD_WINDOW,
                "frequency": METHOD_FREQUENCY,
        }
        parameters = []
        for key, value in self.methods.items():
            self.declare_parameter(key)
            parameters.append(
                    rclpy.parameter.Parameter(key, rclpy.Parameter.Type.STRING, value)
            )
        self.set_parameters_callback(self.set_params)
        self.set_parameters(parameters)

    def set_params(self, params):
        for param in params:
            if param.name in self.methods.keys():
                self.methods[param.name] = param.get_parameter_value().string_value
            else:
                return SetParametersResult(successful=False)
        return SetParametersResult(successful=True)

    def listener_callback_signals(self, msg):
        t1 = time.time()
        self.labels = [f"mic{i}" for i in range(msg.n_mics)]
        self.mic_positions = np.array(msg.mic_positions).reshape((msg.n_mics, -1))

        signals = np.array(msg.signals_vect)
        signals = signals.reshape((msg.n_mics, msg.n_buffer))

        if self.plot_time: 
            if msg.n_buffer != self.current_n_buffer:
                self.plotter_time.clear()

            self.plotter_time.update_lines(signals, range(signals.shape[1]), self.labels)
            self.current_n_buffer = msg.n_buffer

        # processing
        signals_f, freqs = get_stft(signals, msg.fs, self.methods["window"], self.methods["noise"]) # n_samples x n_mics
        if self.methods["frequency"] != "":
            bins = select_frequencies(msg.n_buffer, msg.fs, self.methods["frequency"], buffer_f=signals_f,
                                      **METHOD_FREQUENCY_DICT[self.methods["frequency"]])
            freqs = freqs[bins]
            signals_f = signals_f[bins]

        # TODO: we could publish signals_f to audio/signals_f topic here, but not sure
        # if that would introduce too much overhead.
        self.process_signals_f(signals_f, freqs, msg.fs, msg.timestamp)

        # check that the above processing pipeline does not
        # take too long compared to the desired publish rate.
        t2 = time.time()
        processing_time = t2-t1
        self.get_logger().info(f'listener_callback_signals: Publishing after processing time {processing_time}')

    def listener_callback_signals_f(self, msg):
        t1 = time.time()
        self.labels = [f"mic{i}" for i in range(msg.n_mics)]
        self.mic_positions = np.array(msg.mic_positions).reshape((msg.n_mics, -1))

        # convert msg format to numpy arrays
        signals_f = np.array(msg.signals_real_vect) + 1j*np.array(msg.signals_imag_vect)
        signals_f = signals_f.reshape((msg.n_mics, msg.n_frequencies)).T
        freqs = np.array(msg.frequencies)

        # TODO(FD): will move this scheme to the microprocessor eventually. 
        mask = (freqs < MAX_FREQ) & (freqs > MIN_FREQ)
        freqs = freqs[mask]
        signals_f = signals_f[mask]

        if not len(freqs):
            self.get_logger().error(f'no frequency bins in range {MIN_FREQ}, {MAX_FREQ}')

        self.process_signals_f(signals_f, freqs, msg.fs, msg.timestamp)

        # check that the above processing pipeline does not
        # take too long compared to the desired publish rate.
        t2 = time.time()
        processing_time = t2-t1
        self.get_logger().info(f'listener_callback_signals_f: Publishing after processing time {processing_time}')

    def process_signals_f(self, signals_f, freqs, Fs, timestamp):
        msg_new = create_correlations_message(signals_f, freqs, Fs, signals_f.shape[0], self.methods["frequency"])
        # TODO(FD): replace with a better timestamp.
        msg_new.mic_positions = list(self.mic_positions.astype(float).flatten())
        msg_new.timestamp = timestamp

        # plotting
        if self.plot_freq: 
            if  msg_new.n_frequencies != self.current_n_frequencies:
                self.plotter_freq.clear()
            self.plotter_freq.update_lines(np.abs(signals_f.T), freqs, self.labels)
            self.plotter_freq.ax.set_title(f"time (ms): {msg_new.timestamp}")
            self.plotter_freq.update_axvlines(freqs)
            self.current_n_frequencies = msg_new.n_frequencies
        # publishing
        self.publisher_correlations.publish(msg_new)


def main(args=None):
    rclpy.init(args=args)

    correlator = Correlator(plot_freq=True, plot_time=True)
    rclpy.spin(correlator)

    # Destroy the node explicitly
    correlator.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
