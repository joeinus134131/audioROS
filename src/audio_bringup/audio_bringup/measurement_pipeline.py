#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""
measurement_pipeline.py
"""

import os
import signal
import subprocess
import sys
import time
import warnings

import numpy as np
import rclpy
from scipy.io import wavfile

sys.path.append(os.getcwd() + "/crazyflie-audio/python/")
from play_and_record import get_usb_soundcard_ubuntu
from signals import generate_signal
from serial_motors import SerialMotors, DURATION_50, DURATION_360

from crazyflie_description_py.commands import all_commands_lists
from crazyflie_description_py.parameters import SOUND_EFFECTS, FS

from audio_bringup.helpers import (
    get_active_nodes,
    get_filename,
    set_param,
    EXP_DIRNAME,
    CSV_DIRNAME,
    WAV_DIRNAME,
    TOPICS_TO_RECORD,
)

DEFAULT_PARAMS = {
    "min_freq": 0,
    "max_freq": FS / 2,
    "window_type": 0,
    "bin_selection": 0,
    "props": 0,
    "distance": 0,
    "degree": 0,
    "motors": 0,
    "source": None,
    "appendix": "",
}
# TODO(FD) to be removed once we have used better names for this in Crazyflie firmware
PARAM_NAMES = {"bin_selection": "bin_selection", "props": "filter_props_enable"}

START_DISTANCE = 0
START_ANGLE = 0

# EXTRA_DIRNAME = '2021_02_09_wall'
# EXTRA_DIRNAME = '2021_02_19_windows'
# EXTRA_DIRNAME = '2021_02_23_wall'
# EXTRA_DIRNAME = "2021_03_01_flying"
# EXTRA_DIRNAME = "2021_04_30_hover"
# EXTRA_DIRNAME = "2021_04_30_stepper"
# EXTRA_DIRNAME = "2021_05_04_flying"
# EXTRA_DIRNAME = "2021_05_04_linear"
# EXTRA_DIRNAME = "2021_06_09_stepper"
# EXTRA_DIRNAME = "2021_06_17_stepper"
# EXTRA_DIRNAME = "2021_06_19_stepper"
# EXTRA_DIRNAME = "2021_06_19_stepper_linear"
# EXTRA_DIRNAME = "2021_06_22_stepper"
# EXTRA_DIRNAME = "2021_07_08_stepper"
# EXTRA_DIRNAME = "2021_07_08_rotating"
# EXTRA_DIRNAME = "2021_07_08_stepper_fast"
# EXTRA_DIRNAME = "2021_07_08_stepper_slow"
# EXTRA_DIRNAME = "2021_07_14_propsweep"
# EXTRA_DIRNAME = "2021_07_14_flying"
# EXTRA_DIRNAME = "2021_07_14_flying_hover"
# EXTRA_DIRNAME = "2021_07_27_manual"
# EXTRA_DIRNAME = "2021_07_27_hover"
EXTRA_DIRNAME = "2021_10_07_stepper"

EXTRA_REC_TIME = 2  # extra duration for recording time.
USER_INPUT = True

bag_pid = None
SerialIn = None


def execute_commands(command_name):
    if "mono" in command_name:
        freq = int(command_name.replace("mono", ""))
        command_list = [
            ("/gateway", "buzzer_idx", freq, 0),
        ]
    elif "all" in command_name:
        thrust = int(command_name.replace("all", ""))
        command_list = [("/gateway", "all", thrust, 0)]
    else:
        command_list = all_commands_lists[command_name]

    for command in command_list:
        node, parameter, value, sleep = command
        if node != "":
            print(f"execute {parameter}: {value} and sleep for {sleep:.2f}s...")
            set_param(node, parameter, str(value))
        else:
            print(f"sleep for {sleep}s...")
        time.sleep(sleep)


def get_total_time(command_name):
    if command_name in all_commands_lists.keys():
        command_list = all_commands_lists[command_name]
    else:
        warnings.warn(f"Did not find {command_name} in {all_commands_lists.keys()}")
        return 0
    time = 0
    for command in command_list:
        time += command[3]
    # time += 25 # extra 10 seconds for unexpected waiting times
    return time


def adjust_freq_lims(params):
    min_freq = params.get("min_freq", None)
    max_freq = params.get("max_freq", None)

    if params["source"] is not None:

        if "mono" in params["source"]:
            freq = int(params["source"].replace("mono", ""))
            assert (min_freq is None) or (freq > min_freq)
            assert (max_freq is None) or (freq < max_freq)
            return

        __, (min_freq_buzz, max_freq_buzz), __ = SOUND_EFFECTS[params["source"]]
        if min_freq is not None:
            print(f"Overwriting min_freq {min_freq} with buzzer {min_freq_buzz}.")
        params["min_freq"] = min_freq_buzz

        if max_freq is not None:
            print(f"Overwriting max_freq {max_freq} with buzzer {max_freq_buzz}.")
        params["max_freq"] = max_freq_buzz


def adjust_duration(duration, params):
    distance = params.get("distance", None)
    print(params)
    angle = params.get("degree", None)
    print(angle)

    if (distance is not None) and (abs(distance) == 51):
        if DURATION_50 > duration:
            print(
                f"ignoring global duration {duration} and using move command duration {DURATION_50}"
            )
            duration = DURATION_50
    if (angle is not None) and (abs(angle) == 360):
        print(angle)
        if DURATION_360 > duration:
            print(
                f"ignoring global duration {duration} and using turn command duration {DURATION_360}"
            )
            duration = DURATION_360

    if params["motors"] != 0:
        duration_motors = get_total_time(params["motors"])
        if duration_motors > duration:
            print(
                f"ignoring global duration {duration} and using motor command duration {duration_motors}"
            )
            duration = duration_motors

    if params["source"] is not None:
        if "mono" in params["source"]:
            duration_buzzer = 0
        else:
            *_, duration_buzzer = SOUND_EFFECTS[params["source"]]
        if duration_buzzer > duration:
            print(
                f"ignoring global duration {duration} and using buzzer command duration {duration_buzzer}"
            )
            duration = duration_buzzer
    return duration


def set_audio_parameters(params, params_old):
    audio_parameters = ["min_freq", "max_freq", "window_type", "bin_selection", "props"]
    for key, value in params.items():
        if not key in audio_parameters:
            continue

        value_old = params_old.get(key, DEFAULT_PARAMS[key])
        if value_old != value:
            set_param("/gateway", PARAM_NAMES.get(key, key), str(value))


def start_bag_recording(bag_filename):
    global bag_pid
    set_param("/csv_writer", "filename", "")
    bag_pid = subprocess.Popen(
        ["ros2", "bag", "record", "-o", bag_filename] + TOPICS_TO_RECORD
    )
    print("started bag record")


def start_moving(distance, angle):
    global SerialIn
    if (angle is not None) and abs(angle) == 360:
        print(f"starting turning by {angle}")
        SerialIn.turn(angle, blocking=False)
    if distance == 51:
        print("start moving by 50")
        SerialIn.move(50, blocking=False)
    if distance == -51:
        print("start moving back by 50")
        SerialIn.move(-50, blocking=False)


def save_bag_recording(csv_filename):
    bag_pid.send_signal(signal.SIGINT)
    set_param("/csv_writer", "filename", csv_filename)


def main(args=None):
    def save_wav_recording(recording, wav_filename):
        recording_float32 = recording.astype(np.float32)
        wavfile.write(wav_filename, global_params["fs_soundcard"], recording_float32)
        print("wrote wav file as", wav_filename)

    def perform_experiment(out_signal=None):
        recording = None
        start_time = time.time()
        if (source_type == "soundcard") and (global_params["n_meas_mics"] > 0):
            recording = sd.playrec(out_signal, blocking=False)
        elif source_type == "soundcard":
            sd.play(out_signal, blocking=False)
        elif global_params["n_meas_mics"] > 0:
            print(f"recording measurement mic for {duration + EXTRA_REC_TIME} seconds")
            n_frames = int((duration + EXTRA_REC_TIME) * global_params["fs_soundcard"])
            recording = sd.rec(n_frames, blocking=False)

        # execute motor commands
        if params["motors"] != 0:
            print(f"executing motor commands", params["motors"])
            execute_commands(params["motors"])

        # play onboard sound
        if params["source"] is not None:
            execute_commands(params["source"])

        # wait for exxtra time
        extra_idle_time = duration - (time.time() - start_time)
        if extra_idle_time > 0:
            print(f"Waiting for {extra_idle_time:.2f} seconds...")
            time.sleep(extra_idle_time)
        elif extra_idle_time < 0:
            print(
                f"Error: Finished recording before finishing everything else! {extra_idle_time:.2f}"
            )
        return recording

    def measure_doa(params):
        """ setup: 
        - soundcard or external buzzer
        - stepper motor
        """
        assert source_type in ["buzzer", "soundcard"]
        if source_type == "soundcard":
            out_signal = generate_signal(
                global_params["fs_soundcard"],
                duration,
                signal_type=params["source"],
                frequency_hz=source_params["freq_source"],
                min_dB=source_params["min_dB"],
                max_dB=source_params["max_dB"],
            )
        if source_type == "buzzer":
            input(
                f'make sure external buzzer plays {params["source"]}! Enter to continue'
            )

        start_bag_recording(bag_filename)
        start_turning(distance, angle)

        return perform_experiment(out_signal=out_signal)

    def measure_wall(params):
        """ setup: 
        - onboard buzzer
        - stepper motor
        """
        assert source_type == "buzzer-onboard"

        start_bag_recording(bag_filename)
        print("measure_wall: start moving")
        start_moving(distance, angle)

        return perform_experiment()

    def measure_wall_flying(params):
        """ 
        setup: 
        - onboard buzzer
        - drone flying
        """
        assert source_type == "buzzer-onboard"

        # Unless the source is of type mono, do not play onboard sound yet,
        # as this is part of the motor commands.
        if (params["source"] is not None) and ("mono" in params["source"]):
            execute_commands(params["source"])

        start_bag_recording(bag_filename)
        return perform_experiment()

    def measure_snr(params):
        """ 
        setup: 
        - external buzzer
        - static, no stepper motor or flying
        """

        # we set the frequency even though this drone
        # is not playing, so that snr>=2 works.
        if params["source"] is not None and ("mono" in params["source"]):
            freq = int(params["source"].strip("mono"))
            set_param("/gateway", "buzzer_freq", freq)
            set_param("/gateway", "buzzer_effect", 0)

        input(f'make sure external buzzer plays {params["source"]}! Enter to continue')

        start_bag_recording(bag_filename)
        return perform_experiment()

    def measure_snr_onboard(params):
        """ 
        setup: 
        - onboard buzzer
        - static, no stepper motor or flying
        """

        # order of bag recording vs. buzzer sound is intentionally different!
        start_bag_recording(bag_filename)

        if params["source"] is not None:
            print(f"executing buzzer commands")
            execute_commands(params["source"])

        return perform_experiment()

    rclpy.init(args=args)

    active_nodes = get_active_nodes()
    assert "/csv_writer" in active_nodes
    assert "/gateway" in active_nodes

    extra_dirname = (
        input(
            f"enter experiment folder: (appended to {EXP_DIRNAME}, default:{EXTRA_DIRNAME})"
        )
        or EXTRA_DIRNAME
    )
    exp_dirname = os.path.join(EXP_DIRNAME, extra_dirname)
    csv_dirname = os.path.join(exp_dirname, CSV_DIRNAME)
    wav_dirname = os.path.join(exp_dirname, WAV_DIRNAME)

    sys.path.append(exp_dirname)
    from params import global_params, params_list

    print(f"loaded parameters from {exp_dirname}/params.py")

    # sound card check
    source_type = global_params.get("source_type", "soundcard")
    if (source_type == "soundcard") or (global_params["n_meas_mics"] > 0):
        sd = get_usb_soundcard_ubuntu(
            global_params["fs_soundcard"], global_params["n_meas_mics"]
        )
        sound = np.zeros(10, dtype=float)
        if global_params["n_meas_mics"] > 0:
            if source_type == "soundcard":
                print("playing and recording zero test sound...")
                sd.playrec(sound, blocking=True)
            else:
                print("recording zero test sound...")
                sd.rec(10, blocking=True)
        else:
            print("playing zero test sound...")
            sd.play(sound, blocking=True)

    # motors check
    if any([p.get("distance", None) is not None for p in params_list]) or any(
        [p.get("angle", None) is not None for p in params_list]
    ):
        global SerialIn
        SerialIn = SerialMotors(
            verbose=False, current_distance=START_DISTANCE, current_angle=START_ANGLE,
        )
        print("initalized serial motors")
    else:
        print("not initializing")

    for dirname in [exp_dirname, csv_dirname, wav_dirname]:
        if not os.path.exists(dirname):
            os.makedirs(dirname)

    timestamp = int(time.time())

    param_i = 0
    params_old = {}
    while param_i < len(params_list):

        #### verify parameters ####
        params = params_list[param_i]
        answer = "" if USER_INPUT else "y"
        while not (answer in ["y", "n"]):
            answer = input(f"start experiment with {params}? ([y]/n)") or "y"
        if answer == "n":
            param_i += 1
            continue

        print("experiment:", params)

        #### prepare filenames ####
        filename = get_filename(**params)
        bag_filename = os.path.join(exp_dirname, filename)

        answer = ""
        while os.path.exists(bag_filename):
            answer = (
                input(
                    f"Path {filename} exists, append something? (default:{timestamp}, n to skip)"
                )
                or timestamp
            )
            if answer == "n":
                continue
            filename = f"{filename}_{answer}"
            bag_filename = os.path.join(exp_dirname, filename)

        csv_filename = os.path.join(csv_dirname, filename)
        wav_filename = os.path.join(wav_dirname, filename) + ".wav"

        #### move ####
        distance = params.get("distance", None)
        angle = params.get("degree", None)

        print("checking for blocking movements...")
        if (distance is not None) and (abs(distance) != 51):
            print("moving to", distance)
            SerialIn.move_to(distance, blocking=True)
        if (angle is not None) and (abs(angle) != 360):
            print("moving to", angle)
            SerialIn.move_to(angle, blocking=True)
        print("...done")

        #### set parameters ###
        duration = adjust_duration(global_params.get("duration", 30), params)
        adjust_freq_lims(params)
        set_audio_parameters(params, params_old)

        #### perform experiment ###
        # recording = measure_wall_flying(params)
        recording = measure_wall(params)
        # recording = measure_snr(params)
        # recording = measure_snr_onboard(params)

        #### wrap up ####
        execute_commands("stop_motors")
        execute_commands("stop_buzzer")

        save_bag_recording(csv_filename)
        if recording is not None:
            save_wav_recording(recording, wav_filename)
        param_i += 1
        params_old = params

    # after last experiment: move back to position 0
    if SerialIn is not None:
        SerialIn.move_to(0)
        SerialIn.turn_to(0)


if __name__ == "__main__":
    main()
