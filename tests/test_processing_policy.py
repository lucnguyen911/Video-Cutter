import unittest

from unittest.mock import patch

from processing_policy import (
    HardwareProfile,
    build_hardware_profile,
    choose_parallel_video_workers,
)


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

    def test_high_end_nvidia_uses_three_workers_without_short_benchmark(self):
        with (
            patch(
                "processing_policy.detect_best_encoder",
                return_value=("h264_nvenc", "nvidia", "NVIDIA NVENC"),
            ),
            patch("processing_policy.os.cpu_count", return_value=20),
            patch("processing_policy._ram_gb", return_value=32.0),
            patch(
                "processing_policy._nvidia_info",
                return_value=("NVIDIA GeForce RTX 5070 Ti", 16384),
            ),
            patch("processing_policy._calibrate_parallel_workers") as calibrate,
        ):
            profile = build_hardware_profile("ffmpeg", calibrate=True)

        self.assertEqual(profile.parallel_video_workers, 3)
        calibrate.assert_not_called()
        self.assertEqual(
            choose_parallel_video_workers(
                "nvidia", True, False, 3, profile=profile,
            ),
            3,
        )


if __name__ == "__main__":
    unittest.main()
