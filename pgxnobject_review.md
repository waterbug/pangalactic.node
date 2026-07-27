# pangalactic.node review — `pgxnobject.py` (the object editor), 2026-07-25

Second installment of the `pangalactic.node` review. `pgxnobject.py` (2630
lines) is the object editor, and is the module three threads deferred from
earlier passes pointed at. All three are resolved below, plus new findings.

Context taken as given (author): objects are only editable in `pgxnobject`
when the user is connected — `state['connected'] == True` — which is
enforced through `get_perms()`; and the "Thaw" toolbar button only appears
for a global admin. Both were verified rather than assumed (see
"Confirmed by verification").

---

## Findings (most severe first)

### 1. Validation failure does **not** abort the save if the user dismisses the dialog with Esc or the window close button
`pangalactic/node/pgxnobject.py:2401-2406`
```python
if list(msg_dict.keys()):   # one or more field values are invalid
    orb.log.debug('  validation errors: {}'.format(str(msg_dict)))
    dlg = ValidationDialog(msg_dict)
    if dlg.exec_():
        return
NOW = dtstamp()
for name, val in fields_dict.items():
    setattr(self.obj, name, val)       # <-- invalid values written
```
The guard makes aborting conditional on *how the dialog was dismissed*.
`ValidationDialog` (`dialogs.py:330-353`) has only an **Ok** button wired to
`accept`, but `QDialog` still rejects on **Esc** and on the window-manager
**close (X)** — both return `QDialog.Rejected` (0), which is falsy, so the
`return` is skipped and execution proceeds to write the invalid field
values and `orb.save([self.obj])`.

**Verified by execution** (headless Qt, driving the real dialog):

| dismissal | `exec_()` | guard fires? | outcome |
|---|---|---|---|
| clicks **Ok** | `1` | yes | save aborted (correct) |
| presses **Esc** | `0` | no | **falls through → saves invalid data** |
| closes window (**X**) | `0` | no | **falls through → saves invalid data** |

Pressing Esc to dismiss an error popup is a common reflex, so this is
readily reachable in normal use, and it defeats validation silently — the
user sees an error dialog, dismisses it, and the bad value is saved anyway.
Note the values written here are the *field* values (`id`, `name`, etc.),
so this can persist an `id` that `validate_all` just rejected — e.g. one
containing spaces or duplicating an existing `id`/`version` pair.

Fix: validation failure should abort unconditionally —
```python
if list(msg_dict.keys()):
    dlg = ValidationDialog(msg_dict)
    dlg.exec_()
    return
```

### 2. `thaw()` has no connectivity guard, so a dropped connection leaves the client and server permanently disagreeing
`pangalactic/node/pgxnobject.py:1765-1810`

`freeze()` explicitly guards this case (lines 1580-1582):
```python
if not state.get('connected'):
    orb.log.debug('  not connected -- cannot freeze.')
    return
```
`thaw()` has no equivalent check. Its only gate is the *visibility* of
`thaw_action`, which `init_toolbar` (1360-1363) decides once, at dialog
construction time, from `obj.frozen and state.get('connected') and
is_global_admin(...)`.

Sequence when the connection drops while the editor is open:
1. `thaw()` sets `self.obj.frozen = False` locally (1808) — optimistically,
   before any server round trip.
2. `dispatcher.send(signal="thaw", oids=[...])`.
3. `pangalaxian.on_thaw_signal` (3168-3169) begins
   `if state.get('connected') and oids:` — now False, so it **silently does
   nothing**. The RPC is never sent.
4. Nothing rolls back step 1, and no message reaches the user.

The divergence is then self-perpetuating: `thaw()` does **not** update
`mod_datetime` (contrast `on_save`, which sets it at 2458). Since
`vger.sync_objects` classifies an object whose client and server
`mod_datetime` are equal as "same" and does not return it for update, the
locally-thawed/server-frozen split is invisible to sync and never
reconciled.

The normal connected path is sound: the server publishes the result and
`pangalaxian.on_remote_freeze_or_thaw` (1738-1762) applies the
authoritative `frozen`, `mod_datetime`, and `modifier`, then commits. The
gap is only when that round trip never happens.

**Scope, deliberately narrow.** This is *not* an authorization hole: only a
global admin ever sees the button, and `vger.thaw` re-checks
`is_global_admin` server-side regardless. Because a global admin also
retains `modify` on a frozen Product server-side, subsequent edits would
still be accepted — so the damage is CM bookkeeping (a thaw that the
server never recorded, and a client that shows the product as editable
when the repository still has it frozen), not privilege escalation.

