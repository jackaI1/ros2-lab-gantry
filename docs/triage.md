# Inspect and reproduce a stopped run

I record faults next to motion measurements so I can work backwards from a stop. For each plate request the server writes a shared run identifier into four filenames: `-run.json` (request, initial position and simulation start time), `-events.jsonl` (input, first latched fault and result), `-tracking.csv`, and `-dispenses.csv`. Event rows flush immediately. These files are plain recordings rather than rosbag archives. Pendant programs still use the existing pendant status API; this recorder currently covers plate protocols.

```sh
# Inside the running Linux simulation container, or after sourcing its install setup:
python3 -m gantry_control.triage /logs/<run-id>-run.json > /logs/report.md
python3 -m gantry_control.replay /logs/<run-id>-run.json --simulation
```

The report keeps complete fault reasons, motion phases, simulation times and the 12 nearest tracking rows before each fault. Exact complete signatures map messages to reviewed cause groups. Unfamiliar messages stay in `unknown`, with their original text and context. The cause groups are hypotheses for checking the machine, not automatic proof of a root cause.

Replay actively moves the robot. Use a separate isolated Gazebo session with no hardware connection. The tool requires explicit simulation opt-in and a `/clock` topic, clears simulated inputs, requires a healthy reset, restores the recorded initial pose, then submits the original plate request. It reapplies recorded emergency-stop or limit-switch input changes at their recorded elapsed wall times. The result is checked against the original fault group and written with a new run ID. It does not simply reprint the old failure or replay CSV values as if they were new measurements. Exact trajectories can differ with scheduler and simulator timing.

Automatic reproduction is intentionally limited to the two supported input services. Stale feedback, tracking failures and unknown faults still produce reports and playbooks, but replay refuses to invent an injection for them. No replay means no claimed reproduction.

The [playbooks](playbook/) each give symptoms, checks, a fix and a recovery check. Run `python3 tools/check_playbooks.py` before committing. Every page carries a SHA-256 fingerprint of the exact signature catalog, Python control sources, controller YAML and C++ travel/velocity logic. Any change to those sources invalidates the pages, conservatively including unrelated server edits. Read and update each page before refreshing its fingerprint. The CI test mutates controller settings and adds an unfamiliar fault to prove the guard fails.

The C++ monitor in `src/gantry_monitor` subscribes to actual `/joint_states` and publishes `/gantry/safety_warning` and `/gantry/stop_requested`. It checks all travel bounds, speed magnitude, missing or duplicate joints and non-finite feedback. Its stop topic is advisory and is not wired as a second certified interlock; the existing Python server still cancels controller actions when its own checks latch a fault. The monitor does not have a stale-message timer. GoogleTest exercises its pure limit logic, and the Gazebo launch test moves X to its real end of travel and observes its warning.
