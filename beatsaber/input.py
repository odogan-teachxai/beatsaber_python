"""
Hand tracking input module for Beat Saber visualization.
Uses MediaPipe for hand detection via webcam.
"""
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

# MediaPipe is optional - gracefully handle if not installed
try:
    import cv2
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    mp = None
    cv2 = None


@dataclass
class HandState:
    """Represents the state of a single hand."""
    position: Tuple[float, float, float]  # x, y, z in world space
    rotation: float  # rotation angle in radians
    visible: bool  # whether hand is currently detected
    last_update: float  # timestamp of last update


class HandTracker:
    """
    Tracks hands using webcam and MediaPipe.
    Runs tracking in a background thread to avoid blocking the render loop.
    """

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # Hand states
        self.left_hand = HandState(
            position=(0.0, 0.0, 0.0),
            rotation=0.0,
            visible=False,
            last_update=0.0
        )
        self.right_hand = HandState(
            position=(0.0, 0.0, 0.0),
            rotation=0.0,
            visible=False,
            last_update=0.0
        )

        # Calibration settings
        # Map webcam coordinates to world space
        self.scale = 4.0  # Scale factor for movement range
        self.offset_x = 0.0  # Center offset
        self.offset_y = -1.5  # Height offset (hands at comfortable level)
        self.offset_z = -5.0  # Distance from camera

        # MediaPipe components (initialized in start())
        self.cap = None
        self.hands = None

    @property
    def available(self) -> bool:
        """Check if MediaPipe is available."""
        return MEDIAPIPE_AVAILABLE

    def start(self) -> bool:
        """Start the hand tracking thread."""
        if not MEDIAPIPE_AVAILABLE:
            print("Hand tracking unavailable: MediaPipe not installed.")
            print("Install with: pip install mediapipe opencv-python")
            return False

        if self.running:
            return True

        try:
            # Initialize MediaPipe
            self.hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )

            # Initialize webcam
            self.cap = cv2.VideoCapture(self.camera_index)
            if not self.cap.isOpened():
                print(f"Failed to open camera {self.camera_index}")
                return False

            # Set camera resolution (lower for performance)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

            self.running = True
            self.thread = threading.Thread(target=self._tracking_loop, daemon=True)
            self.thread.start()
            print("Hand tracking started")
            return True

        except Exception as e:
            print(f"Failed to start hand tracking: {e}")
            return False

    def stop(self):
        """Stop the hand tracking thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
        if self.cap:
            self.cap.release()
            self.cap = None
        if self.hands:
            self.hands.close()
            self.hands = None
        print("Hand tracking stopped")

    def _tracking_loop(self):
        """Background thread for hand tracking."""
        while self.running:
            try:
                ret, frame = self.cap.read()
                if not ret:
                    continue

                # Flip for mirror effect
                frame = cv2.flip(frame, 1)

                # Convert BGR to RGB for MediaPipe
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Process frame
                results = self.hands.process(rgb_frame)

                current_time = time.time()

                if results.multi_hand_landmarks and results.multi_handedness:
                    for hand_landmarks, handedness in zip(
                        results.multi_hand_landmarks,
                        results.multi_handedness
                    ):
                        # Determine left/right hand
                        # MediaPipe returns "Left" or "Right" from camera's perspective
                        # Since we flip the image, "Left" is actually right hand
                        label = handedness.classification[0].label
                        is_right_hand = (label == "Left")  # Flipped

                        # Get wrist position (landmark 0)
                        wrist = hand_landmarks.landmark[0]

                        # Get index finger tip (landmark 8) for rotation
                        index_tip = hand_landmarks.landmark[8]

                        # Calculate rotation from wrist to index finger
                        dx = index_tip.x - wrist.x
                        dy = index_tip.y - wrist.y
                        rotation = np.arctan2(dy, dx)

                        # Map normalized coordinates (0-1) to world space
                        # x: -1 to 1 (left to right)
                        # y: -1 to 1 (bottom to top in world)
                        # z: fixed depth
                        world_x = (wrist.x - 0.5) * 2 * self.scale + self.offset_x
                        world_y = (0.5 - wrist.y) * 2 * self.scale + self.offset_y
                        world_z = self.offset_z

                        # Update hand state
                        hand = self.right_hand if is_right_hand else self.left_hand
                        hand.position = (world_x, world_y, world_z)
                        hand.rotation = rotation
                        hand.visible = True
                        hand.last_update = current_time

                # Mark hands as not visible if not detected recently
                timeout = 0.5  # seconds
                for hand in [self.left_hand, self.right_hand]:
                    if current_time - hand.last_update > timeout:
                        hand.visible = False

            except Exception as e:
                print(f"Tracking error: {e}")
                continue

    def get_hand_positions(self) -> Tuple[Optional[HandState], Optional[HandState]]:
        """
        Get current hand positions.
        Returns (left_hand, right_hand) tuples.
        Returns None for hands that are not visible.
        """
        left = self.left_hand if self.left_hand.visible else None
        right = self.right_hand if self.right_hand.visible else None
        return left, right