Two contributing weaknesses worth fixing together:
- Mirror `freeze()`'s `state.get('connected')` guard in `thaw()`.
- `on_thaw_signal` attaches the generic `self.on_result` callback
  (`pangalaxian.py:3871-3886`), which **discards the RPC's return value**
  and unconditionally reports `'synced.'`. `vger.thaw` returns
  `(thawed, failed)` and returns `([], oids)` on refusal, so even an
  explicit server-side rejection is currently invisible to the user. A
  thaw-specific callback that reconciles against `failed` would close both
  this and any future refusal path.

**STATUS: FIXED (both parts).**
- `pgxnobject.thaw()` now returns early when `state['connected']` is falsy,
  mirroring `freeze()`. Verified by driving `thaw()` directly: pre-fix, a
  dropped connection left `obj.frozen=False` locally with the rpc never
  sent (divergence); post-fix the thaw is blocked and `obj.frozen` stays
  `True`, while the connected path is unchanged.
- `on_thaw_signal` now uses a new `Main.on_thaw_result` callback
  (`pangalaxian.py`) instead of the generic `on_result`. It reverts the
  optimistic local `frozen = False` for every oid in `failed`, commits,
  emits `remote_frozen` so an open editor re-reads the object and fixes its
  toolbar, and reports real counts in the status bar.

  Note on the deliberate asymmetry: the callback intentionally does **not**
  apply the `thawed` list. The repository publishes a `thawed` message on
  the public channel which this client also receives, and
  `on_pubsub_msg` already routes it to `on_remote_freeze_or_thaw`
  (`pangalaxian.py:1983`); applying it in the callback as well would commit
  the same values twice and raise a second "thawed" notice. Verified
  against all three payload shapes (refusal, acceptance, malformed).

### 2a. The CM thaw-confirmation dialog ignores "Cancel" — found by sweeping for the pattern in #1
`pangalactic/node/pgxnobject.py:1807` (in `thaw()`) — **FIXED**

Sweeping the file for the "gated on how the dialog was dismissed" shape
from finding #1 turned up one genuine bug, and it is worse than #1 because
it ignores a *deliberate* refusal rather than an incidental one.

When a frozen Product is used as a component in one or more frozen
assemblies, `thaw()` raises a CM warning — "thawing this Product may
violate CM and should only be used for essential corrections" — listing
those assemblies, with **Ok | Cancel**. The guard was:
```python
if notice.exec_():
    thaw_permitted = True
```
`QMessageBox.exec_()` does **not** return `QDialog`'s 0/1; it returns a
`StandardButton` enum value, and every button is non-zero:
`QMessageBox.Ok == 1024`, `QMessageBox.Cancel == 4194304`. Both are truthy,
so the guard fired no matter which button was pressed.

**Verified end-to-end** by driving `thaw()` on a frozen component of a
frozen assembly:

| user action | pre-fix | post-fix |
|---|---|---|
| confirms with **Ok** | thawed | thawed |
| clicks **Cancel** | **thawed anyway** | not thawed |
| presses **Esc** | **thawed anyway** | not thawed |

The user was shown an explicit CM warning, clicked Cancel, and the Product
was thawed regardless. Fixed by comparing to the specific button:
`if notice.exec_() == QMessageBox.Ok:` — matching the already-correct
pattern at line 2253 (`response == QMessageBox.Yes`).

**The general rule** (worth applying beyond this file): `if dlg.exec_():`
is correct for `QDialog` subclasses, where `exec_()` returns
`Accepted`(1)/`Rejected`(0). It is **never** correct for `QMessageBox`,
whose result must be compared against a specific `StandardButton`.

### 3. `on_clone()` dereferences `new_obj` immediately after defaulting it to `None`
`pangalactic/node/pgxnobject.py:1919-1923`
```python
dlg = CloningDialog(self.obj, parent=self)
if dlg.exec_():
    new_obj = getattr(dlg, 'new_obj', None)
    orb.log.debug(f'    got clone [a]: "{new_obj.id}"')
```
The `getattr(..., None)` default explicitly anticipates that
`CloningDialog` may not have set `new_obj`, and the very next line
dereferences `new_obj.id` unguarded — `AttributeError` if that case ever
occurs. The two branches below (1931, 1937) both correctly test
`if new_obj`, so only the debug-logging line is exposed. Cheap to fix by
folding the log line inside a `if new_obj:` check.

### 4. `frozen()` is an empty stub wired to a clickable toolbar action
`pangalactic/node/pgxnobject.py:1762-1763`
```python
def frozen(self):
    pass
```
`init_toolbar` (1315-1318) creates a "Frozen" action with this as its slot
and a tooltip of "This object is frozen". It is evidently intended as a
status indicator rather than a command, but it renders as an ordinary
enabled toolbar button that does nothing when clicked. Calling
`self.frozen_action.setEnabled(False)` when it is shown would make the
intent visible in the UI. (Cosmetic; no functional impact.)

---

## Deferred threads — resolved

