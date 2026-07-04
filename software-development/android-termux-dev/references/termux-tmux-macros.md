# Termux Extra-Keys + Tmux Macros for Tablets

## Macro syntax (from Termux source code)

Defined in `ExtraKeyButton.java` (macro field) and processed by `TerminalExtraKeys.java`.

### Format

In `~/.termux/termux.properties`, the `extra-keys` value is a JSON array of arrays.
Each line must end with ` \` (backslash + newline) because `.properties` format requires
line continuations for multi-line values. **No trailing whitespace after the backslash**.

Each cell can be:

| Format | Example | Meaning |
|--------|---------|---------|
| Plain string | `'ESC'` | Simple key (keycode from PRIMARY_KEY_CODES_FOR_STRINGS) |
| JSON dict | `{key: 'ESC', display: '取消'}` | Key with custom label |
| Macro | `{macro: 'CTRL b c', display: '新窗口'}` | Space-separated key sequence |
| Popup | `{key: 'ESC', popup: {macro: 'CTRL b d', display: '分离'}}` | Swipe-up secondary action |

### Macro processing (TerminalExtraKeys.java:onExtraKeyButtonClick)

Tokens are consumed left to right:

1. **Modifier toggle tokens**: `CTRL`, `ALT`, `SHIFT`, `FN` — set the modifier flag ON
2. **Next non-modifier token**: sent with the currently active modifier flags
3. **Flags auto-cleared** after each non-modifier token

So `CTRL b c` → send `Ctrl+b` → clear → send `c` (literal).

### Key names supported

**Control keys**: `ESC`, `TAB`, `ENTER`, `SPACE`, `BKSP`, `DEL`, `INS`, `HOME`, `END`, `PGUP`, `PGDN`
**Arrows**: `LEFT`, `RIGHT`, `UP`, `DOWN`
**Function keys**: `F1`–`F12`
**Special**: `KEYBOARD` (toggle soft keyboard), `DRAWER` (toggle drawer)

**Aliases** (from `CONTROL_CHARS_ALIASES`):
`ESCAPE→ESC`, `CONTROL→CTRL`, `SHFT→SHIFT`, `DELETE→DEL`, `BACKSPACE→BKSP`,
`PAGEUP→PGUP`, `PAGEDOWN→PGDN`, `RETURN→ENTER`, `BACKSLASH→\\`, `QUOTE→"`,
`APOSTROPHE→'`, `LT→LEFT`, `RT→RIGHT`, `DN→DOWN`

### Literal characters in macros

Any token that is NOT a recognized key name is sent as Unicode code points via
`inputCodePoint()`, which accepts `ctrlDown` and `altDown` but **NOT** `shiftDown` or `fnDown`.

### ⚠️ CRITICAL: SHIFT silently dropped on literal characters

`SHIFT` (and `FN`) modifiers are lost when applied to literal characters because
`inputCodePoint()` doesn't receive the shift/fn flag. Only named keycodes (`LEFT`,
`RIGHT`, `HOME`, `PGUP`, etc.) respect SHIFT because they use the `KeyEvent` path.

