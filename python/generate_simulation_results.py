#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
generate_simulation_results.py: investigate distance inference performance for different types and levels of noise
and different algorithms.
"""

import itertools

import numpy as np
import pandas as pd
import progressbar
from utils.geometry import get_deltas_from_global
from utils.inference import get_probability_cost, get_probability_bayes
from utils.inference import get_approach_angle_fft, get_approach_angle_cost
from utils.simulation import get_df_theory_simple

MIC_IDX = 1
AZIMUTH_DEG = 0

METHODS = ["fft"]  # use only FFT

FREQUENCIES = np.linspace(3000, 4445, 32)
print(FREQUENCIES)
# copied from firmware
# [3002, 3061, 3123, 3186, 3247, 3309, 3375, 3435, 3564, 3624, 3878, 3941, 3996, 4062, 4121, 4191, 4254, 4307, 4373, 4441]


def simulate_frequency_slice(
    distances_cm, frequencies, sigmas_delta_cm, sigmas_f, sigmas_y, n_instances
):

    np.random.seed(1)

    n_methods = len(METHODS)
    distances_grid = np.arange(100)
    deltas_m, d0 = get_deltas_from_global(AZIMUTH_DEG, distances_cm, MIC_IDX)

    n_total = (
        n_instances
        * len(distances_cm)
        * len(sigmas_delta_cm)
        * len(sigmas_f)
        * len(sigmas_y)
        * n_methods
    )

    results_df = pd.DataFrame(
        columns=[
            "sigmadelta",
            "sigmaf",
            "sigmay",
            "method",
            "error",
            "counter",
            "distance",
        ]
    )

    i = 0
    with progressbar.ProgressBar(max_value=n_total) as p:
        for distance_cm, delta_m in zip(distances_cm, deltas_m):
            for (sigma_delta_cm, sigma_f, sigma_y) in itertools.product(
                sigmas_delta_cm, sigmas_f, sigmas_y
            ):
                for counter in range(n_instances):
                    delta_m_noisy = (
                        delta_m + np.random.normal(scale=sigma_delta_cm) * 1e-2
                    )
                    frequencies_noisy = frequencies + np.random.normal(
                        scale=sigma_f, size=len(frequencies)
                    )

                    slice_f = get_df_theory_simple(
                        delta_m_noisy, frequencies_noisy, flat=True, d0=d0,
                    )
                    slice_f += np.random.normal(scale=sigma_y, size=len(slice_f))

                    for method in METHODS:
                        if method == "fft":
                            dist, probs, _ = get_probability_bayes(
                                slice_f,
                                frequencies_noisy,
                                mic_idx=MIC_IDX,
                                distance_range=[
                                    min(distances_grid),
                                    max(distances_grid),
                                ],
                                azimuth_deg=AZIMUTH_DEG,
                                interpolate=False,
                            )
                        elif method == "cost":
                            probs = get_probability_cost(
                                slice_f,
                                frequencies_noisy,
                                distances_grid,
                                mic_idx=MIC_IDX,
                            )
                            dist = distances_grid

                        d_estimate = dist[np.argmax(probs)]
                        error = np.abs(d_estimate - distance_cm)

                        results_df.loc[len(results_df), :] = dict(
                            counter=counter,
                            distance=distance_cm,
                            sigmadelta=sigma_delta_cm,
                            sigmaf=sigma_f,
                            sigmay=sigma_y,
                            method=method,
                            error=error,
                        )
                        p.update(i)
                        i += 1

    results_df = results_df.apply(pd.to_numeric, errors="ignore", axis=1)
    return results_df


def simulate_distance_slice(
    gammas_deg,
    start_distance_cm,
    relative_distances_cm,
    frequencies,
    sigmas_relative_cm,
    sigmas_y,
    n_instances,
    ax=None,
):

    np.random.seed(1)
    n_methods = len(METHODS)

    start_distances_grid = np.arange(40, 60)
    gammas_grid = np.arange(91)

    n_total = (
        n_instances
        * len(gammas_deg)
        * len(sigmas_relative_cm)
        * len(sigmas_y)
        * len(frequencies)
        * n_methods
    )
    results_df = pd.DataFrame(
        columns=[
            "gamma",
            "startdistance",
            "frequency",
            "sigmarelative",
            "sigmay",
            "method",
            "error",
            "counter",
        ]
    )

    i = 0
    with progressbar.ProgressBar(max_value=n_total) as p:
        for (gamma_deg, sigma_relative_cm, sigma_y, frequency,) in itertools.product(
            gammas_deg, sigmas_relative_cm, sigmas_y, frequencies
        ):
            for counter in range(n_instances):
                relative_cm_noisy = relative_distances_cm + np.random.normal(
                    scale=sigma_relative_cm, size=len(relative_distances_cm)
                )
                start_distance_random = start_distance_cm + np.random.uniform(-10, 10)
                distances_cm = start_distance_random - relative_cm_noisy * np.sin(
                    gamma_deg / 180 * np.pi
                )
                deltas_m_noisy, d0 = get_deltas_from_global(
                    AZIMUTH_DEG, distances_cm, MIC_IDX
                )

                slice_d = get_df_theory_simple(
                    deltas_m_noisy, frequency, flat=True, d0=d0
                )
                slice_d += np.random.normal(scale=sigma_y, size=len(slice_d))

                for method in METHODS:
                    if method == "fft":
                        gammas, probs = get_approach_angle_fft(
                            slice_d,
                            frequency,
                            relative_distances_cm,
                            bayes=True,
                            reduced=True,
                        )
                    elif method == "cost":
                        probs = get_approach_angle_cost(
                            slice_d,
                            frequency,
                            relative_distances_cm,
                            start_distances_grid,
                            gammas_grid,
                            mic_idx=MIC_IDX,
                        )  # is of shape n_start_distances x n_gammas_grid
                        gammas = gammas_grid

                    gamma_estimate = gammas[np.argmax(probs)]
                    error = np.abs(gamma_estimate - gamma_deg)

                    results_df.loc[len(results_df), :] = dict(
                        counter=counter,
                        gamma=gamma_deg,
                        startdistance=start_distance_random,
                        frequency=frequency,
                        sigmarelative=sigma_relative_cm,
                        sigmay=sigma_y,
                        method=method,
                        error=error,
                    )
                    p.update(i)
                    i += 1

    results_df = results_df.apply(pd.to_numeric, errors="ignore", axis=1)
    return results_df


def compare_timing(n_instances):
    import time

    distance_cm = 10
    mic_idx = 0
    delta_m, d0 = get_deltas_from_global(AZIMUTH_DEG, distance_cm, MIC_IDX)
    distances_grid = np.arange(10, 100)

    times = {"fft": [], "cost": []}
    with progressbar.ProgressBar(max_value=n_instances) as p:
        for counter in range(n_instances):
            slice_f = get_df_theory_simple(delta_m, frequencies, flat=True, d0=d0)

            t0 = time.time()
            distances_fft, probs_fft, _ = get_probability_bayes(
                slice_f,
                frequencies,
                mic_idx=MIC_IDX,
                distance_range=[min(distances_grid), max(distances_grid)],
                azimuth_deg=AZIMUTH_DEG,
            )
            d_estimate = distances_fft[np.argmax(probs_fft)]
            times["fft"].append(time.time() - t0)

            t0 = time.time()
            probs_cost = get_probability_cost(
                slice_f,
                frequencies,
                distances_grid,
                mic_idx=MIC_IDX,
                azimuth_deg=AZIMUTH_DEG,
            )
            d_estimate = distances_grid[np.argmax(probs_cost)]
            times["cost"].append(time.time() - t0)

            p.update(counter)
    return times


if __name__ == "__main__":
    ######### distance slice study
    ## noisless
    np.random.seed(1)
    start_distance_cm = 50
    relative_distances_cm = np.arange(20)
    frequencies = np.linspace(1000, 5000, 10)
    step = 5
    gammas_deg = np.arange(step, 91, step=step, dtype=float)
    gammas_deg += np.random.uniform(
        low=-step // 2, high=step // 2, size=len(gammas_deg)
    )
    n_instances = 100

    fname = "results/simulation/angle_noiseless_new.pkl"
    sigmas_relative_cm = [0]
    sigmas_y = [0]
    print("generating", fname)
    results_df = simulate_distance_slice(
        gammas_deg,
        start_distance_cm,
        relative_distances_cm,
        frequencies,
        sigmas_relative_cm,
        sigmas_y,
        n_instances,
    )
    pd.to_pickle(results_df, fname)
    print("saved as", fname)

    frequencies = [1000, 3000, 10000]  # np.linspace(1000, 5000, 3)
    n_instances = 10

    fname = "results/simulation/angle_relative_noise_new.pkl"
    sigmas_relative_cm = np.linspace(0, 5, 11)
    sigmas_y = [0]  # np.linspace(0, 2, 10)
    print("generating", fname)
    results_df = simulate_distance_slice(
        gammas_deg,
        start_distance_cm,
        relative_distances_cm,
        frequencies,
        sigmas_relative_cm,
        sigmas_y,
        n_instances,
    )
    pd.to_pickle(results_df, fname)
    # print("saved as", fname)

    fname = "results/simulation/angle_amplitude_noise_new.pkl"
    sigmas_relative_cm = [0]  # np.arange(10, step=2)
    sigmas_y = np.logspace(-2, 0, 10)
    print("generating", fname)
    results_df = simulate_distance_slice(
        gammas_deg,
        start_distance_cm,
        relative_distances_cm,
        frequencies,
        sigmas_relative_cm,
        sigmas_y,
        n_instances,
    )
    pd.to_pickle(results_df, fname)
    print("saved as", fname)

    fname = "results/simulation/angle_joint_noise_new.pkl"
    frequencies = [3000]
    sigmas_relative_cm = np.linspace(0, 5, 11)
    sigmas_y = [0.05, 0.1, 0.2]  # np.logspace(-2, 0, 5)
    print("generating", fname)
    results_df = simulate_distance_slice(
        gammas_deg,
        start_distance_cm,
        relative_distances_cm,
        frequencies,
        sigmas_relative_cm,
        sigmas_y,
        n_instances,
    )
    pd.to_pickle(results_df, fname)
    print("saved as", fname)

if 0:  # __name__ == "__main__":
    ######### frequency slice study
    ### amplitude noise study
    n_instances = 10
    np.random.seed(1)
    frequencies = FREQUENCIES
    distances_cm = np.arange(8, 60, dtype=float)
    # distances_cm += np.random.uniform(low=-1, high=1, size=len(distances_cm))

    fname = "results/simulation/amplitude_noise_new.pkl"
    sigmas_delta_cm = [0]
    sigmas_f = [0]
    sigmas_y = np.linspace(0, 2, 100)
    print("generating", fname)
    results_df = simulate_frequency_slice(
        distances_cm, frequencies, sigmas_delta_cm, sigmas_f, sigmas_y, n_instances,
    )
    pd.to_pickle(results_df, fname)
    print("saved as", fname)

    ### delta noise study
    fname = "results/simulation/delta_noise_new.pkl"
    sigmas_delta_cm = np.arange(30, step=2)
    sigmas_f = [0]
    sigmas_y = [0]
    print("generating", fname)
    results_df = simulate_frequency_slice(
        distances_cm, frequencies, sigmas_delta_cm, sigmas_f, sigmas_y, n_instances,
    )
    pd.to_pickle(results_df, fname)
    print("saved as", fname)

    ### frequency noise study
    fname = "results/simulation/frequency_noise_new.pkl"
    sigmas_delta_cm = [0]
    sigmas_f = np.arange(200, step=10)
    sigmas_y = [0]
    print("generating", fname)
    results_df = simulate_frequency_slice(
        distances_cm, frequencies, sigmas_delta_cm, sigmas_f, sigmas_y, n_instances,
    )
    pd.to_pickle(results_df, fname)
    print("saved as", fname)

    fname = "results/simulation/joint_noise_new.pkl"
    sigmas_f = [0]
    sigmas_delta_cm = np.arange(30, step=2)
    sigmas_y = [0.05, 0.1, 0.2]
    print("generating", fname)
    results_df = simulate_frequency_slice(
        distances_cm, frequencies, sigmas_delta_cm, sigmas_f, sigmas_y, n_instances,
    )
    pd.to_pickle(results_df, fname)
    print("saved as", fname)

    times = compare_timing(n_instances)
    for method, time_list in times.items():
        print(f"average time for {method}: {np.mean(time_list)/n_instances:.3e}s")
