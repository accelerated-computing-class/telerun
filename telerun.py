#!/usr/bin/env python3

import argparse
import urllib
import urllib.parse
import urllib.request
import ssl
import os
import json
import traceback
import time
import base64
import sys
from datetime import datetime
import textwrap
import tarfile
import io
import struct

version = "0.1.2"

network_timeout = 120 # seconds
poll_interval = 0.25 # seconds

job_id_digits = 7 # minimum number of digits to display for job IDs

script_file = os.path.realpath(__file__)

def get_script_dir():
    return os.path.dirname(os.path.abspath(script_file))

def render_job(job_id):
    return str(job_id).zfill(job_id_digits)

def get_connection_config(args):
    if hasattr(args, "connection") and args.connection is not None:
        config_path = args.connection
    else:
        config_path = os.path.join(get_script_dir(), "connection.json")
    if not os.path.exists(config_path):
        print(f"No connection config found at {config_path!r}", file=sys.stderr)
        exit(1)
    with open(config_path, "r") as f:
        config = json.load(f)
    if not isinstance(config, dict):
        print(f"Invalid connection config at {config_path!r}", file=sys.stderr)
        exit(1)
    if not isinstance(config.get("domain"), str):
        print(f"Connection config at {config_path!r} missing field 'domain' of type string", file=sys.stderr)
        exit(1)
    if not isinstance(config.get("port"), int):
        print(f"Connection config at {config_path!r} missing field 'port' of type int", file=sys.stderr)
        exit(1)
    if not isinstance(config.get("cert"), str):
        print(f"Connection config at {config_path!r} missing field 'cert' of type string", file=sys.stderr)
        exit(1)
    return config

def get_auth_config(args):
    if args.auth is not None:
        config_path = args.auth
    else:
        config_path = os.path.join(get_script_dir(), "auth.json")
    if not os.path.exists(config_path):
        print(
            f"No authentication config found at {config_path!r}\n"
            "\n"
            "To create your authentication config, run:\n"
            "\n"
            "    python3 telerun.py login\n"
            "\n",
            end="",
            file=sys.stderr
        )
        exit(1)
    with open(config_path, "r") as f:
        config = json.load(f)
    if not isinstance(config, dict):
        print(f"Invalid auth config at {config_path!r}", file=sys.stderr)
        exit(1)
    if not isinstance(config.get("username"), str):
        print(f"Auth config at {config_path!r} missing field 'username' of type string", file=sys.stderr)
        exit(1)
    if not isinstance(config.get("token"), str):
        print(f"Auth config at {config_path!r} missing field 'token' of type string", file=sys.stderr)
        exit(1)
    return config

def decode_login_code(login_code):
    raw = base64.standard_b64decode(login_code)
    username_len = struct.unpack(">I", raw[:4])[0]
    username = raw[4:4 + username_len].decode("utf-8")
    token = raw[4 + username_len:].hex()
    return {
        "username": username,
        "token": token,
    }

class Context:
    def __init__(self, *, connection, auth=None):
        self.connection = connection
        self.auth = auth
        self.ssl_ctx = ssl.create_default_context(cadata=connection["cert"])

    def request(self, method, path, params, *, body=None, use_auth=False, use_version=True):
        assert path.startswith("/")
        params = dict(params)
        if use_version:
            params["v"] = version
        if use_auth:
            assert self.auth is not None
            params["username"] = self.auth["username"]
            params["token"] = self.auth["token"]
        url = "https://" + self.connection["domain"] + ":" + str(self.connection["port"]) + path + "?" + urllib.parse.urlencode(params, doseq=True)
        if body is not None:
            body = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, method=method, data=body)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=network_timeout) as response:
            return json.load(response)

def request_version(ctx):
    return ctx.request("GET", "/api/version", {}, use_version=False)

def at_least_version(compat_version):
    curr_parts = [int(part) for part in version.split(".")]
    try:
        compat_parts = [int(part) for part in compat_version.split(".")]
        return compat_parts <= curr_parts
    except ValueError:
        return False

