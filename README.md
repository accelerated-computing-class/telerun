# Telerun

Telerun is a tool we've developed for [6.S894](https://accelerated-computing-class.github.io/fall24/) which lets you compile and run code on remote servers. This is the repository for the Telerun client.

## Setup

### Step 1: Download

You can download the Telerun client in two ways. Either...

1. ...clone this repository by running `git clone git@github.com:accelerated-computing-class/telerun.git`...
2. ...or, [download the contents of this repo as a `.zip` file](https://github.com/accelerated-computing-class/telerun/archive/refs/heads/main.zip) and unpack it to a destination of your choosing.

Once you've obtained a copy of the Telerun client on your computer, you should have a directory containing two files: `telerun.py` and `connection.json`. You can put these files anywhere you want, but you should always keep `connection.json` in the **same directory** as `telerun.py`, wherever that is. The `telerun.py` script needs `connection.json` to be present in order to work.

### Step 2: Login

Once you've downloaded the Telerun client, you need to configure it with the credentials you'll use to authenticate with the server.

If you're enrolled in [6.S894](https://accelerated-computing-class.github.io/fall24/), you will receive a "login code" by email in the first week of class. Your login code should look something like this:

```
AAAAB2V4YW1wbGWQmQC9fr2Rt7dPGEritcYGPz1wHs+i+557jZ4L6RWumw==
```

To configure Telerun with your credentials, run:

```bash
python3 telerun.py login
```

and copy and paste your login code into the terminal when prompted.

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

## Server Etiquette

Telerun executes student code on the remote server **without sandboxing**. If you wanted to break or take over the remote execution host by submitting a malicious program, you would find that it is not hard to do so.

We ask that you please don't **deliberately** submit malicious code through Telerun. We rely on a certain level of trust and good faith to keep the system running; additionally, we log the username and source code associated with every job submitted, so that if someone tries to abuse the system we can identify them and ask them to stop.

If you manage to **accidentally** break the Telerun system by submitting a buggy program, then Telerun itself is to blame for failing to protect against that failure mode. We ask that you please let us know (email [wbrandon@mit.edu](mailto:wbrandon@mit.edu)), and we'll do our best to fix the issue quickly.
