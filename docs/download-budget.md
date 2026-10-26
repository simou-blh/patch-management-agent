# Download budget

Budget agreed for this machine: **2–5 GB of mobile data**. Prepare the repository
before fetching large artifacts. This is an estimate, not a download cap.

| Component | Planning allowance |
|---|---:|
| Windows Vagrant 2.4.9 installer | 248 MB (verified Content-Length) |
| One headless Debian base box, reused for three VMs | 400–1,000 MB (not measured) |
| Semaphore Linux amd64 container | 358 MB (registry compressed size) |
| Upstream Semaphore MCP container | 100–300 MB (not measured; optional for now) |
| WSL development tools and Python dependencies | 300–700 MB (depends on existing packages) |
| osquery and minimal package setup on three VMs | 300–900 MB (depends on installed state) |
| Advisory cache and deterministic demo packages | 100–300 MB (not measured) |

Reserve approximately **2–4 GB**, with **5 GB available as a buffer**. The Bento box
may differ from the original Debian-box estimate. Resolve its final artifact size
before downloading; do not promise the whole setup fits if metadata is unavailable.
Disk space is separate: reserve approximately **15–25 GB**, growing with snapshots.

Already installed according to local checks: Docker Desktop CLI, OpenCode on Windows,
Kali WSL2, VirtualBox executable at its usual installation path, Python on Windows.
Vagrant and uv were not on the Windows PATH. Check the WSL tools independently.

Savings: reuse Kali, download one base box, avoid a desktop environment, avoid a full
Kali upgrade on mobile data, skip a separate managed Python when system Python is
3.12+, defer the platform core/PostgreSQL, and avoid repeated container pulls. Guest
package installs still consume data separately on each VM unless cached locally.
LLM API traffic, retries and future advisory refreshes add ongoing usage.

Metadata checked on 2026-10-26; direct dependencies, box version and image digests are
pinned in the repository. Transitive Python dependencies are not yet locked.

Sources:

- [Vagrant installer](https://releases.hashicorp.com/vagrant/2.4.9/)
- [Bento Debian 12 box metadata](https://vagrantcloud.com/api/v2/vagrant/bento/debian-12)
- [Semaphore registry metadata](https://registry.hub.docker.com/v2/repositories/semaphoreui/semaphore/tags/latest)
- [Vagrant cached boxes](https://developer.hashicorp.com/vagrant/tutorials/get-started/setup-project)
