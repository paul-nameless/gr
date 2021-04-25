import base64
import json
from enum import Enum, auto
from typing import List, Optional

import typer
from dateutil.parser import parse
from gr import config
from gr.utils import (
    get,
    get_current_branch,
    get_hostname,
    get_text,
    handle_error,
    parse_dt,
    post,
    pp,
    put,
    run_cmd,
)
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.padding import Padding
from rich.syntax import Syntax
from rich.table import Table

app = typer.Typer(help="Manage pull requests")

base_url = f"https://{get_hostname()}/a"
changes_url = f"{base_url}/changes/"
changes_detail_url = f"{base_url}/changes/{{id}}/detail"
submit_url = f"{base_url}/changes/{{id}}/submit"
review_url = f"{base_url}/changes/{{id}}/revisions/{{revision_id}}/review"
comments_url = f"{base_url}/changes/{{id}}/comments"
name_url = f"{base_url}/accounts/{{account_id}}/name"


def strip(_str, max_len=32):
    return _str if len(_str) < max_len else f"{_str[:max_len-3]}..."


from functools import lru_cache


@lru_cache(maxsize=1024)
def get_name(account_id: int):
    # TODO: cache in files, create decorator for file cache
    return get(name_url.format(account_id=account_id))


@app.command()
def list(
    q: str = "is:open (reviewer:self OR owner:self)",
    limit: int = 10,
    self: bool = False,
):
    """List all CHanges"""
    if self:
        q = "is:open owner:self"
    console = Console()
    with console.status("[bold green]Loading...") as status:
        resp = get(changes_url, {"q": q, "n": limit, "o": "DETAILED_LABELS"})
        table = generate_changes_table(resp)
    console.print(table)


def generate_changes_table(changes: List[dict]) -> Table:
    table = Table(box=box.SIMPLE)
    columns = [
        "Id",
        "Subject",
        "Status",
        "Owner",
        "Project",
        "Branch",
        "Updated",
        "Size",
        "CR",
        "V",
    ]
    for column in columns:
        table.add_column(
            column,
            justify="left",
            style="cyan",
            no_wrap=True,
        )

    for change in changes:
        updated = parse_dt(change["updated"])
        subject = strip(change["subject"], 32)
        status = "-" if change["mergeable"] else "[red]Merge Conflict[/red]"
        owner = get_name(change["owner"]["_account_id"])
        project = change["project"]
        branch = strip(change["branch"])
        size = f"[green]{change['insertions']:+}[/green] [red]{change['deletions']:+}[/red]"
        id = f'{change["_number"]}'

        verified_values = [
            it["value"] for it in change["labels"]["Verified"]["all"]
        ]
        verified = ""
        if any(it for it in verified_values if it < 0):
            verified = f"[red]X[/red]"
        elif any(it for it in verified_values if it > 0):
            verified = f"[green]V[/green]"

        values = [
            it["value"]
            for it in change["labels"]["Code-Review"]["all"]
            if it["value"]
        ]
        cr = ""
        if any(it for it in values if it < 0):
            cr = f"[red]{min(values):+}[/red]"
        elif any(it for it in values if it > 0):
            cr = f"[green]{max(values):+}[/green]"

        table.add_row(
            id,
            subject,
            status,
            owner,
            project,
            branch,
            updated,
            size,
            cr,
            verified,
        )
    return table


@app.command()
def merge(
    id: str,
    force: bool = False,
    delete_branch: bool = False,
):
    """Submit change by ID"""
    if force:
        post(url, {"labels": {"Code-Review": "+2"}})
    url = submit_url.format(id=id)
    resp = post(url)
    print(resp["status"].title())
    if delete_branch:
        # remember current branch, delete
        dst_branch = resp["branch"]
        run_cmd(["git", "checkout", dst_branch])
        src_branch = resp["source"]["branch"]["name"]
        run_cmd(["git", "branch", "-D", src_branch])


@app.command()
def diff(
    id: str,
    revision_id: str = "current",
):
    """Show diff by change ID"""
    diff_url = f"{base_url}/changes/{id}/revisions/{revision_id}/patch"
    console = Console()
    with console.status("[bold green]Loading...") as status:
        diff = base64.b64decode(get_text(diff_url))
        syntax = Syntax(
            diff, "diff", theme=config.THEME, background_color=config.BG_COLOR
        )
    console.print(syntax)


@app.command()
def checkout(
    id: str,
):
    """Checkout change to new branch"""
    console = Console()
    with console.status("[bold green]Loading...") as status:
        resp = get(
            changes_url
            + f"?q=change:{id}&o=DOWNLOAD_COMMANDS&o=CURRENT_REVISION",
        )
    if not resp:
        print(f"Change id {id} not found")
        exit(1)
    revision = next(iter(resp[0]["revisions"].keys()), None)
    cmd = resp[0]["revisions"][revision]["fetch"]["ssh"]["commands"]["Branch"]
    print("Running:", cmd)
    run_cmd(cmd, shell=True)


class CodeReview(str, Enum):
    PLUS_ONE = "+1"
    PLUS_TWO = "+2"
    MINUS_ONE = "-1"
    ZERO = "0"


