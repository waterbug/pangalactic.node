# pangalactic.node review — `pangalaxian.py`, parameter/data-element and object-lifecycle handlers (2026-07-31)

Fourth installment of the `pangalactic.node` review. Covers the chunks
deferred at the end of `pangalaxian_sync_review.md`:

- the local and remote parameter / data-element handlers (`on_parms_set`
  through `on_vger_get_parmz_result`, ~3701-4051);
- `on_vger_save_result` and the result-handler group (~4053-4270);
- the local object-lifecycle signal handlers (`on_new_objects_signal` /
  `on_mod_objects_signal`, ~3599-3700);
- a full sweep of `exec_()` call sites in the file;
- `gen_keys()` and spot checks across the remaining UI actions.

**Covered in the next installment** (`pangalaxian_remaining_chunks_review.md`,
same date): the mode / tree / dashboard machinery, `on_deleted_object_signal`
and `del_object`, the admin-tool result handlers, and `on_pubsub_msg`'s full
dispatch table. Together the two documents complete `pangalaxian.py`, with
the coverage caveat noted at the top of that one.

Every finding below was verified by execution against a real orb with the
standard test fixtures, except where explicitly marked as latent.

---

## Findings (most severe first)

### 1. `on_remote_properties_set` raises `AttributeError` on any "properties set" broadcast for an object the client does not hold
`pangalactic/node/pangalaxian.py:3847-3877`

```python
for oid, prop_dict in prop_mods.items():
    for prop_id, val in prop_dict.items():
        status = orb.set_prop_val(oid, prop_id, val)
        if status == 'succeeded':
            success_oids.add(oid)
if success_oids:
    mod_dt = uncook_datetime(mod_dt_str)
    for oid in success_oids:
        obj = orb.get(oid)
        obj.mod_datetime = mod_dt          # <-- obj may be None
```

`orb.set_prop_val` (`pangalactic.core/uberorb.py:1662`) writes straight into
the `parameterz` / `data_elementz` caches, which are keyed by oid — it never
checks that an object with that oid exists, and returns `'succeeded'`
regardless. So `success_oids` routinely contains oids the client has no
object for, and `obj.mod_datetime` then raises on `None`. The handler has no
`try/except` (contrast its sibling `on_remote_data_elements_set`, which wraps
its whole body), so the pubsub callback aborts.

**This is highly reachable.** `vger.set_properties` publishes
`{'properties set': (prop_mods, mod_dt_str)}` on **`vger.channel.public`**
(`vger.py`), and every client subscribes to that channel
(`subscribe_to_mbus_channels:1100`). A client therefore receives property
changes for *every* project on the server, including the ones it holds no
objects for — which is the normal case, since a client's local db only covers
projects the user has a role on.

**Verified by execution**, with the standard fixtures and an oid the client
does not have:

```
client has this object locally?                    False
orb.set_prop_val(<unknown oid>, "m", 42.0)      -> 'succeeded'
parameterz now has an entry for it?                True
handler raised: AttributeError: 'NoneType' object has no attribute 'mod_datetime'
```

Two distinct defects, worth fixing together:
- **the crash** — guard with `if obj:` before the `mod_datetime` assignment
  (and consider whether the handler should skip unknown oids entirely);
