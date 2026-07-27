# HTTPS for Local-Network Camera Access

## Why the camera is blocked

Chrome will not grant webcam access to a page served from a non-secure origin like:

```text
http://192.168.1.82:5173
```

For camera access, open the app through one of these:

- `https://...`
- `http://localhost`

## Important Let’s Encrypt limitation

As of **January 15, 2026**, Let’s Encrypt supports IP address certificates, but public CAs still cannot issue certificates for **reserved/private LAN IPs** such as:

- `192.168.x.x`
- `10.x.x.x`
- `172.16.x.x` to `172.31.x.x`

That means you **cannot** get a Let’s Encrypt certificate directly for:

```text
https://192.168.1.82:5173
```

## Working options

### Option 1: Best for LAN use without a public domain

Use a locally trusted certificate such as `mkcert`.

Example:

```bash
mkcert 192.168.1.82 localhost 127.0.0.1
```

Then start the React app with:

```bash
cd frontend/react
VITE_DEV_SSL_KEY="/path/to/192.168.1.82+2-key.pem" \
VITE_DEV_SSL_CERT="/path/to/192.168.1.82+2.pem" \
npm run dev
```

Open:

```text
https://192.168.1.82:5173
```

Every device that needs camera access must trust the `mkcert` root CA.

### Option 2: Use Let’s Encrypt with a real domain name

This works if you control a public domain such as:

```text
attendance.example.com
```

Recommended approach:

1. Create a DNS record for your domain.
2. Obtain a Let’s Encrypt certificate for that **domain name**.
3. On your LAN, point that hostname to your internal machine using local DNS or a router DNS override.
4. Run the React app with that certificate:

```bash
cd frontend/react
VITE_DEV_SSL_KEY="/path/to/privkey.pem" \
VITE_DEV_SSL_CERT="/path/to/fullchain.pem" \
npm run dev
```

Open:

```text
https://attendance.example.com:5173
```

## Project support added

The Vite dev server now supports HTTPS certificate files through:

- `VITE_DEV_SSL_KEY`
- `VITE_DEV_SSL_CERT`

If those are not set, the app continues to run over plain HTTP.

## Notes

- The backend API can stay on `http://localhost:8000` because Vite proxies `/api` from the HTTPS frontend.
- If you want fully trusted HTTPS on phones or other laptops across the LAN, Option 2 is the cleanest path.
