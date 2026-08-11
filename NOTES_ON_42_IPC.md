# Design note: the 42 IPC socket link, 2026-08-08

First milestone of the gargleblaster ↔ 42 connection: a protocol layer and a
listener, proven against a real running 42. No GUI yet, deliberately — the
handshake and the parser are the risky part and are worth settling before any
Qt work sits on them.

Upstream reference: `Source/42ipc.c`, `Source/AutoCode/TxRxIPC.c`,
`InOut/Inp_IPC.txt` at commit `f5988756` (the revision our conda recipe pins).

---

## 1. The protocol

`InterProcessComm()` runs **once per simulation step** (`42exec.c:367`).

**42 → peer (TX)**, ASCII, line-oriented:

```
TIME 2024-099-00:00:00.100000000
SC[0].qn = [2.970455206341e-01 7.069619089064e-02 ...]
SC[0].wn = [4.870131279943e-03 ...]
...
[ENDMSG]
```

then 42 **blocks** on `read(Socket, Ack, 4)`.

**peer → 42 (RX)**: 42 does one `read(Socket, Msg, 16384)`, immediately writes
its own 4-byte ack back, and parses the same line format.

Which side listens is per-socket in `Inp_IPC.txt`. 42's shipped default is
`CLIENT` — 42 dials out, the peer listens — which is what `Listener42`
implements.

### The ack is the whole design

**42 blocks until it receives exactly four bytes.** Two consequences, and they
point in opposite directions:

- **It is the control lever.** Withholding or delaying the ack *pauses the
  simulation*. Run / pause / single-step therefore need **no change to 42 at
  all** — they are ack policy. `Listener42.messages()` acks *after* yielding
  for exactly this reason, so a consumer that stops iterating stops 42, and a
  slow consumer throttles it rather than losing data.
- **It is the hazard.** Anything holding the socket must ack even when busy.
  A GUI that blocks its event loop hangs the simulation. Per
  `pydispatcher_migration.md` §1 this is a *cross-thread* concern: a socket
  reader on a worker thread must marshal to the GUI with `pyqtSignal`, **not**
  pydispatcher, which would run the receiver on the worker thread.

### There is no command channel

`ReadFromSocket` parses **state variables only** — `SC[].qn`, `.wn`, `.PosR`,
`.VelR`, `.svb`, `.bvb`, `.Hvb`, `SC[].B[].qn/wn`, `SC[].G[].Ang/AngRate/
Pos/PosRate`, `SC[].Whl[].H`, `Orb[].PosN/VelN`, `World[].eph.PosN`,
`CommLink[].*`. Nothing resembling "slew to X", "reset", "set stop time".

42's commanding is `Inp_Cmd.txt`, read by `CmdInterpreter()` which runs
*before* `InitInterProcessComm()`. So socket "control" means **pacing plus
state injection**, not commanding. Real commanding would need `Inp_Cmd.txt`
plus a restart, or an upstream change to `ReadFromSocket` — and the conda
recipe's history is a caution about carrying source patches (see
`conda_recipe_42/CLAUDE.md` iteration 18).

## 2. A real hazard in upstream: unchecked 16 KB buffer

`WriteToSocket` builds the whole message in `char Msg[16384]` with repeated

```c
memcpy(&Msg[MsgLen],line,LineLen);
MsgLen += LineLen;
```

and **no bounds check anywhere**. Measured against a real captured message
(one spacecraft, one body, 42's shipped default prefixes `SC`, `Orb`,
`World`):

| | bytes | of buffer |
|---|---|---|
| whole message | 14,083 | 86% |
| …of which `World[]` | 13,206 | 81% |
| headroom | 2,301 | 14% |

**The axis that matters is bodies and joints within one spacecraft**, not the
number of spacecraft. That is 42's design centre — multi-body dynamics with a
tree topology and rotational/translational joints — and each one adds lines:

| element | lines | cost |
|---|---|---|
| body | `B[].qn`, `B[].wn` | ~169 B |
| joint / gimbal | `G[].Ang`, `.AngRate`, `.Pos`, `.PosRate` | ~332 B |
| reaction wheel | `Whl[].H` | ~37 B |

So with the default prefixes:

```
  1 body  / 0 joints : 14,083 bytes
  5 bodies/ 4 joints : 16,087 bytes
  6 bodies/ 5 joints : 16,588 bytes   <-- OVERFLOWS char Msg[16384]
```

**A single articulated spacecraft — solar array drives, an antenna gimbal, an
instrument pointing mechanism — overflows a fixed stack buffer with no bounds
check.** Worth reporting upstream.

