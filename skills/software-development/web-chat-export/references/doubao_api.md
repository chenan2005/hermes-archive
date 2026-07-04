# Doubao Export API Reference

## Auth Extraction

Doubao uses HttpOnly cookies. `document.cookie` is insufficient.

```python
cookies = cdp.send_and_wait("Network.getCookies", {
    "urls": ["https://www.doubao.com"]
})
cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies["result"]["cookies"]])
# Gets ~38 cookies including HttpOnly: sid_tt, sessionid, sessionid_ss, etc.
```

Pass as Cookie header, NOT Authorization.

## Main API: Pull Message Chain

```
POST https://www.doubao.com/im/chain/single?version_code=20800&language=zh&device_platform=web&aid=497858&real_aid=497858&pkg_type=release_version&device_id=<id>&pc_version=3.25.3&web_id=<id>

Headers:
  Cookie: <full cookie string>
  Content-Type: application/json; encoding=utf-8
  Referer: https://www.doubao.com/chat/<conv_id>
  Origin: https://www.doubao.com
```

### Request Body

```json
{
  "cmd": 3100,
  "uplink_body": {
    "pull_singe_chain_uplink_body": {
      "conversation_id": "4830199810",
      "anchor_index": 9007199254740991,
      "conversation_type": 3,
      "direction": 1,
      "limit": 50,
      "ext": {},
      "filter": {"index_list": []}
    }
  },
  "sequence_id": "unique_per_request_uuid",
  "channel": 2,
  "version": "1"
}
```

