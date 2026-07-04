# Google Authentication Domains

Complete domain list for Google login flow. Routing only `accounts.google.com` is insufficient — the auth flow touches many domains.

## Core auth

```
accounts.google.com
accounts.google.co.kr
accounts.google.com.hk
accounts.google.com.sg
accounts.youtube.com
```

## OAuth / token exchange

```
oauth2.googleapis.com
www.googleapis.com
openidconnect.googleapis.com
securetoken.googleapis.com
identitytoolkit.googleapis.com
```

## Device / client auth

```
android.googleapis.com
clientauth.googleapis.com
device-provisioning.googleapis.com
```

## API backends

```
people.googleapis.com
content-googleapis.com
apis.google.com
```

## reCAPTCHA / static assets

```
ssl.gstatic.com
www.gstatic.com
```

## Account management

```
myaccount.google.com
play.google.com
```

## UCI command (OpenWrt dnsmasq)

```bash
for domain in \
  accounts.google.com \
  accounts.google.co.kr \
  accounts.google.com.hk \
  accounts.google.com.sg \
  accounts.youtube.com \
  oauth2.googleapis.com \
  www.googleapis.com \
  openidconnect.googleapis.com \
  securetoken.googleapis.com \
  identitytoolkit.googleapis.com \
  android.googleapis.com \
  clientauth.googleapis.com \
  people.googleapis.com \
  content-googleapis.com \
  ssl.gstatic.com \
  www.gstatic.com \
  apis.google.com \
  play.google.com \
  myaccount.google.com; do
  uci add_list dhcp.@dnsmasq[0].ipset="/${domain}/google_auth"
done
uci commit dhcp
/etc/init.d/dnsmasq restart
```
