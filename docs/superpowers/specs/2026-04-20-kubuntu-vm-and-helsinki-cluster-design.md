# Kubuntu GUI VM on Snoochie + Helsinki Proxmox Cluster (Snoochie + Boochies)

**Status**: Draft — awaiting user review
**Date**: 2026-04-20
**Author**: Claude (Opus 4.7), with Chris Brown

## Goals

1. Spin up a Kubuntu 24.04 LTS desktop VM on the Proxmox node `snoochie` (Hetzner `65.21.205.247`, HEL1-DC6) that Chris can access with mouse + keyboard and immediately use the `ubuntu-setup-tool` repo to customize.
2. The VM must come up with the setup tool already cloned and all prerequisites installed so `python3 setup.py` works on first login.
3. Provision Proxmox VE 8 on the bare-metal server `Boochies` (Hetzner `135.181.215.247`, HEL1-DC3) and join it to the existing `helsinki` cluster on Snoochie.
4. Expose the VM over Tailscale (as tailnet peer) so day-to-day access is over Tailscale rather than Proxmox noVNC.
5. Update `README.md` in `ubuntu-setup-tool` to document a new "Network install (Proxmox)" section alongside the existing USB install flow.

## Non-Goals

- Changes to `setup.py` modules. The tool runs the same inside a VM. If KDE-specific adjustments are needed (GNOME tweaks, Kitty theme etc.), those are out of scope; docs will note KDE users may skip modules 1 and 7.
- Shared-storage (Ceph) between cluster nodes. The cluster exists for single-pane-of-glass + live-migration-optional; local-lvm on each node is the storage.
- Production-grade HA/fencing. QDevice gives quorum resilience, not fencing.

## Environment Snapshot (captured 2026-04-20)

### Snoochie (existing PVE host)
- Proxmox VE 8.4.18, kernel 6.8.12-20-pve, hostname `snoochie`
- Cluster `helsinki` already created, single node, config version 1
- 12 vCPU (Intel i7-8700), 125 GiB RAM (3.7 used), local-lvm 841 GiB free
- Networks: `vmbr0` public (`65.21.205.247/26`, IPv6 `2a01:4f9:6a:1487::2/64`), `vmbr1` NAT (`10.10.10.1/24`, MASQUERADE via vmbr0)
- 3 LXC containers already running (100/101/102 — `sandstorm-helsinki-1` etc.)
- No ISOs uploaded to `local:iso`

### Boochies (bare metal, Proxmox NOT installed)
- Hetzner server `#2974693`, `Boochies`, Server Auction, HEL1-DC3
- IPv4 `135.181.215.247`, IPv6 `2a01:4f9:3a:2de9::/64`
- Port 22 open (existing OS — unknown distro), port 8006 closed (no Proxmox)
- Rescue mode and reset-via-API supported
- No vSwitches configured in the Hetzner account

### Credentials (Proton Pass, vault `Claude`)
- `Snoochie Proxmox — root (current)` → root/`%D8Qhf4PqhfXb3` — **this is the working one**; `Hetzner sandstorm host — root` is stale
- `Hetzner Robot — API/webservice` → used to enumerate servers and drive rescue/reboot
- `Tailscale — autoinstall auth key (reusable, preauth)` → for VM + cluster-node Tailscale joins

## Architecture

```
                        Hetzner AS24940 (Helsinki, DC3 + DC6)
   ┌────────────────────────────────────────────────────────────────────┐
   │                                                                    │
   │   ┌──────────────────────┐         ┌──────────────────────┐        │
   │   │ snoochie (DC6)       │         │ boochies (DC3)       │        │
   │   │ 65.21.205.247        │         │ 135.181.215.247      │        │
   │   │ PVE 8.4 (existing)   │         │ PVE 8.4 (to install) │        │
   │   │                      │         │                      │        │
   │   │ vmbr0 public (WAN)   │◄────────┤ vmbr0 public (WAN)   │        │
   │   │ vmbr1 10.10.10.1/24  │         │ vmbr1 10.10.20.1/24  │        │
   │   │  (per-node NAT)      │         │  (per-node NAT)      │        │
   │   │   NAT for VMs/CTs    │         │   NAT for VMs/CTs    │        │
   │   │ vmbr2 10.0.0.1/24    │◄═vSwitch═► vmbr2 10.0.0.2/24   │        │
   │   │   (corosync ring0)   │         │   (corosync ring0)   │        │
   │   │                      │         │                      │        │
   │   │ VM 200 kubuntu-ws    │         │                      │        │
   │   │   vmbr1 10.10.10.200 │         │                      │        │
   │   │   + Tailscale         │         │                      │        │
   │   └──────────────────────┘         └──────────────────────┘        │
   │                                                                    │
   │      Ring1 (fallback): corosync over vmbr0 public IPs              │
   │      QDevice: sandstorm-helsinki-1 LXC (CT 100) on snoochie        │
   └────────────────────────────────────────────────────────────────────┘

                              Tailnet (shiftaltcreate)
                    ┌─────────────────────────────────┐
                    │  kubuntu-ws ←→ monsta-mash etc. │  (RDP/SSH)
                    └─────────────────────────────────┘
```