def check_version(ctx):
    response = request_version(ctx)
    if response["latest_user"] != version:
        supported = at_least_version(response["compat_user"])
        if supported:
            print(f"A new Telerun client version is available (version {response['latest_user']})", file=sys.stderr)
        else:
            print(f"Version {version} of the Telerun client is no longer supported", file=sys.stderr)
        print("\nTo update, pull the latest commit from the Telerun repository\n", file=sys.stderr)
        # # Work in progress:
        # print(
        #     "\n"
        #     f"To update to version {response['latest_user']}, run:\n"
        #     "\n"
        #     "    python3 telerun.py update\n",
        #     "\n",
        #     end="",
        #     file=sys.stderr,
        # )
        if not supported:
            exit(1)

platforms = {
    "x86_64",
    "cuda",
}

filename_platforms = {
    "cpp": "x86_64",
    "cu": "cuda",
}

def cancel_pending(ctx, job_id):
    try:
        response = ctx.request("POST", "/api/cancel", {"job_id": job_id}, use_auth=True)
        assert response["success"] is True
        return "success"
    except urllib.error.HTTPError as e:
        if e.code == 400:
            response_json = json.load(e)
            if response_json.get("error") in {"not_found", "already_executing"}:
                return response_json["error"]
        raise

def get_job_spec(ctx, args, *, cond):
    if args.latest and args.job_id is not None:
        print("Arguments '--latest' and '<job_id>' are mutually exclusive", file=sys.stderr)
        exit(1)

    if args.latest:
        response = ctx.request("GET", "/api/jobs", {}, use_auth=True)
        assert response["success"] is True
        jobs = response["jobs"]
        jobs = [job for job in jobs if cond(job)]
        if not jobs:
            return None
        return jobs[-1]
    elif args.job_id is not None:
        return args.job_id
    else:
        print("Missing argument '<job_id>' or '--latest'", file=sys.stderr)
        exit(1)

def get_out_dir(args, job_id):
    if args.out is not None:
        out_dir = args.out
    else:
        out_dir = os.path.join(os.curdir, "telerun-out", render_job(job_id))
    return out_dir

def timestamp():
    return datetime.now().strftime("%Y-%m-%d %I:%M %p")

