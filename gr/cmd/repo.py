import typer
from gr.utils import get, get_hostname, pp
from rich import box
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Get repo information")
base_url = f"https://{get_hostname()}/a"


@app.command()
def list(
    query: str = "state:active",
    limit: int = 10,
):
    """List projects by query"""
    repo_url = f"{base_url}/projects/"
    console = Console()
    with console.status("[bold green]Loading...") as status:
        resp = get(repo_url, {"query": query, "limit": limit})
        table = generate_repo_table(resp)
    console.print(table)


def generate_repo_table(repos) -> Table:
    table = Table(box=box.SIMPLE)
    columns = [
        "Repo",
        "Browse",
    ]
    for column in columns:
        table.add_column(column, justify="left", style="cyan", no_wrap=True)

    for repo in repos:
        table.add_row(
            repo["name"],
            repo["web_links"][0]["url"],
        )
    return table
