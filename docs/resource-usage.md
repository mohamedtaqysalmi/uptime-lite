# Resource usage notes

Measured on 2026-11-11, Windows 10, Python 3.15.2, local `.venv`.

Command:

```bash
python scripts/measure_resources.py --count 20
```

The script runs 20 checks (alternating fake HTTP and TCP transports with a 1 ms sleep), writes each result into an in-memory SQLite database, and advances the incident state machine. Nothing leaves the machine.

## Numbers from this run

| Metric | Value |
| --- | --- |
| Checks | 20 |
| Wall time | 0.0475 s |
| CPU time (`process_time`) | 0.0156 s |
| Peak traced Python allocations | 4.4 KiB |
| Mean check latency (fake transport) | 1.65 ms |
| ~p95 latency (fake transport) | 5.93 ms |

## How to read this

- These numbers describe Python + SQLite overhead with stub transports. Real HTTP/TCP latency dominates in production and is not included.
- Peak `tracemalloc` is allocation tracking inside the interpreter, not the full process RSS. Expect a few tens of MiB of process memory once interpreters, YAML and SQLite are loaded; I have not published a fake RSS number.
- At 20 checks with 30–60 s intervals, a single process is idle most of the time. CPU cost is a brief spike per tick, not a sustained load.

Re-run the script on your host before quoting numbers in capacity plans.