def submit_handler(args):
    # # Work in progress:
    # if args.async_ and args.out is not None:
    #     print("Arguments '--out' and '--async' are mutually exclusive", file=sys.stderr)
    #     print("To get the output of an asynchronous job, use 'telerun.py get-output <job_id>'", file=sys.stderr)
    #     exit(1)

    connection = get_connection_config(args)
    auth = get_auth_config(args)
    ctx = Context(connection=connection, auth=auth)

    check_version(ctx)

    if args.platform is None:
        if args.file.endswith(".cpp"):
            platform = "x86_64"
        elif args.file.endswith(".cu"):
            platform = "cuda"
        else:
            supported_filenames = ", ".join(f"'*.{ext}'" for ext in filename_platforms.keys())
            supported_platforms = ", ".join(repr(platform) for platform in platforms)
            print(
                f"Could not infer platform from filename {os.path.basename(args.file)!r}\n"
                f"Supported filenames: {supported_filenames}\n"
                "\n"
                "You can also specify the platform explicitly with '--platform'\n"
                f"Supported platforms: {supported_platforms}\n",
                end="",
                file=sys.stderr,
            )
            exit(1)
    elif args.platform not in platforms:
        print(
            f"Unsupported platform {args.platform!r}\n"
            f"Supported platforms: {', '.join(repr(platform) for platform in platforms)}\n",
            end="",
            file=sys.stderr,
        )
        exit(1)
    else:
        platform = args.platform

    with open(args.file, "r") as f:
        source = f.read()

    options = {
        "args": args.args,
    }

    submit_query_args = {}
    if args.force:
        submit_query_args["override_pending"] = "1"

    try:
        submit_response = ctx.request("POST", "/api/submit", submit_query_args, body={
            "platform": platform,
            "source": source,
            "options": options,
        }, use_auth=True)
    except urllib.error.HTTPError as e:
        if e.code == 400:
            response_json = json.load(e)
            if response_json.get("error") == "pending_job":
                print(
                    "You already have a pending job\n"
                    "Pass '--force' if you want to replace it\n",
                    end="",
                    file=sys.stderr,
                )
                exit(1)
        raise

    assert submit_response["success"] is True
    job_id = submit_response["job_id"]

    print()
    print(f"{timestamp()}    submitted job {render_job(job_id)}")
    print()

    # if args.async_:
    #     return

    out_dir = get_out_dir(args, job_id)

    milestones_specs = {
        "compile_claim": "compiling",
        "compile_complete": "compiled successfully",
        "execute_claim": "executing",
        "execute_complete": "completed successfully",
        "compile_fail": "compilation failed",
        "execute_fail": "execution failed",
    }

    log_milestone_specs = {
        "compile_output": {"msg": "compile output", "key": "compile_log"},
        "execute_output": {"msg": "output", "key": "execute_log"},
    }

    compile_all = ["compile_claim", "compile_output", "compile_complete"]

    state_histories = {
        ("compile", False, None): [],
        ("compile", True, None): ["compile_claim"],
        ("execute", False, None): compile_all,
        ("execute", True, None): compile_all + ["execute_claim"],
        ("complete", False, "success"): compile_all
        + ["execute_claim", "execute_output", "execute_complete"],
        ("complete", False, "compile_fail"): [
            "compile_claim",
            "compile_output",
            "compile_fail",
        ],
        ("complete", False, "execute_fail"): compile_all
        + ["execute_claim", "execute_output", "execute_fail"],
    }

    def check_deleted(payload):
        if payload is None:
            print(f"{timestamp()}    job {render_job(job_id)} deleted by server")
            print()
            exit(1)

    milestones_seen = set()

    try:

        while True:

            time.sleep(poll_interval)
            status_response = ctx.request("GET", "/api/status", {"job_id": job_id}, use_auth=True)
            assert status_response["success"] is True
            status = status_response["status"]
            check_deleted(status)

            # download and extract the output archive before printing the completion message so
            # that the user doesn't accidentally CTRL+C out of the script before we've saved all
            # the output
            if status["curr_phase"] == "complete":
                output_archive_response = ctx.request("GET", "/api/output", {"job_id": job_id, "keys": "output_tar_gz"}, use_auth=True)
                assert output_archive_response["success"] is True
                check_deleted(output_archive_response["output"])
                output_archive_base64 = output_archive_response["output"].get("output_tar_gz")
                if output_archive_base64 is not None:
                    output_archive = base64.b64decode(output_archive_base64)
                    os.makedirs(out_dir, exist_ok=True)
                    with io.BytesIO(output_archive) as output_archive_f:
                        with tarfile.open(fileobj=output_archive_f) as tar:
                            tar.extractall(out_dir, filter="data")

            curr_state = (status["curr_phase"], status["claimed"], status["completion_status"])
            for milestone in state_histories[curr_state]:
                if milestone in milestones_seen:
                    continue
                milestones_seen.add(milestone)
                if milestone in milestones_specs:
                    print(f"{timestamp()}    {milestones_specs[milestone]}")
                    print()
                elif milestone in log_milestone_specs:
                    key = log_milestone_specs[milestone]["key"]
                    log_response = ctx.request("GET", "/api/output", {"job_id": job_id, "keys": key}, use_auth=True)
                    assert log_response["success"] is True
                    check_deleted(log_response["output"])
                    milestone_log = log_response["output"][key]
                    if milestone_log is None:
                        milestone_log = ""
                    os.makedirs(out_dir, exist_ok=True)
                    with open(os.path.join(out_dir, key.replace("_", "-")) + ".txt", "w") as f:
                        f.write(milestone_log)
                    if milestone_log.strip():
                        print(f"{timestamp()}    {log_milestone_specs[milestone]['msg']}:")
                        print()
                        print(textwrap.indent(milestone_log, "    "), end="" if milestone_log.endswith("\n") else "\n")
                        print()
                else:
                    assert False

            if status["curr_phase"] == "complete":
                completion_status = status["completion_status"]
                if completion_status != "success":
                    exit(1)
                break

    except KeyboardInterrupt:
        cancel_result = cancel_pending(ctx, job_id)
        if cancel_result != "success":
            print(f"{timestamp()}    detached from job")
            print()

            # # Work in progress:
            # print(f"Job {render_job(job_id)} is already executing and will run to completion")
            # print()
            # print("To track its progress, run:")
            # print()
            # print("    python3 telerun.py list-jobs")
            # print()
            # print("To get its output when it completes, run:")
            # print()
            # print(f"    python3 telerun.py get-output {job_id}")
            # print()
        else:
            print(f"{timestamp()}    cancelled job")
            print()
        exit(130)


