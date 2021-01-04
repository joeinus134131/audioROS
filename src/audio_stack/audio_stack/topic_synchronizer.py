#! /usr/bin/env python3
# -*- coding: utf-8 -*-

ALLOWED_LAG_MS = 20  # allowed lag between latest message and given timestamp

class TopicSynchronizer(object):
    """ Helper class to keep track of the latest message on a given topic within an admissible delay. """
    def __init__(self, allowed_lag=ALLOWED_LAG_MS):
        self.allowed_lag = allowed_lag
        self.latest_message = None

    def get_latest_message(self, timestamp, logger=None):
        """ Get latest message since timestamp-self.allow_lag, or None if it doesn't exist. """
        if self.latest_message is None:
            return None

        latest_time = self.latest_message.timestamp
        if (latest_time >= (timestamp - self.allowed_lag)):
            return self.latest_message
        # happens when we had a timestamp overflow, for instance.
        elif latest_time < timestamp:
            logger.info(f"Latest time {latest_time} smaller than requested {timestamp}. Probably due to timestamp overflow.")
            return self.latest_message
        elif (logger is not None):
            logger.warn(f"Did not register message in valid time window {timestamp-self.allowed_lag, timestamp}. Latest one: {latest_time}")
        return None

    def listener_callback(self, msg):
        self.latest_message = msg
