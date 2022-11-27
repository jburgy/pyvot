import uvicorn
from sqlite3 import Connection, Row, connect

from fastapi import Depends, FastAPI, Form, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pyvot.olap import pivot_table, table_info


app = FastAPI()
app.mount("/static", StaticFiles(directory="pyvot/static", html=True), name="static")
templates = Jinja2Templates(
    directory="pyvot/templates", trim_blocks=True, lstrip_blocks=True
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: Exception):
    print(await request.form())
    print(exc)
    return PlainTextResponse(str(), status_code=400)


def _connect() -> Connection:
    with connect("elections.db", check_same_thread=False) as conn:
        conn.row_factory = Row
        yield conn


def _template_response(
    request: Request,
    rows: list[str],
    cols: list[str],
    measures: list[str],
    conn: Connection,
    template_name: str,
) -> HTMLResponse:
    context = {
        "request": request,
        "rows": rows,
        "cols": cols,
        "measures": measures,
        "rest": sorted(
            set(
                item["name"]
                for item in table_info(conn=conn, table="house_precinct_general")
                if item["type"] == "TEXT"
            ).difference(rows + cols + measures)
        ),
        **(
            pivot_table(
                conn=conn,
                table="house_precinct_general",
                rows=rows,
                cols=cols,
                measures=dict.fromkeys(measures, sum),
                format="{:d}",
            )
        ),
    }
    return templates.TemplateResponse(template_name, context)


@app.get("/", response_class=HTMLResponse)
async def root(
    request: Request,
    rows: list = Form(...),
    cols: list = Form(...),
    measures: list = Form(...),
    conn: Connection = Depends(_connect),
):
    return _template_response(
        request, rows, cols, measures or ["Votes"], conn, "index.html"
    )


@app.post("/table", response_class=HTMLResponse)
async def table(
    request: Request,
    rows: list = Form(...),
    cols: list = Form(...),
    measures: list = Form(...),
    conn: Connection = Depends(_connect),
):
    return _template_response(
        request, rows, cols, measures, conn, "fragments/body.html"
    )


def start(name: str = "pyvot.main:app"):
    uvicorn.run(name, host="0.0.0.0", port=8001, reload=True)


if __name__ == "__main__":
    start("main:app")
