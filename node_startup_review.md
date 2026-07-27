# pangalactic.node review — startup path (2026-07-25)

First installment of the `pangalactic.node` review, covering the client
startup chain end to end:

```
gargleblaster/__main__.py : main()          # builds + creates app_home_dir
  -> pangalaxian.run()                      # resolves + creates home AGAIN
       -> Main.__init__()                   # home-version check + cleanup
            -> orb.start(home=...)          # A/B/C resolution + creates AGAIN
            -> node/startup.py : setup_dirs_and_state()
```

Note: `pangalactic/node/__init__.py` and `gargleblaster/__init__.py` are
both one-line version strings — the startup logic is in `__main__.py`,
`run()` (`pangalaxian.py:7075`), `Main.__init__` (`pangalaxian.py:214`),
and `node/startup.py`.

Context taken as given (author): PyQt5 only (PyQt6 blocked on
`pythonocc-core`); autobahn + twisted by deliberate choice; the
pydispatcher/pyqtSignal mixture is a known in-progress migration toward
pydispatcher and is not reported as a finding.

Every finding below was verified by execution.

---

## Findings (most severe first)

### 1. `pangalaxian.py`'s `--key` is a boolean flag — the new key-file option does not work there
`pangalactic/node/pangalaxian.py:7249`
```python
parser.add_argument('--key', action='store_true',
                    help="name of file holding the user's private key")
...
run(..., key_file_name=options.key, ...)          # line 7279
```
`action='store_true'` makes `--key` take **no value**, so `options.key` is a
`bool`. The sibling definitions in `gargleblaster/__main__.py:104` and
`test/gui_client.py:1034` are correct (`type=str`). Verified against the
real definition:

| invocation | result |
|---|---|
| `pangalaxian.py --key zaphod.key` | argparse **exits(2)**: `unrecognized arguments: zaphod.key` |
| `pangalaxian.py --key` | `key_file_name=True` → `key_path` does `os.path.join(user_home, True)` → **`TypeError`** |
| `pangalaxian.py` (no `--key`) | `options.key=False` → falsy → default `pangalaxian.key` applied → works |

So it works *only* when the option isn't used. The `--key` alone case
fails because `key_path` (line 2648) guards with `if not
self.key_file_name:` — `False` is falsy so the default is applied, but
`True` is truthy so the bool is passed straight to `os.path.join`.

This matters for the stated purpose of the option: running tests as
different users (`--key zaphod.key`, `--key buckaroo.key`). Via
gargleblaster it works; invoking `pangalaxian.py` directly it does not.
Fix: `parser.add_argument('--key', dest='key', type=str, default='', ...)`
to match the other two.

