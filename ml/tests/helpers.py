import csv
import math
import random

from ml.data import CSV_COLUMNS


def write_fixture(path, sessions=18, users=6, reviews=8):
    generator = random.Random(17)
    with path.open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(CSV_COLUMNS)
        for session in range(sessions):
            user = session % users
            half_life = 1.0 + user
            successes, time = 0, 0.0
            for index in range(reviews):
                elapsed = generator.uniform(0.25, 10)
                time += elapsed
                probability = math.exp2(-elapsed / half_life)
                success = int(generator.random() < probability)
                writer.writerow(
                    [
                        1,
                        17,
                        session,
                        user,
                        session,
                        index,
                        elapsed,
                        time,
                        successes,
                        success,
                        1000,
                        half_life,
                        probability,
                    ]
                )
                successes += success
                half_life *= 1.35 if success else 1.1
