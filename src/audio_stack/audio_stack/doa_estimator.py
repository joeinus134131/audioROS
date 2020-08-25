# Copyright 2016 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import rclpy
from rclpy.node import Node
from rcl_interfaces.msg import SetParametersResult

import matplotlib.pylab as plt
import numpy as np

from audio_interfaces.msg import Correlations, Spectrum
from .beam_former import BeamFormer
from .live_plotter import LivePlotter

MAX_YLIM = 1 # set to inf for no effect.
MIN_YLIM = 1e-13 # set to -inf for no effect.


class DoaEstimator(Node):
    def __init__(self):
        super().__init__('doa_estimator')

        self.subscription_correlations = self.create_subscription(
            Correlations, 'audio/correlations', self.listener_callback_correlations, 10)

        self.publisher_spectrum = self.create_publisher(Spectrum, 'audio/spectrum', 10)

        self.beam_former = None 

        self.plotter = LivePlotter(MAX_YLIM, MIN_YLIM)
        self.plotter.ax.set_xlabel('angle [rad]')
        self.plotter.ax.set_ylabel('magnitude [-]')

        # create ROS parameters that can be changed from command line.
        self.declare_parameter("bf_method")
        self.bf_method = "mvdr"
        parameters = [
                rclpy.parameter.Parameter("bf_method", rclpy.Parameter.Type.STRING, self.bf_method),
        ]
        self.set_parameters_callback(self.set_params)
        self.set_parameters(parameters)


    def set_params(self, params):
        for param in params:
            if param.name == "bf_method":
                self.bf_method = param.get_parameter_value().string_value
            else:
                return SetParametersResult(successful=False)
        return SetParametersResult(successful=True)

    def listener_callback_mic_positions(self, msg_mic):
        self.get_logger().info(f'Updating mic_positions: {mic_positions}.')
        mic_positions = np.array(msg_mic.mic_positions).reshape((msg_mic.n_mics, msg_mic.dimension))
        self.beam_former = BeamFormer(mic_positions)

    def listener_callback_correlations(self, msg_cor):
        self.get_logger().info(f'Processing correlations: {msg_cor.timestamp}.')

        n_frequencies = len(msg_cor.frequencies)
        if n_frequencies >= 2**8:
            self.get_logger().error(f"too many frequencies to process: {n_frequencies}")
            return

        if self.beam_former is None:
            if msg_cor.mic_positions:
                mic_positions = np.array(msg_cor.mic_positions).reshape((msg_cor.n_mics, -1))
                self.beam_former = BeamFormer(mic_positions)
            else:
                self.get_logger().error("need to set send mic_positions in Correlation to do DOA")

        frequencies = np.array(msg_cor.frequencies).astype(np.float) #[10, 100, 1000]
        real_vect = np.array(msg_cor.corr_real_vect)
        imag_vect = np.array(msg_cor.corr_imag_vect)

        R = (real_vect + 1j*imag_vect).reshape((len(frequencies), msg_cor.n_mics, msg_cor.n_mics))

        if self.bf_method == "mvdr":
            spectrum = self.beam_former.get_mvdr_spectrum(R, frequencies) # n_frequencies x n_angles 
        elif self.bf_method == "das":
            spectrum = self.beam_former.get_das_spectrum(R, frequencies) # n_frequencies x n_angles 
        else:
            raise ValueError(self.bf_method) 

        # publish
        msg_spec = Spectrum()
        msg_spec.timestamp = msg_cor.timestamp
        msg_spec.n_frequencies = n_frequencies
        msg_spec.frequencies = list(frequencies)
        msg_spec.spectrum_vect = list(spectrum.flatten())
        self.publisher_spectrum.publish(msg_spec)
        self.get_logger().info(f'Published spectrum.')

        # plot
        assert len(frequencies) == spectrum.shape[0]
        mask = (frequencies <= MAX_FREQ) & (frequencies >= MIN_FREQ)
        labels=[f"f={f:.0f}Hz" for f in frequencies[mask]]
        self.plotter.update_lines(spectrum[mask], self.beam_former.theta_scan, labels=labels)

def main(args=None):
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = current_dir + '/../../../crazyflie-audio/data/simulated'

    rclpy.init(args=args)

    estimator = DoaEstimator()

    rclpy.spin(estimator)

    # Destroy the node explicitly
    # (optional - otherwise it will be done automatically
    # when the garbage collector destroys the node object)
    estimator.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
