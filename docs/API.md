# SignalOps API Reference

This document contains the detailed endpoint inventory and operational routes.

## Base

- Local base URL: `http://127.0.0.1:8000`
- Versioned API prefix: `/api/v1`

## Auth

- `POST /api/v1/auth/signup`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`

## Analysis

- `POST /api/v1/srl/analyze`
- `GET /api/v1/srl/history`
- `GET /api/v1/srl/history/{run_id}`

## Shopify Integration

- `POST /api/v1/integrations/shopify/connect/start`
- `GET /api/v1/integrations/shopify/callback`
- `GET /api/v1/integrations/shopify/status`
- `POST /api/v1/integrations/shopify/disconnect`
- `POST /api/v1/integrations/shopify/monitor-now`
- `POST /api/v1/integrations/shopify/webhook/orders`

## Billing

- `GET /api/v1/buy`
- `POST /api/v1/payments/flutterwave/initialize`
- `POST /api/v1/payments/flutterwave/webhook`
- `GET /api/v1/account/plan`

## Admin

- `GET /api/v1/admin/founder-metrics`
- `GET /api/v1/admin/feature-timeseries`

## Internal Scheduled Jobs

These routes require monitor token auth header:

- Header: `x-monitor-token: <MONITOR_INTERNAL_TOKEN>`

Routes:

- `POST /api/v1/monitor/run/shopify`
- `POST /api/v1/maintenance/data-retention/run`

Recommended schedules:

- Shopify monitor: every 30 minutes
- Retention cleanup: once daily

## System

- `GET /health`

## Security Notes

- Do not store secret values in this file.
- Keep production credentials in secret managers.
- Rotate any secret if it was ever committed.
