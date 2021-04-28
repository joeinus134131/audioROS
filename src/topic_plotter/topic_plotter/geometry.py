#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
geometry.py: 
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped

import numpy as np

from audio_interfaces.msg import PoseRaw, DoaEstimates, GroundTruth
from audio_interfaces_py.messages import (
    read_pose_raw_message,
    read_pose_message,
)
from audio_stack.topic_synchronizer import TopicSynchronizer
from audio_simulation.geometry import SPEAKER_POSITION, ROOM_DIM, STARTING_POS

from .live_plotter import LivePlotter

MAX_LENGTH = 1000  # number of positions to plot

XLABEL = "x [m]"
YLABEL = "y [m]"


def plot_room(ax):
    x, y = ROOM_DIM[:2]
    ax.plot([0, 0], [0, y], color="black")
    ax.plot([x, x], [0, y], color="black")
    ax.plot([0, x], [0, 0], color="black")
    ax.plot([0, x], [y, y], color="black")


def plot_source(ax):
    ax.scatter(SPEAKER_POSITION[0], SPEAKER_POSITION[1], color="black")


class GeometryPlotter(Node):
    def __init__(self):
        super().__init__("geometry_plotter")

        self.subscription_pose_raw = self.create_subscription(
            PoseRaw, "geometry/pose_raw", self.listener_callback_pose_raw, 10
        )

        self.subscription_pose = self.create_subscription(
            PoseStamped, "geometry/pose", self.listener_callback_pose, 10
        )

        self.subscription_doa = self.create_subscription(
            DoaEstimates,
            "geometry/doa_estimates",
            self.listener_callback_doa,
            10,
        )

        self.subscription_doa = self.create_subscription(
            DoaEstimates,
            "geometry/ground_truth",
            self.listener_callback_doa,
            10,
        )

        self.plotter_dict = {}
        # initialize a starting position for pose_raw, as it only contains delta positions
        self.pose_imu_list = np.array([STARTING_POS[:2]]).reshape((2, 1))
        self.previous_time = None

        # need no starting position for pose as it has absolute positions
        self.pose_list = np.empty((2, 0))

        # for error calculations
        self.error_list = []
        self.ground_truth_synch = TopicSynchronizer(20)
        self.subscription = self.create_subscription(
            GroundTruth,
            "geometry/ground_truth",
            self.ground_truth_synch.listener_callback,
            10,
        )

    def init_plotter(self, name, xlabel="x", ylabel="y"):
        if not (name in self.plotter_dict.keys()):
            self.plotter_dict[name] = LivePlotter(
                np.inf, -np.inf, label=name, log=False
            )
            self.plotter_dict[name].ax.set_xlabel(xlabel)
            self.plotter_dict[name].ax.set_ylabel(ylabel)
            self.plotter_dict[name].ax.axis("equal")

            # plot_room(self.plotter_dict[name].ax)
            # plot_source(self.plotter_dict[name].ax)

    def update_plotter(
        self,
        name,
        pose_list,
        yaw_deg=None,
        source_direction_deg=None,
        pose_label="pose estimates",
    ):
        self.plotter_dict[name].update_scatter(
            pose_list[0, :], pose_list[1, :], label=pose_label
        )

        if yaw_deg is not None:
            self.plotter_dict[name].update_arrow(
                pose_list[:, -1], yaw_deg, label="yaw"
            )

        if source_direction_deg is not None:
            self.plotter_dict[name].update_arrow(
                pose_list[:, -1], source_direction_deg, label="source direction"
            )

        self.plotter_dict[name].ax.legend(loc="upper right")

    def listener_callback_pose_raw(self, msg_pose_raw):
        """ Plot the latest poses, calculated from the velocity estimates. """
        self.init_plotter("pose raw", xlabel=XLABEL, ylabel=YLABEL)
        r_world, v_world, yaw, yaw_rate = read_pose_raw_message(msg_pose_raw)

        if self.previous_time is None:
            self.previous_time = msg_pose_raw.timestamp

        delta_sec = (msg_pose_raw.timestamp - self.previous_time) / 1000.0
        d_imu = v_world * delta_sec
        self.previous_time = msg_pose_raw.timestamp

        pose_imu = self.pose_imu_list[:, -1] + d_imu
        self.pose_imu_list = np.c_[self.pose_imu_list, pose_imu]

        if self.pose_imu_list.shape[1] > MAX_LENGTH:
            self.pose_imu_list = self.pose_imu_list[:, -MAX_LENGTH:]

        self.update_plotter("pose raw", self.pose_imu_list, pose_label="imu")
        self.plotter_dict["pose raw"].fig.canvas.draw()

    def listener_callback_pose(self, msg_pose):
        """ Plot the latest poses. """
        self.init_plotter("pose", xlabel=XLABEL, ylabel=YLABEL)

        new_position, yaw, pitch, roll = read_pose_message(msg_pose)
        assert pitch == 0, pitch
        assert roll == 0, roll

        self.pose_list = np.c_[self.pose_list, new_position]

        if self.pose_list.shape[1] > MAX_LENGTH:
            self.pose_list = self.pose_list[:, -MAX_LENGTH:]

        self.update_plotter("pose", self.pose_list, yaw)
        self.plotter_dict["pose"].fig.canvas.draw()

    def listener_callback_doa(self, msg_doa):
        """ Plot the estimated DOA directions on the most recent pose. """
        self.init_plotter("pose", xlabel=XLABEL, ylabel=YLABEL)

        doa_estimates = list(msg_doa.doa_estimates_deg)

        for i, doa_estimate in enumerate(doa_estimates):
            self.plotter_dict["pose"].update_arrow(
                self.pose_list[:, -1], doa_estimate, label=f"doa {i}"
            )
        self.plotter_dict["pose"].fig.canvas.draw()

        # calculate the current error
        message = self.ground_truth_synch.get_latest_message(
            msg_doa.timestamp, self.get_logger()
        )

        if message is not None:
            orientation = message.source_direction_deg
            error = abs(orientation - doa_estimates[0])
            self.error_list.append(error)
            avg_error = np.mean(self.error_list)
            self.get_logger().info(
                f"Current error: {error}, current average: {avg_error}"
            )


def main(args=None):
    rclpy.init(args=args)

    plotter = GeometryPlotter()

    rclpy.spin(plotter)

    plotter.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