### 2. `Main.user_home` returns the *parent of orb.home*, not the user's home directory
`pangalactic/node/pangalaxian.py:2628-2636`
```python
@property
def user_home(self):
    """
    Path to the user's home directory.
    """
    p = Path(orb.home)
    absp = p.resolve()
    home = absp.parent
    return str(home)
```
This is correct only under the assumption that the app home directory sits
exactly one level below the user's home directory. Verified:
`orb.home=/home/waterbug/gargleblaster_home_dev` → `/home/waterbug` (right),
but `orb.home=/tmp/scratch/junk_home` → `/tmp/scratch` (wrong — that is not
anyone's home directory).

The assumption is violated by the "if all else fails" fallbacks that place
the app home under the *current working directory*
(`gargleblaster/__main__.py:138`, `pangalaxian.py:7145`), and by any
explicitly-passed nested `--home` path.

Impact is concentrated on finding #1's feature: `key_path` (2650) resolves
the private key as `os.path.join(self.user_home, self.key_file_name)`, so
whenever the assumption breaks the key is silently looked for in the wrong
directory. `user_home` is also used for `state['last_path']` and file-dialog
start paths (6347, 6380, 6726, 6765, 6793, 6955), where a wrong value is
merely annoying rather than breaking.

**Revised recommendation** (prompted by the author's observation that the
user home is platform-dependent): my first suggestion — "derive it from
`USERPROFILE`/`HOME` the way the callers do" — would have made this the
*fifth* copy of that platform branch, which is presumably the very thing
the property was written to avoid. Deriving from `orb.home` is a reasonable
dodge; the problems are only that the name/docstring claim something
stronger than what is computed, and that it breaks in the fallback layouts.
See finding #4 — the right fix for both is one shared helper. 

### 3. Three layers resolve "home", and `app_home` means two different things
This is the full picture behind the `orb.start()` finding deferred from the
`pangalactic.core` pass.

1. **`gargleblaster/__main__.py:114-142`** — builds an **absolute** path
   (`$HOME/gargleblaster_home_dev`) and creates it.
2. **`pangalaxian.run():7123-7148`** — treats `app_home` as a *directory
   name* and joins it under the user home:
   `app_home_path = os.path.join(user_home, app_home)`.
3. **`orb.start():221-245`** — runs its own A/B/C precedence and creates the
   directory a third time.

Layer 2 works with layer 1's absolute path only by accident of
`os.path.join` semantics: a rooted right-hand operand discards everything to
its left. Verified:
```
join('/home/waterbug', '/home/waterbug/gargleblaster_home_dev')
    -> /home/waterbug/gargleblaster_home_dev      # left operand discarded
join('/home/waterbug', 'mydir')
    -> /home/waterbug/mydir                       # joined
```
So the same parameter is a **full path** when gargleblaster passes it and a
**name relative to the user home** when the `--home` CLI option passes it —
and `run()`'s own docstring ("specified name of app home directory") and the
`--home` help text ("name of application home directory") document only the
second reading. Nothing is broken today; the hazard is that the two
readings silently diverge for any path that is relative but not intended to
be under the user home.

This is the context needed to decide the deferred `orb.start()` question:
because layers 1 and 2 always create the directory first, `orb.start()`'s
inability to cope with a non-existent home is unreachable through the real
applications — it only bites direct callers (module `__main__` blocks,
tests, `gui_client.py`). A decision to fix it in core, or to formally
document "home must exist and is the caller's responsibility," can now be
made deliberately.

### 4. The platform-dependent user-home lookup is copy-pasted three times, each with the same latent `TypeError`
The author's point that the user home is platform-dependent is exactly why
this is worth treating as one structural finding rather than three local
bugs. The identical single-argument-`join` pattern appears at:

| location | context |
|---|---|
| `gargleblaster/__main__.py:121` | builds `app_home_dir` |
| `pangalactic.node/pangalaxian.py:7132` | `run()` builds `app_home_path` |
| `pangalactic.core/uberorb.py:232` | `orb.start()` precedence branch [C] |

(`fastorb.py:293` carries a fourth copy but is excluded from review as a
WIP that is not yet functional — noted only so it isn't missed if that
module is ever revived.)

All three are `os.path.join(os.environ.get('USERPROFILE'))` — a
single-argument join that raises `TypeError` when the variable is unset,
rather than yielding a falsy value the surrounding guard could catch.
(All three get the Linux/macOS branch right, via `os.environ.get('HOME', '')
or ''` plus an `if user_home:` guard; only the win32 branch is flawed.)
Add the `user_home` property from #2 and there are effectively **four**
different ways to answer "where is the user's home directory?" — three
explicit copies plus one derived-from-`orb.home` shortcut.

**Suggested fix:** one helper, in `pangalactic.core` (since `uberorb` needs
it too) — something like `get_user_home()` returning `''` when neither
variable is set — and call it from all three sites plus the `user_home`
property. That fixes the `TypeError` once, makes the unreachable fallback
in the sub-finding below reachable, and lets the `user_home` property mean
what its docstring says without adding another platform branch.

#### 4a. Consequence today: the "if all else fails" fallback is unreachable
`gargleblaster/__main__.py:117-142`
```python
if sys.platform == 'win32':
    user_home = os.path.join(os.environ.get('USERPROFILE'))   # None -> TypeError
else:
    user_home = os.environ.get('HOME')                        # may be None
if os.path.exists(user_home):                                 # None -> TypeError
    ...
if not app_home_dir:                    # the "if all else fails" fallback
    app_home_dir = os.path.join(os.getcwd(), 'gargleblaster_home')
```
Verified: `os.path.exists(None)` raises `TypeError`, and
`os.path.join(None)` raises `TypeError`. So with `HOME` unset the function
raises at the `os.path.exists` check and **never reaches the cwd fallback at
137-138 that exists precisely for that situation**.

`run()` gets the Linux/macOS branch right (`user_home = os.environ.get('HOME')`
then `if user_home:`, lines 7137-7139), so this particular unreachability is
gargleblaster-specific — but the win32 half of the problem is shared by all
three sites listed above. Low real-world likelihood; cheap to make robust,
and cheapest as the single helper rather than three separate patches.

### 5. Home-version cleanup deletes every top-level `.json` — including the three authoritative caches
`pangalactic/node/pangalaxian.py:296-328`, with
`compat_versions = [Version('4.4.dev2')]` (line 201-203)

On a version mismatch the cleanup removes `VERSION`, `local.db`, `cache/`,
`onto/`, and then:
```python
fnames = os.listdir(home)
for fname in fnames:
    if fname.endswith('.json'):
        os.remove(os.path.join(home, fname))
```
That set includes `parameters.json`, `data_elements.json`, and
`mode_defs.json` — the three caches identified in the core review as *not*
derivable from the database. This is by design (the comment at 334-340 says
the user is told and the data returns on the next repository sync, which is
consistent with the server holding the authoritative copies), so it is
recorded here as behavior to be aware of rather than a defect. Three
sharp edges around it:

- `compat_versions` contains only the **current** version, so every version
  bump — including dev increments — triggers a full local wipe.
- When `home` exists but `VERSION` does not, `home_version` keeps its
  initial value `Version('3.1')`, which is never in `compat_versions`, so
  the cleanup always runs. Harmless on a genuine first run (the directory is
  empty), but it means "missing VERSION" is treated as "incompatible" rather
  than "unknown".
- `Version(f.read())` (line 303) is unguarded. Verified: a trailing newline
  is fine, but `'garbage'` or an empty file raises `InvalidVersion`, which
  is uncaught and would **abort startup** — an empty `VERSION` is a
  plausible result of a crash or a full disk mid-write. A `try/except
  InvalidVersion` treating it as incompatible would degrade gracefully into
  the cleanup path that already exists.

### 6. `gargleblaster/__main__.py`: duplicated `makedirs`, hardcoded release mode
- **Lines 139-142** — the same guarded `makedirs` twice in a row:
  ```python
  if not os.path.exists(app_home_dir):
      os.makedirs(app_home_dir, mode=0o755)
  if not os.path.exists(app_home_dir):
      os.makedirs(app_home_dir)
  ```
  The second is dead: if the first succeeded the directory exists; if it
  raised, control never reaches the second. (The second also drops the
  explicit `mode`.)
- **Line 34** — `release_mode = "dev"` is hardcoded, so the `test` and
  production branches at 40-46 are unreachable and `app_name` is always
  `Gargleblaster_dev`. Producing a production build requires editing the
  source. Worth driving from a CLI flag, an env var, or the build.
- Minor: the step comments run [1], [2], [3], [4], [6] — no [5].
- Minor: `refdata.core += data.data` (line 216) mutates module-level
  reference data at startup; harmless for a single `main()` call, but it
  would duplicate entries if `main()` were ever invoked twice in one
  process (e.g. from a test harness).

---

## Verified correct / no findings

- **`node/startup.py`'s `setup_dirs_and_state()`** — the four resource-copy
  blocks (images, icons, docs, doc images) all correctly use
  `set(resource_files) - set(existing_files)` so they are idempotent and
  cheap on restart, and each creates its target directory first. The
  prefs/state defaulting logic (dashboards, default parms, default data
  elements) consistently preserves existing user values and only fills gaps.
  The only nit is heavy duplication across the four blocks — they differ
  only in source module and target directory, and could be one helper —
  but there is no bug.
- The `state['app_*']` convention (set fresh by the app each run, never
  restored from the saved state file) is coherent between
  `gargleblaster/__main__.py` (which sets them) and
  `p.core.__init__.read_state()` (which strips them on load).

## Suggested fix order

1. **#1 `--key`** — one line, and it blocks the multi-user test workflow you
   just built the option for.
2. **#4 + #2 together** — add a single `get_user_home()` helper in
   `pangalactic.core` and route all three platform branches plus the
   `user_home` property through it. Doing these as one change fixes the
   shared `TypeError`, makes gargleblaster's fallback reachable, and
   resolves what `user_home` should mean — without adding a fifth copy of
   the platform logic. #1's key lookup depends on this.
3. **#5's `InvalidVersion` guard** — small, and turns a startup abort into
   the already-existing recovery path.
5. **#3** — settle the layering deliberately: either have `run()` accept
   only a full path (and say so), or have it normalize explicitly rather
   than relying on `os.path.join`'s rooted-operand behavior. This is also
   the decision point for the deferred `orb.start()` fix.
6. **#6** — cleanups; the hardcoded `release_mode` is the one with real
   consequences (production packaging).
