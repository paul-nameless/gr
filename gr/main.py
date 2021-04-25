import typer
from gr.cmd import ch, repo

app = typer.Typer()

app.add_typer(ch.app, name="ch")
app.add_typer(repo.app, name="repo")

if __name__ == "__main__":
    app()
