# SA-8: BLE presence sensing from the Kit

## Status: 🔴 Dead at Phase 0 — no stably-identifiable personal device found in this household's
real BLE environment

Third item of Wave 3, following SA-6 (in progress) and SA-9 (stopped at Phase 0). Hardware-gated
by design — the task doc's own framing explicitly welcomes a "dead" outcome here as a legitimate
result, not a failure to force through.

## Phase 0 — feasibility (real hardware, real scans, not a datasheet)

Investigated directly against the household's actual production hardware
(`alfr3d@192.168.2.200`), the same box SA-6's Phase 0 used:

- **Bluetooth adapter confirmed BLE-capable.** `hciconfig hci0 features` shows `<LE support>`
  and `<LE and BR/EDR>`; `btmgmt info` confirms `current settings: powered ssp br/edr le
  secure-conn`. This is a real USB adapter (`hci0`, `50:84:92:86:27:38`), not a hypothetical —
  the hardware gate the task doc calls "not guaranteed" passes cleanly.
- **Ran two real, independent ~30-second passive scans** (`bluetoothctl scan on`, then
  `bluetoothctl devices` to read back what was found), a few minutes apart, to test the actual
  MAC-randomisation question empirically rather than assume an answer either way:
  - **29-30 distinct BLE devices detected per scan**, comfortably confirming the adapter/BlueZ
    stack works for real passive discovery in this environment.
  - **Only fixed smart-home/IoT devices resolved to a stable, human-readable name and MAC across
    both scans**: `Govee_H6199_276F` (a Govee smart light/sensor), `N00ZG`, three TVs (`[TV]
    Samsung Q60AA 65 TV`, `[TV] Moonrise TV`, `65" Crystal UHD`), `Furbo3-S3` (a pet camera),
    `Venus_EC64C928886E`, `JBL Go 3` (a Bluetooth speaker). All identical MAC + name in both
    scans.
  - **Every other device (the large majority — ~20 of ~29 per scan) showed only a MAC-derived
    placeholder name** (BlueZ's fallback when it has no real name, e.g. `2B-CE-28-93-40-2B`),
    and a genuinely different *set* of these anonymous MACs appeared in the second scan than the
    first — new ones appearing, others not recurring — consistent with active BLE address
    rotation defeating identification, not a fixed population of nearby devices.
  - `bluetoothctl info <mac>` on several anonymous entries showed no `Name` and `Paired: no` —
    nothing about them is resolvable without a prior pairing relationship this household has no
    reason to have with a stranger's or even its own members' phones for this purpose.
- **The one recurring anonymous MAC** (`A0:36:BC:8D:89:5C`) broadcasts structured
  `ServiceData` under real Bluetooth SIG UUIDs (`0000fef3-...`, `0000fcf1-...`) whose payload
  bytes changed between observations even though the outer MAC didn't rotate in the ~1-3 minute
  total window tested — the signature of a privacy-preserving proximity/beacon protocol (e.g.
  Google/Apple cross-device-finding-style advertising) that rotates on a slower cadence than
  per-scan random addressing, not a genuinely stable long-term identifier. Not tested over a
  longer window (hours) to see if this specific address eventually rotates too — a reasonable
  next step if this item is ever revived, not concluded either way here.
- **No wearable, headphone, or fitness-tracker-type device was found to be stably identifiable
  at all.** The task doc's own hoped-for outcome ("likely wearables, headphones, fitness
  trackers... not phones") assumed *something* personally-carried would resolve cleanly; this
  household's real environment shows zero such devices today — only fixed home infrastructure
  (TVs, a smart light, a pet camera, a speaker) resolves stably, and none of those can serve as a
  "is a person home" signal.
- Cleaned up fully after testing: `bluetoothctl scan off` initially failed with `Failed to stop
  discovery` (BlueZ state got stuck, no lingering client process was found to explain it);
  resolved with a full adapter power-cycle (`power off` / `power on`), confirmed via `bluetoothctl
  show` afterward: `Discovering: no`, back to the exact pre-test state.
- **Side finding, not otherwise relevant to this item**: this same real scan surfaces a
  legitimate ethical/legal question the task doc's own hard constraints already anticipate —
  every one of those ~29 devices per scan belongs to this household or its neighbours, observed
  without any of them opting in. Nothing was stored or correlated; this was a bounded, throwaway
  Phase 0 read, not the shipped feature. If this item is ever revived, the "explicit opt-in,
  never stored for unclaimed devices" constraints the task doc already specifies are non-
  negotiable, not a formality.

**Verdict: Red — dead, per the task doc's own explicit rule ("if nothing stable is detectable,
stop here").** The hardware gate passes; the actual identification problem does not survive
contact with this household's real BLE environment. Every device a household member could
plausibly be carrying (a phone, or nothing) rotates its address and resolves to nothing; only
fixed appliances that were never the point of this feature are stable.

## Not yet done / possible future re-open conditions

- **A longer-window test** (hours, not minutes) of whether `A0:36:BC:8D:89:5C`-style
  slower-rotating addresses ever stabilise long enough to be useful, or whether they're on the
  same short rotation as everything else and this pass's short window just hadn't caught the
  next rotation yet. Not pursued given the sample size of "zero named personal devices" already
  clears the doc's own "stop here" bar without needing to resolve this.
- If the household ever acquires a BLE wearable/tracker that broadcasts a fixed, resolvable
  identity (some fitness trackers and smart tags do, deliberately, for pairing convenience) --
  worth re-running this exact Phase 0 test against that specific device before assuming the
  answer is still "dead."
- The legal/ethical opt-in design (Phase 0's other required deliverable) was not fully worked
  out, since the feasibility question already returned red first -- no need to design consent UX
  for a feature that isn't being built.

## Out of scope (per the task doc, unchanged)

- Room-level positioning (Phase 3) -- moot, Phase 0 already stopped.
- Any BLE *control* of devices -- this was receive-only scanning throughout, and always would be.
- WiFi probe-request sniffing -- explicitly ruled out in the task doc regardless of this finding.
