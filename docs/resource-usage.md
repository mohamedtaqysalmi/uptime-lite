# Resource usage

Measured on 2026-11-12 with `scripts/measure_resources.py`.

Machine: Intel Core i5-10210U (4 cores, 8 threads), 23.8 GB RAM, Windows 11 Home 10.0.26300, Python 3.15.2, package installed editable in a venv.

## Method

```bash
python scripts/measure_resources.py --runs 10
```

The script starts a small HTTP server on 127.0.0.1 and writes a config with 20 checks: 10 HTTP and 10 TCP, all pointing at that server. It then runs the real `uptime-lite check --no-alerts` entry point in a fresh Python process, 10 times, each with a new database. Each child reports its own peak resident memory (Windows `PeakWorkingSetSize`, `ru_maxrss` elsewhere) and CPU time (`time.process_time`, which includes interpreter startup and imports). The parent times the whole process. It also runs one child that does nothing, to show what an idle interpreter costs on this machine.

## Results

| Metric | Median | Min | Max |
| --- | --- | --- | --- |
| Peak resident memory (MiB) | 33.4 | 33.3 | 33.6 |
| CPU time per run (s) | 1.16 | 0.80 | 1.34 |
| Time spent running the 20 checks (s) | 0.77 | 0.45 | 1.06 |
| Whole process wall time (s) | 1.61 | 1.20 | 2.26 |

An idle interpreter on the same machine peaks at 23.8 MiB and uses 0.59 s of CPU just to start. About 10 MiB of the peak memory is therefore the package, PyYAML, SQLite and the 20 checks. The CPU figure is dominated by start-up on this machine, and I did not separate the two further.

## What this does not tell you

- The targets are on loopback, so there is no real network latency, DNS or TLS cost. Real HTTP checks will take longer and wait on sockets, which costs little CPU.
- This is one `check` run, which is how the tool runs today (from cron or Task Scheduler). There is no long-running scheduler, so memory and CPU of a process that stays up for days are not measured.
- Checks run one after another. With real targets, the run takes at least the sum of the check latencies, and a target that times out holds up the ones after it for up to its timeout.
- One machine, one operating system, one Python version. Linux numbers are not measured.
