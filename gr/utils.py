import json
import os
import subprocess
from functools import lru_cache
from urllib.parse import urlparse

import humanize
import requests
from dateutil.parser import parse
from dateutil.tz import tzlocal
from gr import config
from rich.console import Console
from rich.syntax import Syntax


def get(url, query: dict = None):
    resp = requests.get(url, auth=config.AUTH, params=query)
    if not resp.ok:
        print("Error response:", resp.text)
        exit(1)
    return json.loads(resp.text.split("\n", 1)[-1])


def get_text(url, query: dict = None):
    return requests.get(url, auth=config.AUTH, params=query).text


def post(url: str, data: dict = None):
    resp = requests.post(url, auth=config.AUTH, json=data)
    if not resp.ok:
        print("Error response:", resp.text)
        exit(1)
    return json.loads(resp.text.split("\n", 1)[-1])


def put(url: str, data: dict = None):
    resp = requests.put(url, auth=config.AUTH, json=data)
    if not resp.ok:
        print("Error response:", resp.text)
        exit(1)
    return json.loads(resp.text.split("\n", 1)[-1])


def handle_error(resp: dict):
    if resp.get("type") == "error":
        syntax = Syntax(
            json.dumps(resp),
            "json",
            theme=config.THEME,
            background_color=config.BG_COLOR,
        )
        console = Console()
        console.print(syntax)
        exit(1)


def run_cmd(cmd: list, shell=False):
    proc = subprocess.run(
        cmd,
        cwd=os.getenv("PWD"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=shell,
    )
    if proc.returncode != 0:
        print(f"{cmd} exited with {proc.returncode} code")
        print(proc.stderr.decode())
        exit(1)
    return proc.stdout.decode().strip()


@lru_cache(maxsize=1)
def get_remote():
    return run_cmd(["git", "remote", "get-url", "origin"])


def get_hostname():
    return urlparse(get_remote()).hostname


def get_current_branch():
    return run_cmd(
        ["git", "branch", "--show-current"],
    )


def pp(d: dict):
    syntax = Syntax(
        json.dumps(d, indent=4, sort_keys=True),
        "json",
        theme=config.THEME,
        background_color=config.BG_COLOR,
    )
    console = Console()
    console.print(syntax)


def parse_dt(dt) -> str:
    dt = parse(dt + "Z")
    dt = dt.astimezone(tzlocal()).replace(tzinfo=None)
    return humanize.naturaltime(dt)
