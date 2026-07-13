import collections
import datetime
import re
from dataclasses import dataclass
from pprint import pprint


# Given a log file where each line follows the format TIMESTAMP LEVEL message
# (e.g. 2024-01-15 10:23:01 ERROR disk full), return a summary dict of counts
# per log level, and a list of all ERROR lines.
@dataclass
class LogSummary:
    counts: dict
    errors: list


def error_count(path: str):
    errors = []
    counter = collections.Counter()
    pattern = re.compile(
        "(\\d{4}-\\d{2}-\\d{2}) (\\d{2}:\\d{2}:\\d{2}) (\\w+) (.+)"
    )

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            m = pattern.match(line)
            if not m:
                continue
            _, time, level, msg = m.groups()
            counter[level] += 1
            if level == "ERROR":
                errors.append(f"{time} {msg}")

    return LogSummary(counts=dict(counter), errors=errors)


# print(error_count("./logs.txt"))


# Given an access log where each line contains a request path and duration in
# ms (e.g. GET /api/users 142ms), compute p50, p95, and p99 latency per
# endpoint. Return results sorted by p99 descending.
@dataclass
class EndpointLatency:
    endpoint: str
    p50: float
    p95: float
    p99: float


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = int(len(sorted_vals) * p / 100)
    idx = min(idx, len(sorted_vals) - 1)
    return sorted_vals[idx]


def latency_calc(path: str):
    ret = []
    results = collections.defaultdict(list)
    pattern = re.compile("(\\w+) (\\S+) (\\d+)ms")

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            m = pattern.match(line)
            if not m:
                continue
            _, endpoint, dur = m.groups()
            results[endpoint].append(dur)

    #
    for endpoint, latencies in results.items():
        ret.append(
            EndpointLatency(
                endpoint=endpoint,
                p50=percentile(latencies, 50),
                p95=percentile(latencies, 95),
                p99=percentile(latencies, 99),
            )
        )
    return sorted(ret, key=lambda r: r.p99, reverse=True)


# pprint(latency_calc("./latencies.txt"))


# Given a log file with timestamps and levels, find all 1-minute windows where
# the error rate (errors / total) exceeds a given threshold. Return each
# window's start time and error rate.
@dataclass
class Event:
    time: str
    level: str
    msg: str


def error_rates(path: str, threshold: float = 0.2):
    window_totals: dict[str, int] = collections.defaultdict(int)
    window_errors: dict[str, int] = collections.defaultdict(int)
    pattern = re.compile(
        "(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}) (\\w+) (.+)"
    )

    with open(path, "r") as f:
        for line in f:
            m = pattern.match(line)
            if not m:
                continue
            timestamp, level, msg = m.groups()
            dt = datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            window = dt.strftime("%Y-%m-%d %H:%M")
            window_totals[window] += 1
            if level == "ERROR":
                window_errors[window] += 1

    spikes = []
    for window, total in window_totals.items():
        errors = window_errors.get(window, 0)
        rate = errors / total
        if rate >= threshold:
            spikes.append(
                {
                    "window": window,
                    "error_rate": round(rate, 3),
                    "errors": errors,
                    "total": total,
                }
            )

    return sorted(spikes, key=lambda s: s["window"])


pprint(error_rates("./errors.txt"))
