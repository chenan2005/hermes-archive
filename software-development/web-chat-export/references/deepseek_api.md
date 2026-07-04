# DeepSeek Export API Reference

## Auth Extraction (via CDP)

```python
# Navigate to chat.deepseek.com, wait for load, then:
token = cdp.eval_js("""
    (function() {
        try {
            var t = JSON.parse(localStorage.getItem('userToken') || 'null');
            return t ? t.value : 'NO_TOKEN';
        } catch(e) {
            return 'ERROR: ' + String(e);
        }
    })()
""")
```

Token is passed as: `Authorization: Bearer <token>`

## Session List API

```
POST https://chat.deepseek.com/api/v0/chat_session/fetch_page
Content-Type: application/json
Authorization: Bearer <token>

Body: {"page_size":100,"page_token":"<prev_token_or_null>"}
```

Response:
```json
{
  "biz_data": {
    "chat_sessions": [
      {
        "id": "abc123",
        "title": "Topic name",
        "last_active_time": 1234567890,
        "session_id": "abc123"
      }
    ],
    "next_page_token": "token_for_next_page"
  }
}
```

## Message History API

```
GET https://chat.deepseek.com/api/v0/chat/history_messages?chat_session_id=<session_id>
Authorization: Bearer <token>
```

Returns all messages for a session in one call.

Response format:
```json
{
  "biz_data": {
    "chat_messages": [...],
    "chat_session": {"id": "...", "title": "..."}
  }
}
```

## Full Script

See the working script at `/tmp/export_deepseek.py` (v3 final version that worked). Key points:
- Start Edge with CDP in interactive session via schtasks
- Navigate to chat.deepseek.com
- Extract userToken from localStorage
- Fetch session list with pagination
- For each session, fetch messages
- Save to JSON

## Session Stats
- Total sessions exported: 132
- File size: 6.4 MB
- Output: `~/deepseek_export.json`
