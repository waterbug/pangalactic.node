# pangalactic.node review — `pangalaxian.py`, sync machinery (2026-07-26)

Third installment of the `pangalactic.node` review. `pangalaxian.py` is
~7300 lines, so it is being reviewed in chunks rather than linearly. This
chunk covers the **login/sync chain** (lines ~826-1734): `sync_with_services`,
`on_rpc_get_user_roles_result`, the six `sync_*` methods and their result
handlers, and the `synced_oids` model — the thread deferred from both the
`pangalactic.core` and `pgxnobject.py` passes.

Already covered in earlier installments and not repeated here: `run()` and
`Main.__init__` (startup review), `on_freeze_signal`/`on_thaw_signal`/
`on_thaw_result`/`on_remote_freeze_or_thaw` (pgxnobject review).

Chunks still to do: local object-lifecycle handlers, the remote
parameter/data-element handlers (~3504-3690), mode/tree/dashboard
machinery, and the remaining UI actions.

---

## Findings (most severe first)

### 1. `synced_oids` holds only the user's *own* objects, so offline clients get full permissions on everything they did **not** create
`pangalactic/node/pangalaxian.py:1431-1433` together with
`pangalactic.core/pangalactic/core/access.py:157, 173-180`

`synced_oids` is assigned in exactly one place in the whole codebase:
```python
if user_objs_sync:
    state['synced_oids'] = [o.oid for o in
                            self.local_user.created_objects]
```
That is, it is populated **only** from the local user's `created_objects`,
during the `sync_user_created_objs_to_repo` phase. Objects the user did not
create — library items, other users' products, project objects arriving via
`sync_project` / `sync_library_objects` / `force_sync_managed_objects` — are
never added to it. (The only other references remove entries on deletion, at
3897-3898 and 5680-5681.)

`access.py` then does:
```python
object_not_synced = obj.oid not in state.get('synced_oids', [])
...
if client and not connected and object_not_synced:
    # client user always has full perms when not connected AND the object
    # has not been synced to the repo (which implies that the user created
    # the object)
    perms = ['view', 'modify', 'add docs', 'add models', 'delete', ...]
```
The comment's inference — *not synced ⟹ the user created it* — is the exact
inverse of what the population logic produces. Because `synced_oids`
contains **only** user-created objects, "absent from `synced_oids`" in
practice means "the user did **not** create it".

**Verified by execution.** Using the standard test fixtures, with
`synced_oids` populated exactly as line 1432 does it, and local user
`zaphod`:

```
objects zaphod cannot modify while online: 427
test object     : FDValve-0000866   creator = admin
in synced_oids? : False
ONLINE  -> ['add docs', 'add models', 'view']
OFFLINE -> ['add docs', 'add models', 'delete', 'modify',
            'offline & object not synced', 'view']
```
Online, `zaphod` correctly has no `modify` and no `delete` on an object
created by `admin`. Offline, he gets both — plus the
`'offline & object not synced'` marker confirming it is precisely the
`access.py:173-180` branch firing. 427 objects in the test data are in this
category.

**Scope — and why this is not a repository breach.** The repository still
re-authorizes independently: `vger.save()` checks `get_perms(obj_in_repo,
user)` server-side and `vger.delete()` checks creator/role/`get_perms`
before deleting. So offline over-permission does not by itself let a user
change the authoritative copy — consistent with the layered model used
throughout PGEF. What it does produce is a **client-side divergence**: while
offline the user can edit and delete objects they have no rights to, the
local database accepts those changes, and only on reconnect does the server
refuse to persist them. Deletions are the sharper edge, since the local
object is already gone and the oid has been recorded in the client's
`deleted` cache.