def cancel_handler(args):
    connection = get_connection_config(args)
    auth = get_auth_config(args)
    ctx = Context(connection=connection, auth=auth)

    check_version(ctx)

    def is_cancellable(job):
        if job["curr_phase"] == "complete":
            return False
        if job["curr_phase"] == "execute":
            return job["curr_phase_claimed_at"] is None
        return True

    job = get_job_spec(ctx, args, cond=is_cancellable)
    if job is None:
        print("No pending jobs to cancel")
        return
    job_id = job["job_id"]

    cancel_result = cancel_pending(ctx, job_id)
    if cancel_result == "success":
        print(f"Cancelled job {render_job(job_id)}")
    elif cancel_result == "not_found":
        print(f"Job {render_job(job_id)} not found")
    elif cancel_result == "already_executing":
        print(f"Job {render_job(job_id)} is already executing and will run to completion")

def version_handler(args):
    print("Telerun client version:   " + version)
    if hasattr(args, "offline") and args.offline:
        return
    connection = get_connection_config(args)
    ctx = Context(connection=connection)
    response = request_version(ctx)
    print(f"Latest supported version: {response['compat_user']}")
    print(f"Latest available version: {response['latest_user']}")
    if not at_least_version(response["latest_user"]):
        print()
        print("To update, pull the latest version from the Telerun repository")
        print()

# # Work in progress:
# def update_handler(args):
#     connection = get_connection_config(args)
#     ctx = Context(connection=connection)
#     version_response = request_version(ctx)
#     latest_version = version_response["latest_user"]
#     if latest_version == version and not args.force:
#         print("Already up to date with version " + version)
#         return
#     print("Current version: " + version)
#     print("Available version: " + latest_version)

#     i = 0
#     backup_path = os.path.join(get_script_dir(), "/old-telerun-v{version}.py.backup")
#     while os.path.exists(backup_path):
#         i += 1
#         backup_path = os.path.join(get_script_dir(), "/old-telerun-v{version}-{i}.py")

#     if not args.yes:
#         print()
#         print(f"Update {script_file!r} to version {latest_version}?")
#         print(f"(A backup of the current version will be saved to {backup_path!r})")
#         print("[Y/n] ", end=" ")
#         prompt_response = input().strip().lower()
#         if prompt_response not in {"", "y", "yes"}:
#             print("Cancelled")
#             return
#     # TODO: Strictly speaking there's a race condition here where the user could update to a new
#     # version that's released between the time they check and the time they update. This is probably
#     # fine for now, but it could be fixed by checking the version again after the update.
#     update_response = ctx.request("GET", "/api/update", {"client_type": "user"}, use_version=False)

#     os.rename(script_file, backup_path)
#     print(f"Saved backup of old client to {backup_path!r}")

#     with open(script_file, "w") as f:
#         f.write(update_response["source"])

#     print(f"Successfully updated {script_file!r} to version {latest_version}")

# # Work in progress:
# def list_jobs_handler(args):
#     raise NotImplementedError()

# # Work in progress:
# def get_output_handler(args):
#     raise NotImplementedError()

def login_handler(args):
    if args.auth is None:
        auth_path = os.path.join(get_script_dir(), "auth.json")
    else:
        auth_path = args.auth
    if os.path.exists(auth_path) and not args.force:
        print(
            f"Authentication file {auth_path!r} already exists\n"
            "Pass '--force' if you want to replace it\n",
            end="",
            file=sys.stderr
        )
        exit(1)
    if args.login_code is None:
        print("Enter your Telerun login code:")
        print(">>> ", end="")
        login_code = input()
    else:
        login_code = args.login_code
    login_code = login_code.strip()
    auth_config = decode_login_code(login_code)
    with open(auth_path, "w") as f:
        json.dump(auth_config, f, indent=2)
    print(f"Saved authentication config to {auth_path!r}")

