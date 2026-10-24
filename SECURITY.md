# Security

## Reporting

Please report a vulnerability privately through GitHub Security Advisories for [Unicorn-Commander/Podcast-Ops](https://github.com/Unicorn-Commander/Podcast-Ops/security/advisories/new).

This repository does not publish a security mail address. A public issue or pull request is a poor place for an unfixed exploit. Include the git revision or the 0.1.0 version you ran, the route or command, and what an attacker gains.

## What this app does and does not enforce

`apps/api/run.sh` listens on all interfaces, port 8011 unless `PORT` is set.

If `PODCAST_OPS_API_TOKEN` is set, HTTP routes other than `GET /health` require `Authorization: Bearer <token>`. That token is one shared secret. It is not per-user login, and the HTTP middleware does not cover `WS /render-jobs/{job_id}/stream`. The Next.js studio does not send the header. Leave the token unset for local UI use, and set it before any other machine can reach the port. When you set it, call the API with your own client.

The render queue is in memory. Cancelling a job terminates the child process on the API host.

`podcast-ops-export` sends `PODCAST_EXPORT_TOKEN` only to the ingest host you pass as `--endpoint`. Storage URLs returned by that host are not given the bearer. The CLI refuses redirects. Treat the selection file and the token as secrets.

Voice clone copies a WAV with `scp` to `VIBEVOICE_VOICE_MOUNT_REMOTE`. Point that variable at a destination you control.
