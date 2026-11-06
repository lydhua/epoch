"""Black-box CLI/schema tests using only Python's standard library."""

import csv
import math
import os
import resource
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

EXECUTABLE = str(Path(sys.argv.pop(1)).resolve())


def limit_output_size():
    """Inject a real write failure in the single-threaded POSIX child process."""
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024, 1024))
    signal.signal(signal.SIGXFSZ, signal.SIG_IGN)


class SimulatorCLI(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [EXECUTABLE, *map(str, args)], capture_output=True, text=True, check=False, timeout=15
        )

    def test_schema_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.csv"
            result = self.run_cli("--output", path, "--sessions", 20, "--users", 4, "--reviews", 5)
            self.assertEqual(result.returncode, 0, result.stderr)
            with path.open(newline="") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 100)
            observed_updates = set()
            for session in range(20):
                history = rows[session * 5 : (session + 1) * 5]
                prior_successes = 0
                previous_time = 0
                previous_half_life = None
                previous_success = None
                for index, row in enumerate(history):
                    self.assertEqual(int(row["schema_version"]), 1)
                    self.assertEqual(int(row["seed"]), 42)
                    self.assertEqual(int(row["session_id"]), session)
                    self.assertEqual(int(row["item_id"]), session)
                    self.assertEqual(int(row["user_id"]), session % 4)
                    self.assertEqual(int(row["review_index"]), index)
                    self.assertEqual(int(row["prior_successes"]), prior_successes)
                    elapsed = float(row["elapsed_days"])
                    self.assertTrue(0.25 <= elapsed <= 30)
                    self.assertAlmostEqual(float(row["time_days"]), previous_time + elapsed)
                    previous_time = float(row["time_days"])
                    probability = float(row["oracle_recall_probability"])
                    half_life = float(row["oracle_half_life_days"])
                    self.assertTrue(math.isfinite(probability) and 0 <= probability <= 1)
                    self.assertAlmostEqual(probability, 2 ** (-elapsed / half_life))
                    if previous_half_life is not None:
                        multiplier = 1.35 if previous_success else 1.1
                        self.assertTrue(
                            math.isclose(half_life, previous_half_life * multiplier, rel_tol=1e-12)
                        )
                        observed_updates.add(previous_success)
                    previous_half_life = half_life
                    previous_success = int(row["success"])
                    self.assertIn(row["success"], ("0", "1"))
                    self.assertGreater(float(row["solve_seconds"]), 0)
                    prior_successes += int(row["success"])
            self.assertEqual(observed_updates, {0, 1}, "must test success and failure updates")
            self.assertEqual(set(Path(directory).iterdir()), {path}, "no staging files remain")

    def test_reproducibility_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.csv"
            second = Path(directory) / "second.csv"
            for path in (first, second):
                result = self.run_cli("--output", path, "--sessions", 3)
                self.assertEqual(result.returncode, 0, result.stderr)
            original = first.read_bytes()
            self.assertEqual(original, second.read_bytes())
            self.assertNotEqual(self.run_cli("--output", first).returncode, 0)
            self.assertEqual(original, first.read_bytes())

    def test_existing_links_and_directories_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            target = directory / "target.csv"
            link = directory / "link.csv"
            link.symlink_to(target)
            result = self.run_cli("--output", link, "--sessions", 1)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(link.is_symlink())
            self.assertFalse(target.exists())
            target.write_text("do not overwrite")
            self.assertNotEqual(self.run_cli("--output", link).returncode, 0)
            self.assertEqual(target.read_text(), "do not overwrite")
            hard_link = directory / "hard-link.csv"
            os.link(target, hard_link)
            self.assertNotEqual(self.run_cli("--output", hard_link).returncode, 0)
            self.assertEqual(target.read_text(), "do not overwrite")
            self.assertNotEqual(self.run_cli("--output", directory).returncode, 0)

    def test_write_failure_leaves_no_final_or_staging_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.csv"
            result = subprocess.run(
                [EXECUTABLE, "--output", str(path), "--sessions", "100"],
                capture_output=True,
                text=True,
                preexec_fn=limit_output_size,
                timeout=15,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("write", result.stderr)
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_concurrent_writers_publish_exactly_one_complete_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.csv"
            processes = []
            try:
                for seed in range(4):
                    processes.append(
                        subprocess.Popen(
                            [
                                EXECUTABLE,
                                "--output",
                                str(path),
                                "--sessions",
                                "1000",
                                "--seed",
                                str(seed),
                            ],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                        )
                    )
                for process in processes:
                    process.communicate(timeout=15)
                self.assertEqual(sum(process.returncode == 0 for process in processes), 1)
                with path.open(newline="") as source:
                    rows = list(csv.DictReader(source))
                self.assertEqual(len(rows), 8000)
                self.assertEqual(len({row["seed"] for row in rows}), 1)
                self.assertEqual(set(Path(directory).iterdir()), {path})
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                    process.communicate()

    def test_invalid_arguments_do_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.csv"
            for args in (
                ("--sessions", "0"),
                ("--users", "-1"),
                ("--reviews", "101"),
                ("--seed", "12oops"),
                ("--sessions", "4294967296"),
                ("--unknown", "4"),
                ("--reviews",),
            ):
                with self.subTest(args=args):
                    self.assertNotEqual(self.run_cli("--output", path, *args).returncode, 0)
                    self.assertFalse(path.exists())
            self.assertNotEqual(self.run_cli().returncode, 0)
            self.assertNotEqual(
                self.run_cli("--output", Path(directory) / "missing" / "file.csv").returncode,
                0,
            )

    def test_help(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Usage:", result.stdout)


if __name__ == "__main__":
    unittest.main()
