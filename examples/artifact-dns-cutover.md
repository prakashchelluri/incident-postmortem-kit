# Postmortem: Artifact downloads failing after a DNS cut-over

| | |
|---|---|
| **Date** | Relative timeline (T+0 = GeoDNS change applied) |
| **Severity** | SEV2 |
| **Status** | resolved |
| **Authors** | Platform SRE |
| **Time to detect** | 40m |
| **Time to mitigate** | 2h 30m |
| **Time to resolve** | 1d 2h 00m |

_Blameless postmortem: we look at how systems and processes allowed this to happen, not at who did what._

## Summary

A GeoDNS change pointed artifacts.example.com at a new repository site. Clusters in one region then could not pull artifacts: pulls hung. Replication to the new site was incomplete, so many versions did not exist there. The DNS change was rolled back and pulls recovered, but the next day jobs failed again because the rollback had not restored the original state: not all repositories were configured in federated mode. The owning team fixed this within about an hour of coming on duty.

## Impact

Build and deployment jobs in the affected region that needed artifacts from the repository hung or failed, first after the DNS change and again the following day. Other regions were not affected.

## Detection

Teams in the affected region reported pipelines hanging while downloading artifacts. There was no alert on artifact pull failures or latency.

## Timeline

| Time | Event |
|---|---|
| T+0 | GeoDNS updated so artifacts.example.com resolves to the new site for one region. **[start]** |
| T+40m | Pipelines in the region report artifact pulls hanging. **[detected]** |
| T+1h | Network path between the clusters and the new site investigated first; nothing wrong found there. |
| T+1h 45m | Comparing the two sites shows the new site only has versions up to v5, while the original site has up to v10: replication to the new site is incomplete. |
| T+2h | Decision to roll back the DNS change. The rollback procedure did not cover the new site and had to be adjusted before it could be applied. |
| T+2h 30m | DNS rolled back to the original site; artifact pulls verified from the region. **[mitigated]** |
| T+1d | Jobs fail again. The rollback had not restored the original state: not all repositories were configured in federated mode. |
| T+1d 1h | Owning team for the repository platform comes on duty and starts the fix. |
| T+1d 2h | Federated mode configured for the remaining repositories; jobs succeed again. **[resolved]** |

## Root cause

The cut-over was made before replication to the new site was complete, so requests routed there asked for versions that did not exist and the pulls hung. The rollback procedure had not been tested against the new topology: it needed manual changes during the incident, and it did not return every repository to its original federated configuration, which caused the second failure the next day.

## What went well

- Comparing the two sites side by side found the version gap quickly once network checks came back clean.
- The DNS rollback restored pulls the same day.
- Once the owning team was on duty, the second failure was fixed within about an hour.

## What went wrong

- No check that replication was complete before changing DNS.
- The rollback procedure was untested and did not include the new site.
- The rollback left some repositories outside federated mode, which only surfaced the next day.
- The team that owns the repository platform was not on duty in the affected time zone.
- The first hypothesis (network) was checked before the cheaper "is the content there?" question.

## Action items

| # | Action | Owner | Due | Status |
|---|---|---|---|---|
| 1 | Add a pre-cut-over gate that compares repository contents (latest version per repository) between sites and blocks the DNS change on any difference. | Repository platform team | Sprint +1 | open |
| 2 | Rewrite the DNS rollback procedure to cover both sites and the federated configuration of every repository, and rehearse it in a test environment. | Platform SRE | Sprint +2 | open |
| 3 | Alert on artifact pull latency and failures per region. | Observability team | Sprint +1 | open |
| 4 | Schedule infrastructure cut-overs only when the owning team has someone on duty in every affected time zone, or arrange cover in advance. | Change management | Sprint +1 | done |

## Lessons learned

- Verify replication completeness before any cut-over.
- Test the rollback procedure itself; an untested rollback is a second change, not a safety net.
- After a rollback, verify the full original state, not only that the symptom went away.
- Make sure an owner is on duty across time zones for changes that affect other regions.
