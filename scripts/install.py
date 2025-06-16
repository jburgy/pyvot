#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "pandas",
# ]
# ///

from sqlite3 import connect

import pandas as pd  # type: ignore

pd.read_csv("HOUSE_precinct_general.tab.gz", sep="\t").to_sql(
    "house_precinct_general", con=connect("elections.db")
)
