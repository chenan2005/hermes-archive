# Cloudflare DNS Migration (DNSPod → Cloudflare)

Migration steps for domains registered at Tencent Cloud with DNSPod DNS, moving to Cloudflare for CDN proxy.

## Pre-flight

Check current DNS records on DNSPod:
```bash
# Query current NS and A records
dig +short yourdomain.com NS
dig +short www.yourdomain.com A
dig +short sub.yourdomain.com A
```

## Step 1: Add domain to Cloudflare

Navigate to [dash.cloudflare.com/add-site](https://dash.cloudflare.com/add-site), enter the domain, and let it scan existing records. Cloudflare's auto-scan is hit-or-miss — it may miss records. Manually verify afterward.

## Step 2: Create DNS records via API

If the auto-scan missed records, add them manually with the Cloudflare API.

**Token scope note:** The "Edit zone DNS" template only grants `DNS:Write` permission — enough for record changes but NOT for SSL/TLS settings. If you later need to change the SSL mode (e.g., switch from "Full" to "Flexible"), do it via the web dashboard or create a separate token with `SSL and Certificates:Write`.

```bash
# Install jq if needed (apt install jq, or use python)
TOKEN="your_api_token"
ZONE_ID=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones?name=yourdomain.com" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['result'][0]['id'])")

# Add records
for entry in '{"type":"A","name":"www","content":"122.51.232.209","proxied":false}' \
             '{"type":"A","name":"kvm","content":"154.40.40.38","proxied":false}' \
             '{"type":"A","name":"seoul","content":"43.108.41.245","proxied":true}'; do
  curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$entry"
done
```

Key: Set `proxied: true` (🟠 orange cloud) for domains that need CDN acceleration. Set `proxied: false` (⚪ gray cloud) for non-proxy services.

## Step 3: Change NS at Tencent Cloud

1. Open https://console.cloud.tencent.com/domain
2. Click the domain → **Manage** → **Modify DNS Servers**
3. Replace DNSPod NS (`f1g1ns1.dnspod.net`, `f1g1ns2.dnspod.net`) with Cloudflare's NS
4. Cloudflare NS are listed in the zone overview, typically like:
   - `adele.ns.cloudflare.com`
   - `weston.ns.cloudflare.com`
5. Save

## Step 4: Wait for propagation

Check if propagation is complete:
```bash
# Check what NS the outside world sees
dig +short yourdomain.com NS

# Check if Cloudflare-proxied domain resolves to CF IPs
dig +short seoul.yourdomain.com
# Should return Cloudflare IPs (104.x.x.x, 172.x.x.x), not the origin IP

# Check Cloudflare zone status
curl -s -X GET "https://api.cloudflare.com/client/v4/zones/$ZONE_ID" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json; z=json.load(sys.stdin)['result']; print(z['status'], z.get('observed_name_servers',''))"
# Status "active" = propagation complete
```

Propagation typically takes 10 minutes to 2 hours depending on TTL and registrar. The old `pending` status means Cloudflare can see DNSPod NS are still responding.

## Step 5: SSL mode

New Cloudflare zones default to **Full** SSL mode — this accepts self-signed origin certificates. If you used a self-signed cert on the origin:
- `Full` (default) ✅ — works
- `Flexible` — works but origin receives plain HTTP
- `Full (strict)` ❌ — requires valid CA-signed origin cert

No change needed unless you see Cloudflare connection errors.

## Verification

```bash
# Test Cloudflare proxy is working
curl -s -o /dev/null -w "HTTP:%{http_code}\n" "https://seoul.yourdomain.com/somefile"
# Should return 200 (or appropriate backend response), not timeout

# Check Cloudflare hits in access log
# The origin sees connections from Cloudflare IPs (not client IPs)