### Component boundaries

- **Kubuntu VM (VM 200)** — the thing Chris will actually use. Single well-defined interface: "SSH/RDP in as `chris`, `cd ~/ubuntu-setup-tool && python3 setup.py`."
- **Autoinstall seed ISO** — a one-shot artifact built on snoochie that contains `user-data` + `meta-data` for Subiquity. It bakes in: user `chris` with Chris's ed25519 public key, Tailscale auth key, apt packages (`openssh-server`, `git`, `python3`, `curl`, `xrdp`), and a late-command that clones `ubuntu-setup-tool` to `/home/chris/ubuntu-setup-tool`.
- **Cluster networking layer** — Hetzner vSwitch + VLAN-tagged `vmbr2` on both hosts. Corosync ring0 on vmbr2 (10.0.0.0/24), ring1 on public IPs.
- **QDevice** — `corosync-qnetd` running in the existing `sandstorm-helsinki-1` LXC (CT 100) on snoochie. It doesn't care about fencing; it just exists to break 2-node quorum ties. (If we later lose snoochie entirely we lose the QDevice with it, but that's the same failure domain as Snoochie itself — acceptable trade for this setup.)

## Build sequence

### Phase 1 — Kubuntu VM on Snoochie (gets Chris working ASAP)

1. Upload **Ubuntu Server 24.04 LTS ISO** (not Kubuntu — see step 4 for why) to `local:iso` on snoochie (`wget` directly on the host; ~2.6 GB).
2. Build autoinstall seed ISO on snoochie using `cloud-localds` (or `genisoimage` with NoCloud layout):
   - `user-data`: identity (user `chris`, password hashed, sudo NOPASSWD), SSH authorized key (Chris's ed25519 pulled from agent), packages, late-commands (install Tailscale, `tailscale up --authkey=... --ssl-name=kubuntu-ws`, `git clone` into `/home/chris/ubuntu-setup-tool`, `chown -R chris:chris`).
   - `meta-data`: `instance-id: kubuntu-ws-1` and hostname.
3. `qm create 200 --name kubuntu-ws --memory 16384 --cores 6 --cpu host --bios ovmf --machine q35 --efidisk0 local-lvm:1,format=raw,efitype=4m --scsihw virtio-scsi-single --scsi0 local-lvm:120,discard=on,ssd=1 --ide2 local:iso/ubuntu-24.04-live-server.iso,media=cdrom --ide3 local:iso/kubuntu-ws-seed.iso,media=cdrom --net0 virtio,bridge=vmbr1,firewall=0 --ipconfig0 ip=10.10.10.200/24,gw=10.10.10.1 --agent enabled=1 --vga qxl --serial0 socket --ostype l26 --boot order='ide2;scsi0'`
4. `qm start 200` — attended first boot in Proxmox noVNC to confirm Subiquity picks up the seed. **Why Ubuntu Server not Kubuntu**: Kubuntu's live ISO ships Calamares (interactive only); headless autoinstall requires the Subiquity-based Server/live-server ISO. We install `kubuntu-desktop` as a late-command, which still lands Chris in a KDE Plasma session on first login. Trade-off: first boot is longer (~10 min to install the KDE meta-package).
5. Reboot. VM comes up with:
   - Tailscale joined, visible as `kubuntu-ws` on the tailnet
   - SSH reachable over Tailscale
   - RDP (xrdp) listening
   - `~/ubuntu-setup-tool` cloned, owned by `chris`
   - Eject ISOs (`qm set 200 --ide2 none,media=cdrom --ide3 none,media=cdrom` and set boot order to `scsi0` only).
6. Chris connects: Tailscale IP + RDP client, or `ssh chris@kubuntu-ws`. Runs `cd ~/ubuntu-setup-tool && python3 setup.py`.

### Phase 2 — Proxmox on Boochies

1. Via Hetzner Robot API: enable rescue (`POST /boot/{server-number}/rescue` with `os=linux, arch=64`), get rescue root password, `POST /reset` with `type=hw`.
2. SSH into rescue, run `installimage` non-interactively with a config file that lays down Debian 12 on the full disk with the standard Hetzner partition scheme.
3. First boot. Add `pve-no-subscription` repo, `apt update && apt install proxmox-default-kernel`, reboot into PVE kernel, then `apt install proxmox-ve postfix open-iscsi chrony`. Remove `os-prober`. Disable enterprise repo.
4. Reboot. Confirm `https://135.181.215.247:8006` is up.
5. Store `boochies-root` password in Proton Pass (title "Boochies Proxmox — root (current)").

### Phase 3 — Cluster join (vSwitch + corosync)

1. In Hetzner Robot UI/API: create a vSwitch (name `helsinki-cluster`, VLAN `4000`), attach servers `Snoochie` (#2972994) and `Boochies` (#2974693).
2. On each host, add `vmbr2` on VLAN 4000 via `/etc/network/interfaces`:
   - snoochie: `10.0.0.1/24`, MTU 1400
   - boochies: `10.0.0.2/24`, MTU 1400
3. `ifreload -a`; verify `ping -M do -s 1372 10.0.0.2` from snoochie (checks path MTU).
4. From boochies: `pvecm add 10.0.0.1 --link0 10.0.0.2 --link1 135.181.215.247` (two-ring cluster; ring0 private, ring1 public fallback).
5. Verify on snoochie: `pvecm status` shows 2 nodes, 2 rings, Quorate.

### Phase 4 — QDevice (quorum tiebreaker)

1. On `sandstorm-helsinki-1` LXC (CT 100 on snoochie): `apt install corosync-qnetd`.
2. On each cluster node: `apt install corosync-qdevice`.
3. From snoochie: `pvecm qdevice setup <lxc-ip-on-vmbr1>`.
4. Verify: `pvecm status` shows 3 votes (2 nodes + 1 QDevice).

### Phase 5 — README update

Add to `README.md` before "## Modules", a new section `## Network install (Proxmox)` with concrete steps:

1. Prereqs (Proxmox node, ISO storage, some vmbr bridge Chris wants the VM on).
2. Build autoinstall seed from a template we commit to `scripts/proxmox/` (user-data template, `make-seed.sh`).
3. `qm create` one-liner (with variables called out so someone copy-pasting can adjust).
4. Access via Proxmox noVNC for first boot, then switch to SSH/RDP.
5. Cross-link to the existing "## Quick Start" (renamed "## USB install") for bare-metal users.

Also add `scripts/proxmox/` directory with:
- `user-data.template` — autoinstall seed template with `{{SSH_KEY}}`, `{{TAILSCALE_KEY}}`, `{{USERNAME}}` placeholders
- `make-seed.sh` — builds the seed ISO from the template
- `create-vm.sh` — wraps the `qm create` + `qm start` one-liner

## Risks & open questions

1. **Kubuntu live ISO doesn't speak autoinstall** — mitigated by switching to Ubuntu Server ISO + `kubuntu-desktop` late-command. Adds ~10 min to first boot. Confirmed acceptable by design goals ("installed and ready").
2. **Tailscale NAT-to-public** — VM is behind vmbr1 NAT; Tailscale needs outbound UDP to Tailscale's DERP relays. The vmbr1 MASQUERADE rule already allows this.
3. **vSwitch MTU** — Hetzner vSwitch enforces MTU 1400. If anything on `vmbr2` tries 1500, corosync will silently fail. Mitigation: set MTU 1400 on vmbr2 and on corosync ring config.
4. **IP conflict** — snoochie's vmbr1 is `10.10.10.0/24`; boochies vmbr1 will be `10.10.20.0/24` to keep per-node NAT ranges distinct. If we ever want VMs on one node to reach VMs on the other via internal addresses, we route via vmbr2 (and add iptables/forward rules).
5. **QDevice lives in an LXC on snoochie** — losing snoochie loses the QDevice too, but snoochie losing itself is the same failure domain. Documented limitation.
6. **No fencing** — this cluster can live-migrate-if-both-up and share a UI, but a dead node won't be fenced. Acceptable for the current goal.

## Acceptance criteria

- [ ] `https://65.21.205.247:8006` shows VM 200 `kubuntu-ws` running
- [ ] `tailscale status` on monsta-mash shows `kubuntu-ws` online
- [ ] `ssh chris@kubuntu-ws` works using Chris's ed25519 key
- [ ] `cd ~/ubuntu-setup-tool && python3 setup.py` launches the TUI on first login, no prior setup needed
- [ ] RDP from monsta-mash to `kubuntu-ws` shows a KDE Plasma session
- [ ] `https://135.181.215.247:8006` shows Boochies as a cluster node
- [ ] `pvecm status` on either host shows 2 nodes + 1 QDevice, Quorate, two rings
- [ ] `README.md` in `ubuntu-setup-tool` has "## Network install (Proxmox)" section and `scripts/proxmox/` artifacts
