# Resume Point — Kubuntu VM + Helsinki Cluster

**Last updated**: 2026-04-20, mid-session, power loss imminent.

## Context

- Spec: `docs/superpowers/specs/2026-04-20-kubuntu-vm-and-helsinki-cluster-design.md`
- Plan: `docs/superpowers/plans/2026-04-20-kubuntu-vm-and-helsinki-cluster.md` (19 tasks)
- Execution mode: **subagent-driven development** on `main`, no worktree
- Branch is `main`, all commits below already pushed to `origin/main`

## What's done

**Tasks 1–3 complete** (repo scaffolding, all reviewed and pushed):
- Task 1 → commit `98116cd` — `scripts/proxmox/user-data.template` (Subiquity autoinstall, Tailscale key staged in 0600 file + shred'd)
- Task 2 → commit `9e47604` — `scripts/proxmox/meta-data.template`
- Task 3 → commit `254a525` — `scripts/proxmox/make-seed.sh` (cloud-localds branch dropped, always uses genisoimage)

## What's next — resume here

**Task 4: Create `scripts/proxmox/create-vm.sh`** (status: `in_progress` in the task list). This is the last repo-scaffolding task before infrastructure work on Snoochie/Boochies begins. Exact content is in the plan at Task 4.

After Task 4, remaining order:
- 5. Upload Ubuntu Server 24.04 ISO to snoochie (root/`%D8Qhf4PqhfXb3`@`65.21.205.247`)
- 6. rsync `scripts/proxmox/` to snoochie, build seed ISO with Chris's SSH key + the Tailscale key from Proton Pass (`Tailscale — autoinstall auth key (reusable, preauth)`)
- 7. `qm create` VM 200 `kubuntu-ws` on vmbr1 (`10.10.10.200/24`)
- 8. Wait for autoinstall (~25 min), detach ISOs, reboot, verify Tailscale + SSH + xrdp + kubuntu-desktop
- 9. RDP smoke-test, run `python3 setup.py` on first login
- 10–13. Hetzner rescue → installimage Debian 12 → PVE 8 → bridges on Boochies (`135.181.215.247`)
- 14–16. Hetzner vSwitch (VLAN 4000) → vmbr2 MTU 1400 → `pvecm add` from Boochies
- 17. QDevice in CT 100 on snoochie for 2-node quorum tiebreaker
- 18–19. README split into `## USB install` + `## Network install (Proxmox)`, push

## Credentials (all in Proton Pass `Claude` vault)

- **Snoochie Proxmox — root (current)** → `root` / `%D8Qhf4PqhfXb3` at `https://65.21.205.247:8006`
- **Hetzner Robot — API/webservice** → used to enumerate/reboot servers
- **Tailscale — autoinstall auth key (reusable, preauth)** → `tskey-auth-ki9r4Q4Bkm11CNTRL-xkAkwebFHrNft8bWmtFZrN2MkqY5HdB6` (saved this session)
- On monsta-mash: `pass-cli logout --force && pass-cli login --pat <from ~/.claude/credentials.local.md>` if session expires

## Known facts captured during the session

- Snoochie: PVE 8.4.18, hostname `snoochie`, cluster `helsinki` (1 node), 12 vCPU, 125 GiB RAM, `local-lvm` 841 GiB free, `vmbr0` (`65.21.205.247/26`) + `vmbr1` (`10.10.10.0/24` NAT). 3 LXCs already running. No ISOs yet.
- Boochies: Hetzner #2974693, `135.181.215.247`, HEL1-DC3, port 8006 closed → Proxmox NOT yet installed. No vSwitch exists yet.
- Snoochie is HEL1-DC6, Boochies is HEL1-DC3 — different physical DCs, same site; vSwitch latency fine for corosync.
- `sandstorm-helsinki-1` (CT 100) on snoochie is the intended QDevice host.

## How to restart

1. `cd ~/projects/ubuntu-setup-tool && git pull` (just in case)
2. Re-invoke me with something like: "Continue the Kubuntu VM + Helsinki cluster plan from Task 4"
3. I should re-read `docs/superpowers/plans/2026-04-20-kubuntu-vm-and-helsinki-cluster.md` and this file, then resume subagent-driven execution on Task 4.
