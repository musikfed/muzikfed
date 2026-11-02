# Installation / deployment (Ubuntu CORE .100, Windows GRAPHICS .103, Acer)

## Network topology

- `CORE .100` (Ubuntu Server 24.04, RTX 3060 12GB): API, MIDI/MusicXML generation, local Ollama if chosen, fast FluidSynth preview.
- `GRAPHICS .103` (Windows 11, RX 7600 XT): MuseScore Studio + MuseSounds Core for manual *high-quality* WAV/FLAC export.
- `Acer` (Windows 11): remote SSH/RDP/WireGuard client and web control desk. No web browser or desktop is required on Ubuntu.

`.100` and `.103` are only descriptions of your hosts, **not validated full IP addresses**. Use the actual WireGuard address. The API binds to **127.0.0.1:8765** by default.

## One-time CORE setup (from a normal unprivileged SSH account)

```bash
sudo apt update
sudo apt install -y git fluidsynth fluid-soundfont-gm
# uv 0.12.0 + Python 3.12 already exist on the user's CORE.
git clone https://github.com/musikfed/muzikfed.git ~/pocket-orchestra
cd ~/pocket-orchestra
bash scripts/install-core.sh
systemctl --user status pocket-orchestra --no-pager
curl --fail http://127.0.0.1:8765/api/health
```

If `systemctl --user` is not available, use `uv run pocket-orchestra` while logged in. An optional user service that persists after logout may require a sysadmin to run `sudo loginctl enable-linger "$USER"`; this is *not* done automatically.

Check preview availability (the health endpoint reports whether `fluidsynth` and its SoundFont are detected). The preview is deliberately not the final-quality MuseSounds mix.

## Deploy/update from Acer via SSH over VPN

Acer with WSL, Git Bash, or any Bash-capable shell:

```bash
git clone https://github.com/musikfed/muzikfed.git
cd muzikfed
bash scripts/deploy-to-core.sh YOUR_USER@YOUR_CORE_WIREGUARD_IP
```

The script checks the remote Git checkout, performs a `git pull --ff-only` if it already exists, installs Python dependencies with `uv`, runs tests, and configures a localhost-bound `systemd --user` service. It will **stop rather than overwrite** unrelated directories or uncommitted changes.

From the Ubuntu server itself, after each new GitHub commit:

```bash
cd ~/pocket-orchestra
bash scripts/update-core.sh
```

Create a local-only tunnel in the Acer PowerShell:

```powershell
ssh -N -L 8765:127.0.0.1:8765 YOUR_USER@YOUR_CORE_WIREGUARD_IP
```

Keep the SSH process open; navigate to http://127.0.0.1:8765 on Acer. The tunnel transfers web traffic securely between Acer and CORE. If localhost port 8765 is already occupied on Acer, change its left side, e.g. `8877:127.0.0.1:8765` and browse `127.0.0.1:8877`.

## GRAPHICS .103

1. Install MuseScore Studio and the free MuseSounds Core libraries separately on Windows .103.
2. Download `score.musicxml` from the Pocket Orchestra dashboard on Acer and copy it to .103 through the VPN/RDP shared folders.
3. Open it with MuseScore Studio; fix transpositions, instrument assignments and mixer sounds as needed.
4. Export WAV or FLAC from MuseScore Studio; preserve the editable `.mscz` score.
5. For a separated arrangement, export `choir.musicxml` or `orchestra.musicxml` and align at the same BPM. WAV stems from MuseSounds are **not yet automatically generated**.

## Optional local LLM

The composer uses deterministic rules unless you enable `use_ollama` in the dashboard. Ollama and its language model must be installed independently. The LLM currently proposes bounded musical parameters, not every individual note; no promise of long-form composition or realistic Russian lyrics.

## Troubleshooting

```bash
systemctl --user status pocket-orchestra --no-pager
journalctl --user -u pocket-orchestra -n 80 --no-pager
cd ~/pocket-orchestra && uv run pytest -q
curl -fsS http://127.0.0.1:8765/api/health
```

## Security rules

- Do not commit `.env`, TLS `privkey.pem` / `fullchain.pem`, SSH keys, WireGuard credentials, private recordings, copyrighted sound libraries or model weights.
- **Never port-forward 8765 on a public router or expose it via the white IP.** The v0.1 API has no authentication, quotas, or rate limits. SSH tunnels are the recommended access path.
- Don't run setup scripts as root; `sudo` only for explicitly chosen OS dependencies.
- Pin dependencies and review upstream packages before production exposure; v0.1 is a prototype, not a hardened public service.