**Note on an earlier exchange.** During the `pangalactic.core` pass this
branch was raised as "an unchecked assumption that not-synced implies
user-created", and the author explained it as a structural guarantee — that
a client's local db contains only what it created or received via a
completed sync, so an absent oid can only be locally created. That reasoning
is sound *given* a `synced_oids` that records everything received from the
repository; the defect is that the one line which populates it records only
`created_objects` instead. The fix is therefore most likely in
`pangalaxian.py:1432` (record every oid confirmed present on the server, not
just the user's own), rather than in `access.py`.

**Reconnect behaviour for offline deletes: traced, see finding #2.**

### 2. Offline deletions are never queued, so they are silently undone on the next sync
`pangalactic/node/pangalaxian.py:4435-4518` (`del_object`), with
`pangalactic.core/pangalactic/core/uberorb.py:2435+` (`orb.delete`)

Traced end to end. `del_object` deletes the object from the local database
and then:
```python
if state.get('connected'):
    orb.log.info('  - calling "vger.delete"')
    rpc = self.mbus.session.call('vger.delete', [oid])
```
The `vger.delete` rpc is sent **only while connected**, and nothing is
recorded for later transmission when it is not. There is no
pending-deletion queue anywhere:

- `orb.delete()` does record `trash[obj.oid] = serialize(...)`, but only for
  `Product` instances whose creator is the local user, and its own comment
  marks it as a TODO for an undo feature. `trash` is never read to push
  deletions — its only two read sites (1548, 1672) use it in the *opposite*
  direction, deciding whether to drop local objects the **server** doesn't
  know about.
- `state['deleted_oids']` (1412-1414) is filled from the **server's**
  deleted cache, not from client-side pending deletions.

On reconnect the repository is therefore never told, and both sync paths
actively restore the object, because each treats "the client didn't report
this oid" as "the client needs it":

- `vger.sync_project`:
  `newer_objs = [obj for obj in server_objs if obj.oid not in dts_by_oid]`
  — every server object absent from the client's report is returned.
- `vger.sync_library_objects`: selects on `earlier(client_dt, server_dt)`,
  and `earlier()` documents and implements `None` as earlier than anything
  — **verified**: `earlier(None, <server dt>) == True`. An object the client
  no longer has has `client_dt is None`, so it qualifies.

Two distinct consequences:

- **Unauthorized offline deletes** (the ones finding #1 makes possible) are
  self-healing: the object reappears at the next project or library sync
  and the repository was never at risk. The user experience is still poor —
  the object vanishes, then silently returns.
- **Authorized offline deletes are undone too.** A user deleting *their
  own* object while offline gets exactly the same treatment: the deletion
  is never sent, and the object is restored on the next sync. A legitimate
  user action is quietly reverted with no error and no explanation. This is
  the more serious half, since it is ordinary intended usage rather than a
  consequence of finding #1.

Fixing this means recording deletions that occur while offline (an oid
queue persisted alongside `trash`/`deleted`) and replaying them as
`vger.delete` calls during the sync handshake — where the server will
authorize each one normally, refusing the ones the user had no right to
make. That also gives finding #1's unauthorized deletes a clean, explicit
rejection path instead of a silent reappearance.

### 3. `on_rpc_get_user_roles_result` raises `InvalidVersion` on the very "no response" case it defends against
`pangalactic/node/pangalaxian.py:889-899`
```python
# data should be a list with 6 elements, but if no response from server
# data may be None, so fall back to a list of 6 empty elements ...
data = data or ['', '', '', '', '', '']
szd_user, szd_orgs, szd_people, szd_ras, bad_oids, min_version = data
...
if (Version(this_version) < Version(min_version)
    and state.get('connected')):
```
The fallback sets `min_version = ''`, and `Version('')` raises
`packaging.version.InvalidVersion` — **verified**:
`Version('4.4.dev2') < Version('')` → `InvalidVersion: Invalid version: ''`.
The exception is uncaught, so the deliberate "no response from server"
defence at line 889 turns into a traceback in the login callback rather than
a graceful degradation.

This is the same shape as the unguarded `Version(f.read())` on the home
`VERSION` file (startup review, finding #5) — both take a version string
from an untrusted/absent source and hand it straight to `Version()`. Worth
fixing together, e.g. a small helper that returns `None` on
`InvalidVersion` and a guard that skips the comparison when either side is
unknown.

### 4. The "local user was 'me'" migration is dead code — offline-created objects keep the placeholder creator
`pangalactic/node/pangalaxian.py:945-958`
```python
state['local_user_oid'] = str(self.local_user.oid)   # 945: overwrites
if str(state.get('local_user_oid')) == 'me':         # 946: ...then tests it
    # current local user is 'me' -- replace ...
    state['local_user_oid'] = str(self.local_user.oid)
    me = orb.get('me')
    if me and me.created_objects:
        for obj in me.created_objects:
            obj.creator = self.local_user
            obj.modifier = self.local_user
            orb.save([obj])
            dispatcher.send('modified object', obj=obj)
```
Line 945 sets `state['local_user_oid']` to the real user's oid, and line 946
then tests that same key for `'me'`. It can only be true if the
server-returned `Person` literally has `oid == 'me'`, which it never does —
`self.local_user` comes from `orb.select('Person', id=state['userid'])` at
line 942. The migration block is unreachable, and the intent is clearly to
test the *previous* value before overwriting it.

The placeholder is real: `get_or_create_local_user` (563-584) creates a
`Person` with `oid='me'`, `id='me'`, `name='Me'` and sets
`state['local_user_oid'] = 'me'` when no local user is known — and it runs
at startup (`Main.__init__`, line 342) before any login. So objects created
before the first successful login are attributed to the `'me'` Person and,
because this block never runs, **stay** attributed to it.

Consequences: `access.py:189` grants creator-based full permissions via
`obj.creator is user`, which stays False for these objects; and
`vger.save()`'s "objects created by the user" fast path
(`so.get('creator') == user_oid`) never matches them. The user can lose the
creator relationship to their own pre-login work. Fix: capture the previous
value before overwriting, e.g.
```python
was_me = (str(state.get('local_user_oid')) == 'me')
state['local_user_oid'] = str(self.local_user.oid)
if was_me:
    ...
```

---

## Observations (no action proposed)

- `sync_with_services` (840-861) retries `rpc_get_roles` once after a bare
  `time.sleep(1)`. `time.sleep` blocks the Qt/twisted event loop for a full
  second — harmless at login, but it is the kind of call that causes UI
  freezes if the pattern spreads.
- The login chain (1033-1048) builds a long `addCallback`/`addErrback`
  ladder on a single deferred, alternating callback and errback. Each
  `addErrback(self.on_failure)` only catches failures from the immediately
  preceding link, and `on_failure` merely logs the traceback — so a failure
  partway through leaves the sync sequence half-completed with no
  user-visible indication and no state rollback. Restructuring is a larger
  change than this review should propose, but it is worth knowing that a
  mid-chain failure is silent.
