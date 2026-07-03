<!-- Written by Napat Srichan <me@napatsc.com> (June 20, 2026) --->

# BDI Young Innovator Hackathon 2026 Computing Resources Guide

Welcome! This guide walks you through every computing resource provided to your team during the hackathon. Whether you are connecting to the KKU VPN for the first time, spinning up a web server on your virtual machine, or running a training job on the H100 GPU cluster. Everything you need is documented here step by step.

---

## Table of Contents

1. [Overview of Provided Resources](#overview-of-provided-resources)
2. [KKU VPN](#kku-vpn)
3. [Virtual Machine](#virtual-machine)
   - [Accessing the VM via SSH](#accessing-the-vm-via-ssh)
   - [Example: Deploy a Simple Web Server with Docker](#example-deploy-a-simple-web-server-with-docker)
4. [H100 AI Cluster](#h100-ai-cluster)
   - [Accessing the LiCO Web Portal](#accessing-the-lico-web-portal)
   - [Example: Submit a Simple Job (Hello World)](#example-submit-a-simple-job-hello-world)
   - [Example: Start a Jupyter Notebook Server with GPU](#example-start-a-jupyter-notebook-server-with-gpu)
   - [Resource Limitations](#resource-limitations)

---

## Overview of Provided Resources

Each team will receive credentials to **three** distinct services. All three services require the KKU VPN to be active before you can reach them (see the [KKU VPN](#kku-vpn) section below).

| Resource | Purpose | Credentials Provided |
|---|---|---|
| **KKU VPN account** | Grants access to services that live inside the KKU campus network (the VM and the H100 cluster are behind this VPN). | Registered Email (sent to its inbox) |
| **Virtual machine** | A general-purpose Ubuntu server for hosting web servers, databases, APIs, or any on-premise service your project needs. | IP address, Username, Password |
| **H100 AI cluster** | A GPU-powered cluster for machine learning training, heavy inference, or any short-lived compute-intensive task. | Username, Password |

> **Important dates:**
> - **June 26, 2026**: All credentials will be distributed to every group **via Discord**.
> - **July 3, 2026**: The full dataset will be made available on the virtual machine and H100 cluster.

---

## KKU VPN

Before you can reach **either** the virtual machine or the H100 AI cluster, you must be connected to the KKU VPN. Think of the VPN as a secure tunnel that lets your computer talk to services inside the KKU campus network as if you were physically on campus.

### What you will receive

| Item | Description |
|---|---|
| **Activation link** | Your VPN registeration is made by the activation link sent to the leader email inbox. |

### How to connect

Refer to this document: <https://kku.world/ztnaguide>

---

## Virtual Machine

Each team gets a dedicated **Ubuntu Server 26.04 LTS** virtual machine. It is suitable for running web servers, databases, APIs, data-processing pipelines, or any backend service you want to build for your hackathon project.

### Machine specification

| Resource | Allocation |
|---|---|
| Operating system | Ubuntu Server 26.04 LTS |
| CPU | 4 cores |
| Memory | 8 GB RAM |

### Pre-installed software

The following tools are already installed and ready to use:

- **Node.js** (`node`): for running JavaScript / TypeScript applications.
- **uv**: a fast Python package and project manager (alternative to `pip`/`poetry`).
- **Docker** (`docker`): for running containerised applications.

You can install any additional development or deployment tools of your choice using Ubuntu's package manager:

```bash
sudo apt update
sudo apt install <package-name>
```

### What you will receive

| Item | Description |
|---|---|
| **IP address** | The IP address of your VM. |
| **Username** | The SSH user you will log in as. |
| **Password** | The corresponding SSH password. |

> [!NOTE]
> We officially support accessing the virtual machine **only via terminal (SSH)**. If you prefer to use a GUI client (e.g., PuTTY, VS Code Remote SSH, Termius), you are free to do so, but any issues that arise from the GUI client are outside our scope of support.

### Accessing the VM via SSH

SSH (Secure Shell) is the standard way to log into a remote Linux machine from your terminal. The steps are the same across all operating systems. You just need to know where your terminal is.

1. **Open a terminal** on your computer:
  - **macOS**: Open **Terminal** (Applications > Utilities).
  - **Linux**: Open your preferred terminal emulator (e.g., GNOME Terminal, Konsole, xterm).
  - **Windows**: Open **PowerShell**, **Command Prompt**, or [Windows Terminal](https://apps.microsoft.com/detail/9n0dx20hk701).

2. Run the SSH command below, replacing `<YOUR-USERNAME>` and `<YOUR-VM-IP-ADDRESS>` with the credentials you received:

   ```bash
   ssh <YOUR-USERNAME>@<YOUR-VM-IP-ADDRESS>
   ```

3. The first time you connect, you will see a message like:

   ```
   The authenticity of host '...' can't be established.
   Are you sure you want to continue connecting?
   ```

   Type `yes` and press Enter to continue. This adds the VM to your list of known hosts.

4. When prompted, enter the password that was provided to you. **Note:** the password characters will not show on screen as you type. This is normal.

5. You should now see a command prompt that looks something like:

   ```
   group-demo@bdihack-vm:~$
   ```

   Congratulations! You are now logged into the virtual machine!

---

### Example: Deploy a Simple Web Server with Docker

This example walks you through running an Nginx web server inside a Docker container on your VM. Nginx is a popular web server that can serve static files or act as a reverse proxy.

1. **Log in to the virtual machine** using the SSH steps described above.

2. **Pull the Nginx image** from Docker Hub:

   ```bash
   docker pull nginx:latest
   ```

   This downloads the official Nginx container image to your machine.

3. **Run an Nginx container** in detached mode (`-d`), mapping port 8080 on the VM to port 80 inside the container:

   ```bash
   docker run -d --name my-web-server -p 8080:80 nginx:latest
   ```

   | Flag | Meaning |
   |---|---|
   | `-d` | Detached mode: runs the container in the background. |
   | `--name my-web-server` | Gives the container a human-readable name. |
   | `-p 8080:80` | Maps host port 8080 to container port 80. |

4. **Verify the container is running:**

   ```bash
   docker ps
   ```

   You should see a line with `my-web-server` and status `Up`.

5. **Test the web server.** From your local machine (not inside the VM), open a browser and navigate to:

   ```
   http://<YOUR-VM-IP-ADDRESS>:8080
   ```

   You should see the Nginx welcome page.

6. **Stopping and cleaning up** (when you are finished):

   ```bash
   docker stop my-web-server
   docker rm my-web-server
   ```

---

## H100 AI Cluster

The H100 AI cluster provides access to NVIDIA H100 GPUs, which are powerful accelerators ideal for training deep learning models, running large-scale inference, or performing any compute-heavy task that benefits from GPU parallelism.

> **Note:** This cluster is intended for **short, powerful tasks**. It is not a persistent server like the virtual machine. Jobs are submitted through a queue system, run on allocated GPU nodes, and exit when they finish.

The cluster is managed by **LiCO** (Life Cycle of Jobs), a web-based interface that sits on top of **SLURM**. You will do almost everything through the LiCO web portal: uploading files, creating and submitting jobs, monitoring progress, and retrieving results.

---

### What you will receive

| Item | Description |
|---|---|
| **Username** | Your personal login name for the cluster's LiCO web portal. |
| **Password** | The corresponding password for the username above. |

---

### Accessing the LiCO Web Portal

1. **Connect to the KKU VPN** first (see [KKU VPN](#kku-vpn) section). The cluster is not reachable without the VPN.

2. **Open your web browser** and go to:

   ```
   https://10.198.253.15:8000
   ```

3. **Accept the self-signed certificate warning.** The cluster portal uses a self-signed certificate, so your browser may show a security warning (e.g., "Your connection is not private"). It is safe to proceed. Click **Advanced** → **Proceed to 10.198.253.15:8000** (or similar).

4. **Log in** with the username and password you received.

   You will land on the LiCO dashboard. From here you can:
  - Upload and manage files using the built-in **file tree**.
  - Create and submit jobs using **Job Templates**.
  - Monitor running jobs in **Job Monitoring**.

---

### Example: Submit a Simple Job (Hello World)

This example walks you through submitting your first job entirely through the LiCO web interface. No terminal needed.

Go to <https://10.198.253.15:8000> and log in with your credentials (see [Accessing the LiCO Web Portal](#accessing-the-lico-web-portal) above).

1. Go to **Job Templates** in the left sidebar.
2. Select **Common Job** (the most flexible template; it runs any shell script or command directly on a compute node).
3. Fill in the form:

   | Field | Value |
   |---|---|
   | **Job Name** | `hello-world` (alphanumeric, underscores allowed) |
   | **Workspace** | Pick the directory of your project |
   | **Queue** | `GPU_FOR_BDI` |
   | **Node** | `1` |
   | **CPU Cores Per Node** | `1` |
   | **GPU Per Node** | `0` (no GPU needed for this simple example) |
   | **Memory Used** | `256` (MB) |
   | **Wall Time** | `00:10:00` (10 minutes) |

4. In the **Run Script** field, enter:

   ```bash
   echo "hello world"
   ```
5. Click **Submit**.
6. Go to **Job Monitoring** in the left sidebar.
7. Your job will first appear in the **Waiting** tab (queued, waiting for resources), then move to **Running**, and finally to **Completed**.
8. Click on the **job name** (not the scheduler ID) → **Log** tab to see the output.

If everything worked, you should see:

```
hello world
```

### Example: Start a Jupyter Notebook Server with GPU

If you want an interactive coding environment to explore data, train models, or visualise results, all while having a GPU available, you can launch a Jupyter Notebook server as a job on the cluster. Follow the same flow as the Hello World example above, but with a different script and resource settings.

1. **Log in** to <https://10.198.253.15:8000> (see [Accessing the LiCO Web Portal](#accessing-the-lico-web-portal)).

2. Go to **Job Templates** → **Common Job**.

3. Fill in the form:

   | Field | Value |
   |---|---|
   | **Job Name** | `jupyter-gpu` |
   | **Workspace** | Pick the directory of your project |
   | **Queue** | `GPU_FOR_BDI` |
   | **Node** | `1` |
   | **CPU Cores Per Node** | `2` |
   | **GPU Per Node** | `1` |
   | **GPU Resource Type** | `gpu:STU_GPU` |
   | **Memory Used** | `8192` (8 GB in MB) |
   | **Wall Time** | `06:00:00` (6 hours; adjust as needed) |

4. In the **Run Script** field, enter:

   ```bash
   # Install uv (fast Python package manager)
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Source it so the 'uv' command becomes available in this session
   . $HOME/.bashrc

   # Launch the Jupyter Notebook server
   # --ip 10.198.199.202 binds to the cluster's internal network so you can reach it
   uvx jupyter server --ip 10.198.199.202
   ```

   > **What this does:** The script first installs `uv` (if not already present), then uses it to run Jupyter without needing a manual Python environment setup. The `--ip 10.198.199.202` flag tells Jupyter to listen on a specific internal IP so you can connect to it from your browser.

5. Click **Submit**.

6. Go to **Job Monitoring**. Once the job moves from **Waiting** → **Running**, click the **job name** → **Log** tab.

7. After a few seconds, the log will show Jupyter's startup output. Look for a line that looks like:

   ```
   http://10.198.199.202:8888/tree?token=abc123...
   ```

   This is your Jupyter URL. Copy the entire link.

8. **Paste the link** into your browser. You should see the Jupyter file browser, where you can create new notebooks, upload files, and run code, all backed by the cluster's GPU.

> [!TIP]
>
> - The Jupyter server runs **only as long as the job is running**. If the job exits or reaches the wall time, the server stops. Keep the wall time long enough for your work session.
> - If you want to keep working later, you can submit a new Jupyter job (or copy this one using the **Copy Job** action in Job Monitoring).
---

### Resource Limitations

Be mindful of the following limits when configuring your jobs. Jobs that exceed these limits may get stuck in the queue indefinitely.

| Resource | Amount |
|---|---|
| CPU cores per job | 4 |
| Memory per job | 8 GiB |
| GPU per job | 1 (10 GB MIG) |
| Wall time (max duration) | 7 days |

---

## Need help?

If you run into any trouble, reach out via the official hackathon Discord channel. Include as much detail as possible (screenshots, error messages, what step you were on) so we can help you quickly.

Good luck, and happy hacking! 🚀
