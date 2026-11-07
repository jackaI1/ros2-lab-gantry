# My pendant design

I designed four control screens around the command-line pendant I already use: jog, teach a point, run a program, and recover from a stop. The blue controls change or inspect the simulated gantry; red identifies the stop. Position values on the design are illustrative, not live feedback.

`pendant.penpot` is the native editable Penpot export. Import it through Penpot's dashboard, open the Pendant page, and start the **Jog, teach, run** prototype. The bottom navigation moves between the three main boards. The Components board holds the shared action and stop-button components. `jog.png`, `teach.png` and `run.png` are screenshots of the actual Penpot prototype taken in Linux CI. The design is a clickable specification, not a web interface that sends motion.

I keep the source in `tools/ui/design.json`. Its 14 actions include real JSON payloads and service paths. `tools/ui/check_actions.py` reads the actual server dispatch, checks pendant program instructions through `Pendant.prepare`, and rejects unknown names. The payloads go to `/gantry/pendant/command`, `/gantry/pendant/run` or the named stop/reset services. Cancellation uses the action's cancel interface. The existing Gazebo tests exercise these real actions.

The generator `tools/ui/build_penpot.py` uses a disposable Penpot API to create native editable shapes, reusable components and prototype interactions, exports the design, and reimports it to test the file. No external account is needed. The CI browser opens only that instance, exercises the clickable navigation, takes screenshots and closes its page, context and browser in `finally`. Compose removes the owned services and volumes even when tests fail.

To regenerate on Linux, set `PENPOT_EPHEMERAL_SECRET` to a freshly generated random string, run `docker compose -p gantry-penpot -f tools/ui/compose.yml up -d`, install `requests` and `playwright`, run `playwright install --with-deps chromium`, then run `python tools/ui/build_penpot.py`. Finish with `docker compose -p gantry-penpot -f tools/ui/compose.yml down -v --remove-orphans`. The workflow runs this process and saves `penpot-evidence.json` alongside the export.

The native file format and API are documented in [Penpot's integration guide](https://help.penpot.dev/technical-guide/integration/) and [file format reference](https://help.penpot.dev/technical-guide/developer/data-model/penpot-file-format/).
