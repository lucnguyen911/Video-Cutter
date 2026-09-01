import unittest

from processing_policy import HardwareProfile, choose_parallel_video_workers


class ProcessingPolicyTests(unittest.TestCase):
    def test_nvidia_scene_batch_uses_two_workers(self):
        self.assertEqual(
            choose_parallel_video_workers("nvidia", True, False, 3),
            2,
        )

    def test_single_video_stays_single_worker(self):
        self.assertEqual(
            choose_parallel_video_workers("nvidia", True, False, 1),
            1,
        )

    def test_non_scene_mode_stays_single_worker(self):
        self.assertEqual(
            choose_parallel_video_workers("nvidia", False, False, 3),
            1,
        )

    def test_shared_sequence_names_stay_single_worker(self):
        self.assertEqual(
            choose_parallel_video_workers("nvidia", True, True, 3),
            1,
        )

    def test_non_nvidia_stays_single_worker(self):
        self.assertEqual(
            choose_parallel_video_workers("cpu", True, False, 3),
            1,
        )

    def test_calibrated_strong_gpu_can_use_three_workers(self):
        profile = HardwareProfile(
            hardware_type="nvidia",
            parallel_video_workers=3,
        )
        self.assertEqual(
            choose_parallel_video_workers(
                "nvidia", True, False, 3, profile=profile,
            ),
            3,
        )


if __name__ == "__main__":
    unittest.main()