@app.command()
def review(
    id: str,
    cr: CodeReview = CodeReview.PLUS_ONE,
    revision_id: str = "current",
):
    """Review change by ID"""
    url = review_url.format(id=id, revision_id=revision_id)
    data = {"labels": {"Code-Review": cr}}
    console = Console()
    with console.status("[bold green]Loading...") as status:
        resp = post(url, data)
    cr = resp["labels"]["Code-Review"]
    print(f"Code-Review {cr:+}")


@app.command()
def comment(
    id: str,
    msg: str,
    cr: Optional[CodeReview] = None,
    revision_id: str = "current",
):
    """Comment change by ID"""
    url = review_url.format(id=id, revision_id=revision_id)
    data = {"message": msg}
    if cr:
        data["labels"] = {"Code-Review": cr}

    console = Console()
    with console.status("[bold green]Loading...") as status:
        resp = post(url, data)


@app.command()
def comments(
    id: str,
):
    """List change comments by ID"""
    url = comments_url.format(id=id)
    console = Console()
    with console.status("[bold green]Loading...") as status:
        resp = get(url)
    for filepath, comments in resp.items():
        console.print(f"[bold]{filepath}[/bold]")

        for comment in comments:
            user = comment["author"]["name"]
            patch_set = comment["patch_set"]
            line = comment["line"]
            msg = comment["message"]
            console.print(
                f"    [bold]Patchset {patch_set}, Line {line}[/bold] {msg}"
            )


@app.command()
def abandon(
    id: str,
):
    """Abandon change by ID"""
    abandon_url = f"{base_url}/changes/{id}/abandon"
    url = abandon_url.format(id=id)
    console = Console()
    with console.status("[bold green]Loading...") as status:
        resp = post(url)
    print(resp["status"].title())


@app.command()
def rebase(
    id: str,
):
    """Rebase change to target branch by ID"""
    rebase_url = f"{base_url}/changes/{id}/rebase"
    url = rebase_url.format(id=id)
    console = Console()
    with console.status("[bold green]Loading...") as status:
        resp = post(url)
    print("Rebased")


@app.command()
def view(id: str, limit: int = 4):
    """View change comments and details"""
    detail_url = f"{base_url}/changes/{id}/detail"
    console = Console()
    with console.status("[bold green]Loading...") as status:
        resp = get(detail_url)
    if "mergeable" not in resp:
        status = f"[green]{resp['status'].title()}[/green] "
    else:
        status = (
            "[cyan]Active[/cyan] "
            if resp.get("mergeable", True)
            else "[red]Merge Conflict[/red] "
        )

    updated = parse_dt(resp["updated"])
    repo = resp["project"]
    branch = resp["branch"]
    subject = resp["subject"]

    console.print(f"{status}{id} {subject}")
    console.print(f"[bold]Updated[/bold] {updated}")

    console.print(f"[bold]Repo | Branch[/bold] {repo} | {branch}")

    for label, info in resp["labels"].items():
        values = []
        for comment in info.get("all", []):
            user = comment["username"]
            value = comment.get("value")
            if not value:
                continue
            color = "red" if value < 0 else "green"
            values.append(f"[{color}]{value:+} {user}[/{color}]")
        reviews = ", ".join(values)
        console.print(f"[bold]{label.title()}:[/bold] {reviews}")

    files_url = f"{base_url}/changes/{id}/revisions/current/files/"
    files = get(files_url)
    console.print("[bold]Files:[/bold]")

    table = Table(box=box.SIMPLE, pad_edge=False)
    for column in ("", "File", "Comments", "Delta"):
        table.add_column(
            column,
            justify="left",
            style="cyan",
            no_wrap=True,
        )

    for filepath in sorted(files, key=str.lower):
        info = files[filepath]
        if filepath == "/COMMIT_MSG":
            continue
        # if info["size"] == info["size_delta"] or info["size"] == 0:
        #     size = ""
        # else:
        #     if info["size"]:
        #         size = round(info["size_delta"] / info["size"] * 100, 2)
        #         size = f"[white on red]{size}%[/white on red]"
        #     else:
        #         size = f"{info['size_delta']} {info['size']}"

        inserted = info.get("lines_inserted", 0)
        deleted = info.get("lines_deleted", 0)
        delta = f"[green]{inserted:+}[/green] [red]{deleted:+}[/red]"

        status = info.get("status", "M")
        comments = ""
        table.add_row(status, f"[blue]{filepath}[/blue]", comments, delta)
    console.print(table)

    console.print(f"\n[bold]Last {limit} messages:[/bold]")
    for msg in resp["messages"][-limit:]:
        user = msg["author"]["name"]
        dt = parse_dt(msg["date"])
        message = msg["message"]
        console.print(Padding(f"[bold]{user}[/bold] {dt} ", (0, 2)))
        console.print(Padding(f"{message}", (0, 4)))


@app.command()
def add_reviewers(id: str, users: List[str]):
    """Abandon change by ID"""
    add_reviewers_url = f"{base_url}/changes/{id}/reviewers"
    url = add_reviewers_url.format(id=id)
    console = Console()
    with console.status("[bold green]Loading...") as status:
        for user in users:
            resp = post(url, {"reviewer": user})

    print("Added")


@app.command()
def create(branch: str = "master", reviewers: List[str] = []):
    """Create change from current branch"""
    _reviewers = "%" + ",".join(f"r={r}" for r in reviewers)
    refs = f"HEAD:refs/for/master{_reviewers}"
    run_cmd(["git", "push", "origin", refs])