- **`clone()`'s "copy an existing object" mode** (from the `pangalactic.core`
  pass, where the author corrected an initial mis-ranking): `on_clone`
  (1908-1930) is the documented consumer, and it confirms the correction.
  It calls `clone(self.obj, id='new-id', version='1', version_sequence=1)`
  for black-box products and `clone(self.obj, id='new-id')` otherwise —
  it **never passes `oid`, `name`, or `description`**. So `clone()`
  overwriting those three in mode 2 is unreachable from this call site, as
  the author stated. No finding.
- **`validation.validate_all()`'s `ids` kwarg** (from the same pass): the
  call site here (2398-2400) passes `required=`, `idvs=`, and `html=True`
  — **not `ids`**. Since this is the only caller, the parameter that
  `validation.py:355` unconditionally overwrites is genuinely unused by
  anyone, and can simply be dropped from the signature. Closes that item.
- **The CM / frozen-object model**: `pgxnobject.py` is confirmed to be the
  UI half the author described. The **Edit button is not created at all**
  when the object is frozen (1231-1234 for the embedded case, 1262-1267 for
  the external dialog), independent of `perms` — so even a global admin,
  who does retain `modify` on a frozen Product at the `access.py` layer,
  cannot edit one through the editor. `thaw` is exposed only to global
  admins (1360-1363). This matches the described design exactly; the only
  defect found in it is #2 above.

## Full sweep of `exec_()` call sites in `pgxnobject.py`

Every site classified; all dialog classes checked for whether they are
`QDialog` subclasses (0/1) or `QMessageBox` (button enum).

| line | dialog | type | verdict |
|---|---|---|---|
| 687 | `ObjectSelectionDialog` | QDialog | OK — reject means "don't change the value" |
| 1597 | `FreezingDialog` | QDialog (Ok/Cancel) | OK |
| 1623 | `CannotFreezeDialog` | QDialog (Ok only) | OK — body is only a debug log |
| 1628 | `FreezingDialog` | QDialog | OK |
| 1699 | `QMessageBox` Information (Ok only) | QMessageBox | **OK — see correction below** |
| 1741 | `QMessageBox` Information (Ok only) | QMessageBox | **OK — see correction below** |
| 1807 | `QMessageBox` Warning (Ok\|Cancel) | QMessageBox | **BUG — finding #2a, fixed** |
| 1933 | `CloningDialog` | QDialog | OK |
| 2253 | `QMessageBox` Question (Yes/No) | QMessageBox | OK — correctly compares `== QMessageBox.Yes` |
| 2417 | `ValidationDialog` | QDialog | was finding #1 — fixed |
| 2560 | `ObjectSelectionDialog` | QDialog | OK |

**Correction to an earlier claim in this review.** While flagging finding
#2's fix I stated that `on_remote_frozen` (1699) and `on_remote_thawed`
(1741) had the same defect — that pressing Esc on those "Frozen"/"Thawed"
notices would skip the toolbar and Edit-button updates. **That was wrong,
and testing disproved it.** For a `QMessageBox` with a *single* button, Qt
automatically makes that button the escape button, so Esc *and* the window
close (X) both return `QMessageBox.Ok` (1024):

| dismissal of an Ok-only QMessageBox | `exec_()` | guard fires? |
|---|---|---|
| clicks Ok | 1024 | yes |
| presses Esc | 1024 | yes |
| closes window (X) | 1024 | yes |

So those two sites are safe as written. `ValidationDialog` (finding #1)
behaved differently only because it is a `QDialog` subclass, where Esc and
window-close invoke `reject()` and yield 0. The distinction that matters is
the *dialog base class*, not the button set.

## Confirmed by verification

- **"Objects are only editable when connected"** — verified directly
  against `get_perms()` with a synced object: `connected=True` yields
  `['add docs', 'add models', 'delete', 'modify', 'view']`;
  `connected=False` yields `['add docs', 'add models', 'view']` — no
  `modify`, so the Edit button (which requires `'modify' in perms`) is not
  created. The `state['connected']` convention is used consistently.
- **"Thaw appears only for a global admin"** — `init_toolbar:1360-1363`
  requires `obj.frozen and state.get('connected') and
  is_global_admin(...)`; `thaw_action` is otherwise `setVisible(False)`
  (1342).
- `on_save` correctly stamps `modifier`/`mod_datetime` (2453-2458) and
  `creator`/`create_datetime` for new objects, and regenerates
  `HardwareProduct` ids via `orb.gen_product_id` (2465-2468).

## Suggested fix order

1. **#1 validation bypass** — three-line change, and it is the only finding
   here that silently persists bad data during ordinary use.
2. **#2 `thaw()`** — add the `state.get('connected')` guard to match
   `freeze()`, and give the thaw RPC a callback that reconciles against the
   server's `(thawed, failed)` result instead of the generic `on_result`.
3. **#3 / #4** — small robustness and UI-clarity cleanups.
