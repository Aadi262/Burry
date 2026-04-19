#!/usr/bin/env python3
"""
clap_detector.py — Double-clap detection using sounddevice + numpy.

Listens to the Mac's microphone for a double-clap pattern:
  1. Detects a sharp amplitude spike above threshold
  2. Waits for a second spike within 300-700ms
  3. Triggers the callback (butler.main)

Auto-calibrates the threshold by sampling 2 seconds of ambient noise on start.
Has a 4-second cooldown after triggering to avoid re-triggering during speech.

Requires microphone permissions:
  System Settings → Privacy & Security → Microphone → add your terminal app
"""

import time
import threading
from pathlib import Path
import numpy as np
import sounddevice as sd

from state import butler_state


# Audio settings
SAMPLE_RATE = 44100    # Hz
BLOCK_SIZE = 1024      # Samples per block (~23ms at 44100Hz)
CHANNELS = 1           # Mono

# Clap detection settings
CLAP_WINDOW_MIN = 0.15   # Minimum gap between claps (seconds)
CLAP_WINDOW_MAX = 0.70   # Maximum gap between claps (seconds)
COOLDOWN_SECONDS = 4.0    # Cooldown after triggering (avoid re-trigger during speech)
CALIBRATION_SECONDS = 2   # How long to sample ambient noise
THRESHOLD_MULTIPLIER = 3.0  # How many times above ambient = clap
STARTUP_GRACE_SECONDS = 1.5
SESSION_FLAG = Path("/tmp/butler_session.flag")
CLAP_PEAK_MULTIPLIER = 4.0
CLAP_MIN_CREST_RATIO = 4.0


