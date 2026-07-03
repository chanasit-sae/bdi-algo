<!-- Written and edited by Napat Srichan <me@napatsc.com> (June 25, 2026) --->

# BDI Young Innovator Hackathon 2026: Dataset Usage & Computing Resource Policy

<sup>Updated on June 29, 2026</sup>

## 1. General Principle

This competition uses a **Closed Dataset in a Closed Environment**. This means:

- The dataset is **closed**. Participants can only access it within the environment provided by the organizers.
- **Any computation on the dataset outside the provided environment is strictly prohibited.**

## 2. Prohibited Actions

The following actions are considered violations of this policy:

- Copying the dataset to a local laptop or desktop for offline development.
- Using other cloud providers[^1] to process the dataset, including AI agents that access the dataset directly.
- Spinning up a web demo on other cloud providers that relays or exposes dataset content.
- Active VPN tunneling, proxying, or any other method that routes internet traffic into the provided VM or Slurm cluster.

[^1]: **"Other cloud providers"** means any computing resource outside the provided environment, including personal laptops, on-premise servers, or third-party cloud platforms (AWS, GCP, Azure, etc.).

## 3. Permitted Actions

The following actions are allowed:

- Observing and processing the dataset inside the provided VM, controlled remotely from a laptop.
- Spinning up a web demo on other cloud providers that does **not** involve the dataset in any way.
- Having AI agents analyze or brainstorm on dataset **metadata only** (e.g., column names, descriptions, schema), not the actual data rows.

## 4. Evidence & Monitoring

The organizers may use the following as evidence when investigating potential violations:

- **Process & Resource Usage Logs**: system-level logs from the VM and Slurm cluster. The monitoring tools used will be disclosed to participants.
- **CCTV Footage**: surveillance footage from the competition area (where applicable).
- **Staff Reports**: observations reported by competition staff.

## 5. Penalties

| Offense | Penalty |
|---------|---------|
| 1st violation of Section 2 | **Warning** |
| 2nd violation of Section 2 | **Disqualification from the competition** |
| Sharing a noticeable portion of the dataset over the internet with clear intent | **Immediate disqualification**, plus notification to the dataset owner |

> [!NOTE]
> Using external computing resources to gain an advantage on the dataset may result in **point deduction** for unfair advantage, and will be considered as a part of violation.

## 6. Notification & Rebuttal

- Staff will directly contact one member of the team via Discord or in-person to notify them of an alleged violation.
- The team may immediately rebut with supporting evidence to the IT staff members.
- The organizers will review the rebuttal and evidence before reaching a **final and conclusive decision**.

## 7. AI Usage Policy

The use of AI (e.g., large language models, code assistants, and similar tools) is permitted under the following guidelines:

| Usage | Allowed? |
|-------|----------|
| writing code and analyzing ideas | Yes |
| reading dataset metadata (column names, schema, descriptions) or example/sample datasets | Yes |
| reading the **full dataset** | No. Considered external computation and is a **violation** |

## 8. Effective Date

| Item | Date |
|------|------|
| This policy takes effect | June 26, 2026 |
| Teams sign the Non-Disclosure Agreement (NDA) for the dataset | July 3, 2026, at on-site registration |

*For any questions regarding this policy, please contact the competition staff.*