*(An earlier draft of this note framed the risk as "5 spacecraft". That was
wrong, and wrong in a way that understated it: 42's multi-body support is
primarily about one spacecraft made of many bodies, not constellations —
author's correction, 2026-08-08.)*

### Mitigation on our side is trivial

`World[]` is 94% of the message and buys nothing for ACS work. Dropping that
prefix:

| | bytes | of buffer | bodies+joints that fit |
|---|---|---|---|
| `SC`, `Orb`, `World` | 14,083 | 86% | ~5 |
| `SC`, `Orb` | 877 | 5% | ~31 |

**Subscribe to the narrowest prefix set that serves the purpose.** For ACS
work that is `SC` — and `SC[0].AC` when we want the controller's own state.

## 3. What was built

`pangalactic/node/ipc42.py` — pure protocol plus a blocking listener. No Qt,
no orb, no dependency on the rest of the package, so it can be driven from a
script, a worker thread, or a test.

- `parse_message(text) -> Message42` — a `Time42` plus `{name: value}`, names
  kept verbatim as 42 writes them so callers can filter with the same literal
  prefix semantics 42 uses to configure (`strncmp`). Unrecognised lines are
  collected in `.unparsed` rather than dropped, so an upstream format change
  surfaces as data instead of silence.
- `build_message(time, values)` / `format_value` — the RX direction.
  `format_value` renders C's `%18.12le` as Python's `{:18.12e}`; verified
  **byte-identical** to 42's own output on a captured line.
- `Listener42` — accepts 42's connection, reassembles messages on `[ENDMSG]`
  across TCP segment boundaries, and acks. Note 42's *own* RX side does a
  single unframed `read()`, which constrains what we may send, not what we
  can receive.

## 4. Verification

Driven against a real 42 (`42-2026.07.24`, headless, TX/CLIENT, default
prefixes):

- 42 connected, **10 messages** read and acked, time advancing 0.1 s per step;
- **176 values parsed per message, zero unparsed lines**;
- prefix filtering reproduced 42's own counts (`SC` → 9, `Orb` → 2,
  `World` → 165, `SC[0].AC` → 0).

`test/test_ipc42.py` — 18 cases against `test/data/42_ipc_message.txt`, which
is a **real captured message**, not a hand-written approximation. That
distinction matters: the format comes from `sprintf` in C, so a transcription
error would be invisible in a test written from reading the source. The suite
covers parsing, the value grammar, prefix semantics, round-tripping, framing
(split and coalesced reads, clean close), the 4-byte ack, and that
`messages()` acks *after* yielding — the property the pause/step design rests
on.

## 5. The Qt front end (2026-08-11)

`pangalactic/node/ipc42_gui.py` — `Ipc42Worker` (a `QObject` moved onto a
`QThread`, owning the `Listener42`) plus `Ipc42Panel` (clock, message count,
watched values, Run/Pause/Step/Stop).

**Run / pause / step are ack policy.** The worker emits the message *first*
and acks *after* — while paused it simply doesn't ack, so 42 stays parked in
`read(Socket, Ack, 4)`. Nothing is sent to 42 and 42 needs no support for it.
Step is a `threading.Semaphore` with one permit per requested step.

**pyqtSignal here, not pydispatcher** — the boundary from §1, and the first
new code that depends on it. `test_02` asserts on `threading.current_thread()
.ident` inside the slot rather than trusting the docs.

`test_signal_migration.py` `CROSS_THREAD_MODULES` now lists `ipc42_gui.py`
alongside `threads.py`, with a pinned signal count so a *new* pyqtSignal in
either still has to justify itself.

### Three defects the tests found

1. **Qt aborted the process on shutdown.** The worker sat in `accept()` with
   nothing ever connecting; `stop()` closed the socket, which on Linux does
   **not** reliably interrupt a blocked `accept()`. `thread.wait()` timed out
   and Qt aborts when a still-running `QThread` is destroyed. Fixed by giving
   `Listener42` an `accept_timeout` *separate from* its read timeout — the
   listening socket polls (`ACCEPT_POLL`, 0.1 s) so a stop is noticed, while
   reads still block indefinitely, since a simulation step may take as long
   as it takes.

2. **42 exiting was reported as an error.** A peer that closes with data
   still unread sends RST, so the same event surfaces as `ECONNRESET` on a
   read or `EPIPE` on the ack purely by timing — the failure was
   intermittent, roughly 1 run in 6. `_DISCONNECT_ERRNOS` now classifies
   those as a disconnect. `test_09a` forces it deterministically with
   `SO_LINGER` 0 rather than waiting for the race.

3. **A chained signal with no consumers.** The panel re-emitted the stream as
   its own `message` signal — `worker.message` → `on_message` → `panel
   .message`. Removed: anything wanting the raw stream connects to
   `panel.worker.message`, which is also the more specific signal.

## 6. Next

- Deciding what "control" should mean given there is no command channel.
- Wiring the panel into pangalaxian (a dock or a tool window) once there is
  something for the stream to drive.
- Separately, goal (1) — generating 42 input files from a gargleblaster ACS
  assembly — extends `interface42.py` and does not touch any of this.
