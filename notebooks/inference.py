#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
inference.py: Get probability distributions and estimates of angle or distance from distance-frequency measurements.
"""

import numpy as np

YAW_DEG = 0


def get_abs_fft(f_slice, n_max=1000, norm=True):
    if norm:
        f_slice_norm = f_slice - np.nanmean(f_slice)
    else:
        f_slice_norm = f_slice
    n = max(len(f_slice), n_max)
    return np.abs(np.fft.rfft(f_slice_norm, n=n))


def get_interference_distances(frequencies, mic_idx=1, distance_range=None, n_max=1000):
    from constants import SPEED_OF_SOUND
    from simulation import get_orthogonal_distance_from_global

    n = max(len(frequencies), n_max)
    df = np.mean(frequencies[1:] - frequencies[:-1])
    deltas_cm = np.fft.rfftfreq(n, df) * SPEED_OF_SOUND * 100
    distances = get_orthogonal_distance_from_global(
        yaw_deg=YAW_DEG, deltas_cm=deltas_cm, mic_idx=mic_idx
    )
    if distance_range is not None:
        mask = (distances >= distance_range[0]) & (distances <= distance_range[1])
        distances = distances[mask]
    else:
        mask = None
    return distances, mask


def get_probability_fft(
    f_slice, frequencies, mic_idx=1, distance_range=None, n_max=1000
):
    assert f_slice.ndim == 1
    abs_fft = get_abs_fft(f_slice, n_max)
    distances, mask = get_interference_distances(
        frequencies, mic_idx, distance_range, n_max=n_max
    )
    if mask is not None:
        abs_fft = abs_fft[mask]
    prob = abs_fft / np.sum(abs_fft)
    return distances, prob


def get_posterior(abs_fft, sigma=None, data=None):
    N = len(abs_fft)
    periodogram = 1 / N * abs_fft ** 2
    # print('periodogram:', np.min(periodogram), np.max(periodogram))

    if sigma is not None:
        if np.any(sigma > 0):
            periodogram /= sigma ** 2
            # TODO(FD) we do below for numerical reasons. its effect
            # is undone by later exponentiation anyways. Make sure
            # this really as no effect on the result.
            periodogram -= np.max(periodogram)
            posterior = np.exp(periodogram)
        else:  # this is the limit of exp for sigma > 0
            posterior = np.zeros(len(periodogram))
            posterior[np.argmax(periodogram)] = 1.0
    else:
        d_bar = 1 / len(data) * np.sum((data - np.mean(data)) ** 2)
        posterior = (1 - 2 * periodogram / (N * d_bar)) ** ((2 - N) / 2)
        # posterior = np.exp(periodogram)
    posterior /= np.sum(posterior)
    return posterior


def get_probability_bayes(
    f_slice, frequencies, mic_idx=1, distance_range=None, n_max=1000, sigma=None
):
    assert f_slice.ndim == 1
    abs_fft = get_abs_fft(f_slice, n_max=n_max, norm=True)
    distances, mask = get_interference_distances(
        frequencies, mic_idx, distance_range, n_max=n_max
    )
    if mask is not None:
        abs_fft = abs_fft[mask]

    posterior = get_posterior(abs_fft, sigma, data=f_slice)
    return distances, posterior


def get_probability_cost(
    f_slice,
    frequencies,
    distances,
    ax=None,
    mic_idx=1,
    relative_ds=None,
    absolute_yaws=None,
):
    from simulation import get_freq_slice_theory

    if absolute_yaws is not None:
        yaw_deg = absolute_yaws
    else:
        yaw_deg = YAW_DEG

    f_slice_norm = f_slice - np.mean(f_slice)
    f_slice_norm /= np.std(f_slice_norm)

    probs = []
    for d in distances:
        if relative_ds is not None:
            d += relative_ds
        f_slice_theory = get_freq_slice_theory(frequencies, d, yaw_deg)[:, mic_idx]
        f_slice_theory -= np.mean(f_slice_theory)
        f_slice_theory /= np.std(f_slice_theory)
        probs.append(np.exp(-np.linalg.norm(f_slice_theory - f_slice_norm)))

        if ax is not None:
            ax.plot(frequencies, f_slice_theory, color="black")

    if ax is not None:
        ax.plot(frequencies, f_slice_norm, color="green")

    probs /= np.sum(probs)
    return probs


def get_approach_angle_fft(
    d_slice,
    frequency,
    relative_distances_cm,
    mic_idx=1,
    n_max=1000,
    bayes=False,
    sigma=None,
):
    from simulation import factor_distance_to_delta
    from constants import SPEED_OF_SOUND

    d_m = np.mean(relative_distances_cm[1:] - relative_distances_cm[:-1]) * 1e-2

    n = max(len(d_slice), n_max)

    period_90 = 2 * frequency / SPEED_OF_SOUND  # 1/m in terms of orthogonal distance
    periods_k = (np.arange(0, n // 2 + 1)) / (d_m * n)  # 1/m in terms of delta
    sines_gamma = periods_k / period_90
    if np.any(sines_gamma > 1):
        print(f"Values bigger than 1: {np.sum(sines_gamma>1)}/{len(sines_gamma)}")

    abs_fft = get_abs_fft(d_slice, n_max=1000, norm=True)
    # abs_fft = abs_fft[sines_gamma <= 1]
    # sines_gamma= sines_gamma[sines_gamma <= 1]
    # sines_gamma[sines_gamma>1] = 1
    gammas = np.full(len(sines_gamma), 90)
    gammas[sines_gamma <= 1] = np.arcsin(sines_gamma[sines_gamma <= 1]) * 180 / np.pi

    if bayes:
        prob = get_posterior(abs_fft, sigma, d_slice)
    else:
        prob = abs_fft / np.sum(abs_fft)
    return gammas, prob, periods_k


def get_approach_angle_cost(
    d_slice,
    frequency,
    relative_distances_cm,
    start_distances_grid_cm,
    gammas_grid_deg,
    mic_idx=1,
    ax=None,
):
    from simulation import get_dist_slice_theory

    yaw_deg = YAW_DEG

    d_slice_norm = d_slice - np.mean(d_slice)
    d_slice_norm /= np.std(d_slice_norm)

    probs = np.zeros((len(start_distances_grid_cm), len(gammas_grid_deg)))
    for i, start_distance_cm in enumerate(start_distances_grid_cm):
        for j, gamma_deg in enumerate(gammas_grid_deg):
            distances_cm = start_distance_cm - relative_distances_cm * np.sin(
                gamma_deg / 180 * np.pi
            )
            assert np.all(distances_cm >= 0)
            d_slice_theory = get_dist_slice_theory(frequency, distances_cm, yaw_deg)[
                :, mic_idx
            ]
            d_slice_theory -= np.nanmean(d_slice_theory)
            std = np.nanstd(d_slice_theory)
            if std > 0:
                d_slice_theory /= std
            assert d_slice_theory.shape == d_slice_norm.shape
            loss = np.linalg.norm(d_slice_theory - d_slice_norm)
            probs[i, j] = np.exp(-loss)

            if ax is not None:
                ax.plot(
                    distances_cm,
                    d_slice_theory,
                    label=f"{start_distance_cm}cm, {gamma_deg}deg",
                )
    probs_angle = np.nanmax(probs, axis=0)  # take maximum across distances
    probs_angle /= np.nansum(probs_angle)
    return probs_angle