# aidcbot

Read-only Linux telemetry agent for GPU servers listed on OpenNEXT. It samples aggregate CPU load, memory, root-disk usage, and NVIDIA GPU utilization, VRAM, temperature, and power. It reports over HTTPS every 30 seconds by default; it does not execute commands received from the API.

## Enrollment

1. In OpenNEXT Terminal, add the server as Seller or Broker and install the Platform Agent SSH public key for a dedicated, unprivileged SSH user. The platform verifies SSH access and the GPU inventory, and pins the resolved public IP to that capacity.
2. Once SSH verification succeeds, click **Monitor token** for that capacity. This rotates any previous token and shows the new token once. The API accepts reports only when the token **and** source IP match this capacity. If the machine's outbound NAT IP differs from its SSH endpoint IP, reporting will be denied until the platform verifies/approves that IP.
3. On the server, install `aidcbot_agent.py` in `/opt/aidcbot/`, create a dedicated `aidcbot` user, and save the token in `/etc/aidcbot/token` readable only by that user. Never put the token in shell history, the service unit, a container image, or this repository.
4. Create `/etc/aidcbot/agent.env` with non-secret values:

   ```ini
   OPENNEXT_API_URL=https://open-next.ai
   OPENNEXT_CAPACITY_ID=<capacity UUID>
   OPENNEXT_TOKEN_FILE=/etc/aidcbot/token
   OPENNEXT_INTERVAL_SECONDS=30
   ```

5. Install `aidcbot.service` as a systemd unit, then enable and start it. The agent needs Python 3.10+, Linux `/proc`, outbound HTTPS, and `nvidia-smi` for GPU readings. It does not need root or `sudo`.

   ```sh
   sudo useradd --system --no-create-home --shell /usr/sbin/nologin aidcbot
   sudo install -d -o root -g root -m 0755 /opt/aidcbot /etc/aidcbot
   sudo install -o root -g root -m 0644 aidcbot_agent.py /opt/aidcbot/aidcbot_agent.py
   sudo install -o root -g root -m 0644 aidcbot.service /etc/systemd/system/aidcbot.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now aidcbot.service
   ```

   Create the token file before starting the service; its owner must be `aidcbot` and mode `0400`. Avoid passing the token as a command-line argument.

The token file should be owned by `aidcbot` and mode `0400`; the config file can be mode `0644` because it contains no token. First test with `python3 aidcbot_agent.py --once` as the `aidcbot` user. The one-shot command waits for the configured interval to produce a CPU utilization delta.

If authentication, source IP, or GPU inventory validation fails, the platform does not mark the monitor healthy. Data older than two minutes is not considered live; retained metric samples are deleted after 30 days. The agent uses bounded retry delays and never disables TLS certificate verification.

## Data contract

`POST /api/v1/terminal/capacities/{id}/metrics` with `Authorization: Bearer <capacity token>` and JSON containing `sampledAt`, `cpu`, `memory`, `disk`, and `gpus`. Metrics are percentages and bytes, with nullable readings when hardware does not expose a value. The API returns `202` for an accepted sample, `403` for token/IP mismatch, `422` for invalid or stale samples, and `409` for replayed or over-frequent samples. The capacity owner can read history at `GET /api/v1/terminal/capacities/{id}/metrics` using the signed-in Terminal session.

## Tests

```sh
python3 -m unittest -v
```

MIT licensed. See [LICENSE](LICENSE).