def add_connection_config_arg(parser):
    parser.add_argument("--connection", help="connection config file (defaults to 'connection.json' in the same directory as your Telerun install)")

def add_auth_arg(parser):
    parser.add_argument("--auth", help="user authentication file (defaults to 'auth.json' in the same directory as your Telerun install)")

def add_out_dir_arg(parser):
    parser.add_argument("--out", help="directory to which to write job output (defaults to './telerun-out/<job_id>' in the current working directory)")

def add_job_spec_arg(parser):
    parser.add_argument("job_id", help="the ID of the job", nargs="?")
    parser.add_argument("--latest", action="store_true", help="use the latest job")

def main():
    parser = argparse.ArgumentParser(description="Remote Code Execution as a Service", )
    subparsers = parser.add_subparsers(title='subcommands', dest='subcommand')

    parser.add_argument("--version", action="store_true", dest="version_flag", help="alias for 'version'")

    submit_parser = subparsers.add_parser('submit', help='submit a job')
    add_connection_config_arg(submit_parser)
    add_auth_arg(submit_parser)
    submit_parser.add_argument("-f", "--force", action="store_true", help="allow overriding pending jobs")
    add_out_dir_arg(submit_parser)
    submit_parser.add_argument("-p", "--platform", help="platform on which to run the job (default is inferred from filename: {})".format(", ".join([f"'*.{ext}' -> {platform!r}" for ext, platform in filename_platforms.items()])), choices=list(platforms))
    submit_parser.add_argument("file", help="source file to submit")
    submit_parser.add_argument("args", nargs=argparse.REMAINDER, help="arguments for your program")

    # # Work in progress:
    # submit_parser.add_argument("--async", action="store_true", dest="async_", help="do not wait for the job to complete")

    submit_parser.set_defaults(func=submit_handler)

    # # Work in progress:
    # cancel_parser = subparsers.add_parser('cancel', help='cancel a job')
    # add_connection_config_arg(cancel_parser)
    # add_auth_arg(cancel_parser)
    # add_job_spec_arg(cancel_parser)
    # cancel_parser.set_defaults(func=cancel_handler)

    # # Work in progress:
    # list_jobs_parser = subparsers.add_parser('list-jobs', help='list all jobs for your user')
    # add_connection_config_arg(list_jobs_parser)
    # add_auth_arg(list_jobs_parser)
    # list_jobs_parser.set_defaults(func=list_jobs_handler)

    # # Work in progress:
    # get_output_parser = subparsers.add_parser('get-output', help='get the output of a job')
    # add_connection_config_arg(get_output_parser)
    # add_auth_arg(get_output_parser)
    # add_out_dir_arg(get_output_parser)
    # add_job_spec_arg(get_output_parser)
    # get_output_parser.set_defaults(func=get_output_handler)

    version_parser = subparsers.add_parser('version', help='print the version of the client and check for updates')
    version_parser.add_argument("--offline", action="store_true", help="do not check for updates")
    add_connection_config_arg(version_parser)
    version_parser.set_defaults(func=version_handler)

    # # Work in progress:
    # update_parser = subparsers.add_parser('update', help='update the client')
    # add_connection_config_arg(update_parser)
    # update_parser.add_argument("-f", "--force", action="store_true", help="force update even if already up to date")
    # update_parser.add_argument("-y", "--yes", action="store_true", help="do not prompt for confirmation")
    # update_parser.set_defaults(func=update_handler)

    login_parser = subparsers.add_parser('login', help="log in to Telerun")
    login_parser.add_argument("-f", "--force", action="store_true", help="force overwriting authentication file even if it already exists")
    login_parser.add_argument("--auth", help="location to write authentication file (defaults to 'auth.json' in the same directory as your Telerun install)")
    login_parser.add_argument("login_code", help="login code (will prompt if not provided)", nargs="?")
    login_parser.set_defaults(func=login_handler)

    args = parser.parse_args()

    if args.version_flag:
        version_handler(args)
        return

    if not hasattr(args, "func"):
        parser.print_help()
        exit(1)

    try:
        args.func(args)
    except urllib.error.HTTPError as e:
        traceback.print_exc()
        print(e.read().decode("utf-8"), file=sys.stderr)
        exit(1)

if __name__ == "__main__":
    main()