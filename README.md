# Telerun

Telerun is a tool we've developed for [6.S894](https://accelerated-computing-class.github.io/fall24/) which lets you compile and run code on remote servers. This is the repository for the Telerun client.

## Setup

### Step 1: Download

Download the Telerun client by cloning this git repo:

```bash
git clone git@github.com:accelerated-computing-class/telerun.git
```
If your Python version is less than `3.11.0`, please upgrade python.

Once you've obtained a copy of the Telerun client on your computer, you should have a directory containing `telerun.py`.

### Step 2: Login

Once you've downloaded the Telerun client, you need to configure it with the credentials you'll use to authenticate with the server.

If you're enrolled in [6.S894](https://accelerated-computing-class.github.io/fall24/), you will receive a username and token by email in the first week of class. Your token should look something like this:

```
4ed3536faf4ac1440b996a2f770578a26e1855f2ce11af15b64a4f18ac1e7cd5
```

To configure Telerun with your credentials, run:

```bash
python3 telerun.py login
```

and copy and paste your username and token into the terminal when prompted.

This will create a file `auth.json` in the same directory as your Telerun install. You should keep `auth.json` in the **same directory** as `telerun.py`, wherever that is.

## Using Telerun

### Submitting Jobs

Once you've downloaded the client and logged in, you can submit programs to be compiled and executed by running:

```python
python3 telerun.py submit my_program.cpp
```

This uploads your source code to the server and creates a "job," which is a unit of work to be executed by the Telerun server.

### Running on Different Platforms

Currently, Telerun can run jobs on either a powerful CPU-only x86-64 execution host, or a GPU-enabled execution host (with weaker CPUs). The availability of different platforms may vary week-by-week over the course of the semester.

* **To run C++ code on the CPU-only host**: make sure your source filename ends with the **extension `.cpp`**
* **To run CUDA code on the GPU-enabled host**: make sure your source filename ends with the **extension `.cu`**

### Job Output

When you submit a Telerun job, the Telerun client saves the job's output on your local machine at the path `./telerun-out/<job_id>/`, relative to the current working directory.

The terminal output from compiling and executing your job will be saved to `./telerun-out/<job_id>/compile_log.txt` and `./telerun-out/<job_id>/execute_log.txt`.

Additionally, the program you submit can write arbitrary output files to the directory `./out/` **on the remote server**, and any files in that directory will be downloaded and saved on your local machine in the directory `./telerun-out/<job_id>/`.

If you want ASM/PTX/SASS output, you can run Telerun with the `--asm` flag.

## Server Etiquette

Telerun executes student code on the remote server **without sandboxing**. If you wanted to break or take over the remote execution host by submitting a malicious program, you would find that it is not hard to do so.

We ask that you please don't **deliberately** submit malicious code through Telerun. We rely on a certain level of trust and good faith to keep the system running; additionally, we log the username and source code associated with every job submitted, so that if someone tries to abuse the system we can identify them and ask them to stop.

If you manage to **accidentally** break the Telerun system by submitting a buggy program, then Telerun itself is to blame for failing to protect against that failure mode. We ask that you please let us know (email [somo@mit.edu](mailto:somo@mit.edu)), and we'll do our best to fix the issue quickly.