| Wrong            | Right      | What tmux sees     |
|------------------|------------|---------------------|
| `SHIFT 5`        | `%`        | `Ctrl+b` + `%`     |
| `SHIFT APOSTROPHE` | `QUOTE`    | `Ctrl+b` + `"`     |
| `SHIFT 7`        | `&`        | `Ctrl+b` + `&`     |
| `SHIFT BACKSLASH` | `\``       | `Ctrl+b` + `` ` `` |

### Auto-confirm pattern (⚠️ MAY NOT WORK)

Appending `y` to a macro (e.g. `CTRL b x y`) is intended to auto-confirm tmux prompts
`(y/n)`, but **user testing on realme GT7 via Termux showed this does NOT work** —
the `y` arrives before tmux is ready to read it, or tmux reads prompts through a
different input path than `inputCodePoint` supplies.

**Workaround accepted by user**: use `CTRL b x` (non-auto-confirm), tap `y` manually
when the prompt appears.

Alternatively, define a custom tmux binding that skips confirmation entirely:
```bash
# in ~/.tmux.conf
bind X kill-pane
bind K kill-window
```
Then use `CTRL b X` (uppercase X) and `CTRL b K` (uppercase K) in macros.
**Note**: the `bind X kill-pane` approach was also tested and **did not work** via
Termux extra-keys macros — the uppercase `X` was not recognized by tmux's key parser
when sent through `inputCodePoint`. Test on your device before relying on this.

---

## Design pattern: popup for tmux on tablets

When running Termux + tmux on a tablet without a hardware keyboard, there's a
tension: you need both **basic terminal keys** (ESC, TAB, CTRL, arrows) and
**tmux shortcuts** (`Ctrl+b` combinations). The solution is a **2-row layout**
with popup (swipe-up) on selected keys:

- **Row 1**: Keys that have both a basic function (tap) and a tmux function (swipe up)
- **Row 2**: A mix of plain basic keys and dedicated tmux macro buttons

The `display` parameter can show both functions on the button face (e.g. `"ESC/d"`
means tap = ESC, swipe = d = detach). Direction buttons (←↓↑→) should generally
keep their default arrow display — they're already self-explanatory.

---

## Final iterative layout (MagicPad, tested & refined)

This evolved from user feedback across multiple iterations. It starts from the
Termux **classic 2-row template**:

```properties
extra-keys = [[ \
    {key: ESC, display: "ESC/d", popup: {macro: "CTRL b d", display: "分离"}}, \
    {key: "/", display: "/竖分", popup: {macro: "CTRL b QUOTE", display: "竖分"}}, \
    {key: "-", display: "-横分", popup: {macro: "CTRL b %", display: "横分"}}, \
    {key: HOME, display: "HOME/z", popup: {macro: "CTRL b z", display: "缩放"}}, \
    {key: UP, popup: {macro: "CTRL b UP", display: "上窗"}}, \
    {key: END, display: "END/x", popup: {macro: "CTRL b x", display: "关pane"}}, \
    "PGUP", \
    "KEYBOARD" \
],[ \
    "TAB", \
    "CTRL", \
    "ALT", \
    {key: LEFT, popup: {macro: "CTRL b LEFT", display: "左窗"}}, \
    {key: DOWN, popup: {macro: "CTRL b DOWN", display: "下窗"}}, \
    {key: RIGHT, popup: {macro: "CTRL b RIGHT", display: "右窗"}}, \
    "PGDN" \
]]
```

**Design rationale:**
- **Row 1**: ESC, /, -, HOME, ↑, END — keys with popup for most-used tmux operations;
  PGUP, KEYBOARD — plain keys, no popup
- **Row 2 (left)**: TAB, CTRL, ALT — plain keys, user explicitly wanted no binds  
- **Row 2 (center)**: ←↓→ — tap = cursor movement, swipe up = tmux pane navigation
- **Row 2 (right)**: PGDN — plain key, no popup
- Direction buttons use **default display** (just "←" etc.) — the arrow icons are
  clear enough without annotation

### What each popup does (MagicPad variant)

| Button   | Popup   | Macro              | Tmux                      |
|----------|---------|--------------------|---------------------------|
| ESC/d    | 分离     | `CTRL b d`         | detach session            |
| /竖分    | 竖分     | `CTRL b QUOTE`     | `Ctrl+b "` vertical split |
| -横分    | 横分     | `CTRL b %`         | `Ctrl+b %` horizontal split |
| HOME/z   | 缩放     | `CTRL b z`         | toggle pane zoom          |
| ↑ (UP)   | 上窗     | `CTRL b UP`        | navigate to upper pane    |
| END/x    | 关pane   | `CTRL b x`         | kill pane                 |
| ←        | 左窗     | `CTRL b LEFT`      | navigate to left pane     |
| ↓        | 下窗     | `CTRL b DOWN`      | navigate to lower pane    |
| ➡        | 右窗     | `CTRL b RIGHT`     | navigate to right pane    |

---

## Compact variant: realme GT7 (6.8" phone)

Optimized for a smaller phone screen with no hardware keyboard. Key differences from the tablet layout:

| Feature | MagicPad (tablet) | realme GT7 (phone) |
|---------|-------------------|--------------------|
| `extra-keys-style` | default (text labels) | `all` (Unicode symbols — ↵ ⌦ ⌫ etc.) |
| Display labels | Custom `display` strings on most keys | None — relies on symbol style |
| Row 1 end | `PGUP`, `KEYBOARD` | `BKSP`, `KEYBOARD` |
| Row 2 middle | Plain `CTRL`, `ALT` | `CTRL(Ctrl+C popup)`, `@`, `ALT`, `ENTER` |
| Row 2 end | `PGDN` | `ALT`, `ENTER` |
| Total keys | 15 (8+7) | 16 (8+8) |

**Design rationale (phone vs tablet):**
- **BKSP instead of PGUP**: Phone users type short commands on the go, need backspace more than page-up
- **ENTER in row 2**: Essential for running commands without the system keyboard popping up
- **@ in row 2**: Quickly type SSH addresses (`user@host`) without switching to system keyboard
- **CTRL popup (Ctrl+C)**: Common copy gesture on phone where long-press selection is awkward
- **No custom display labels**: Phone buttons are tiny; Unicode symbols from `extra-keys-style = all` are more readable than Chinese text at small sizes
- **No PGUP/PGDN**: Sacrificed for BKSP + ENTER — phone screen real estate is scarce

```properties
### realme GT7 compact 2-row, symbol style, tmux popups on tmux keys

extra-keys-style = all

extra-keys = [[ \
    {key: ESC, popup: {macro: "CTRL b d", display: "分离"}}, \
    {key: "/", popup: {macro: "CTRL b QUOTE", display: "竖分"}}, \
    {key: "-", popup: {macro: "CTRL b %", display: "横分"}}, \
    {key: HOME, popup: {macro: "CTRL b z", display: "缩放"}}, \
    {key: UP, popup: {macro: "CTRL b UP", display: "上窗"}}, \
    {key: END, popup: {macro: "CTRL b x", display: "关pane"}}, \
    "BKSP", \
    "KEYBOARD" \
],[ \
    "TAB", \
    {key: CTRL, popup: {macro: "CTRL c", display: "复制"}}, \
    "@", \
    {key: LEFT, popup: {macro: "CTRL b LEFT", display: "左窗"}}, \
    {key: DOWN, popup: {macro: "CTRL b DOWN", display: "下窗"}}, \
    {key: RIGHT, popup: {macro: "CTRL b RIGHT", display: "右窗"}}, \
    "ALT", \
    "ENTER" \
]]
```

**Tap vs swipe-up behavior** — same popup semantics as the MagicPad layout:

| Tap key | Popup (swipe up) | Function |
|---------|-----------------|----------|
| ESC     | 分离             | tmux detach |
| /       | 竖分             | `Ctrl+b "` vertical split |
| -       | 横分             | `Ctrl+b %` horizontal split |
| HOME    | 缩放             | `Ctrl+b z` toggle pane zoom |
| ↑       | 上窗             | `Ctrl+b ↑` pane up |
| END     | 关pane           | `Ctrl+b x` kill pane |
| BKSP    | —                | Backspace (plain) |
| KEYBOARD| —                | Toggle soft keyboard |
| TAB     | —                | Tab (plain) |
| CTRL    | 复制             | `Ctrl+c` copy |
| @       | —                | Literal `@` character |
| ←↓→     | 左/下/右窗       | `Ctrl+b ←/↓/→` pane navigation |
| ALT     | —                | Alt modifier (plain) |
| ENTER   | —                | Enter (plain) |

**Converting between phone and tablet:** To migrate a MagicPad user to the phone layout (or vice versa):
1. Change `extra-keys-style` to `all` (phone) or remove it (tablet)
2. Swap `PGUP`/`PGDN` with `BKSP`/`ENTER`
3. Move `@` from row-2-end to middle (after CTRL)
4. Add CTRL popup for Ctrl+C copy (optional on tablet)
5. Strip or add custom `display` labels as needed

---

