#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""
snr_pipeline.py

Experiment with a fixed loudspeaker playing some stationary signal.
"""

import os
import signal
import subprocess
import sys
import time

import numpy as np
import rclpy
from scipy.io import wavfile

sys.path.append(os.getcwd() + "/crazyflie-audio/python/")
from play_and_record import get_usb_soundcard_ubuntu
from signals import generate_signal
from serial_motors import SerialMotors

from crazyflie_description_py.commands import command_dict, buzzer_dict
from crazyflie_description_py.parameters import SOUND_EFFECTS

from audio_bringup.helpers import get_filename, set_param, EXP_DIRNAME, CSV_DIRNAME, WAV_DIRNAME, TOPICS_TO_RECORD


APPENDIX = None #"new" # set to None for no effect
START_DISTANCE = 0
START_ANGLE = 0

#EXTRA_DIRNAME = '2020_12_7_moving'
#EXTRA_DIRNAME = '2020_12_9_rotating'
#EXTRA_DIRNAME = '2020_12_11_calibration'
#EXTRA_DIRNAME = '2020_12_18_flying'
#EXTRA_DIRNAME = '2020_12_18_stepper'
#EXTRA_DIRNAME = '2021_01_07_snr_study'
#EXTRA_DIRNAME = '2021_01_14_snr_study'
#EXTRA_DIRNAME = '2021_01_15_snr_study'
#EXTRA_DIRNAME = '2021_01_15_snr_study_2'
#EXTRA_DIRNAME = '2021_01_21_snr_study'
EXTRA_DIRNAME = '2021_01_21_snr_study_foam'
#EXTRA_DIRNAME = '2021_01_15_snr_study_3'
#EXTRA_DIRNAME = '2021_01_15_snr_study_4'


def execute_commands(command_list, source='sweep_slow'):
    for command in command_list:
        node, parameter, value, sleep = command
        if (parameter == 'buzzer_effect') and (value is None) and (source is not None):
            value = SOUND_EFFECTS[source][0]
        elif (parameter == 'buzzer_effect') and (source is None):
            continue

        print(f'execute {parameter}: {value} and sleep for {sleep}s...')
        if parameter != '':
            set_param(node, parameter, str(value))
        time.sleep(sleep)


def get_total_time(command_list):
    time = 0
    for command in command_list:
        time += command[3]
    #time += 25 # extra 10 seconds for unexpected waiting times 
    return time


def get_active_nodes():
    param_pid = subprocess.Popen(['ros2', 'node', 'list'], stdout=subprocess.PIPE)
    out_bytes, err = param_pid.communicate()
    out_string = out_bytes.decode("utf-8").strip()
    return out_string


def main(args=None): 
    def measure_doa(params):
        distance = params.get('distance', 0)
        angle = params.get('degree', 0)
        #### prepare sound and turntable interfaces ####
        if (previous_angle != angle) or (distance != previous_distance):
            SerialIn = SerialMotors(verbose=False)

        duration = global_params.get("duration", 30)

        # If given in parameters, min_freq and max_freq overwrite all other settings. Otherwise 
        # these parameters are read from the buzzer frequency characteristics.
        min_freq = params.get('min_freq', None)
        max_freq = params.get('max_freq', None)

        if type(params['motors']) == str:
            duration_motors = get_total_time(command_dict[params['motors']])
            if duration_motors > duration:
                print(f'ignoring global duration {duration} and using motor command duration {duration_motors}')
                duration = duration_motors
        if ('buzzer-onboard' in source_type) and (params['source'] is not None):
            c, (min_freq_buzz, max_freq_buzz), duration_buzzer = SOUND_EFFECTS[params['source']]
            if duration_buzzer > duration:
                print(f'ignoring global duration {duration} and using buzzer command duration {duration_buzzer}')
                duration = duration_buzzer
            if min_freq is None:
                print(f'Using buzzer min_freq {min_freq_buzz}.')
                min_freq = min_freq_buzz
            if max_freq is None:
                print(f'Using buzzer max_freq {max_freq_buzz}.')
                max_freq = max_freq_buzz


        if distance == 51:
            duration_move = 100 #165  
            if duration_move > duration:
                print(f'ignoring global duration {duration} and using turn command duration {duration_move}')
                duration = duration_move
        elif distance == -51:
            duration_move = 165
            if duration_move > duration:
                print(f'ignoring global duration {duration} and using turn command duration {duration_move}')
                duration = duration_move

        if angle == 360:
            # TODO(FD) replace below with serial_motors.py command durations
            duration_turn = 18  
            if duration_turn > duration:
                print(f'ignoring global duration {duration} and using turn command duration {duration_turn}')
                duration = duration_turn

        if source_type == 'soundcard':
            out_signal = generate_signal(global_params['fs_soundcard'], 
                    duration, 
                    signal_type=params['source'], 
                    frequency_hz=source_params['freq_source'], 
                    min_dB=source_params['min_dB'], 
                    max_dB=source_params['max_dB'])
        elif source_type == 'buzzer':
            input(f'make sure external buzzer plays {params["source"]}! Enter to continue')

        filter_snr = params.get('snr', 0) 
        set_param('/gateway', 'filter_snr_enable', str(filter_snr))
        if (filter_snr > 0) and ((min_freq is None) or (max_freq is None)): 
            raise Warning('Need to set min_freq and max_freq when using snr filtering!')
        set_param('/gateway', 'filter_prop_enable', str(params['props']))
        if min_freq is not None:
            set_param('/gateway', 'min_freq', str(min_freq))
        if max_freq is not None:
            set_param('/gateway', 'max_freq', str(max_freq))

        #### move ####
        if (distance is not None) and not (distance in [-51, 51]):
            delta = distance - previous_distance 
            if delta > 0:
                print('moving forward by', delta)
                SerialIn.move(delta)
            elif delta < 0:
                print('moving backward by', delta)
                SerialIn.move_back(-delta)
            previous_distance = distance

        if not (angle == 360):
            delta = angle - previous_angle
            if delta > 0:
                print('turning by', delta)
                SerialIn.turn(delta, blocking=True)
            elif delta < 0:
                print('turning back by', delta)
                SerialIn.turn_back(-delta, blocking=True)

        #### record ####
        set_param('/csv_writer', 'filename', '')
        bag_pid = subprocess.Popen(['ros2', 'bag', 'record', '-o', bag_filename] + TOPICS_TO_RECORD)
        print('started bag record')


        #### play ####
        if source_type == 'buzzer-onboard':
            if params['source'] is not None:
                execute_commands(buzzer_dict[params['source']])
        elif source_type == 'buzzer-onboard-flying':
            source = params['source']
            if source not in [None, 'sweep_slow','sweep_fast']:
                execute_commands(buzzer_dict[source])

        if angle == 360:
            print('starting turning by 360')
            SerialIn.turn(angle, blocking=False)

        if distance == 51:
            print('start moving by 50')
            SerialIn.move(50, blocking=False)
            previous_distance = 50 + previous_distance

        if distance == -51:
            print('start moving back by 50') 
            SerialIn.move_back(50, blocking=False)
            previous_distance = previous_distance - 50

        # when we use an external speaker, we play and record. 
        if source_type == 'soundcard':
            if global_params['n_meas_mics'] > 0:
                print('playing and recording sound...')
                recording = sd.playrec(out_signal, blocking=True)
            else:
                print('playing (not recording) sound...')
                sd.play(out_signal, blocking=True)
        # when we use the buzzer, we simply record what the measurement mics get.    
        elif ('buzzer-onboard' in source_type) or (source_type == 'buzzer'):
            start_time = time.time()

            if global_params['n_meas_mics'] > 0:
                print(f'recording sound for {duration} seconds...')
                n_frames = int(duration * global_params['fs_soundcard'])
                recording = sd.rec(n_frames, blocking=False)

            if type(params['motors']) == str:
                print(f'executing motor commands:')
                execute_commands(command_dict[params['motors']], source=params['source'])
                extra_idle_time = duration - (time.time() - start_time)
                if extra_idle_time > 0:
                    print(f'finished motor commands faster than expected. sleeping for {extra_idle_time:.2f} seconds...')
                    time.sleep(extra_idle_time)
                elif extra_idle_time < 0:
                    print(f'Warning: finished recording before finishing motor commands! {extra_idle_time:.2f}')
            elif (type(params['motors']) == int) and (params['motors'] > 0):
                set_param('/gateway', 'all', str(params['motors']))
                print(f'waiting for {duration} seconds...')
                time.sleep(duration)
            else:
                print(f'waiting for {duration} seconds...')
                time.sleep(duration)

        #### wrap up ####
        if 'buzzer-onboard' in source_type:
            execute_commands(buzzer_dict['stop'])
        print('...done')

        set_param('/gateway', 'all', '0')
        bag_pid.send_signal(signal.SIGINT)
        set_param('/csv_writer', 'filename', csv_filename)

        if global_params['n_meas_mics'] > 0:
            recording_float32 = recording.astype(np.float32)
            wav_filename = os.path.join(wav_dirname, filename) + '.wav'
            wavfile.write(wav_filename, global_params['fs_soundcard'], recording_float32)
            print('wrote wav file as', wav_filename)

        if angle == 360:
            print('turning back by 360')
            SerialIn.turn_back(angle, blocking=True)
        return

    def measure_snr(params):
        assert source_type == 'buzzer'
        duration = global_params.get("duration", 30)

        # If given in parameters, min_freq and max_freq overwrite all other settings. Otherwise 
        # these parameters are read from the buzzer frequency characteristics.
        min_freq = params.get('min_freq', None)
        max_freq = params.get('max_freq', None)

        if (type(params['motors']) == str) or (params['motors'] > 0):
            duration_motors = get_total_time(command_dict[params['motors']])
            if duration_motors > duration:
                print(f'ignoring global duration {duration} and using motor command duration {duration_motors}')
                duration = duration_motors

        
        # we set the frequency even though this drone 
        # is not playing, so that snr=2 works. 
        if params["source"] is not None and ("mono" in params["source"]):
            freq = int(params["source"].strip("mono"))
            set_param('/gateway', 'buzzer_freq', freq)
            set_param('/gateway', 'buzzer_effect', 0)
        elif params["source"] is not None:
            c, (min_freq_buzz, max_freq_buzz), duration_buzzer = SOUND_EFFECTS[params['source']]
            if duration_buzzer > duration:
                print(f'ignoring global duration {duration} and using buzzer command duration {duration_buzzer}')
                duration = duration_buzzer

        input(f'make sure external buzzer plays {params["source"]}! Enter to continue')

        filter_snr = params.get('snr', 0) 
        set_param('/gateway', 'filter_snr_enable', str(filter_snr))
        if (filter_snr > 0) and ((min_freq is None) or (max_freq is None)): 
            raise Warning('Need to set min_freq and max_freq when using snr filtering!')
        set_param('/gateway', 'filter_prop_enable', str(params['props']))
        if min_freq is not None:
            set_param('/gateway', 'min_freq', str(min_freq))
        if max_freq is not None:
            set_param('/gateway', 'max_freq', str(max_freq))

        #### record ####
        set_param('/csv_writer', 'filename', '')
        bag_pid = subprocess.Popen(['ros2', 'bag', 'record', '-o', bag_filename] + TOPICS_TO_RECORD)
        print('started bag record')

        #### play ####
        start_time = time.time()

        if global_params['n_meas_mics'] > 0:
            print(f'recording sound for {duration} seconds...')
            n_frames = int(duration * global_params['fs_soundcard'])
            recording = sd.rec(n_frames, blocking=False)

        if type(params['motors']) == str:
            print(f'executing motor commands:')
            execute_commands(command_dict[params['motors']], source=params['source'])
            extra_idle_time = duration - (time.time() - start_time)
            if extra_idle_time > 0:
                print(f'finished motor commands faster than expected. sleeping for {extra_idle_time:.2f} seconds...')
                time.sleep(extra_idle_time)
            elif extra_idle_time < 0:
                print(f'Warning: finished recording before finishing motor commands! {extra_idle_time:.2f}')
        else: # if motors is set to 0, so no motor commands are sent. 
            print(f'waiting for {duration} seconds...')
            time.sleep(duration)

        #### wrap up ####
        print('...done')
        set_param('/gateway', 'all', '0')
        bag_pid.send_signal(signal.SIGINT)
        set_param('/csv_writer', 'filename', csv_filename)

        if global_params['n_meas_mics'] > 0:
            recording_float32 = recording.astype(np.float32)
            wav_filename = os.path.join(wav_dirname, filename) + '.wav'
            wavfile.write(wav_filename, global_params['fs_soundcard'], recording_float32)
            print('wrote wav file as', wav_filename)
        return

    def measure_snr_onboard(params):
        assert source_type == 'buzzer-onboard'
        duration = global_params.get("duration", 30)

        # If given in parameters, min_freq and max_freq overwrite all other settings. Otherwise 
        # these parameters are read from the buzzer frequency characteristics.
        min_freq = params.get('min_freq', None)
        max_freq = params.get('max_freq', None)

        if (type(params['motors']) == str) or (params['motors'] > 0):
            duration_motors = get_total_time(command_dict[params['motors']])
            if duration_motors > duration:
                print(f'ignoring global duration {duration} and using motor command duration {duration_motors}')
                duration = duration_motors

        if params["source"] is not None:
            c, (min_freq_buzz, max_freq_buzz), duration_buzzer = SOUND_EFFECTS[params['source']]
            if duration_buzzer > duration:
                print(f'ignoring global duration {duration} and using buzzer command duration {duration_buzzer}')
                duration = duration_buzzer

        filter_snr = params.get('snr', 0) 
        set_param('/gateway', 'filter_snr_enable', str(filter_snr))
        if (filter_snr > 0) and ((min_freq is None) or (max_freq is None)): 
            raise Warning('Need to set min_freq and max_freq when using snr filtering!')
        set_param('/gateway', 'filter_prop_enable', str(params['props']))
        if min_freq is not None:
            set_param('/gateway', 'min_freq', str(min_freq))
        if max_freq is not None:
            set_param('/gateway', 'max_freq', str(max_freq))

        #### record ####
        set_param('/csv_writer', 'filename', '')
        bag_pid = subprocess.Popen(['ros2', 'bag', 'record', '-o', bag_filename] + TOPICS_TO_RECORD)
        print('started bag record')

        #### play ####

        if params['source'] is not None:
            print(f'executing buzzer commands')
            execute_commands(buzzer_dict[params['source']])

        start_time = time.time()
        if global_params['n_meas_mics'] > 0:
            print(f'recording sound for {duration} seconds...')
            n_frames = int(duration * global_params['fs_soundcard'])
            recording = sd.rec(n_frames, blocking=False)

        if type(params['motors']) == str:
            print(f'executing motor commands:')
            execute_commands(command_dict[params['motors']], source=params['source'])
            extra_idle_time = duration - (time.time() - start_time)
            if extra_idle_time > 0:
                print(f'finished motor commands faster than expected. sleeping for {extra_idle_time:.2f} seconds...')
                time.sleep(extra_idle_time)
            elif extra_idle_time < 0:
                print(f'Warning: finished recording before finishing motor commands! {extra_idle_time:.2f}')
        else: # if motors is set to 0, so no motor commands are sent. 
            print(f'waiting for {duration} seconds...')
            time.sleep(duration)

        #### wrap up ####
        print('...done')
        set_param('/gateway', 'all', '0')
        bag_pid.send_signal(signal.SIGINT)
        set_param('/csv_writer', 'filename', csv_filename)

        execute_commands(buzzer_dict['stop'])

        if global_params['n_meas_mics'] > 0:
            recording_float32 = recording.astype(np.float32)
            wav_filename = os.path.join(wav_dirname, filename) + '.wav'
            wavfile.write(wav_filename, global_params['fs_soundcard'], recording_float32)
            print('wrote wav file as', wav_filename)
        return


    rclpy.init(args=args)

    extra_dirname = input(f'enter experiment folder: (appended to {EXP_DIRNAME}, default:{EXTRA_DIRNAME})') or EXTRA_DIRNAME
    exp_dirname = os.path.join(EXP_DIRNAME, extra_dirname)
    csv_dirname = os.path.join(exp_dirname, CSV_DIRNAME)
    wav_dirname = os.path.join(exp_dirname, WAV_DIRNAME)

    sys.path.append(exp_dirname)
    from params import global_params, params_list
    print(f'loaded parameters from {exp_dirname}/params.py')

    active_nodes = get_active_nodes()
    assert '/csv_writer' in active_nodes
    assert '/gateway' in active_nodes

    source_type = global_params.get('source_type', 'soundcard')
    if (source_type == 'soundcard') or (global_params['n_meas_mics'] > 0):
        sd = get_usb_soundcard_ubuntu(global_params['fs_soundcard'], global_params['n_meas_mics'])

        sound = np.zeros(10, dtype=float)
        if global_params['n_meas_mics'] > 0:
            if source_type == 'soundcard':
                print('playing and recording zero test sound...')
                sd.playrec(sound, blocking=True)
            else:
                print('recording zero test sound...')
                sd.rec(10, blocking=True)
        else:
            print('playing zero test sound...')
            sd.play(sound, blocking=True)

    for dirname in [exp_dirname, csv_dirname, wav_dirname]:
        if not os.path.exists(dirname):
            os.makedirs(dirname)
            print(f'created {dirname}')
        print(f'saving under {dirname}')

    previous_distance = START_DISTANCE
    previous_angle = START_ANGLE
    timestamp = int(time.time())

    distance = None
    angle = 0
    param_i = 0
    while param_i < len(params_list):
        params = params_list[param_i]
        answer = ''
        #answer = 'y'
        while not (answer in ['y', 'n']):
            answer = input(f'start experiment with {params}? ([y]/n)') or 'y'
        if answer == 'n':
            param_i += 1
            continue
        print(f'starting experiment {param_i+1}/{len(params_list)} with {params}')

        if type(params['motors']) == str:
            if source_type == 'soundcard':
                raise ValueError('cannot play sound card and control motors at the same time')

        #### prepare filenames ####
        filename = get_filename(**params)
        bag_filename = os.path.join(exp_dirname, filename)
        csv_filename = os.path.join(csv_dirname, filename)

        answer = ''
        while os.path.exists(bag_filename):
            if APPENDIX is None:
                answer = input(f'Path {filename} exists, append something? (default:{timestamp}, n to skip)') or timestamp
            else:
                answer = APPENDIX 
            if answer == 'n':
                break
            filename = f'{filename}_{answer}'
            bag_filename = os.path.join(exp_dirname, filename)
            csv_filename = os.path.join(csv_dirname, filename)
        if answer == 'n':
            continue

        #measure_doa(params)
        #measure_snr(params)
        measure_snr_onboard(params)
        param_i += 1

    # after last experiment: move back to position 0
    if (distance is not None) and not (distance in [0, 51, -51]):
        print('moving back by', distance)
        SerialIn.move_back(distance)

    if not (angle in [0, 360]):
        print('turning back by', angle)
        SerialIn.turn_back(angle)


if __name__ == "__main__":
    main()