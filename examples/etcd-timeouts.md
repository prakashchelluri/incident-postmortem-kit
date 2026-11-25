# Postmortem: etcd timeouts on Dev and QA Kubernetes clusters

| | |
|---|---|
| **Date** | Relative timeline (T+0 = first timeouts observed) |
| **Severity** | SEV3 (non-production) |
| **Status** | mitigated, monitoring |
| **Authors** | Platform SRE |
| **Time to detect** | 2h 00m |
| **Time to mitigate** | 5d 0h 00m |

_Blameless postmortem: we look at how systems and processes allowed this to happen, not at who did what._

## Summary

The Dev and QA Kubernetes clusters showed frequent etcd timeouts, which made the API server slow or unavailable for short periods. The underlying storage could not provide the I/O that etcd needs. Moving etcd to SSD helped but was not enough, so fsync was disabled for etcd in Dev and QA only, and container logs were moved off the node disks into a compressed RAM area. Production was not affected and keeps fsync enabled.

## Impact

Engineers and CI pipelines using the Dev and QA clusters saw intermittent API timeouts: kubectl commands hung or failed, and deployments to these environments had to be retried. No production cluster was involved.

## Detection

Reported by teams whose deployments to Dev and QA were timing out. etcd logs on the control plane nodes showed slow request and timeout warnings, which pointed the investigation at etcd rather than at the API server itself.

## Timeline

| Time | Event |
|---|---|
| T+0 | Intermittent API timeouts begin on the Dev and QA clusters. **[start]** |
| T+2h | Teams report failing deployments; etcd logs show slow requests and timeouts. **[detected]** |
| T+1d | Investigation finds etcd disk writes are limited by the storage IOPS available to the control plane nodes (etcd data on HDD). |
| T+3d | etcd data moved from HDD to SSD. Timeouts become less frequent but continue. |
| T+4d | Measurements show the hardware still cannot provide enough I/O for etcd's synchronous (fsync) writes under normal cluster load. |
| T+5d | fsync disabled for etcd on Dev and QA only, as a documented exception for non-production. etcd timeouts stop being reported. **[mitigated]** |
| T+8d | Container log writes identified as an additional source of node disk I/O. Container logs moved to a 1 GB ZRAM-backed compressed RAM area with log rotation. |
| T+9d | Lower log-write disk I/O and lower observed I/O pressure on the nodes. |

## Root cause

etcd persists every write to its write-ahead log and calls fsync before acknowledging it, so its latency follows disk latency. The storage behind the Dev and QA control plane nodes could not deliver the IOPS and latency etcd needs: first on HDD, and still not enough after moving to SSD. Container logs written to the same node disks added more I/O and made the contention worse. There was no pre-provisioning check of etcd's disk requirements for these environments.

## What went well

- etcd logs pointed quickly at disk latency rather than at the API server.
- Changes were made one at a time (SSD, then fsync, then logs), so the effect of each was visible.
- The fsync change was limited to Dev and QA and recorded as a non-production exception.

## What went wrong

- Dev and QA control planes ran on storage that had never been checked against etcd's disk requirements.
- The SSD move alone did not solve the problem, which cost several days.
- There was no alert on etcd disk latency; users noticed before monitoring did.

## Action items

| # | Action | Owner | Due | Status |
|---|---|---|---|---|
| 1 | Provision control plane storage for Dev and QA that meets etcd's disk latency guidance, then re-enable fsync there. | Platform SRE | Next quarter | open |
| 2 | Alert on etcd WAL fsync and backend commit latency (p99) for every cluster. | Observability team | Sprint +1 | open |
| 3 | Add a config check that blocks the fsync-disabled etcd setting on any production cluster. | Platform SRE | Sprint +1 | open |
| 4 | Document the ZRAM log area (1 GB, rotation settings) and that logs held there are lost on node reboot. | Platform SRE | Sprint +1 | done |

## Lessons learned

- Disabling fsync trades durability for speed: etcd can acknowledge writes that are not yet on disk, so a crash can lose or corrupt data. That is acceptable only for environments that can be rebuilt, never for production.

- Check etcd's disk requirements before building a cluster, not after it is slow.
- Look at everything else writing to the same disk (logs, images) when a latency-sensitive service is slow.
- The mitigations reduced I/O pressure; they did not make the hardware sufficient. The real fix is better storage.