## Connecting to Android devices when both LAN SSH and FRP are down

Android Termux devices require manual `sshd` restart after Termux is killed from recents. When both connection paths fail:

| Symptom | Cause | Fix |
|---------|-------|-----|
| LAN SSH: timeout | Termux sshd not running | Open Termux → `sshd` |
| FRP: "Connection closed" on FRP server port | Device-side frpc not running | Open Termux → restart frpc |
| FRP resolves to 198.18.x.x fake-IP | OpenClash hijacks `www.bernarty.xyz` DNS | Use direct IP `122.51.232.209` instead of hostname, or temporarily disable OpenClash fake-IP filtering for bernarty |

The only recovery path is physical access to the device or someone on-site opening Termux.

---

## Macro reference (all tmux functions)

| Label    | Macro                   | Tmux equivalent           |
|----------|-------------------------|---------------------------|
| 新建     | `CTRL b c`              | new window                |
| 下窗     | `CTRL b n`              | next window               |
| 上窗     | `CTRL b p`              | previous window           |
| 横分     | `CTRL b %`              | `Ctrl+b %` split horiz    |
| 竖分     | `CTRL b QUOTE`          | `Ctrl+b "` split vert     |
| 分离     | `CTRL b d`              | detach session            |
| 滚动     | `CTRL b [`              | enter copy/scroll mode    |
| ←        | `CTRL b LEFT`           | go to left pane           |
| ↓        | `CTRL b DOWN`           | go to bottom pane         |
| ↑        | `CTRL b UP`             | go to upper pane          |
| →        | `CTRL b RIGHT`          | go to right pane          |
| 缩放     | `CTRL b z`              | toggle pane zoom          |
| 关闭     | `CTRL b x`              | kill pane (prompts y/n)   |
| 列表     | `CTRL b w`              | window list (interactive) |
| 轮换     | `CTRL b o`              | cycle to next pane        |
| 关窗口   | `CTRL b & y`            | kill window (auto-confirm) |

---

## Other config: pure-tmux 2-row (no popups)

For a button-only layout without popups (every tap = tmux macro):

```properties
extra-keys = [[ \
    {macro: "CTRL b c", display: "新窗"}, \
    {macro: "CTRL b n", display: "下窗"}, \
    {macro: "CTRL b p", display: "上窗"}, \
    {macro: "CTRL b %", display: "横分"}, \
    {macro: "CTRL b QUOTE", display: "竖分"}, \
    {macro: "CTRL b d", display: "分离"}, \
    {macro: "CTRL b [", display: "滚动"}, \
    "KEYBOARD" \
],[ \
    {macro: "CTRL b LEFT", display: "←"}, \
    {macro: "CTRL b DOWN", display: "↓"}, \
    {macro: "CTRL b UP", display: "↑"}, \
    {macro: "CTRL b RIGHT", display: "→"}, \
    {macro: "CTRL b z", display: "缩放"}, \
    {macro: "CTRL b x", display: "关闭"}, \
    {macro: "CTRL b w", display: "列表"}, \
    {macro: "CTRL b o", display: "轮换"} \
]]
```

---

## Loading & troubleshooting

```bash
# Edit the config file
nano ~/.termux/termux.properties

# Reload
termux-reload-settings
```

**Common errors:**

| Error | Likely cause | Fix |
|-------|-------------|-----|
| Toast shows "invalid extra-keys" | Missing backslash `\` at end of line | Ensure each continued line ends with ` \` |
| Buttons show wrong labels or wrong keys | `.properties` parsing split the value | Use line continuations on ALL rows |
| Keyboard won't show after tapping | Termux lost keyboard focus after BT keyboard disconnect | Add `KEYBOARD` button; check overlay permission |
| Extra keys row not appearing | Config completely failed to parse | Check JSON: commas between rows `],[`, no trailing commas |

**Termux.app display customization:**
- `extra-keys-style = default|arrows-only|arrows-all|all|none` — choose Unicode
  symbols for key labels
- `extra-keys-text-all-caps = true` — force uppercase button labels
- `hide-soft-keyboard-on-startup = true` — hide keyboard when app opens
