"""Knob Mixer: physical/virtual knobs -> any audio software's volume channels.

Three decoupled layers:
  inputs/     turn hardware or keys into knob actions (up/down/mute/set)
  core.py     maps knobs to channels, keeps state, drives the overlay
  providers/  talk to an audio backend (SteelSeries Sonar, Windows, ...)
"""
APP_NAME = "Knob Mixer"