- **the cache pollution** — even without the crash, `set_prop_val` has by then
  written a `parameterz` entry for an object the client does not have and
  will never display. Since `parameterz` is one of the three *authoritative*
  caches (see `pangalactic.core`'s cache-class distinction), it accumulates
  junk keyed to foreign oids for the life of the session, and gets persisted
  to `parameters.json`.

Also note `orb.db.commit()` is called **inside** the per-oid loop (3869)
rather than once after it.

**STATUS: FIXED.** Oids with no local object are now skipped *before*
`set_prop_val` is called (and counted in a debug log line), which closes both
the crash and the cache pollution in one step; the commit was moved out of
the loop. **Verified by execution** with a broadcast carrying one foreign oid
and one known oid:

| | pre-fix | post-fix |
|---|---|---|
| handler outcome | `AttributeError` on `None` | completed: 1 applied, 1 skipped |
| foreign oid written into `parameterz` | yes | no |
| known object still updated | — (never reached) | yes |

### 2. Parameter edits made offline are silently lost on reconnect
`pangalaxian.py:3701-3715` (`on_parms_set`), `3948-3960`
(`on_vger_get_parmz_result`), with
`pangalactic/node/pgxnobject.py:2480-2505` (`on_save`'s parameter-only path)

Three separate pieces combine into a silent-loss path. Traced end to end and
**verified by execution**:

1. **A parameter-only edit never bumps the object's `mod_datetime`.** When an
   object's only editable widgets are parameters, `pgxnobject.on_save`
   takes an early-return branch that sets the parameter values, sends
   `"parms set"`, and `return`s — *before* reaching
   `self.obj.mod_datetime = NOW` at line 2578.
2. **`on_parms_set` is gated on connectivity** and queues nothing:
   `if parms and state.get('connected'):`. Offline, the rpc is simply not
   sent, and no record is kept. (`on_parm_added` / `on_parm_del`, 3724-3756,
   are gated identically.)
3. **On reconnect the server's cache overwrites the client's.**
   `on_vger_get_parmz_result` does `parameterz.update(parmz_data)`, and
   `vger.get_parmz()` called with no arguments returns the **entire** server
   `parameterz` cache. Because `parameterz` is `{oid: {pid: value}}`, a
   top-level `.update()` replaces each per-oid dict *wholesale*.

Since (1) leaves `mod_datetime` untouched, the object is classified "same" by
the sync and is never pushed, so (2)'s omission is never repaired. Then (3)
replaces the local values with the server's.

Measured, on `FDValve-0000866`:

| step | result |
|---|---|
| offline edit `m`: 0.46 → 999.0 | applied locally |
| `vger.set_parameters` sent? | **no** |
| `obj.mod_datetime` changed by the edit? | **no** |
| after reconnect + `get_parmz` | `m` is **0.46** — the edit is gone |

Two consequences follow from the wholesale per-oid replacement:
- an offline **edit** to an existing parameter is overwritten by the server's
  value;
- a parameter **added** offline (`on_parm_added`, also connectivity-gated) is
  dropped entirely, since it is absent from the server's per-oid dict.

Neither produces an error, a log entry, or any user-visible indication.

This is the parameter-cache analogue of the object-level silent discard
documented in `NOTES_ON_OFFLINE_AND_SYNC.md` §5.C, and it is arguably worse:
the object-level case at least leaves the local object diverged, whereas here
the local value is actively reverted to the server's. §3.5 of that note
raised the authoritative caches as a concern but did not establish this
specific loss path; it should be folded into the conflict-policy decision
(§3.3) and the reconciliation report (§3.4), and it is a case the check-out
model would close by construction for claimed objects.

**STATUS: NOT FIXED HERE — folded into the check-out work** (author's
decision, 2026-07-31). This is not to be patched locally in
`pangalaxian.py`; it is now a requirement of the offline model:
**offline parameter and data-element adds, modifications and deletions are
permitted only for checked-out ("locked") objects, and behave exactly as
regular attribute editing does.** Both are edited only through the
`pgxnobject` editor, so enforcement has one home. Written up as §4a of
`pangalactic.core/NOTES_ON_CHECKOUT_MODEL.md`, and attached to phases 2 and 3
of that note's plan; `NOTES_ON_OFFLINE_AND_SYNC.md` §3.5 updated to match.

With that permission rule in place, the loss path closes at the source: an
object that is not checked out is not editable offline, so no orphaned
offline parameter edits exist to be lost.

**Layer (a) below is now applied**: `pgxnobject.on_save`'s parameter-only
branch stamps `modifier`/`mod_datetime` and calls `orb.save()` before sending
`"parms set"` — always, not only while disconnected (author's decision).
Verified end to end: pre-fix the object is never classified as newer than the
server, so the offline edit is reverted to 0.46; post-fix it is pushed and
the edit survives. Layers (b) and (c) remain, and are recorded in §4a (2)/(3)
of the check-out note.

The three layers, increasing in cost:

**(a) Stamp `mod_datetime` on a parameter-only save — APPLIED.** The
smallest change, in `pgxnobject.on_save`'s early-return branch. This works
because `serialize()` already carries parameters with the object
(`serializers.py:383`, `d['parameters'] = serialize_parms(obj.oid)`) and
`deserialize()` applies them, so an object that enters the sync's
"older on server" set pushes its parameters *for free*. Stamping is what
makes it enter that set. Decided to stamp **always**, accepting the extra
sync churn while connected (where `vger.set_parameters` already handles the
change live) in exchange for the object's timestamp telling the truth about
whether it changed.

**(b) An offline parameter queue** — the real fix, and the exact analogue of
the offline *deletion* queue proposed in `NOTES_ON_OFFLINE_AND_SYNC.md` §3.2.
Record `{oid: {pid: value}}` changes made while disconnected, persist them in
the home directory alongside `trash`/`deleted`, and replay them as
`vger.set_parameters` during the sync handshake. **Ordering is the critical
constraint: the replay must happen before `get_parmz()`**, or the server's
cache will overwrite the very edits being replayed. Entries should clear only
on confirmed server acceptance, so an interrupted sync retries rather than
losing the work. `on_parm_added` / `on_parm_del` need the same treatment, or
parameters added offline stay lost.

**(c) ~~Make `on_vger_get_parmz_result` merge instead of replace~~ —
WITHDRAWN. Full replacement is correct and must stay.** (Author, 2026-07-31.)

I proposed replacing `parameterz.update(parmz_data)` with a per-oid
`setdefault(oid, {}).update(parms)` so that locally-added parameters would
not be dropped. That was wrong, for a reason grounded in production
experience: **merging was implemented once, and in highly active
collaborative use clients would drift out of sync; moving to full
replacement fixed it.** It is inefficient but sufficiently performant, and
since the server's copy is authoritative, replacement is what guarantees the
client ends up with a correct version.

The principle worth stating explicitly, because it governs the rest of this
work: **the wholesale replacement is a convergence mechanism, not a naive
overwrite.** Any local drift — a failed push, a race, a partially applied
update — is corrected on the next sync. A merge has no such property: a
divergent local entry survives every subsequent sync, with nothing that can
ever remove it. That is precisely the failure mode that was observed.

This also explains why finding #2 was a real defect and yet replacement was
never the bug. `get_parmz` is the **tail of the save chain** — `on_vger_get_parmz_result`'s own docstring notes it is "typically the last in
a chain of rpc callbacks", and `on_vger_save_result` calls it after the save
completes. So the correct sequence is *push, then pull, then replace*, and
replacement is safe exactly because the local changes have already landed on
the server by the time it runs. The loss in #2 happened because the push
never occurred at all (no `mod_datetime` stamp) — not because the pull
replaced too much.

**Therefore the rule for everything remaining: never weaken the replacement;
make sure the push happens first.** Layer (b) follows from this directly —
queued offline parameter changes must be replayed *before* `get_parmz`, in
exactly the way the offline deletion queue must be replayed before
`sync_project`/`sync_library_objects`. Same shape, same reason.

  One small, genuinely separate item survives from that proposal:
  `vger.get_parmz`'s `oids` branch returns
  `{oid: parameterz.get(oid) for oid in oids}`, which yields `None` for any
  oid the server does not know — and `parameterz.update({oid: None})` would
  write a `None` where every consumer expects a dict. Unreachable today,
  since the client always calls `get_parmz()` with no arguments, but worth a
  guard on the server side (skip unknown oids rather than emitting `None`).
  This is independent of merge-vs-replace.

Remaining sequencing: (c) is withdrawn; **(b)** belongs with the deletion
queue in check-out phase 3, since they share the queue-and-replay machinery
and the same push-before-pull ordering constraint. With (a) applied, (b)'s
scope narrows usefully: an offline parameter *edit* on an object the user
still holds now rides along with the object at sync, so the queue is needed
for the cases (a) does not reach — notably `on_parm_added` /
`on_parm_del`, which are separately connectivity-gated and do not go through
the object save path.

### 3. Both "data elements set" local handlers are dead code
`pangalaxian.py:3806-3841` (`on_des_set`, `on_des_set_qtsignal`)

Neither handler can currently fire:

- `on_des_set` is connected to the pydispatcher signal `'des set'`
  (line 445), and **nothing in any of the four repos sends that signal** —
  the only occurrences of the string are the `connect` call and two
  docstrings.
- `on_des_set_qtsignal` is connected to nothing at all: there is no
  `des_set` `pyqtSignal` declared on `Main` (see the declarations at
  207-214), and no `.connect(self.on_des_set_qtsignal)` anywhere.

The two are near-identical copies of the same `vger.set_data_elements` call.
Data elements do still reach the repository, but only by other routes — the
`new_acts` branch of `on_vger_save_result` (4148-4158) and
`vger.set_properties` via `on_act_mods_signal` — so this is dead code rather
than a functional gap. Worth deciding whether the intended local
"data elements were edited" path was lost in the pydispatcher/pyqtSignal
migration, or whether both handlers should simply be removed.

**STATUS: FIXED — both handlers removed** (author's decision).
The evidence pointed to removal rather than rewiring: `serialize()` carries
data elements with the object (`serializers.py:381`,
`d['data_elements'] = serialize_des(obj.oid)`), exactly as it does
parameters. So any local data-element change on an object that gets saved
already travels to the repository through `vger.save` — for example
`pgxnobject`'s data-element drop handler (`pgxnobject.py:610-628`) adds the
DE, stamps `modifier`/`mod_datetime`, calls `orb.save()`, and sends
`'modified object'`. A separate `vger.set_data_elements` push would be
redundant with that path.

Applied: `on_des_set` and `on_des_set_qtsignal` are gone, along with the
`dispatcher.connect(self.on_des_set, 'des set')` line, replaced by a comment
recording why they were dead and why they were redundant.
`on_vger_set_des_result` was kept and is still reached from
`on_vger_save_result` (confirmed: one live `addCallback` remains).

**Confirmed: nothing emits `'des set'` anywhere.** Verified with `grin` over
all of `/home/waterbug/clones` — which covers `cattens`, `datahub`,
`pangalactic.mbif`, `interface42`, `vger_docker` and `python-bootcamp` as
well as the four packages under review. The only occurrences are the
`connect` call and two docstrings in `pangalaxian.py` (plus this document).

Note the asymmetry this exposes with finding #2, which is worth thinking
about together: data-element changes ride along with the object because the
things that change them also stamp `mod_datetime` and save the object;
parameter-only changes do not, which is precisely why they are lost offline.

### 4. `on_mod_objects_signal` tests a stale `cname` from a previous loop
`pangalaxian.py:3652-3657`

```python
for obj in objs:                       # 3616: loop 1
    cname = obj.__class__.__name__
    ...
for obj in objs:                       # 3652: loop 2
    if cname == "Activity":            # <-- cname is loop 1's LAST value
        n = obj.sub_activity_sequence
```

`cname` is not recomputed in the second loop, so it holds the class name of
the *last* object in `objs` and is applied to every object in the batch. The
intent is plainly per-object (`obj.__class__.__name__ == "Activity"`).

**Latent today, but the failure mode is severe if it becomes reachable.** For
a heterogeneous batch whose last element is an `Activity`, the branch fires
for every object, and `obj.sub_activity_sequence` raises `AttributeError` on
any non-`Activity`. That loop sits **outside** the `try` block that begins at
3658, so the exception propagates and `vger.save` is never called — the
user's modified objects would silently fail to reach the repository.

All four current emitters send homogeneous batches, which is why this has not
bitten: `timeline.py:804` (Activities), `timeline.py:523` (Activities),
`rqtmanager.py:677` (Requirements), `wizards.py:1087` (all of one
`self.object_type`). One-line fix; worth taking before some future caller
sends a mixed batch.

**STATUS: FIXED.** The test is now `obj.__class__.__name__ == "Activity"`.
**Verified by execution** on a `[HardwareProduct, Activity]` batch (a true
`Activity` last, not a `Mission` — note that `orb.db.query(Activity)` returns
subclasses too, which made a first attempt at this test vacuous):

| | pre-fix | post-fix |
|---|---|---|
| `[HardwareProduct, Activity]` | `AttributeError: 'HardwareProduct' object has no attribute 'sub_activity_sequence'` — `vger.save()` never called | loop completes, `vger.save()` reached |

### 5. Two findings from earlier installments are still unfixed
Confirmed against current source:

- **`Version(f.read())` is still unguarded** (`pangalaxian.py:305`) — startup
  review finding #5. An empty or corrupt `VERSION` file in the home directory
  raises `InvalidVersion` and aborts startup, instead of degrading into the
  cleanup path that already exists a few lines below.
- **`Version(min_version)` is still unguarded** (`pangalaxian.py:900`) — sync
  review finding #3. The deliberate "no response from server" fallback at
  line 891 sets `min_version = ''`, and `Version('')` raises
  `InvalidVersion` — so the defence turns into a traceback in the login
  callback.

Both are the same shape and were recommended for a shared fix (a small helper
returning `None` on `InvalidVersion`, plus a guard that skips the comparison
when either side is unknown). That recommendation stands.

**STATUS: FIXED, as one shared helper.** A module-level `safe_version(txt)`
in `pangalaxian.py` returns `Version(txt.strip())` or `None` on
`InvalidVersion`. The `VERSION` file read falls back to the pre-existing
`Version('3.1')` sentinel, which is not in `compat_versions`, so a corrupt
file degrades into the cleanup path that already exists instead of aborting
startup. The `min_version` comparison is skipped (with a debug log line)
whenever either side is unparseable. **Verified by execution:**

| input | `safe_version()` |
|---|---|
| `'4.4.dev3'` | `4.4.dev3` |
| `'4.4.dev3\n'` (trailing newline) | `4.4.dev3` |
| `''` (server gave no response) | `None` |
| `'garbage'` (corrupt VERSION file) | `None` |
| `None` | `None` |

With `min_version = ''` the guard `this_v and min_v` is `False`, so the
comparison is skipped and no `InvalidVersion` is raised.

### 6. `gen_keys()` — private key handling (consolidated)
`pangalaxian.py:7959-8010`

**This is the single record for `gen_keys()`.** It previously appeared here
and, from the other direction, in `admin_tool_review.md` #4; that entry now
cross-references this one. See also `pangalactic.vger/NOTES_ON_TESTING.md`
§8.2, which generates vger's own key pair and follows the same shape.

#### What was wrong

```python
f = open(self.key_path, 'wb')
f.write(privkey.encode())
f.close()
os.chmod(self.key_path, 0o400)
```

- **The private key was created at the process umask and only `chmod`ed to
  `0o400` afterwards**, so there was a window in which it sat on disk
  world-readable. Not theoretical — **measured at `0o664`.**
- **If `write()` raised, the `chmod` never ran at all**, leaving a partial
  private key permanently at default permissions.
- **No `with`** — on an exception the handle leaked and a truncated key file
  was left behind. The same unguarded open/write/close was repeated for
  `public.key`.

Two smaller things in the same function: `PrivateKey.generate()` ran *before*
the "key already exists" check, so a key pair was generated and discarded on
every aborted call; and `if response == QMessageBox.Ok: return` was
effectively unconditional, since `Ok` is the dialog's only button and Qt
returns it for Esc and window-close too — it read as a choice that was never
offered.

*On the `with` point (author, 2026-08-02): this code predates the `with`
statement, which arrived in Python 2.5. The bare open/write/close is vintage,
not oversight — worth knowing before reading it as carelessness. The retrofit
is still the right move.*

#### What was applied (2026-08-02)

**STATUS: FIXED.** The existence check moved above `PrivateKey.generate()`;
the unconditional `if response ==` wrapper is gone; both writes use `with`;
and the private key is created already-restricted:

```python
fd = os.open(self.key_path,
             os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'wb') as f:
    f.write(privkey.encode())
os.chmod(self.key_path, 0o400)
```

`O_EXCL` makes the create fail rather than overwrite if a key appeared between
the check and the open — belt and braces, since the check above already
returns in that case.

**Deviation from the originally proposed fix, and why.** The proposal created
the file `0o400` directly. As applied it creates `0o600` and `chmod`s to
`0o400` after the write. Both close the exposure window identically — that is
the entire security property at stake — but `0o600` does not depend on being
able to write to a file created read-only, which is the part that differs on
Windows, and this app ships a Windows build. The original entry named this as
the fallback; it is preferable as the default precisely because the platform
question then never has to be answered.

**Verified by execution**, with the real `nacl`/`cryptosign` calls rather than
a model of them:

| | old | new |
|---|---|---|
| private key perms *during* write | `0o664` — **world-readable** | `0o600` |
| private key perms after | `0o400` | `0o400` |
| perms left by a failed write | umask default | `0o600` |
| `O_EXCL` refuses to clobber an existing key | n/a | yes |

#### The coupling with `admin_tool_review.md` #4 — do not break this

`gen_keys()` writes `public.key` with **no trailing newline**, and that must
stay true. vger stores the string verbatim in `principals.db` and the
authenticator matches it against the bare hex key from the WAMP handshake, so
a newline here would silently prevent login for every app-generated key — the
person is added, the administrator is told it succeeded, and login simply
never works.

The two findings are the same failure arriving by different routes: #4 covers
a key that acquired a newline *in transit* (editor, email, copy-paste) and is
fixed by `strip()` + validation on the receiving side; this one covers not
introducing one at the source. Confirmed still 64 hex characters with no
trailing newline after the rewrite.

Marked at the site in the source, because it is the kind of thing a later
tidy-up ("shouldn't a text file end in a newline?") would quietly reintroduce.

---

## Verified correct / no findings

- **Full sweep of `exec_()` call sites in `pangalaxian.py`** — no instance of
  the `QMessageBox` truthiness bug found in `pgxnobject.py` (#2a). Every
  `QMessageBox` result is either compared against a specific `StandardButton`
  (5941 `== QMessageBox.Yes`, 7345 `== QMessageBox.Ok`) or discarded for an
  Ok-only notice (2006, 2014, 7134, 7162). Every truthiness test
  (`if dlg.exec_():` at 4845, 6735, 7197, 7208) is on a genuine `QDialog`
  subclass, where `Accepted`/`Rejected` are 1/0; the rest compare
  `== QDialog.Accepted` explicitly.
- **`prepare_for_offline_work`** (1987-2023) — connectivity and
  project-selected preconditions are both checked with clear user-facing
  notices before the dialog is built, and the result is correctly gated on
  `== QDialog.Accepted`. No findings.
- **`on_vger_save_result`** (4053-4170) — the three defects recorded in
  `NOTES_ON_OFFLINE_AND_SYNC.md` §3.4 (assignment instead of accumulation,
  debug-only logging, `showMessage` reachable only when nothing happened) are
  **fixed**; `msg_parts` accumulates, refusals are logged at info with the
  object ids, and rejections are recorded in `state['last_sync_report']` and
  surfaced in the status bar via `QTimer.singleShot(0, ...)`. The deferral
  comment explaining the `QBackingStore::endPaint()` hazard is a useful piece
  of institutional memory.
- **`on_remote_parm_added` / `on_remote_parm_del` / `on_remote_de_added` /
  `on_remote_de_del`** (3762-3926) — all four correctly check local presence
  before acting and are idempotent with respect to repeated broadcasts.

## Observation: the rpc callback chain, and why restructuring it is delicate

Not a finding, and not a proposal — recorded because the subject came up and
the constraints are easy to lose. `pangalaxian.py` contains **116**
`addCallback`/`addErrback` calls, and the login/sync path builds a long
ladder on a single deferred, alternating callback and errback
(~1071 onward: `subscribe_to_mbus_channels` → `sync_user_created_objs_to_repo`
→ `on_user_objs_sync_result` → `get_checkouts` → …). There are real
efficiencies available in there, but three properties of the current shape
are load-bearing and any restructuring has to preserve them:

1. **GUI work is deliberately deferred to the end of the chain.**
   `on_vger_get_parmz_result`'s docstring states it outright: "Since this rpc
   is typically the last in a chain of rpc callbacks, it has responsibility
   for doing all needed GUI updates (which would cause various problems and
   possibly crashes if attempted while rpc operations are being processed)."
   The `QTimer.singleShot(0, ...)` in `on_vger_save_result` and its
   `QBackingStore::endPaint()` comment are the same constraint surfacing
   again. This is not incidental sequencing — it is the mechanism that keeps
   Qt painting out of the middle of a twisted callback chain.

2. **`state` flags are the chain's actual communication channel.** At least
   six keys are written by one callback and read by a later one:
   `'tree needs refresh'`, `'diagram needs refresh'`, `'lib updates needed'`,
   `'upd_obj_in_trees_needed'`, `'modal views need update'`, and
   `'updates_needed_for_remote_obj_deletion'` — 43 references between them in
   this file alone. Any reordering or parallelising changes which flags are
   set when a later link reads them, and the coupling is invisible from the
   call sites.

3. **Push-before-pull is an ordering guarantee, not an accident.**
   `get_parmz` sitting at the tail is what makes the wholesale `parameterz`
   replacement safe (see #2 above). Anything that moves the pull earlier, or
   runs it concurrently with the save, breaks that guarantee.

A separate weakness, already noted in `pangalaxian_sync_review.md`, is worth
repeating here since it bears on any rework: each
`addErrback(self.on_failure)` catches only the failure of the link
immediately preceding it, and `on_failure` merely logs a traceback — so a
failure partway along leaves the sequence half-completed, with no
user-visible indication and no state rollback. That is arguably a stronger
argument for restructuring than efficiency is; it is also the reason
restructuring is risky, since the half-completed states are currently
invisible and therefore uncharacterised.

If this is ever taken on, the cheap first step is probably observability
rather than restructuring: make the chain's completion (and non-completion)
explicit and logged, so the failure modes are known before the shape changes.

## Status summary

**Fixed** (2026-07-31), each verified by execution and annotated inline:

- **#1** `on_remote_properties_set` — unknown oids skipped before
  `set_prop_val`; commit moved out of the loop.
- **#4** stale `cname` — now tests each object's own class.
- **#5** both unguarded `Version()` calls — one shared `safe_version()`
  helper.

- **#3** dead `des set` handlers — both removed, along with the
  `dispatcher.connect` line; `on_vger_set_des_result` kept.

**Reassigned to the offline/check-out work:**

- **#2** offline parameter loss — settled in principle: offline parameter and
  data-element editing is confined to checked-out objects and behaves as
  attribute editing does. See `NOTES_ON_CHECKOUT_MODEL.md` §4a; the
  mechanics land in phases 2 and 3 of that plan. One sub-decision remains —
  whether a parameter-only save stamps `mod_datetime` always or only while
  disconnected.

**Open, awaiting your decision:**

- *(none — #6 was applied 2026-08-02)*

## Original suggested fix order (all now triaged)

1. **#1 `on_remote_properties_set`** — a `None` guard is one line, and this
   fires in ordinary multi-project use on the public channel. Decide at the
   same time whether unknown oids should be skipped before `set_prop_val`, to
   stop foreign entries accumulating in `parameterz`.
2. **#5 the two `Version()` guards** — small, already specified, and one of
   them can abort startup.
3. **#4 stale `cname`** — one line, removes a latent save-blocking crash.
4. **#2 offline parameter loss** — the largest of these, and a design
   question rather than a patch: it needs the conflict-policy and
   reconciliation decisions from `NOTES_ON_OFFLINE_AND_SYNC.md` §3.3/§3.4,
   and is a natural fit for check-out phase 2/3.
5. **#6 `gen_keys()`** — small hardening of private-key handling. **DONE
   (2026-08-02);** this section is now the consolidated record for
   `gen_keys()`, including the coupling with `admin_tool_review.md` #4.
6. **#3 dead `des set` handlers** — decide remove-vs-rewire.