- `cmd: 3100` = pull single chain
- `anchor_index` = pagination cursor (start from MAX_SAFE_INTEGER for latest, then use response's `next_index`)
- `direction: 1` = backward (older messages), `0` = forward (newer)
- `limit` = messages per batch
- `sequence_id`: UUID v4, must be unique per request (the page generates a new one each time)
- `channel: 2` and `version: "1"`: always present, purpose unclear
- `evaluate_ab_params: ""` and `evaluate_common_params: ""`: AB testing parameters, always empty strings in web requests

### Response Structure

```json
{
  "cmd": 3100,
  "sequence_id": "...",
  "downlink_body": {
    "pull_singe_chain_downlink_body": {
      "messages": [
        {
          "conversation_id": "4830199810",
          "message_id": "49085136451096578",
          "sender_id": "7234781073513644036",
          "user_type": 1,
          "content_type": 1,
          "index_in_conv": 4301,
          "create_time": 1783010005,
          "tts_content": "Plain text markdown of the message",
          "content": "{\"multi_reference\":{...}}" ,
          "brief": "Short preview",
          "section_name": "Section/topic name",
          "fetch_token": "49085136451096578",
          "ext": { ... huge metadata dict ... }
        }
      ],
      "has_more": true,
      "next_index": 4269,
      "msg_cursor": 1
    }
  },
  "status_code": 0,
  "status_desc": "OK"
}
```

### Pagination

1. First call: `anchor_index=9007199254740991`, `direction=1`
2. Response contains `next_index` and `has_more`
3. Next call: `anchor_index=<next_index>`, same `direction`
4. Repeat until `has_more=False` or `next_index=None`

## Conversation Info API

```
POST https://www.doubao.com/im/conversation/info?<query_params>
Body: {"cmd":1110,"uplink_body":{"get_conv_info_uplink_body":{"conversation_id":"...","ext":{"cold_start":"true"},"bot_id":"","conversation_type":3,"option":{"need_bot_info":true}}},"sequence_id":"..."}
```

## Other Endpoints Discovered

| Endpoint | Cmd | Purpose |
|---|---|---|
| `/im/conversation/info` | 1110 | Conversation metadata |
| `/im/chain/single` | 3100 | Pull messages from single conversation |
| `/im/chain/recent_conv` | 3200 | Recent conversations list |
| `/alice/commerce/sale/subscription/entry/config` | — | Subscription/membership config |
| `/alice/call/downgrade_config_pc` | — | PC downgrade config |
| `/samantha/notice/info` | — | Notifications |

## Message Content Parsing

- `tts_content`: Clean markdown text (PREFERRED for export)
- `content`: JSON string containing `multi_reference` (search sources), `search_references`, etc.
- `user_type`: 1=user, 2=assistant, 3=system
- `index_in_conv`: Message number in conversation (4301 means very long conversation)
- `create_time`: Unix timestamp (seconds)

## Critical: Index Density ≠ Message Count

`index_in_conv` is a monotonically-increasing server-side sequence number, NOT a 1:1 counter of messages. Observed density: **~44%** (1902 messages across 4301 index slots). Gaps are filled by system events (tool calls, image generation, deleted messages, internal markers).

Pattern: user messages use even-ish indices; assistant responses use adjacent indices; 2-3 index gaps between each pair for system events.

`total_count` in API metadata (e.g., 4301) counts ALL events including system ones, NOT just user-visible messages. **Do NOT interpret it as message count.**

## Working Export Pattern: CDP Network Intercept + Manual Scroll

Despite programmatic replay failing, the FULL conversation IS accessible via the web API — just not through direct pagination. The winning pattern:

1. **Open doubao chat page** via CDP `Page.navigate`
2. **Enable CDP Network monitoring**: `Network.enable`
3. **User manually scrolls up** through conversation — each scroll triggers native API calls
4. **Intercept ALL `/im/chain/single` responses**:
   - Listen for `Network.responseReceived` events with matching URL
   - On `Network.loadingFinished`, call `Network.getResponseBody` to get body
   - Parse `downlink_body.pull_singe_chain_downlink_body.messages[]`
   - Deduplicate by `index_in_conv`
5. **Incremental save** after each batch to prevent data loss (see pitfall below)
6. **Auto-stop** after 20s of no new messages (user stopped scrolling)

### Incremental Save Pattern (CRITICAL)

Always save data incrementally — do NOT wait until the end. The listener process may die unexpectedly (SSH timeout, Edge crash, buffering issues). Accumulated in-memory data is lost; only persisted data survives.

```python
# After each batch of new messages captured:
export = build_export(collected_msgs)  # sorted by index_in_conv
with open(inc_path, 'w', encoding='utf-8') as f:
    json.dump(export, f, ensure_ascii=False)
# Also save final version to timestamped file after completion
```

Without incremental save: process collected 1203 messages, died before final write → 0 saved.
With incremental save: each batch persists → worst case loses only the last batch.

## Mobile App Alternative

If web export is impractical:
- Android: Shizuku access to `/data/data/com.larus.nova/databases/` (requires ADB + Shizuku)
- Possible: contact Doubao support for official data export (required by Chinese data protection laws)

## Anti-Replay Protection (Critical)

**Programmatic API replay returns 0 messages.** Even when using `Runtime.evaluate` + `fetch()` from the browser tab context with exact same URL, POST body, cookies, and headers as the page's own requests — all responses return empty message lists.

Tested approaches that ALL fail:
- `eval_js(fetch(api_url, {method:'POST', body: exact_body}))` → 0 messages
- Using captured `sequence_id` UUID from first response → 0 messages
- Generating new random UUID for `sequence_id` → 0 messages
- Including `evaluate_ab_params` and `evaluate_common_params` from captured request → 0 messages
- Varying `direction` (0/1), `anchor_index`, `limit` → 0 messages

**Only the page's own native fetches (triggered by actual user scroll) return data.** Likely mechanism: Service Worker interception or per-request token binding.

**Practical implication:** Do NOT attempt programmatic pagination. The only working approach is:
1. User manually scrolls through conversation (triggers native API calls)
2. CDP `Network.responseReceived` + `Network.getResponseBody` intercepts responses
3. Script collects and deduplicates messages

## CDP Scroll Simulation Failure

ALL programmatic scroll methods fail to trigger lazy loading on doubao:

| Method | Result |
|---|---|
| `element.scrollBy(0, -clientHeight)` | Scrolls container but no API call |
| `element.scrollTo({top: 0})` | Scrolls to top but no API call |
| `element.dispatchEvent(new Event('scroll'))` | Event fires but no API call |
| `element.dispatchEvent(new WheelEvent('wheel'))` | Event fires but no API call |
| CDP `Input.dispatchMouseEvent({type:'mouseWheel'})` | Mouse events sent but no API call |
| Multiple rounds of any above | Still no API calls triggered |

The virtual list (`v_list_scroller-BxcoIX`, 4710px scrollHeight) uses IntersectionObserver or React-internal state tracking that filters injected/emulated events. **Must use real human scroll input.**

## Settings Page

- URL: `https://www.doubao.com/settings` (NOT `/setting` — that's 404)
- `https://www.doubao.com/settings/privacy` for privacy settings
- No built-in conversation export feature as of 2026-07

## Key Cookies Required

Must include (HttpOnly indicates must use Network.getCookies):
- `sessionid` (HttpOnly)
- `sid_tt` (HttpOnly)
- `sessionid_ss` (HttpOnly)
- `passport_csrf_token`
- `s_v_web_id`
- `multi_sids` (HttpOnly)
