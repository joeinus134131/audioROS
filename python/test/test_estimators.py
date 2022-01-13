#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_estimators.py:  Test estimators
"""

import sys, os

import numpy as np
from scipy.stats import norm

sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "..", "utils")))
sys.path.append(os.path.join(os.getcwd(), "utils"))
from moving_estimators import MovingEstimator
from geometry import get_deltas_from_global

MIC_IDX = [0, 1]


def test_moving_delta():
    print("==== testing with delta ====")
    do_test_moving("delta", n_window=2)
    do_test_moving("delta", n_window=3)


def test_moving_normal():
    print("==== testing with normal ====")
    do_test_moving("normal", n_window=2)
    do_test_moving("normal", n_window=3)


def do_test_moving(prob_method, n_window):
    """ Test on simple toy example """

    moving_estimator = MovingEstimator(n_window=n_window)  # 2 or 3 works.
    delta_grid = np.arange(100)

    def measure_wall(pose):
        distance = 30 - pose[1]
        angle = 90 - pose[2]
        return distance, angle

    def get_delta_distribution(distance, angle, mic_idx, prob_method="delta"):
        delta = (
            get_deltas_from_global(
                azimuth_deg=angle, distances_cm=distance, mic_idx=mic_idx
            )[0]
            * 1e2
        )
        if prob_method == "delta":
            probs = np.zeros(len(delta_grid))
            probs[np.argmin(np.abs(delta_grid - delta))] = 1.0
        elif prob_method == "normal":
            probs = norm.pdf(delta_grid, loc=delta, scale=10)
        return probs

    # toy example: the robot does a diamond-shaped movement,
    # and rotate by -90 degrees at each position.
    # the wall is located at 30cm north from the origin, horizontal.
    distance_glob = 30
    angle_glob = 90

    poses = [[0, 10, -90], [10, 20, -180], [20, 10, 90], [10, 0, 0]]
    for i, pose in enumerate(poses):
        distance, angle = measure_wall(pose)
        diff_dict = {}
        for mic_idx in MIC_IDX:
            probs = get_delta_distribution(distance, angle, mic_idx, prob_method)
            diff_dict[mic_idx] = (delta_grid, probs)
        moving_estimator.add_distributions(diff_dict, pose[:2], pose[2])
        # print(f"added {distance, angle} at pose {i}")

        if i < n_window - 1:
            continue

        # prob_matrix = moving_estimator.get_joint_distribution(verbose=True)
        # print("joint (angles x distances)")
        # print(prob_matrix)
        # print("angles:", moving_estimator.ANGLES_DEG)
        # print("distances:", moving_estimator.DISTANCES_CM)

        prob_distances, prob_angles = moving_estimator.get_distributions(verbose=True)
        angles = moving_estimator.ANGLES_DEG
        distances = moving_estimator.DISTANCES_CM

        distance_estimate = moving_estimator.get_distance_estimate(prob_distances)
        angle_estimate = moving_estimator.get_angle_estimate(prob_angles)
        assert (
            distance_estimate == distance_glob
        ), f"distance at position {i}: {distance_estimate} != true {distance_glob}"
        assert (
            angle_estimate == angle_glob
        ), f"angle at position {i}: {angle_estimate} != true {angle_glob}"


if __name__ == "__main__":
    test_moving_delta()
    test_moving_normal()
    print("done")