class ClapDetector:
    """
    Listens for double-clap patterns on the microphone.
    Calls the trigger callback when a double-clap is detected.
    """

    def __init__(self, on_clap_detected=None):
        """
        Args:
            on_clap_detected: Callback function, called when double-clap detected.
                              Will be called in a new thread.
        """
        self.on_clap_detected = on_clap_detected
        self.threshold = 0.3            # Will be calibrated on start
        self.last_clap_time = 0.0       # Timestamp of the first clap
        self.last_trigger_time = 0.0    # Timestamp of last trigger (for cooldown)
        self.waiting_for_second = False # Are we in the window waiting for clap #2?
        self._running = False
        self.device_id = None
        self.device_name = None
        self.sample_rate = SAMPLE_RATE
        self.channels = CHANNELS
        self.armed_at = 0.0

    def _resolve_input_device(self):
        """Pick a real microphone instead of trusting the macOS default device."""
        devices = sd.query_devices()
        default_input = None

        try:
            default_input = sd.default.device[0]
        except Exception:
            default_input = None

        candidate_ids = []
        if isinstance(default_input, int) and default_input >= 0:
            candidate_ids.append(default_input)

        for idx, device in enumerate(devices):
            if device["max_input_channels"] <= 0 or idx in candidate_ids:
                continue
            candidate_ids.append(idx)

        if not candidate_ids:
            raise RuntimeError("No microphone input device available")

        for idx in candidate_ids:
            device = devices[idx]
            try:
                samplerate = int(device.get("default_samplerate") or SAMPLE_RATE)
                channels = max(1, min(CHANNELS, int(device["max_input_channels"])))
                return idx, device["name"], samplerate, channels
            except Exception:
                continue

        raise RuntimeError("Could not configure any microphone input device")

    def calibrate(self):
        """
        Sample ambient noise for a few seconds to set the clap threshold.
        This avoids false positives in quiet or noisy environments.
        """
        self.device_id, self.device_name, self.sample_rate, self.channels = (
            self._resolve_input_device()
        )
        print(f"[Clap] 🎤 Calibrating... stay quiet for {CALIBRATION_SECONDS}s")
        print(f"[Clap] Using input device: {self.device_name}")

        samples = []

        def calibration_callback(indata, frames, time_info, status):
            rms = np.sqrt(np.mean(indata ** 2))
            samples.append(rms)

        with sd.InputStream(
            device=self.device_id,
            samplerate=self.sample_rate,
            blocksize=BLOCK_SIZE,
            channels=self.channels,
            callback=calibration_callback,
        ):
            time.sleep(CALIBRATION_SECONDS)

        if samples:
            ambient = np.mean(samples)
            self.threshold = max(ambient * THRESHOLD_MULTIPLIER, 0.05)
            print(f"[Clap] ✅ Ambient noise: {ambient:.4f}, threshold set to: {self.threshold:.4f}")
        else:
            print("[Clap] ⚠️  No audio data during calibration, using default threshold")

    def _audio_callback(self, indata, frames, time_info, status):
        """Called for each audio block — check for clap-like spikes."""
        if status:
            return  # Skip glitchy blocks

        now = time.time()

        if self.armed_at and now < self.armed_at:
            return

        # In cooldown? Skip.
        if (now - self.last_trigger_time) < COOLDOWN_SECONDS:
            return

        # Ignore clap processing while Butler is already active.
        if butler_state.is_busy or SESSION_FLAG.exists():
            self.waiting_for_second = False
            return

        # A clap should look like a sharp transient, not sustained loud audio.
        rms = np.sqrt(np.mean(indata ** 2))
        peak = float(np.max(np.abs(indata))) if indata is not None else 0.0
        crest_ratio = peak / max(float(rms), 1e-6)

        if peak < max(self.threshold * CLAP_PEAK_MULTIPLIER, self.threshold) or crest_ratio < CLAP_MIN_CREST_RATIO:
            if self.waiting_for_second and (now - self.last_clap_time) > CLAP_WINDOW_MAX:
                self.waiting_for_second = False
            return

        if rms > self.threshold:
            if self.waiting_for_second:
                # Check if second clap is within the valid window
                gap = now - self.last_clap_time
                if CLAP_WINDOW_MIN <= gap <= CLAP_WINDOW_MAX:
                    # Double clap detected!
                    self.waiting_for_second = False
                    self.last_trigger_time = now
                    print(f"\n[Clap] 👏👏 Double clap detected! (gap: {gap:.2f}s)")

                    if self.on_clap_detected:
                        # Run callback in a separate thread
                        thread = threading.Thread(
                            target=self.on_clap_detected,
                            daemon=True,
                        )
                        thread.start()
                elif gap > CLAP_WINDOW_MAX:
                    # Too slow — treat this as a new first clap
                    self.last_clap_time = now
            else:
                # First clap — start waiting for the second
                self.last_clap_time = now
                self.waiting_for_second = True
        else:
            # If too much time has passed since first clap, reset
            if self.waiting_for_second:
                gap = now - self.last_clap_time
                if gap > CLAP_WINDOW_MAX:
                    self.waiting_for_second = False

    def start(self):
        """Start listening for claps. Blocks until Ctrl+C."""
        self._running = True
        self.calibrate()

        print("[Clap] 👂 Listening for double claps...")
        print("[Clap] Clap twice quickly to trigger Butler.")
        print("[Clap] Press Ctrl+C to stop.\n")
        self.armed_at = time.time() + STARTUP_GRACE_SECONDS

        try:
            with sd.InputStream(
                device=self.device_id,
                samplerate=self.sample_rate,
                blocksize=BLOCK_SIZE,
                channels=self.channels,
                callback=self._audio_callback,
            ):
                while self._running:
                    sd.sleep(100)
        except KeyboardInterrupt:
            print("\n[Clap] Stopped listening.")
        except Exception as e:
            print(f"[Clap] ❌ Audio error: {e}")
            print("[Clap] Make sure microphone permissions are granted:")
            print("  System Settings → Privacy & Security → Microphone")

    def stop(self):
        """Stop listening."""
        self._running = False


if __name__ == "__main__":
    # Standalone test — clap twice and it prints a message
    print("=== Clap Detector Test ===\n")

    def test_callback():
        print("🎉 CLAP TRIGGER FIRED! Butler would run now.\n")

    detector = ClapDetector(on_clap_detected=test_callback)
    detector.start()
